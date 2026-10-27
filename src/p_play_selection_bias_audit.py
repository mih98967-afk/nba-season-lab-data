"""Pre-registered truth-coverage and selection-bias diagnostic for p_play shadow.

NO model training. Verified explicit DNPs/positive minutes are a selected
ESPN-boxscore cohort, NOT the complete Sports.ru fantasy eligible population.
In particular an official OUT often never appears as didNotPlay=true; these
missing labels must NEVER be scored as 'played' or 'did not play' without a
second independently verified source.

Report exact binary-label best/worst Brier and log-loss bounds for *already
finished and fully DNP-checked* game opportunities. Loss intervals are sharp
over the unknown outcomes in THIS restricted issued cohort, not population
confidence intervals. Freeze first-issued predictions and first-known report
statuses. Public research-only data; no user/Firestore/site/transfers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import math

from src.sync import DATA
from src.rolling_decision_research import instant, stamp, official_asof

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
STATUS = "research_only_not_deployed"
VALID_OFFICIAL = {"out", "doubtful", "questionable", "probable", "available"}
FIELDS = ("baseline_p_selected_listed_proxy", "candidate_p_selected_listed_proxy")


def _loss(p, y, name):
    if type(y) is not int or y not in (0, 1):
        raise ValueError("UNKNOWN cannot be treated as a binary label")
    if not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 < p < 1:
        raise ValueError("Invalid frozen pregame probability")
    if name == "brier":
        return (p-y)**2
    if name == "logloss":
        return -(y*math.log(p) + (1-y)*math.log1p(-p))
    raise ValueError("Invalid scoring rule")


def _interval(known, missing):
    """Sharp same-player binary outcome bounds, NOT bootstrap uncertainty."""
    n = len(known)+len(missing)
    if not n:
        return None
    table = {}
    for measure in ("brier", "logloss"):
        sums = [[0., 0.] for _ in FIELDS]
        paired = [0.,0.]
        for p,y in known:
            values = [_loss(p[f],y,measure) for f in FIELDS]
            for i,v in enumerate(values):
                sums[i][0]+=v
                sums[i][1]+=v
            paired[0]+=values[0]-values[1]
            paired[1]+=values[0]-values[1]
        for p in missing:
            losses = [[_loss(p[f],y,measure) for y in (0,1)] for f in FIELDS]
            for i,possible in enumerate(losses):
                sums[i][0]+=min(possible)
                sums[i][1]+=max(possible)
            difference = [losses[0][y]-losses[1][y] for y in (0,1)]
            paired[0]+=min(difference)
            paired[1]+=max(difference)
        table[measure] = {
            "baseline_range": [round(z/n,6) for z in sums[0]],
            "candidate_range": [round(z/n,6) for z in sums[1]],
            "paired_baseline_minus_candidate_gain_range":
                [round(z/n,6) for z in paired],
            "all_unknown_are_binary_only_as_a_mathematical_sensitivity":
                True,
        }
    return {"n":n, "verified":len(known), "missing":len(missing),
            "bounds":table,
            "individual_model_bounds_cannot_be_compared_as_if_independent":
                True,
            "not_a_population_estimate":True}


def audit(shadow, live, explicit, official, now):
    if now.utcoffset() is None:
        raise ValueError("Audit clock must be timezone aware")
    now = now.astimezone(UTC)
    if (shadow.get("status") != STATUS or
            shadow.get("adopt_on_site") is not False or
            shadow.get("population_brier_enabled") is not False or
            explicit.get("status") != STATUS or
            explicit.get("adopt_on_site") is not False or
            official.get("status") !=
                "official_report_observed_pit_research_only" or
            official.get("adopt_on_site") is not False):
        raise ValueError("Untrusted or deployable research input")
    issued = shadow.get("issued")
    observed = shadow.get("observations")
    checked = explicit.get("checked_final_game_ids")
    if (not isinstance(issued,list) or not isinstance(observed,list)
            or not isinstance(checked,list) or len(checked)!=len(set(checked))):
        raise ValueError("Invalid shadow or checked-game archive")
    finals = {}
    for game in live.get("games", []):
        if not isinstance(game,dict) or game.get("status")!="final":
            continue
        gid=game.get("id")
        if not isinstance(gid,str) or gid in finals:
            raise ValueError("Repeated final game")
        finals[gid]=game
    checked = set(checked)
    keys=set()
    for p in issued:
        if not isinstance(p,dict):
            raise ValueError("Invalid prospective prediction")
        key=(p.get("game_id"), p.get("player_id"))
        if (not all(isinstance(x,str) and x for x in key)
                or key in keys):
            raise ValueError("Duplicate immutable prediction")
        keys.add(key)
        at=instant(p["issued_at_utc"])
        lock=instant(p["individual_lock_utc"])
        tip=instant(p["tipoff_utc"])
        if (not at < lock or not lock < tip or
                at > now or p.get("adopt_on_site") is not False):
            raise ValueError("Prediction was not frozen before lock")
        if (tip-lock).total_seconds()!=1800:
            raise ValueError("Individual lock is not 30 minutes")
    verified={}
    for o in observed:
        if not isinstance(o,dict):
            raise ValueError("Malformed verified result")
        key=(o.get("game_id"),o.get("player_id"))
        if key not in keys or key in verified:
            raise ValueError("Orphan/duplicated verified player-game")
        y=o.get("actual_played")
        if type(y) is not int or y not in (0,1):
            raise ValueError("Unknown cannot be treated as a verified negative")
        if o.get("label_provenance") != (
                "positive_minutes_verified_sportsru_fp" if y else
                "explicit_espn_didNotPlay_true"):
            raise ValueError("Verified outcome lacks explicit provenance")
        verified[key]=o
    by_status=defaultdict(Counter)
    by_game=defaultdict(Counter)
    breakdown=Counter()
    known,missing=[],[]
    known_high,missing_high=[],[]
    out_review=[]
    completed_et=set()
    for p in issued:
        game=finals.get(p["game_id"])
        if game is None or p["game_id"] not in checked:
            breakdown["not_yet_completed_or_not_DNP_checked"]+=1
            continue
        if (p["team"] not in (game.get("home"), game.get("away")) or
                game.get("utc")!=p["tipoff_utc"] or
                instant(game["utc"]) > now):
            raise ValueError("Game or team changed after a first-issue forecast")
        at=instant(p["issued_at_utc"])
        event=official_asof(official,p["game_id"],p["player_id"],p["team"],at)
        current_status=event["status"] if event else None
        stored=p.get("official_status_first_known_asof_issue")
        if current_status!=stored:
            raise ValueError("Official report status does not match frozen issue-time evidence")
        if stored is not None and stored not in VALID_OFFICIAL:
            raise ValueError("Unknown official injury status")
        status=stored or "no_observed_official_status"
        group=by_status[status]
        game_group=by_game[p["game_id"]]
        group["finished_checked"]+=1
        game_group["finished_checked"]+=1
        breakdown["finished_checked"]+=1
        completed_et.add(instant(game["utc"]).astimezone(ET).date().isoformat())
        v=verified.get((p["game_id"],p["player_id"]))
        if v is None:
            group["outcome_UNKNOWN"]+=1
            game_group["outcome_UNKNOWN"]+=1
            missing.append(p)
            if p.get("club_link_evidence")=="same_club_independent_ESPN_ID_observed":
                missing_high.append(p)
            if status == "out":
                # This is an EVIDENCE REVIEW QUEUE, not a filled negative.
                out_review.append({
                    "game_id":p["game_id"],
                    "player_id":p["player_id"],
                    "team":p["team"],
                    "first_issue_at_utc":p["issued_at_utc"],
                    "source_observed_status":"out",
                    "official_event_id":event.get("event_id") if event else None,
                    "official_source_url":event.get("source_url") if event else None,
                    "game_verified_final":True,
                    "complete_explicit_DNP_audit":True,
                    "actual_played":"UNKNOWN_NOT_INFERRED",
                    "needs_independent_full_boxscore_athlete_ID_review":True,
                })
        else:
            observed_at=instant(v["source_first_observed_at_utc"])
            tip=instant(p["tipoff_utc"])
            if observed_at < tip or observed_at>now:
                raise ValueError("Postgame label observed before tipoff or after audit")
            y=v["actual_played"]
            if v["tipoff_utc"]!=p["tipoff_utc"]:
                raise ValueError("Verified result shifted to a different fixture")
            group["verified_played" if y else "explicit_DNP"]+=1
            game_group["verified_played" if y else "explicit_DNP"]+=1
            known.append((p,y))
            if p.get("club_link_evidence")=="same_club_independent_ESPN_ID_observed":
                known_high.append((p,y))
    if breakdown["finished_checked"]!=len(known)+len(missing):
        raise ValueError("Broken source coverage accounting")
    prior_known=_interval(known,[])
    full=_interval(known,missing)
    return {
        "schema_version":1, "status":STATUS, "adopt_on_site":False,
        "updated_at_utc":stamp(now),
        "prediction_target":"player_positive_minutes_with_verified_explicit_DNP_if_available",
        "reference_population":"first_issued_prelock_predictions_with_completed_checked_NBA_games",
        "total_issued_predictions":len(issued),
        "finished_checked":len(known)+len(missing),
        "verified_postgame_results":len(known),
        "unknown_postgame_results":len(missing),
        "future_or_not_checked":breakdown["not_yet_completed_or_not_DNP_checked"],
        "distinct_finished_ET_dates":len(completed_et),
        "by_first_observed_official_status":{
            s:dict(by_status[s]) for s in sorted(by_status)},
        "by_game":{g:dict(by_game[g]) for g in sorted(by_game)},
        "out_status_missing_review_queue":out_review,
        "official_OUT_unknown_review_priority_count":len(out_review),
        "selected_verified_only":prior_known,
        "all_finished_with_unknown_binary_sensitivity":full,
        "high_confidence_ESPN_ID_subset_binary_sensitivity":
            _interval(known_high,missing_high),
        "quality_gate":{
            "official_OUT_missing_label_count":len(out_review),
            "unknown_are_not_DNP":True,
            "first_issue_status_anchored":True,
            "full_game_day_roster_membership_verified":False,
            "population_p_play_validated":False,
            "prospective_model_adoption_allowed":False,
            "keep_transfer_economic_value_proven":False,
        },
        "limits":[
            "All UNKNOWN outcomes are still UNKNOWN. Binary bounds are sensitivity calculations only.",
            "An official OUT before issue does not prove ESPN didNotPlay=true; needs an independently checked complete boxscore.",
            "No status means no status FIRST OBSERVED BY ISSUE, not proof of health.",
            "Fantasy player population and all game-day club memberships are not verified.",
            "A single NBA ET date and a selected ESPN cohort cannot establish calibrated p_play.",
            "Negative labels cannot be backfilled from missing played rows or stale catalogs.",
            "No new p_play model, injury weight, Telegram weight, site or real transfer is deployed.",
        ],
    }


def run():
    now=datetime.now(UTC)
    load=lambda x:json.loads((DATA/x).read_text(encoding="utf8"))
    report=audit(load("p_play_shadow_research.json"),load("live.json"),
                 load("explicit_dnp_research.json"),
                 load("official_injury_status_archive.json"),now)
    target=DATA/"p_play_selection_bias_audit.json"
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    tmp.replace(target)
    return {"status":report["status"],"finished_checked":report["finished_checked"],
            "verified":report["verified_postgame_results"],
            "UNKNOWN":report["unknown_postgame_results"],
            "official_OUT_missing":report["official_OUT_unknown_review_priority_count"],
            "adopt_on_site":report["adopt_on_site"]}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
