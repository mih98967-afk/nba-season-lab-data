"""Research-only forward test of FROZEN 2024/25-calibrated appearance proxy.

The target for the historical model was *a logged positive-minute appearance*
among previously active same-club players, NOT verified DNP or membership.
Its raw tuning and calibration were selected on 2024/25 and checked on
2025/26. Here we issue fresh predictions for future 2026/27 matches ONLY,
never reconstructing a score with a historical issuance timestamp.

Compare on exactly matched, separately verified p_play-shadow postgame
positive/explicit-DNP labels; neither this comparison nor the historical
proxy is calibrated population p_play. No site/account/transfer mutation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo
import json
import math

from src.sync import DATA
from src.historical_appearance_proxy_research import (
    positive_logs, validated_fixtures, estimate,
    MIN_TENURE_APPEARANCES, MIN_TENURE_TEAM_GAMES,
    MAX_DAYS_SINCE_PLAYED,
)
from src.rolling_decision_research import instant, stamp, canonical_hash

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
MODEL_STATUS = "research_only_not_deployed"
VERSION = 1
LOCK = timedelta(minutes=30)
HIGH_ID = "same_club_independent_ESPN_ID_observed"
ISSUE_MAX_LAG_HOURS = 72
DRAWS = 1000
SEED = 20261027


def _utc(value):
    if value.utcoffset() is None:
        raise ValueError("A research clock must carry timezone")
    return value.astimezone(UTC)


def frozen(frozen_report, historical_report):
    """Read-only frozen fit, never re-estimate on 2026/27 outcomes."""
    if (historical_report.get("status") != MODEL_STATUS
            or historical_report.get("adopt_on_site") is not False
            or historical_report.get("training_season") != "2024/25"
            or historical_report.get("untouched_holdout_season") != "2025/26"
            or historical_report.get("confirmed_DNP_observations") != 0
            or frozen_report.get("status") != MODEL_STATUS
            or frozen_report.get("adopt_on_site") is not False
            or frozen_report.get("used_in_live_site_or_forecast") is not False
            or frozen_report.get("actual_DNP_label_count") != 0
            or frozen_report.get("scope") !=
                "retrospective_selected_logged_appearance_PROXY_NOT_DNP"):
        raise ValueError("Historical model was not frozen as research-only")
    params = historical_report.get("selected_development_params")
    fit = frozen_report.get("calibration_training_only_2024_25")
    fixed = frozen_report.get("frozen_raw_parameters")
    if not all(isinstance(x, dict) for x in (params, fit, fixed)):
        raise ValueError("Missing frozen model configuration")
    if ((fixed.get("shrinkage"), fixed.get("recent_weight")) !=
            (params.get("shrinkage"), params.get("recent_weight"))):
        raise ValueError("Frozen raw tuning inconsistent")
    raw = (params["shrinkage"], params["recent_weight"])
    shrink = fit.get("selected_shrink")
    base_rate = fit.get("smoothed_development_appearance_rate")
    if (any(type(x) not in (int,float) or not math.isfinite(x) for x in
            (*raw,shrink,base_rate))
            or not 0 <= shrink <= 1 or not 0 < base_rate < 1):
        raise ValueError("Frozen calibration malformed")
    cfg = {"raw_shrinkage": raw[0], "raw_recent_weight":raw[1],
           "calibration_shrink":shrink, "development_prior_rate":base_rate,
           "development_only":"2024/25",
           "historical_source_season":"2025/26"}
    return cfg,canonical_hash(cfg)


def historical_profiles(historical_log, identity, calendar):
    """Historical, entirely past, team tenure; never use current outcomes."""
    games=validated_fixtures(calendar)
    positives,_=positive_logs(historical_log,identity,games)
    season="2025/26"
    fixtures=games[season]
    scheduled=defaultdict(list)
    for g in fixtures:
        for team in (g["home"],g["away"]):
            scheduled[team].append(g)
    results={}
    qa=Counter()
    for pid,played in positives[season].items():
        if not played:
            continue
        most_recent=played[-1]
        team=most_recent["club"]
        tenure=[]
        for item in reversed(played):
            if item["club"]!=team:
                break
            tenure.append(item)
        tenure.reverse()
        if len(tenure)<MIN_TENURE_APPEARANCES:
            qa["short_last_observed_team_tenure"]+=1
            continue
        club_games=scheduled[team]
        # The latest team-game is a real past 2025/26 regular-season fixture.
        if ((club_games[-1]["utc"]-most_recent["utc"]).days >
                MAX_DAYS_SINCE_PLAYED):
            qa["inactive_by_end_of_2025_26"]+=1
            continue
        previous_team_games=[g for g in club_games
                             if tenure[0]["utc"]<=g["utc"]]
        if len(previous_team_games)<MIN_TENURE_TEAM_GAMES:
            qa["insufficient_2025_26_team_fixtures"]+=1
            continue
        appeared={g["id"] for g in tenure}
        last20=previous_team_games[-20:]
        last5=previous_team_games[-5:]
        row={"last20_appeared":sum(g["id"] in appeared for g in last20),
             "last20_team_games":len(last20),
             "last5_appeared":sum(g["id"] in appeared for g in last5),
             "last5_team_games":len(last5)}
        results[pid]={"last_verified_played_club_2025_26":team,
                      "history_row":row,
                      "season":"2025/26",
                      "last_logged_appearance_utc":stamp(most_recent["utc"]),
                      "2025_26_games_in_observed_tenure":len(tenure)}
        qa["eligible_historical_profiles"]+=1
    return results,dict(qa)


def _validate_archive(prior, hash_value):
    if not prior:
        return [],[],{}
    if (prior.get("schema_version")!=VERSION
            or prior.get("status")!=MODEL_STATUS
            or prior.get("adopt_on_site") is not False
            or prior.get("population_p_play_calibrated") is not False
            or prior.get("historical_frozen_configuration_sha256")!=hash_value):
        raise ValueError("Research archive incompatible with frozen parameters")
    issued=prior.get("issued")
    outcome=prior.get("observed")
    if not isinstance(issued,list) or not isinstance(outcome,list):
        raise ValueError("Historical research archive incomplete")
    keys=set()
    for row in issued:
        key=(row.get("game_id"),row.get("player_id"))
        if (not all(isinstance(v,str) and v for v in key) or key in keys):
            raise ValueError("Duplicated historical benchmark issue")
        keys.add(key)
        at=instant(row["historical_proxy_issued_at_utc"])
        lock=instant(row["individual_lock_utc"])
        if (not at<lock or row.get("frozen_configuration_sha256")!=hash_value):
            raise ValueError("A historical issue was backdated or changed")
    seen=set()
    for row in outcome:
        key=(row.get("game_id"),row.get("player_id"))
        if key not in keys or key in seen:
            raise ValueError("Orphan/duplicate observed outcome")
        seen.add(key)
    return list(issued),list(outcome),prior


def _new_issues(saved, profiles, current_pplay, cfg, sha, now):
    used={(o["game_id"],o["player_id"]) for o in saved}
    add=[]
    qa=Counter()
    if (current_pplay.get("status")!=MODEL_STATUS
            or current_pplay.get("adopt_on_site") is not False
            or current_pplay.get("population_brier_enabled") is not False):
        raise ValueError("Untrusted live p_play shadow artifact")
    for p in current_pplay.get("issued",[]):
        key=(p.get("game_id"),p.get("player_id"))
        if key in used:
            qa["already_issued_unchanged"]+=1
            continue
        original=instant(p["issued_at_utc"])
        tip=instant(p["tipoff_utc"])
        lock=instant(p["individual_lock_utc"])
        if tip-lock!=LOCK or not original<lock or original>now:
            raise ValueError("Upstream p_play first-issued clock invalid")
        if now>=lock:
            qa["already_locked_no_historical_backfill"]+=1
            continue
        if now-original>timedelta(hours=ISSUE_MAX_LAG_HOURS):
            qa["upstream_issue_too_old"]+=1
            continue
        if p.get("club_link_evidence")!=HIGH_ID:
            qa["weak_or_unknown_cross_source_identity"]+=1
            continue
        profile=profiles.get(p["player_id"])
        if profile is None:
            qa["no_high_confidence_recent_2025_26_profile"]+=1
            continue
        if profile["last_verified_played_club_2025_26"]!=p["team"]:
            qa["different_club_since_2025_26_excluded"]+=1
            continue
        if (instant(p["catalog_capture_utc"])>original or
                instant(p["espn_capture_utc"])>original):
            raise ValueError("Upstream future roster capture detected")
        raw=estimate(profile["history_row"],
                     (cfg["raw_shrinkage"],cfg["raw_recent_weight"]))
        score=(1-cfg["calibration_shrink"])*raw + (
            cfg["calibration_shrink"]*cfg["development_prior_rate"])
        if not math.isfinite(score) or not 0<score<1:
            raise ValueError("Invalid frozen historical score")
        add.append({
            "game_id":p["game_id"],"player_id":p["player_id"],
            "club_at_2026_issue":p["team"],"position":p["position"],
            "game_utc":p["tipoff_utc"],"individual_lock_utc":p["individual_lock_utc"],
            "original_pplay_issued_at_utc":p["issued_at_utc"],
            "historical_proxy_issued_at_utc":stamp(now),
            "current_vs_historical_issue_lag_hours":
                round((now-original).total_seconds()/3600,3),
            "identity":"same_club_independent_ESPN_ID_observed",
            "2025_26_last_played_club_matches_2026_club":True,
            "historical_team_membership_verified_for_each_game":False,
            "2025_26_positive_log_source_only":True,
            "historical_last5_logged":profile["history_row"]["last5_appeared"],
            "historical_last5_team_games":profile["history_row"]["last5_team_games"],
            "historical_last20_logged":profile["history_row"]["last20_appeared"],
            "historical_last20_team_games":profile["history_row"]["last20_team_games"],
            "historical_score_uncalibrated":
                round(raw,6),
            "historical_score_dev_calibrated":
                round(score,6),
            "current_pplay_baseline_frozen":
                p["baseline_p_selected_listed_proxy"],
            "current_pplay_candidate_frozen":
                p["candidate_p_selected_listed_proxy"],
            "frozen_configuration_sha256":sha,
            "model_status":MODEL_STATUS,"adopt_on_site":False
        })
        qa["new_historical_benchmark_issues"]+=1
    return add,dict(qa)


def _observed(issued, previous, current_pplay, now):
    verified={(x["game_id"],x["player_id"]):x
              for x in current_pplay.get("observations",[])}
    existing={(x["game_id"],x["player_id"]):x for x in previous}
    if len(existing)!=len(previous) or len(verified)!=len(current_pplay.get("observations",[])):
        raise ValueError("Duplicate postgame observation")
    qa=Counter()
    for pred in issued:
        key=pred["game_id"],pred["player_id"]
        observed=verified.get(key)
        if observed is None:
            qa["no_explicit_verified_outcome_UNKNOWN"]+=1
            continue
        tip=instant(pred["game_utc"])
        at=instant(observed["source_first_observed_at_utc"])
        first_issue=instant(pred["historical_proxy_issued_at_utc"])
        if (at<tip or at<first_issue or at>now):
            raise ValueError("Postgame outcome provenance not chronological")
        if (pred["original_pplay_issued_at_utc"]>=pred["game_utc"]
                or observed["tipoff_utc"]!=pred["game_utc"]
                or observed["club_link_evidence_at_issue"]!=HIGH_ID):
            raise ValueError("Verified original issue differs from frozen historical benchmark")
        label=observed["actual_played"]
        if type(label) is not int or label not in (0,1):
            raise ValueError("Unknown outcome cannot be assigned DNP")
        if observed.get("label_provenance")!=(
                "positive_minutes_verified_sportsru_fp" if label else
                "explicit_espn_didNotPlay_true"):
            raise ValueError("Postgame observation has unverified participation source")
        if key in existing:
            if (existing[key]["actual_played"]!=label or
                    existing[key]["source_first_observed_at_utc"]!=stamp(at)):
                raise ValueError("Saved evaluation changed after first observation")
            continue
        existing[key]={
            "game_id":key[0],"player_id":key[1],"game_utc":pred["game_utc"],
            "actual_played":label,
            "label_provenance":observed["label_provenance"],
            "source_first_observed_at_utc":stamp(at),
            "historical_score_dev_calibrated":pred["historical_score_dev_calibrated"],
            "current_pplay_baseline_frozen":pred["current_pplay_baseline_frozen"],
            "current_pplay_candidate_frozen":pred["current_pplay_candidate_frozen"],
            "evaluated_at_utc":stamp(now)}
        qa["new_same_game_verified_outcomes"]+=1
    return sorted(existing.values(),key=lambda x:(x["game_utc"],x["game_id"],x["player_id"])),dict(qa)


def _metrics(rows):
    if not rows:
        return None
    fields={"current_baseline":"current_pplay_baseline_frozen",
            "current_candidate":"current_pplay_candidate_frozen",
            "historical_dev_calibrated":"historical_score_dev_calibrated"}
    per_game=defaultdict(list)
    for row in rows:
        label=row["actual_played"]
        loss={}
        for k,field in fields.items():
            prob=float(row[field])
            if type(label) is not int or label not in (0,1) or not 0<prob<1:
                raise ValueError("Improperly paired probability outcome")
            loss[k]=((prob-label)**2,
                     -(label*math.log(prob)+(1-label)*math.log1p(-prob)))
        per_game[row["game_id"]].append(loss)
    all_rows=[x for a in per_game.values() for x in a]
    n=len(all_rows)
    result={
        "scope":"overlap_high_ESPN_ID_prior_2025_26_same_observed_club",
        "verified_player_games":n,
        "distinct_NBA_games":len(per_game),
        "distinct_NBA_ET_dates":len({
            instant(o["game_utc"]).astimezone(ET).date().isoformat() for o in rows}),
        "baselines":{
            k:{"Brier":round(sum(x[k][0] for x in all_rows)/n,6),
               "logloss":round(sum(x[k][1] for x in all_rows)/n,6)}
            for k in fields},
        "historical_is_logged_appearance_proxy_not_true_pplay":True,
        "selected_verified_participation_labels_only":True,
        "population_model_adoption_permitted":False,
        "confounding_issue_time_not_identical":True,
    }
    if len(per_game)>1:
        rng=Random(SEED)
        groups=[per_game[k] for k in sorted(per_game)]
        simulations=[[],[]]
        for _ in range(DRAWS):
            sampled=[groups[rng.randrange(len(groups))] for x in groups]
            values=[v for g in sampled for v in g]
            for metric in (0,1):
                simulations[metric].append(
                    sum(x["current_candidate"][metric]-x["historical_dev_calibrated"][metric]
                        for x in values)/len(values))
        for z in simulations:z.sort()
        result["game_cluster_95pct_gain_historical_over_current"]={
            "Brier":[round(simulations[0][24],6),round(simulations[0][974],6)],
            "logloss":[round(simulations[1][24],6),round(simulations[1][974],6)],
            "repeats":DRAWS,"seed":SEED,
            "positive_means_historical_lower_error":True,
            "few_ET_dates_caution":result["distinct_NBA_ET_dates"]<4,
        }
    return result


def advance(previous, current_pplay, profiles, config, config_sha, now):
    now=_utc(now)
    issued,observed,old=_validate_archive(previous,config_sha)
    if not isinstance(profiles,dict):
        raise ValueError("Historical profiles not available")
    additions,qa=_new_issues(issued,profiles,current_pplay,config,config_sha,now)
    issued.extend(additions)
    observed,results=_observed(issued,observed,current_pplay,now)
    if old and not additions and not results.get("new_same_game_verified_outcomes"):
        return old,{"result":"unchanged",
                    "issued_total":len(issued),"evaluated_total":len(observed)}
    metrics=_metrics(observed)
    value={
        "schema_version":VERSION,"status":MODEL_STATUS,"model_status":MODEL_STATUS,
        "adopt_on_site":False,"updated_at_utc":stamp(now),
        "frozen_model_selection_season":"2024/25",
        "historical_source_season":"2025/26",
        "current_prospective_season":"2026/27",
        "historical_frozen_configuration_sha256":config_sha,
        "historical_configuration":config,
        "target":"postgame_explicit_positive_or_DNP_in_selected_boxscore_only",
        "population_p_play_calibrated":False,
        "true_game_day_roster_denominator_known":False,
        "historical_model_trained_on_logged_appearance_NOT_DNP":True,
        "keep_transfer_value_proven":False,
        "issued":issued,"observed":observed,
        "summary":{"issued_new":len(additions),"issued_total":len(issued),
                   "matched_verified_labels":len(observed),
                   "unobserved_UNKNOWN":len(issued)-len(observed)},
        "issue_QA":qa,"observation_QA":results,
        "same_game_competition_metrics_research_only":metrics,
        "limitations":[
            "2025/26 logged appearance has NO official active or DNP denominator.",
            "Only high-confidence independently ESPN-ID-linked existing same-club players are eligible.",
            "Player tenure is inferred from preceding played logs, not actual signed membership.",
            "Both historical and current shadow predictions must exist before the individual game lock.",
            "Historical score has a real issue time, never backdated to the original p_play issue.",
            "Only verified positive-minute / explicit-DNP labels are evaluated; unknown is excluded.",
            "Raw tuning and calibration are frozen from 2024/25; no 2026/27 retuning.",
            "A few one-day NBA games cannot validate broad injury or transfer probabilities.",
            "No real Sports.ru prices, week decisions, transfer value or production adoption.",
        ],
    }
    return value,{"result":"appended","issued_new":len(additions),
                  "issued_total":len(issued),"evaluated_total":len(observed),
                  "QA":qa}


def run():
    def read(name):return json.loads((DATA/name).read_text(encoding="utf8"))
    historical=read("historical_appearance_proxy_research.json")
    calibrated=read("historical_appearance_calibration_research.json")
    config,sha=frozen(calibrated,historical)
    historical_logs=read("nba_history.json")
    profiles,profile_qa=historical_profiles(
        historical_logs,read("identity.json"),read("historical_tipoffs.json"))
    target=DATA/"historical_prior_prospective_shadow_research.json"
    prior=read(target.name) if target.exists() else {}
    value,details=advance(prior,read("p_play_shadow_research.json"),
                          profiles,config,sha,datetime.now(UTC))
    if value!=prior:
        temp=target.with_suffix(".tmp")
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf8")
        temp.replace(target)
    return {**details,"profile_QA":profile_qa,
            "status":MODEL_STATUS,"adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
