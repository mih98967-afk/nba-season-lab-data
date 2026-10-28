"""Development-only conditional short-minutes risk and role-band research.

The 2024/25 same-team, chronologically prior played-game residuals are the
only fit inputs. The first five *observed played* games per player in 2025/26
are for an exploratory temporal comparison only. Prior PR #65 had already
inspected the 2025/26 holdout: its group thresholds and this follow-on study
are NOT a freshly preregistered independent test of a selected new model.
Never train p(play), impute absence as DNP, refit 2025/26 outcomes or deploy.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import ceil, isfinite, log, log1p
from random import Random
from zoneinfo import ZoneInfo
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, stamp
from src.conditional_minutes_fp_research import (
    MODEL, STATUS, TRAIN, HOLDOUT, historical, calibration,
    historical_holdout, forecast, same_team_tail,
)

SHORT_MINUTES = 10.0
GROUPS = ("under_15", "15_to_under_25", "25_to_under_35", "35_plus")
MIN_DEV_GROUP = 100
SMOOTHING_STRENGTH = 40.0
PROBABILITY_FLOOR = 0.005
Q90 = 0.90
SEED = 20261028
DRAWS = 1200
ET = ZoneInfo("America/New_York")


def group_by_predicted_minutes(minutes):
    if not isinstance(minutes, (int, float)) or not isfinite(minutes) or minutes < 0:
        raise ValueError("Predicted minutes must be finite and non-negative")
    return ("under_15" if minutes < 15 else
            "15_to_under_25" if minutes < 25 else
            "25_to_under_35" if minutes < 35 else "35_plus")


def clipped(p):
    return max(PROBABILITY_FLOOR, min(1-PROBABILITY_FLOOR, p))


def quantile90(values):
    if not values:
        raise ValueError("No calibration residuals")
    x = sorted(values)
    return x[max(0, ceil(Q90*len(x))-1)]


def cohort(people):
    dev, holdout = [], []
    for pid, seasons in sorted(people.items()):
        prior = seasons.get(TRAIN) or []
        next_year = seasons.get(HOLDOUT) or []
        if len(prior) >= 25:
            for i in range(max(20, len(prior)-10), len(prior)):
                seen = same_team_tail(prior[:i])
                predicted = forecast(seen)
                if predicted is None:
                    continue
                actual = prior[i]
                if (predicted["sample_last_played_date"] > actual["d"]
                        or actual["g"][:5] != "00224"):
                    raise ValueError("Development prediction leaked future played result")
                dev.append({
                    "player_id": pid, "game_id": actual["g"],
                    "outcome_date": actual["d"], "forecast_minutes": predicted["minutes_if_play"],
                    "actual_minutes": actual["min"], "split": "2024_25_dev",
                })
        frozen = forecast(same_team_tail(prior))
        if frozen is None or not next_year:
            continue
        for actual in next_year[:5]:
            if (frozen["sample_last_played_date"] >= "2025-07-01"
                    or actual["g"][:5] != "00225"
                    or not "2025-10-01" <= actual["d"] <= "2026-07-01"):
                raise ValueError("Historical holdout was not strictly out of season")
            holdout.append({
                "player_id": pid, "game_id": actual["g"],
                "outcome_date": actual["d"], "forecast_minutes": frozen["minutes_if_play"],
                "actual_minutes": actual["min"], "split": "2025_26_previously_inspected_holdout",
            })
    if (len(dev) != len({(x["player_id"], x["game_id"]) for x in dev})
            or len(holdout) != len({(x["player_id"], x["game_id"]) for x in holdout})):
        raise ValueError("Duplicate development/holdout outcomes")
    return dev, holdout


def fit_development_only(rows, original_global_q90):
    if not rows or any(r["split"] != "2024_25_dev" for r in rows):
        raise ValueError("Cannot fit from an out-of-time outcome")
    if not (isinstance(original_global_q90, (int, float))
            and isfinite(original_global_q90) and original_global_q90 > 0):
        raise ValueError("Invalid original 2024/25 residual quantile")
    preval = sum(r["actual_minutes"] < SHORT_MINUTES for r in rows)/len(rows)
    baseline = clipped(preval)
    source = defaultdict(list)
    for row in rows:
        source[group_by_predicted_minutes(row["forecast_minutes"])].append(row)
    bands = {}
    for name in GROUPS:
        segment = source[name]
        n = len(segment)
        short = sum(r["actual_minutes"] < SHORT_MINUTES for r in segment)
        group_risk = clipped((short + SMOOTHING_STRENGTH * preval)/
                             (n + SMOOTHING_STRENGTH))
        residuals = [abs(r["forecast_minutes"]-r["actual_minutes"]) for r in segment]
        use_group = n >= MIN_DEV_GROUP
        q = quantile90(residuals) if use_group else original_global_q90
        bands[name] = {
            "dev_cases": n, "dev_short_under_10_count": short,
            "dev_short_under_10_rate": round(short/n, 6) if n else None,
            "dev_only_smoothed_conditional_short_probability": round(group_risk, 8),
            "dev_only_residual_q90_minutes": round(q, 5),
            "used_group_q90_not_global_fallback": use_group,
        }
    if sum(x["dev_cases"] for x in bands.values()) != len(rows):
        raise ValueError("Development case partition incomplete")
    return {
        "global_dev_played_only_short_under_10_rate": round(preval, 8),
        "global_dev_played_only_short_baseline_probability": round(baseline, 8),
        "original_global_dev_q90_minutes": round(original_global_q90, 5),
        "development_cases": len(rows),
        "group_parameters_fitted_on_dev_only": bands,
        "no_2025_26_outcome_used_for_fitting": True,
    }


def scored_holdout(rows, params):
    if any(r["split"] != "2025_26_previously_inspected_holdout" for r in rows):
        raise ValueError("Holdout contains development observations")
    details = []
    for r in rows:
        name = group_by_predicted_minutes(r["forecast_minutes"])
        band = params["group_parameters_fitted_on_dev_only"][name]
        actual, pred = r["actual_minutes"], r["forecast_minutes"]
        y = int(actual < SHORT_MINUTES)
        global_risk = params["global_dev_played_only_short_baseline_probability"]
        group_risk = band["dev_only_smoothed_conditional_short_probability"]
        err_global = abs(actual-pred) <= params["original_global_dev_q90_minutes"]
        err_group = abs(actual-pred) <= band["dev_only_residual_q90_minutes"]
        def brier(p):
            return (p-y)**2
        def logloss(p):
            return -(y*log(p)+(1-y)*log1p(-p))
        details.append({
            "player_id":r["player_id"], "game_id":r["game_id"],
            "group":name, "actual_minutes":actual, "forecast_minutes":pred,
            "event_under_10_minutes_given_played":y,
            "global_brier":brier(global_risk), "group_brier":brier(group_risk),
            "global_logloss":logloss(global_risk), "group_logloss":logloss(group_risk),
            "paired_global_minus_group_Brier_gain":brier(global_risk)-brier(group_risk),
            "paired_global_minus_group_logloss_gain":logloss(global_risk)-logloss(group_risk),
            "global_q90_minutes_covered":int(err_global),
            "group_q90_minutes_covered":int(err_group),
            "coverage_group_minus_global":int(err_group)-int(err_global),
            "global_band_width":(pred + params["original_global_dev_q90_minutes"]
                                 -max(0,pred-params["original_global_dev_q90_minutes"])),
            "group_band_width":(pred + band["dev_only_residual_q90_minutes"]
                                -max(0,pred-band["dev_only_residual_q90_minutes"])),
        })
    return details


def mean(values):
    return sum(values)/len(values) if values else None


def summarize(rows):
    if not rows:
        return {"played_only_cases":0}
    def average(key):
        return mean([r[key] for r in rows])
    return {
        "played_only_cases": len(rows),
        "distinct_players":len({r["player_id"] for r in rows}),
        "distinct_NBA_games":len({r["game_id"] for r in rows}),
        "observed_under_10_minutes_count":sum(r["event_under_10_minutes_given_played"] for r in rows),
        "observed_under_10_minutes_rate":round(average("event_under_10_minutes_given_played"),6),
        "global_short_minutes_Brier":round(average("global_brier"),6),
        "group_short_minutes_Brier":round(average("group_brier"),6),
        "paired_Brier_gain_global_minus_group":round(
            average("paired_global_minus_group_Brier_gain"),6),
        "global_short_minutes_logloss":round(average("global_logloss"),6),
        "group_short_minutes_logloss":round(average("group_logloss"),6),
        "paired_logloss_gain_global_minus_group":round(
            average("paired_global_minus_group_logloss_gain"),6),
        "original_global_q90_coverage":round(average("global_q90_minutes_covered"),6),
        "new_group_dev_q90_coverage":round(average("group_q90_minutes_covered"),6),
        "new_group_minus_global_coverage_pp":round(
            100*average("coverage_group_minus_global"),3),
        "original_global_band_mean_width":round(average("global_band_width"),4),
        "new_group_band_mean_width":round(average("group_band_width"),4),
        "new_minus_original_width_minutes":round(
            average("group_band_width")-average("global_band_width"),4),
        "global_90pct_target_gap_pp":round(
            100*(Q90-average("global_q90_minutes_covered")),3),
        "new_group_90pct_target_gap_pp":round(
            100*(Q90-average("group_q90_minutes_covered")),3),
    }


METRICS = (
    "paired_global_minus_group_Brier_gain",
    "paired_global_minus_group_logloss_gain",
    "coverage_group_minus_global",
)


def whole_player_uncertainty(rows, seed=SEED, draws=DRAWS):
    grouped=defaultdict(list)
    for row in rows:
        grouped[row["player_id"]].append(row)
    players=sorted(grouped)
    if len(players) < 100 or draws < 100:
        raise ValueError("Insufficient player bootstrap denominator")
    blocks=[
        (len(grouped[pid]),tuple(sum(r[metric] for r in grouped[pid]) for metric in METRICS))
        for pid in players
    ]
    samples={metric:[] for metric in METRICS}
    rng=Random(seed)
    for _ in range(draws):
        size=0
        accum=[0.0]*len(METRICS)
        for _ in players:
            n,totals=blocks[rng.randrange(len(blocks))]
            size += n
            for j,v in enumerate(totals):
                accum[j] += v
        for j,metric in enumerate(METRICS):
            samples[metric].append(accum[j]/size)
    def q(values,p):
        arr=sorted(values)
        x=(len(arr)-1)*p
        lo=int(x)
        hi=min(lo+1,len(arr)-1)
        return arr[lo]*(hi-x)+arr[hi]*(x-lo)
    return {
        metric:{"lower":round(q(values,.025),6),"upper":round(q(values,.975),6)}
        for metric,values in samples.items()
    }


def build(index, loader, frozen, now):
    if now.utcoffset() is None:
        raise ValueError("Research clock must be aware")
    if (frozen.get("schema_version") != 1 or frozen.get("status") != STATUS
            or frozen.get("adopt_on_site") is not False
            or frozen.get("full_game_day_roster_denominator_known") is not False
            or frozen.get("unconditional_FP_enabled") is not False
            or frozen.get("p_play_assumed_calibrated") is not False
            or frozen.get("model_selection_on_2025_26_holdout") is not False
            or frozen.get("frozen_rule_hash") != canonical_hash(MODEL)
            or frozen.get("frozen_structure_development_only") != MODEL
            or frozen.get("historical_source_index_version") != index.get("version")):
        raise ValueError("Invalid original frozen conditional minutes model")
    people, qa=historical(index,loader)
    devq, devmeta=calibration(people)
    holdmeta=historical_holdout(people,devq)
    if (frozen.get("2024_25_chronological_development_residuals") != devmeta
            or frozen.get("2025_26_untouched_early_season_played_holdout") != holdmeta
            or frozen.get("source_qa") != qa):
        raise ValueError("Historical evaluation does not equal frozen audited report")
    dev, hold=cohort(people)
    if (len(dev) != devmeta["2024_25_past_only_dev_cases"]
            or len(hold) != holdmeta["all"]["played_cases"]
            or len({r["player_id"] for r in hold}) != holdmeta["distinct_players"]
            or len({r["game_id"] for r in hold}) != holdmeta["distinct_NBA_games"]
            or round(mean([
                int(abs(r["forecast_minutes"]-r["actual_minutes"])<=devq["minutes"])
                for r in hold]),6) != holdmeta["all"]["minutes_empirical_dev_q90_coverage"]):
        raise ValueError("2024/25 development or 2025/26 heldout denominator drift")
    params=fit_development_only(dev,devq["minutes"])
    scored=scored_holdout(hold,params)
    overall=summarize(scored)
    strata=defaultdict(list)
    for row in scored:
        strata[row["group"]].append(row)
    ci=whole_player_uncertainty(scored)
    gain_ci=ci["paired_global_minus_group_Brier_gain"]
    improvement_nonzero=gain_ci["lower"]>0 or gain_ci["upper"]<0
    return {
        "schema_version":1, "status":STATUS, "model_status":STATUS,
        "adopt_on_site":False, "updated_at_utc":stamp(now),
        "target":"probability_minutes_below_10_given_positive_minutes_and_90pct_minutes_bands",
        "population":"2025_26_first_five_POSITIVE_MINUTE_games_only_not_full_scheduled_fantasy_roster",
        "historical_index_version":index["version"],
        "immutable_2024_25_model_hash":frozen["frozen_rule_hash"],
        "development_source":"2024_25_rolling_same_team_past_played_only",
        "test_source":"2025_26_first_five_played_only_already_inspected_by_PR65",
        "protocol":{
            "threshold_short_actual_minutes":SHORT_MINUTES,
            "strata_prior_predicted_minutes":[15,25,35],
            "strata_selected_after_previous_2025_26_audit":True,
            "dev_only_residual_quantile":Q90,
            "minimum_development_cases_per_group_for_band":MIN_DEV_GROUP,
            "short_minute_probability_pseudocount_strength":SMOOTHING_STRENGTH,
            "short_minute_probability_clip":PROBABILITY_FLOOR,
            "no_selection_or_refitting_on_2025_26_holdout":True,
            "prior_season_frozen_prediction_reused_first_five_played_games":True,
        },
        "dev_only_fit":params,
        "holdout_exploratory":overall,
        "holdout_by_predicted_minutes_before_2025_outcomes":{
            name:summarize(strata[name]) for name in GROUPS
        },
        "player_cluster_uncertainty":{
            **ci, "resamples":DRAWS, "seed":SEED,
            "independent_unit":"historical_player_not_individual_game",
            "Brier_gain_interval_excludes_zero_exploratory_only":improvement_nonzero,
            "not_fresh_independent_holdout_for_model_choice":True,
        },
        "quality_gate":{
            "fresh_unused_holdout_for_new_strata":False,
            "prospective_2026_27_separate_model_issues_exist":False,
            "p_play_full_denominator_verified":False,
            "unconditional_FP_from_this_risk_allowed":False,
            "new_individual_minutes_interval_calibrated":False,
            "false_DNP_created_from_absence":False,
            "live_model_changed":False,
            "KEEP_TRANSFER_gain_proven":False,
            "adopt_on_site":False,
        },
        "limitations":[
            "Only actual positive-minute appearances; conditional short minutes is not player DNP probability.",
            "The four group cutpoints were investigated AFTER previous 2025/26 diagnostics; cannot treat this 2025/26 result as fresh model-selection validation.",
            "All fitted quantities are calculated solely from 2024/25 chronological development played cases.",
            "Historical prior is reused for the first five 2025/26 played games; no 2025/26 rolling updates.",
            "Whole-player bootstrap acknowledges correlated first-five repeated outcomes; not team/game generalization.",
            "Group 2024/25 q90 bands and risk are frozen exploratory alternatives, not future prediction intervals.",
            "No full game-day roster, DNP imputation, Sports.ru credited FP, Firebase/Hosting or personal transfer changes.",
        ],
    }


def run():
    read=lambda path:json.loads((DATA/path).read_text(encoding="utf8"))
    report=build(read("history/index.json"),
                 lambda filename:read("history/"+filename),
                 read("conditional_minutes_fp_research.json"),
                 datetime.now(timezone.utc))
    path=DATA/"short_minutes_role_bands_research.json"
    old=read(path.name) if path.exists() else {}
    if not old or {
        k:v for k,v in report.items() if k!="updated_at_utc"
    } != {
        k:v for k,v in old.items() if k!="updated_at_utc"
    }:
        temp=path.with_suffix(".tmp")
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        temp.replace(path)
    return {"holdout":report["holdout_exploratory"],
            "dev_only_groups":report["dev_only_fit"]["group_parameters_fitted_on_dev_only"],
            "adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
