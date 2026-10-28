"""Research-only temporal holdout audit for frozen minutes × FP/min bands.

Replays each 2025/26 athlete's FIRST FIVE observed positive-minute games
against a 2024/25-only fixed same-club last-20-game forecast. Independent
2025/26 holdout outcomes are never used to fit the 2024/25 rule/quantiles.
The player is the resampling cluster (up to five correlated outcomes).
Missing logs are UNKNOWN, NOT DNP or scored as zero.
No on-site use, p(play), Sports.ru personal credits or transfer actions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from math import sqrt
from pathlib import Path
from random import Random
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, stamp
from src.conditional_minutes_fp_research import (
    historical, calibration, historical_holdout, same_team_tail,
    forecast, _error, MODEL, STATUS, TRAIN, HOLDOUT,
)

SEED = 20261028
DRAWS = 1600
NOMINAL = 0.9
COLUMNS = (
    "paired_direct_minus_decomposed_FP_gain",
    "minutes_dev_q90_covered",
    "decomposed_FP_dev_q90_covered",
)


def avg(numbers):
    return sum(numbers) / len(numbers) if numbers else None


def qpercent(sorted_values, p):
    if not sorted_values:
        raise ValueError("Empty interval")
    k = (len(sorted_values)-1) * p
    lower = int(k)
    upper = min(lower+1, len(sorted_values)-1)
    return sorted_values[lower]*(upper-k)+sorted_values[upper]*(k-lower)


def cluster_by_player(rows, draws=DRAWS, seed=SEED):
    """Entire athlete histories are the bootstrap unit, NOT 1554 independent rows."""
    if type(draws) is not int or draws < 100 or type(seed) is not int:
        raise ValueError("Invalid fixed resampling protocol")
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["player_id"]].append(row)
    names = sorted(grouped)
    if len(names) < 100:
        raise ValueError("Insufficient independent players")
    per_player = [
        (len(grouped[name]), tuple(sum(r[c] for r in grouped[name]) for c in COLUMNS))
        for name in names
    ]
    rng = Random(seed)
    samples = {c:[] for c in COLUMNS}
    for _ in range(draws):
        total = 0
        sums = [0.0]*len(COLUMNS)
        for _ in per_player:
            count, vals = per_player[rng.randrange(len(per_player))]
            total += count
            for j,v in enumerate(vals):
                sums[j] += v
        for j,col in enumerate(COLUMNS):
            samples[col].append(sums[j]/total)
    return {
        name:{"lower":round(qpercent(sorted(scores), .025), 6),
              "upper":round(qpercent(sorted(scores), .975), 6)}
        for name,scores in samples.items()
    }


def summary(rows):
    if not rows:
        return {"played_cases":0}
    size=len(rows)
    gain=avg([r["paired_direct_minus_decomposed_FP_gain"] for r in rows])
    mcover=avg([r["minutes_dev_q90_covered"] for r in rows])
    fpcover=avg([r["decomposed_FP_dev_q90_covered"] for r in rows])
    return {
        "played_cases": size,
        "distinct_players":len({r["player_id"] for r in rows}),
        "distinct_NBA_games":len({r["game_id"] for r in rows}),
        "minutes_MAE":round(avg([r["minutes_abs_error"] for r in rows]),4),
        "minutes_forecast_minus_actual_bias":round(
            avg([r["predicted_minutes"]-r["actual_minutes"] for r in rows]),4),
        "decomposed_FP_MAE":round(avg([r["decomposed_fp_abs_error"] for r in rows]),4),
        "direct_FP_MAE":round(avg([r["direct_fp_abs_error"] for r in rows]),4),
        "FP_per_minute_MAE":round(
            avg([r["fp_per_minute_abs_error"] for r in rows]),4),
        "paired_direct_minus_decomposed_FP_MAE_gain":round(gain,4),
        "minutes_dev_q90_coverage":round(mcover,6),
        "decomposed_FP_dev_q90_coverage":round(fpcover,6),
        "minutes_nominal_minus_empirical_coverage_pp":round(100*(NOMINAL-mcover),3),
        "FP_nominal_minus_empirical_coverage_pp":round(100*(NOMINAL-fpcover),3),
    }


def build(index, loader, frozen, now):
    if now.utcoffset() is None:
        raise ValueError("Evaluation clock requires timezone")
    if (frozen.get("schema_version") != 1 or frozen.get("status") != STATUS
            or frozen.get("adopt_on_site") is not False
            or frozen.get("full_game_day_roster_denominator_known") is not False
            or frozen.get("model_selection_on_2025_26_holdout") is not False
            or frozen.get("unconditional_FP_enabled") is not False
            or frozen.get("training_negative_from_UNKNOWN") is not False
            or frozen.get("historical_source_index_version") != index.get("version")
            or frozen.get("frozen_rule_hash") != canonical_hash(MODEL)
            or frozen.get("frozen_structure_development_only") != MODEL):
        raise ValueError("Frozen research model/config or source is incompatible")
    people, qa = historical(index, loader)
    q, dev = calibration(people)
    historical_check = historical_holdout(people, q)
    if (frozen.get("source_qa") != qa or
            frozen.get("2024_25_chronological_development_residuals") != dev or
            frozen.get("2025_26_untouched_early_season_played_holdout") != historical_check):
        raise ValueError("Historical holdout or dev quantiles differ from original frozen report")
    rows = []
    postgame_stability = defaultdict(list)
    by_pred_minutes = defaultdict(list)
    by_actual_minutes = defaultdict(list)
    by_index = defaultdict(list)
    counted = Counter()
    for pid, seasons in sorted(people.items()):
        past = seasons.get(TRAIN) or []
        target = seasons.get(HOLDOUT) or []
        prior = forecast(same_team_tail(past))
        if not prior or not target:
            counted["prior_not_eligible_or_no_played_2025_26_log"] += 1
            continue
        if (prior.get("sample_last_played_date") >= "2025-07-01"
                or prior.get("played_sample_n") != 20):
            raise ValueError("2025/26 holdout leaked into frozen prior")
        stable = target[0]["team"] == prior["last_sample_team"]
        stability = ("first_played_2025_26_same_club_as_2024_25_prior"
                     if stable else "first_played_2025_26_changed_club_postgame_only")
        # This is a *postgame* group, not something known at the 2025/26 deadline.
        for slot, outcome in enumerate(target[:5],1):
            if outcome["d"] < "2025-10-01" or outcome["d"] > "2026-07-01":
                raise ValueError("Outcome outside untouched 2025/26 played season")
            errors = _error(prior,outcome)
            mins = outcome["min"]
            rate = outcome["fp"]/mins
            pred_min = prior["minutes_if_play"]
            mgroup = ("predicted_under_15" if pred_min < 15 else
                      "predicted_15_to_under_25" if pred_min < 25 else
                      "predicted_25_to_under_35" if pred_min < 35 else
                      "predicted_35_plus")
            # Actual-time strata are diagnostic ONLY, and must NEVER be used
            # as available pre-lock features for selecting model parameters.
            observed_group = ("actual_under_5" if mins < 5 else
                              "actual_5_to_under_10" if mins < 10 else
                              "actual_10_to_under_20" if mins < 20 else
                              "actual_20_plus")
            row={
                "game_id":outcome["g"],"player_id":pid,"played_date":outcome["d"],
                "first_5_played_game_number":slot,
                "player_team_at_actual_game":outcome["team"],
                "first_played_club_stability_postgame_only":stability,
                "predicted_minutes":pred_min,"actual_minutes":mins,
                "predicted_fp_if_played":prior["decomposed_fp_if_play"],
                "actual_fp_reconstructed":outcome["fp"],
                "actual_FP_per_minute":round(rate,8),
                "minutes_abs_error":errors["minutes"],
                "fp_per_minute_abs_error":errors["fp_per_minute"],
                "decomposed_fp_abs_error":errors["decomposed_fp"],
                "direct_fp_abs_error":errors["direct_fp"],
                "paired_direct_minus_decomposed_FP_gain":
                    errors["direct_fp"]-errors["decomposed_fp"],
                "minutes_dev_q90_covered":int(errors["minutes"]<=q["minutes"]),
                "decomposed_FP_dev_q90_covered":
                    int(errors["decomposed_fp"]<=q["decomposed_fp"]),
                "predicted_minutes_group_preoutcome":mgroup,
                "observed_minutes_group_POSTGAME_ONLY":observed_group,
            }
            rows.append(row)
            by_pred_minutes[mgroup].append(row)
            by_actual_minutes[observed_group].append(row)
            postgame_stability[stability].append(row)
            by_index[str(slot)].append(row)
    historical_summary = historical_check["all"]
    actual_summary=summary(rows)
    if (len(rows) != historical_summary["played_cases"]
            or len({r["player_id"] for r in rows}) != historical_check["distinct_players"]
            or len({r["game_id"] for r in rows}) != historical_check["distinct_NBA_games"]
            or abs(actual_summary["minutes_MAE"]-historical_summary["minutes_MAE"])>.00005
            or abs(actual_summary["decomposed_FP_MAE"]-historical_summary["decomposed_fp_MAE"])>.00005
            or abs(actual_summary["direct_FP_MAE"]-historical_summary["direct_fp_MAE"])>.00005
            or abs(actual_summary["minutes_dev_q90_coverage"]-
                   historical_summary["minutes_empirical_dev_q90_coverage"])>.000001
            or abs(actual_summary["decomposed_FP_dev_q90_coverage"]-
                   historical_summary["decomposed_fp_empirical_dev_q90_coverage"])>.000001):
        raise ValueError("Independent replay does not match frozen holdout")
    player_ci=cluster_by_player(rows)
    within0=(player_ci["paired_direct_minus_decomposed_FP_gain"]["lower"]<=0<=
             player_ci["paired_direct_minus_decomposed_FP_gain"]["upper"])
    result={
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,
        "updated_at_utc":stamp(now),
        "target":"played_minutes_and_reconstructed_Sportsru_FP_conditional_on_play",
        "historical_source_index_version":index["version"],
        "model_sha256":frozen["frozen_rule_hash"],
        "only_2024_25_past_chronological_development":True,
        "2025_26_holdout_reused_for_untuned_diagnostics_only":True,
        "frozen_dev_q90_absolute_error_bands":q,
        "summary":actual_summary,
        "source_checks":{"players_loaded":qa["players_loaded"],
                         "development_residuals":dev["2024_25_past_only_dev_cases"],
                         "holdout_player_games":len(rows),
                         "holdout_players":len({r["player_id"] for r in rows}),
                         "holdout_NBA_games":len({r["game_id"] for r in rows}),
                         "out_of_time_cutoff_verified":True,
                         "frozen_holdout_metrics_identical":True},
        "by_predicted_minutes_PREOUTCOME":{
            k:summary(v) for k,v in sorted(by_pred_minutes.items())},
        "by_actual_minutes_POSTGAME_DIAGNOSTIC_ONLY":{
            k:summary(v) for k,v in sorted(by_actual_minutes.items())},
        "by_first_2025_played_club_POSTGAME_ONLY":{
            k:summary(v) for k,v in sorted(postgame_stability.items())},
        "by_first_five_played_game_slot_POSTGAME_ONLY":{
            k:summary(v) for k,v in sorted(by_index.items())},
        "player_cluster_exploratory_95pct_intervals":{
            **player_ci,
            "method":"whole_player_bootstrap_percentile_fixed_seed",
            "seed":SEED,
            "resamples":DRAWS,
            "independent_unit":"player_with_up_to_5_repeated_played_games",
            "paired_FP_gain_interval_contains_zero":within0,
            "not_full_fantasy_roster_generalization":True,
            "not_calibration_fix":True,
        },
        "quality_gate":{
            "minute_intervals_have_prospective_90pct_coverage_proven":False,
            "conditional_FP_model_outperforms_direct_on_full_population":False,
            "unconditional_FPs_can_be_computed":False,
            "p_play_population_calibrated":False,
            "keep_transfer_value_proven":False,
            "can_train_from_absent_or_unknown_player":False,
            "new_model_deployed":False,
            "adopt_on_site":False,
        },
        "interpretation":[
            "2024/25 residual quantiles and parameters were frozen before 2025/26 holdout; no retuning.",
            "For each athlete, ONE frozen 2024/25 forecast is reused for up to five first 2025/26 PLAYED games.",
            "5 outcomes for one athlete are correlated, so uncertainty is resampled by PLAYER, not row.",
            "Postgame minutes and first-2025 played team groupings are diagnostics and NOT pre-lock predictors.",
            "Undercounted 90% development bands are not fixed using the already inspected holdout.",
            "Only played NBA boxscore rows included. Missing player is UNKNOWN, never zero-FP or confirmed DNP.",
            "Reconstructed FP is not the official Fantasy Sports.ru account credit or transfer value.",
            "This independent 2025/26 played-only test is separate from small 2026/27 prospective checks.",
            "No personal account/Firestore/Hosting, new calibration selection, or automatic transfers.",
        ],
    }
    return result


def run():
    load=lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
    index=load("history/index.json")
    report=build(index,lambda name:load("history/"+name),
                 load("conditional_minutes_fp_research.json"),
                 datetime.now(timezone.utc))
    target=DATA/"historical_minutes_interval_coverage_research.json"
    old=load(target.name) if target.exists() else {}
    if not old or {
        k:v for k,v in report.items() if k!="updated_at_utc"
    } != {
        k:v for k,v in old.items() if k!="updated_at_utc"
    }:
        temp=target.with_suffix(".tmp")
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        temp.replace(target)
    return {"holdout":report["summary"],
            "by_predicted_minutes":report["by_predicted_minutes_PREOUTCOME"],
            "CI":report["player_cluster_exploratory_95pct_intervals"],
            "adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
