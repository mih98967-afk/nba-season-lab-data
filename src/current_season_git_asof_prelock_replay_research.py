"""Research-only 2026/27 T-30 counterfactual using saved prelock rosters and Git row versions.

This is NOT a forecast genuinely issued in October. Candidate selection comes
only from independently archived Sports.ru+ESPN prelock team snapshots, and
features only from public Git or row versions actually observed by T-30.
Outcomes are attached afterward for diagnostic conditional FP/minute MAE.
Older 2025/26 priors may be used (already finished before 2026/27).
No population P(play), DNP inference, calibrated intervals, transfer gain,
or deployment. Frozen weights came from exploratory earlier-season research.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp, player_games
from src.conditional_minutes_fp_research import forecast, same_team_tail
from src.historical_current_minutes_walkforward_research import load_history

STATUS = "research_only_not_deployed"
LOCK = timedelta(minutes=30)
MAX_FORM_AGE = timedelta(days=16)
NY = ZoneInfo("America/New_York")
MODEL = {
    "name": "git_proven_2026_27_prelock_counterfactual_v1",
    "current_positive_played_min": 3,
    "current_positive_played_max": 5,
    "current_same_club_latest_game_age_days": 16,
    "previous_season_minutes_prior_games": 5,
    "previous_season_FP_rate_prior_games": 10,
    "same_team_tail_after_trade": True,
    "retrospective_not_genuinely_prelock_issued": True,
    "FP_rate_weights_posthoc_historical_research": True,
    "adopt_on_site": False,
}
MODEL_SHA256 = canonical_hash(MODEL)
FIELDS = (
    "prior_previous_season_FP",
    "updated_minutes_old_FP_rate",
    "updated_minutes_shrunk_FP_rate_10",
    "updated_minutes_current_FP_rate_unsmoothed",
)


def number(x, low, high):
    if type(x) not in (int, float) or not isfinite(x) or not low <= x <= high:
        raise ValueError("Nonfinite or implausible NBA row/forecast")
    return float(x)


def provenance_index(git_proof, observed):
    """Merge Git snapshots and later actual-value observations, never first-seen proxies."""
    if (git_proof.get("status") != STATUS
            or git_proof.get("adopt_on_site") is not False
            or not git_proof.get("quality_gate", {}).get(
                "historical_commit_blobs_anchored_to_original_immutable_git_SHA")
            or observed.get("status") != STATUS
            or observed.get("adopt_on_site") is not False
            or not isinstance(git_proof.get("versions"), dict)
            or not isinstance(observed.get("versions"), dict)):
        raise ValueError("Missing audited Git-to-row-version source bridge")
    if (instant(git_proof["first_row_version_archive_at_utc"]) !=
            instant(observed["first_version_archive_at_utc"])):
        raise ValueError("Git recovery not anchored to first official value archive")
    # The Git proof is anchored to the FIRST sealed row-value archive.
    # The current archive is append-only: newly observed player-games must NOT
    # invalidate this immutable initial bridge or be given earlier timestamps.
    first_capture = instant(observed["first_version_archive_at_utc"])
    original_keys = set()
    for key, events in observed["versions"].items():
        if not isinstance(events, list) or not events:
            raise ValueError("Missing observed row-version chain")
        recorded_at = instant(events[0]["version_observed_at_utc"])
        if recorded_at < first_capture:
            raise ValueError("Observed row version falsely predates sealed archive")
        if recorded_at == first_capture:
            original_keys.add(key)
    if (original_keys != set(git_proof["versions"])
            or len(original_keys) != git_proof.get("summary", {}).get(
                "first_row_version_archive_keys_exactly_reconciled")
            or len(observed["versions"]) != observed.get("summary", {}).get(
                "unique_player_games")):
        raise ValueError("Original Git-to-row-version source bridge drift")
    for key in original_keys:
        first = observed["versions"][key][0]
        git_events = git_proof["versions"][key]
        if (not git_events or git_events[-1].get("kind") != "observed"
                or instant(git_events[-1]["observed_at_utc"]) > first_capture
                or git_events[-1].get("row_sha256") != first.get("row_sha256")
                or canonical_hash(first["row"]) != first["row_sha256"]):
            raise ValueError("Original observed value differs from sealed Git proof")
    result = {}
    for key in sorted(set(git_proof["versions"]) | set(observed["versions"])):
        timeline = []
        for event in git_proof["versions"].get(key, []):
            at = instant(event["observed_at_utc"])
            if event["kind"] == "absent":
                timeline.append((at, None, "git_absent_not_DNP"))
            elif event["kind"] == "observed":
                if canonical_hash(event["row"]) != event["row_sha256"]:
                    raise ValueError("Corrupted earlier Git value")
                timeline.append((at, event["row"], "git_commit"))
            else:
                raise ValueError("Unrecognized historical Git event")
        for event in observed["versions"].get(key, []):
            at = instant(event["version_observed_at_utc"])
            if canonical_hash(event["row"]) != event["row_sha256"]:
                raise ValueError("Corrupted later captured value")
            timeline.append((at, event["row"], "current_version_archive"))
        timeline.sort(key=lambda e:e[0])
        if not timeline:
            raise ValueError("Empty historical observation series")
        prev = None
        for at, row, origin in timeline:
            if prev is not None and at <= prev:
                raise ValueError("Non-monotone or same-time competing row versions")
            prev = at
            if row is None:
                continue
            if (row.get("game_id")+"|"+row.get("player_id") != key
                    or instant(row["utc"]) > at
                    or number(row["minutes"], 0.00001, 70) <= 0):
                raise ValueError("Observed positive-minute row invalid or future-dated")
            number(row["fp"], -150, 250)
        result[key] = timeline
    return result


def values_at(timelines, cutoff):
    """True as-of public row values; no final current row substituted for older revisions."""
    if cutoff.utcoffset() is None:
        raise ValueError("As-of requested without timezone")
    cutoff = cutoff.astimezone(timezone.utc)
    rows = defaultdict(list)
    for timeline in timelines.values():
        known = None
        first = None
        origin = None
        for at, row, kind in timeline:
            if at > cutoff:
                break
            known, first, origin = row, at, kind
        if known is not None:
            if instant(known["utc"]) >= cutoff:
                raise ValueError("Target/future boxscore leaked into prelock features")
            rows[known["player_id"]].append({
                "game_id":known["game_id"],
                "team":known["team"],
                "game_utc":known["utc"],
                "minutes":number(known["minutes"], 0.00001, 70),
                "fp":number(known["fp"], -150, 250),
                "version_proven_at_utc":stamp(first),
                "provenance":origin,
                "row_sha256":canonical_hash(known),
            })
    for items in rows.values():
        items.sort(key=lambda x:(x["game_utc"],x["game_id"]))
        if len({x["game_id"] for x in items}) != len(items):
            raise ValueError("Same player-game appeared twice in historical asof")
    return rows


def candidate_prediction(candidate, history, known, cutoff):
    """No target outcome enters here. Historical prior must predate current season."""
    base = forecast(same_team_tail(history))
    if base is None:
        return None, "no_20_game_previous_season_same_club_prior"
    club = candidate["team_in_catalog_snapshot"]
    if base["last_sample_team"] != club:
        return None, "previous_season_prior_other_club"
    pid = candidate["player_id"]
    played = known.get(pid, [])
    if not played:
        return None, "no_git_proven_current_season_form"
    if any(x["game_id"] == candidate["game_id"] for x in played):
        raise ValueError("Own target match was already in prelock source features")
    if played[-1]["team"] != club:
        return None, "last_proven_current_season_club_changed"
    i = len(played)
    while i and played[i-1]["team"] == club:
        i -= 1
    tenure = played[i:]
    sample = tenure[-MODEL["current_positive_played_max"]:]
    if len(sample) < MODEL["current_positive_played_min"]:
        return None, "fewer_than_3_git_proven_played_same_club"
    last_tip = instant(sample[-1]["game_utc"])
    if not timedelta(0) < cutoff-last_tip <= MAX_FORM_AGE:
        return None, "last_proven_same_club_form_too_old"
    n = len(sample)
    old_minutes = number(base["minutes_if_play"], 0, 70)
    old_fp = number(base["decomposed_fp_if_play"], -150, 250)
    old_rate = number(base["fp_per_minute_if_play"], -100, 100)
    recent_minutes = sum(x["minutes"] for x in sample)/n
    minutes = round((5*old_minutes+n*recent_minutes)/(5+n),5)
    observed_rate = sum(x["fp"] for x in sample)/sum(x["minutes"] for x in sample)
    shrunk_rate = (10*old_rate+n*observed_rate)/(10+n)
    variants = {
        FIELDS[0]:old_fp,
        FIELDS[1]:round(minutes*old_rate,5),
        FIELDS[2]:round(minutes*shrunk_rate,5),
        FIELDS[3]:round(minutes*observed_rate,5),
    }
    for value in variants.values():
        number(value,-500,500)
    return {
        "game_id":candidate["game_id"],"player_id":pid,"club":club,
        "fantasy_position":candidate["fantasy_position"],
        "simulated_cutoff_Tminus30_utc":stamp(cutoff),
        "catalog_captured_before_lock_utc":candidate["catalog_capture_utc"],
        "ESPN_roster_captured_before_lock_utc":candidate["espn_roster_capture_utc"],
        "model_sha256":MODEL_SHA256,
        "source_previous_season":"2025/26",
        "prior_previous_season_last_played_date":base["sample_last_played_date"],
        "original_prior_minutes":old_minutes,
        "updated_minutes":minutes,
        "prior_fp_per_minute":old_rate,
        "source_form_rows":[dict(x) for x in sample],
        "source_form_sha256":canonical_hash(sample),
        "source_form_n":n,
        "prelock_source_clock_verified":True,
        "FP_variants":variants,
        "not_genuine_historical_issue":True,
        "adopt_on_site":False,
    },None


def score(rows):
    if not rows:
        return {"played_scored":0}
    n=len(rows)
    output={"played_scored":n,"games":len({x["game_id"] for x in rows}),
            "ET_dates":len({x["et_date"] for x in rows})}
    actual=[number(x["actual_fp_reconstructed"],-150,250) for x in rows]
    for field in FIELDS:
        err=[number(x["FP_variants"][field],-500,500)-y for x,y in zip(rows,actual)]
        prior=[abs(x["FP_variants"][FIELDS[0]]-y) for x,y in zip(rows,actual)]
        output[field] = {
            "MAE":round(sum(abs(e) for e in err)/n,4),
            "RMSE":round(sqrt(sum(e*e for e in err)/n),4),
            "prediction_minus_actual_bias":round(sum(err)/n,4),
            "paired_gain_over_previous_season_FP":round(
                sum(a-abs(e) for a,e in zip(prior,err))/n,4),
        }
    diff=[abs(x["original_prior_minutes"]-x["actual_minutes"])-
          abs(x["updated_minutes"]-x["actual_minutes"]) for x in rows]
    output["minutes"]={
        "baseline_MAE":round(sum(abs(x["original_prior_minutes"]-x["actual_minutes"])
                                  for x in rows)/n,4),
        "updated_MAE":round(sum(abs(x["updated_minutes"]-x["actual_minutes"])
                                 for x in rows)/n,4),
        "paired_gain":round(sum(diff)/n,4),
    }
    return output


def build(proof, versions, opportunities, players, identity, live):
    if (opportunities.get("status") != STATUS or
            opportunities.get("adopt_on_site") is not False or
            opportunities.get("verified_game_day_roster_denominator") is not False or
            opportunities.get("postgame_labels_are_not_pregame_features") is not True or
            live.get("schema_version") != 4 or
            not isinstance(players, dict) or
            not isinstance(identity.get("players"),dict)):
        raise ValueError("Invalid research / prelock data provenance")
    records=opportunities.get("records", [])
    if len(records) != opportunities.get("summary",{}).get("catalog_proxy_player_games"):
        raise ValueError("Prelock candidate source denominator drift")
    timelines=provenance_index(proof,versions)
    finals={}
    for g in live.get("games", []):
        if g.get("status") == "final":
            if g["id"] in finals:
                raise ValueError("Repeated finalized NBA game")
            finals[g["id"]]=g
    targets,_=player_games(live,instant(live["updated_at_utc"]))
    qa=Counter()
    predictions=[]
    outcomes=[]
    seen=set()
    snapshot_cache={}
    for item in sorted(records,key=lambda x:(x["game_utc"],x["game_id"],x["player_id"])):
        qa["catalog_proxy_opportunities"]+=1
        key=item["game_id"],item["player_id"]
        if key in seen:
            raise ValueError("Duplicate prelock roster candidate")
        seen.add(key)
        if item["club_cross_source_evidence"]!="same_club_independent_ESPN_ID_observed":
            qa["not_strong_2_source_identity"]+=1
            continue
        ident=identity["players"].get(key[1],{})
        if ident.get("confidence")!="high":
            qa["historical_identity_not_high_confidence"]+=1
            continue
        tip=instant(item["game_utc"])
        lock=instant(item["individual_lock_utc"])
        if tip-lock != LOCK:
            raise ValueError("Prelock candidate deadline does not equal T-30")
        if (instant(item["catalog_capture_utc"])>lock or
                instant(item["espn_roster_capture_utc"])>lock):
            raise ValueError("Postlock roster evidence used in replay")
        if item["game_id"] not in snapshot_cache:
            snapshot_cache[item["game_id"]]=values_at(timelines,lock)
        prior=players.get(key[1],{}).get("2025/26",[])
        predicted,reason=candidate_prediction(
            item,prior,snapshot_cache[item["game_id"]],lock)
        if reason:
            qa[reason]+=1
            continue
        if (predicted["source_form_n"] < 3 or
                any(instant(x["version_proven_at_utc"])>lock for x in
                    predicted["source_form_rows"])):
            raise ValueError("As-of form after cutoff")
        qa["counterfactual_prelock_candidates"]+=1
        predictions.append(predicted)
        final=finals.get(key[0])
        result_label=item["postgame_outcome"]
        if final is None:
            if result_label!="unknown_outcome_or_unverified_game_day_membership":
                raise ValueError("Verified outcome without finalized NBA game")
            qa["pending_unfinished_game"]+=1
            continue
        if (final["utc"]!=item["game_utc"] or
                item["team_in_catalog_snapshot"] not in (final["home"],final["away"])):
            raise ValueError("Final fixture contradicts original prelock input")
        if result_label=="explicit_dnp_verified_after_game":
            if (item["postgame_evidence"] != "explicit_espn_didNotPlay_true" or
                not item["postgame_first_seen_timestamp_verified"]):
                raise ValueError("DNP without independent affirmative evidence")
            qa["literal_DNP_excluded_from_conditional_scoring"]+=1
            continue
        if result_label=="unknown_outcome_or_unverified_game_day_membership":
            qa["finished_UNKNOWN_not_DNP_or_FP_zero"]+=1
            continue
        if (result_label!="played_verified_after_game" or
                item["postgame_evidence"]!="positive_minutes_verified_sportsru_fp" or
                not item["postgame_first_seen_timestamp_verified"]):
            raise ValueError("Unverified postgame label cannot be scored")
        actual=targets.get(key)
        if (actual is None or actual["team"]!=predicted["club"] or
                instant(item["postgame_first_seen_at_utc"])<tip or
                instant(item["postgame_first_seen_at_utc"])>
                     instant(live["updated_at_utc"])):
            raise ValueError("Postgame verified positive minutes unavailable")
        outcome={
            "game_id":key[0],"player_id":key[1],
            "team":actual["team"],
            "et_date":tip.astimezone(NY).date().isoformat(),
            "actual_minutes":number(actual["minutes"],0.00001,70),
            "actual_fp_reconstructed":number(actual["fp"],-150,250),
            "postgame_first_seen_at_utc":item["postgame_first_seen_at_utc"],
            "source_prelock_predicted_sha256":canonical_hash(predicted),
            "original_prior_minutes":predicted["original_prior_minutes"],
            "updated_minutes":predicted["updated_minutes"],
            "FP_variants":predicted["FP_variants"],
        }
        outcomes.append(outcome)
        qa["paired_verified_positive_played"]+=1
    dates=defaultdict(list)
    for record in outcomes:
        dates[record["et_date"]].append(record)
    if (qa["counterfactual_prelock_candidates"] !=
        qa["pending_unfinished_game"] +
        qa["literal_DNP_excluded_from_conditional_scoring"]+
        qa["finished_UNKNOWN_not_DNP_or_FP_zero"]+
        qa["paired_verified_positive_played"]):
        raise ValueError("Counterfactual issued-cohort accounting drift")
    if not predictions:
        raise ValueError("No restored as-of prelock replay candidates")
    predictions.sort(key=lambda r:(r["simulated_cutoff_Tminus30_utc"],
                                    r["game_id"],r["player_id"]))
    outcomes.sort(key=lambda r:(r["et_date"],r["game_id"],r["player_id"]))
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"model_sha256":MODEL_SHA256,
        "model":MODEL,
        "research_type":"RETROSPECTIVE_git_proven_asof_prelock_replay_NOT_issued_forecasts",
        "source_prelock_roster_report_updated_at_utc":opportunities["updated_at_utc"],
        "source_git_proof_sha256":canonical_hash({
            "summary":proof["summary"],"fixed_last_git_sha":proof["fixed_last_git_sha"]}),
        "source_version_archive_first_capture_utc":versions["first_version_archive_at_utc"],
        "selection":"Sports.ru catalog plus independent ESPN ID & club prelock; high historical ID confidence",
        "issue_at_historical_cutoff_is_simulation_not_recorded_issue":True,
        "source_feature_cutoff":"individual T-30; saved Git commit / row-version observation time",
        "counterfactual_candidates":predictions,
        "postgame_positive_played_only":outcomes,
        "summary":{
            "catalog_proxy_player_games":qa["catalog_proxy_opportunities"],
            "retrospectively_simulated_prelock_candidates":len(predictions),
            "verified_played_scored":len(outcomes),
            "literal_DNP_NOT_scored":qa["literal_DNP_excluded_from_conditional_scoring"],
            "finished_UNKNOWN_not_imputed":qa["finished_UNKNOWN_not_DNP_or_FP_zero"],
            "future_pending_not_scored":qa["pending_unfinished_game"],
            "distinct_verified_scored_NBA_games":len({x["game_id"] for x in outcomes}),
            "distinct_verified_scored_ET_dates":len(dates),
        },
        "coverage_QA":dict(qa),
        "played_only_paired_metrics":score(outcomes),
        "by_ET_date":{d:score(rows) for d,rows in sorted(dates.items())},
        "quality_gate":{
            "observed_git_value_versions_only_before_each_cutoff":True,
            "candidate_selection_prelock_not_target_outcome":True,
            "reconstructed_git_commit_at_not_original_provider_published":True,
            "retrospective_not_prospective_issue":True,
            "full_population_P_play_or_unconditional_FP_known":False,
            "historical_model_weights_frozen_before_2026_27_season":False,
            "independent_new_season_confirmatory_sample":False,
            "sportsru_account_credited_FP_reconciled":False,
            "KEEP_TRANSFER_real_gain_established":False,
            "adopt_on_site":False,
        },
        "limitations":[
            "Predictions in this file are retro-simulated AFTER the games, not historically issued.",
            "Git commit and row-value version clocks prove repository values, not provider publication time.",
            "The older ESPN roster list is not active game-day roster membership.",
            "Only high-confidence cross-provider club and historical identity are accepted.",
            "Changed club since previous season or last observed game abstains rather than extrapolates.",
            "Historical previous-season and current rates are research-tuned, not pristine future validation.",
            "The selected played-only conditional FP sample excludes literal DNP and UNKNOWN.",
            "Several players share each game and ET date, so observations are correlated.",
            "Final outcomes use latest verified reconstructed FP, not necessarily official Sports.ru account credited FP.",
            "No Firebase, Hosting, private budgets, account roster or transfers modified.",
        ],
    }


def run():
    def read(p):
        return json.loads((DATA/p).read_text(encoding="utf8"))
    index=read("history/index.json")
    history,_=load_history(index,lambda name:read("history/"+name))
    result=build(
        read("git_preversion_boxscore_proof_research.json"),
        read("observed_boxscore_versions_research.json"),
        read("prelock_roster_opportunities_research.json"),
        history,read("identity.json"),read("live.json"))
    target=DATA/"current_season_git_asof_prelock_replay_research.json"
    payload=json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n"
    if not target.exists() or target.read_text(encoding="utf8")!=payload:
        tmp=target.with_suffix(".tmp")
        tmp.write_text(payload,encoding="utf8")
        tmp.replace(target)
    return {"summary":result["summary"],
            "played_only_paired_metrics":result["played_only_paired_metrics"],
            "research_only":True,"adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
