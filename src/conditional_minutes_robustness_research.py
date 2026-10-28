"""Frozen conditional-minutes FP robustness protocol (research only).

Reads only the already verified, pre-lock minutes-if-play evaluation and
its immutable source issues. Rechecks the entire selected scored denominator,
game/date/club/provenance and original predictions without fitting anything.
A paired FP MAE gain is DESCRIPTIVE until >=8 distinct ET dates, >=100 verified
played cases and >=24 NBA games permit a first ET-DATE clustered exploratory
interval. Even such an interval is NOT population/transfer benefit evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from math import isfinite, sqrt
from random import Random
from zoneinfo import ZoneInfo
import json

from src.sync import DATA

STATUS = "research_only_not_deployed"
ET = ZoneInfo("America/New_York")
SEED = 20261028
RESAMPLES = 2000
MIN_ET_DATES = 8
MIN_PLAYED = 100
MIN_GAMES = 24
EXPLICIT = "explicit_espn_didNotPlay_true"


def instant(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing provenance UTC timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Malformed time provenance") from exc
    if result.utcoffset() is None:
        raise ValueError("Naive provenance time")
    return result.astimezone(timezone.utc)


def n(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("Unsupported numerical field")
    return float(value)


def identity(rows, what):
    if not isinstance(rows, list):
        raise ValueError("Missing " + what)
    result = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("Bad record in " + what)
        key = item.get("game_id"), item.get("player_id")
        if any(not isinstance(s, str) or not s for s in key) or key in result:
            raise ValueError("Duplicate/invalid " + what)
        result[key] = item
    return result


def near(actual, expected):
    return abs(n(actual) - n(expected)) <= 0.000011


def mean(values):
    return sum(values) / len(values) if values else None


def percentile(sorted_samples, fraction):
    # Fixed linear interpolation, deterministic across Python platforms.
    i = (len(sorted_samples)-1) * fraction
    low = int(i)
    high = min(low+1, len(sorted_samples)-1)
    return sorted_samples[low]*(high-i)+sorted_samples[high]*(i-low)


def validate(evaluation, source, now):
    if now.utcoffset() is None:
        raise ValueError("Research clock requires timezone")
    now = now.astimezone(timezone.utc)
    for obj, name in ((evaluation, "conditional evaluation"),
                      (source, "frozen minutes issues")):
        if (obj.get("schema_version") != 1 or obj.get("status") != STATUS
                or obj.get("adopt_on_site") is not False):
            raise ValueError("Invalid/deployable " + name)
    if (evaluation.get("quality_gate", {}).get("unconditional_FP_allowed") is not False
            or evaluation.get("quality_gate", {}).get("p_play_full_denominator_calibrated") is not False
            or evaluation.get("quality_gate", {}).get("adopt_on_site") is not False
            or source.get("p_play_assumed_calibrated") is not False
            or source.get("unconditional_FP_enabled") is not False
            or source.get("training_negative_from_UNKNOWN") is not False
            or source.get("model_selection_on_2025_26_holdout") is not False):
        raise ValueError("Unsafe original research claims")
    originals = identity(source.get("issued"), "original immutable issues")
    if len(originals) != source.get("issued_total") or not originals:
        raise ValueError("Malformed frozen issued population")
    canonical = sha256(json.dumps(source["issued"], sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False).encode("utf8")).hexdigest()
    if (canonical != evaluation.get("frozen_minutes_issue_sha256")
            or source.get("frozen_rule_hash") != evaluation.get("model_frozen_hash")):
        raise ValueError("Evaluation no longer matches immutable frozen issues")
    groups = {
        "played": evaluation.get("scored_played"),
        "explicit_DNP": evaluation.get("explicit_DNP_not_in_conditional_metrics"),
        "UNKNOWN": evaluation.get("UNKNOWN_unscored"),
    }
    keys = set()
    scores = []
    all_finished = []
    summary = evaluation.get("summary") or {}
    for label, entries in groups.items():
        for row in entries if isinstance(entries, list) else ():
            key = row.get("game_id"), row.get("player_id")
            if key in keys or key not in originals:
                raise ValueError("Outcome identity or partition inconsistency")
            keys.add(key)
            old = originals[key]
            tip, issued, lock = (instant(old["game_utc"]),
                                 instant(old["issued_at_utc"]),
                                 instant(old["individual_lock_utc"]))
            if (not (issued < lock < tip <= now)
                    or tip - lock != timedelta(minutes=30)
                    or old.get("observed_game_outcome") != "UNKNOWN"
                    or old.get("game_day_membership_verified") is not False
                    or old.get("adopt_on_site") is not False
                    or old.get("frozen_rule_hash") != source["frozen_rule_hash"]
                    or old.get("historical_training_season") != "2025/26"
                    or old.get("historical_source_index_version") !=
                       source["historical_source_index_version"]
                    or old.get("historical_source_last_game_date", "9999") >= "2026-07-01"):
                raise ValueError("Invalid original pre-lock issue or source cutoff")
            et = tip.astimezone(ET).date().isoformat()
            if (row.get("team") != old.get("team")
                    or row.get("game_utc") != old["game_utc"]
                    or row.get("minutes_issued_at_utc") != old["issued_at_utc"]
                    or row.get("p_play_first_issued_at_utc") != old["p_play_first_issued_at_utc"]
                    or row.get("et_date") != et
                    or row.get("outcome") != label):
                raise ValueError("Wrong team, ET date, score category or provenance")
            if not instant(old["p_play_first_issued_at_utc"]) <= issued:
                raise ValueError("First p_play issue after minutes forecast")
            for evidence_field in ("actual_minutes", "actual_fp_reconstructed",
                                   "actual_rate", "predicted_decomposed_fp",
                                   "predicted_direct_fp"):
                if label != "played" and evidence_field in row:
                    raise ValueError("Conditional FP incorrectly scored for DNP/UNKNOWN")
            if label != "UNKNOWN":
                observed = instant(row["postgame_first_seen_at_utc"])
                if observed < tip or observed > now:
                    raise ValueError("Postgame outcome observed before tipoff/in future")
            if label == "explicit_DNP":
                if (row.get("evidence") != EXPLICIT
                        or row.get("not_scored_as_zero_FP") is not True):
                    raise ValueError("DNP not individually verified or incorrectly scored")
            if label == "played":
                if (n(row["actual_minutes"]) <= 0
                        or not near(row["actual_rate"],
                                    n(row["actual_fp_reconstructed"])/n(row["actual_minutes"]))):
                    raise ValueError("Played minutes/FP rate contradict boxscore")
                for rk, ok in (
                    ("predicted_minutes", "min_if_play"),
                    ("predicted_rate", "fp_per_minute_if_play"),
                    ("predicted_decomposed_fp", "decomposed_fp_if_play"),
                    ("predicted_direct_fp", "direct_fp_if_play")):
                    if not near(row[rk], old[ok]):
                        raise ValueError("Issued forecast was retrospectively altered")
                band = old["development_2024_25_error_bands_not_guaranteed"]
                if (row.get("frozen_dev_minutes_band") != band["minutes_if_play"]
                        or row.get("frozen_dev_fp_band") != band["fp_if_play"]):
                    raise ValueError("Frozen development interval was refit")
                for label2, values in (
                    ("minutes", row["frozen_dev_minutes_band"]),
                    ("FP", row["frozen_dev_fp_band"])):
                    if (not isinstance(values, list) or len(values) != 2 or
                            n(values[0]) > n(values[1])):
                        raise ValueError("Bad source " + label2 + " band")
                actual_fp = n(row["actual_fp_reconstructed"])
                gain = (abs(n(row["predicted_direct_fp"]) - actual_fp)
                        - abs(n(row["predicted_decomposed_fp"]) - actual_fp))
                scores.append({
                    "game_id": key[0], "player_id": key[1], "ET_date": et,
                    "paired_absolute_FP_gain": gain,
                    "direct_abs_FP_error": abs(n(row["predicted_direct_fp"]) - actual_fp),
                    "decomposed_abs_FP_error": abs(n(row["predicted_decomposed_fp"]) - actual_fp),
                    "minutes_abs_error": abs(n(row["predicted_minutes"]) - n(row["actual_minutes"])),
                    "minutes_in_frozen_dev_band": (
                        n(row["frozen_dev_minutes_band"][0]) <=
                        n(row["actual_minutes"]) <=
                        n(row["frozen_dev_minutes_band"][1])),
                    "FP_in_frozen_dev_band": (
                        n(row["frozen_dev_fp_band"][0]) <= actual_fp <=
                        n(row["frozen_dev_fp_band"][1])),
                    "FP_band_width": n(row["frozen_dev_fp_band"][1])-n(row["frozen_dev_fp_band"][0]),
                    "minutes_band_width": n(row["frozen_dev_minutes_band"][1])-n(row["frozen_dev_minutes_band"][0]),
                })
            all_finished.append({"game_id":key[0], "player_id":key[1],
                                 "ET_date":et, "outcome":label})
    if (len(scores) != summary.get("played")
            or len(groups["explicit_DNP"]) != summary.get("explicit_DNP_not_scored")
            or len(groups["UNKNOWN"]) != summary.get("UNKNOWN_not_imputed")
            or len(keys) != summary.get("finished_checked")
            or len(originals) != summary.get("issued_total")
            or len(originals) != len(keys)+summary.get("awaiting_or_unchecked", -1)
            or len({r["game_id"] for r in scores}) != summary.get("played_distinct_games")
            or len({r["ET_date"] for r in scores}) != summary.get("played_distinct_ET_dates")):
        raise ValueError("Prospective played/UNKNOWN/DNP population drift")
    if scores:
        audit = evaluation["positive_minutes_selected_only_metrics"]
        for attr, key in (("direct_abs_FP_error", "direct_FP"),
                          ("decomposed_abs_FP_error", "decomposed_FP"),
                          ("minutes_abs_error", "predicted_minutes")):
            if abs(mean([s[attr] for s in scores])-n(audit[key]["MAE"])) > 0.000051:
                raise ValueError("Published FP/minute absolute error mismatch")
        if (abs(mean([s["paired_absolute_FP_gain"] for s in scores]) -
                n(audit["direct_minus_decomposed_FP_MAE"])) > 0.000051):
            raise ValueError("Published paired FP gain mismatch")
    return scores, all_finished, canonical


def cluster_bootstrap_by_ET_date(scores, seed=SEED, draws=RESAMPLES,
                                min_dates=MIN_ET_DATES, min_cases=MIN_PLAYED,
                                min_games=MIN_GAMES):
    days = defaultdict(list)
    for row in scores:
        days[row["ET_date"]].append(row["paired_absolute_FP_gain"])
    dates = sorted(days)
    games = len({row["game_id"] for row in scores})
    eligible = len(dates) >= min_dates and len(scores) >= min_cases and games >= min_games
    if not eligible:
        return None
    if draws < 100 or seed is None or any(not day for day in days.values()):
        raise ValueError("Invalid bootstrap protocol")
    rng = Random(seed)
    samples = []
    for _ in range(draws):
        sample_dates = [dates[rng.randrange(len(dates))] for _ in dates]
        vals = [delta for d in sample_dates for delta in days[d]]
        samples.append(mean(vals))
    samples.sort()
    return {
        "lower": round(percentile(samples, 0.025), 4),
        "upper": round(percentile(samples, 0.975), 4),
        "resamples": draws, "seed": seed,
        "resampling_unit": "NBA_ET_date_with_all_verified_played_player_games",
        "gain_unit": "FP_per_selected_verified_played_player_game",
        "interval_kind": "date_cluster_percentile_95_exploratory_NOT_population_proof",
        "different_ET_dates_are_the_resampling_clusters": True,
        "can_establish_full_population_effect": False,
    }


def build(evaluation, frozen, now):
    scored, finished, fingerprint = validate(evaluation, frozen, now)
    grouped = defaultdict(list)
    for row in scored:
        grouped[row["ET_date"]].append(row)
    total_days = len(grouped)
    game_count = len({r["game_id"] for r in scored})
    gate_dates = total_days >= MIN_ET_DATES
    gate_cases = len(scored) >= MIN_PLAYED
    gate_games = game_count >= MIN_GAMES
    groups = {}
    for date, rows in sorted(grouped.items()):
        groups[date] = {
            "played": len(rows),
            "distinct_NBA_games": len({r["game_id"] for r in rows}),
            "paired_direct_minus_decomposed_FP_MAE": round(
                mean([r["paired_absolute_FP_gain"] for r in rows]), 4),
            "decomposed_FP_MAE": round(
                mean([r["decomposed_abs_FP_error"] for r in rows]), 4),
            "direct_FP_MAE": round(
                mean([r["direct_abs_FP_error"] for r in rows]), 4),
            "minutes_MAE": round(mean([r["minutes_abs_error"] for r in rows]), 4),
            "minutes_frozen_band_empirical_coverage": round(
                mean([int(r["minutes_in_frozen_dev_band"]) for r in rows]), 6),
            "FP_frozen_band_empirical_coverage": round(
                mean([int(r["FP_in_frozen_dev_band"]) for r in rows]), 6),
        }
    n_fp = evaluation["positive_minutes_selected_only_metrics"]
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False,
        "updated_at_utc": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": "same_first_issued_prelock_selected_prospective_minutes_if_play_only",
        "frozen_issue_sha256": fingerprint,
        "frozen_model_sha256": frozen["frozen_rule_hash"],
        "input_evaluation_last_updated_at_utc": evaluation.get("updated_at_utc"),
        "summary": {
            "frozen_issues_total": len(frozen["issued"]),
            "finished_checked": len(finished),
            "played_scored_conditional": len(scored),
            "explicit_DNP_not_scored_as_zero": len(evaluation["explicit_DNP_not_in_conditional_metrics"]),
            "UNKNOWN_not_imputed": len(evaluation["UNKNOWN_unscored"]),
            "independent_ET_date_clusters": total_days,
            "distinct_NBA_games": game_count,
            "observed_pairwise_direct_minus_decomposed_FP_MAE_gain": (
                round(mean([r["paired_absolute_FP_gain"] for r in scored]), 4)
                if scored else None),
            "relative_gain_pct_descriptive_ONLY": (
                round(100*mean([r["paired_absolute_FP_gain"] for r in scored])/
                      n_fp["direct_FP"]["MAE"], 2)
                if scored and n_fp["direct_FP"]["MAE"] else None),
            "positive_gain_does_not_prove_future_generalization": True,
        },
        "frozen_bands_descriptive_played_only": {
            "minutes_coverage": round(mean([
                int(r["minutes_in_frozen_dev_band"]) for r in scored]), 6) if scored else None,
            "minutes_mean_width": round(mean([
                r["minutes_band_width"] for r in scored]), 4) if scored else None,
            "FP_coverage": round(mean([
                int(r["FP_in_frozen_dev_band"]) for r in scored]), 6) if scored else None,
            "FP_mean_width": round(mean([
                r["FP_band_width"] for r in scored]), 4) if scored else None,
            "not_validated_prospective_individual_intervals": True,
        },
        "by_NBA_ET_date": groups,
        "fixed_research_thresholds": {
            "min_ET_dates_for_exploratory_cluster_bootstrap": MIN_ET_DATES,
            "min_positive_minutes_cases": MIN_PLAYED,
            "min_distinct_NBA_games": MIN_GAMES,
            "date_gate": gate_dates,
            "played_gate": gate_cases,
            "game_gate": gate_games,
            "first_exploratory_interval_eligible": gate_dates and gate_cases and gate_games,
        },
        "ET_date_cluster_paired_MAE_gain_95pct_interval_if_eligible":
            cluster_bootstrap_by_ET_date(scored),
        "quality_gate": {
            "frozen_model_parameters_changed": False,
            "individual_FP_interval_calibration_proven": False,
            "correct_full_fantasy_roster_denominator_verified": False,
            "p_play_population_probabilities_calibrated": False,
            "Sportsru_account_credited_FP_verified": False,
            "actual_KEEP_TRANSFER_gain_demonstrated": False,
            "unconditional_FP_allowed": False,
            "adopt_on_site": False,
        },
        "interpretation": [
            "44 played cases on one ET date can produce a descriptive paired MAE, NOT a robust interval.",
            "Future cluster intervals resample ET DATES, never players as independent draws.",
            "The gates are necessary exploratory sample checks, NOT deployment acceptance.",
            "Development-2024/25 frozen residual bands do not guarantee future individual coverage.",
            "DNP is not scored as zero conditional minutes or FP; UNKNOWN is never imputed.",
            "FP here is reconstructed from NBA boxscore under Sports.ru formula, not official user credit.",
            "No model reissue, parameter tuning, live site, private data or transfer backtest.",
        ],
    }


def run():
    read = lambda path: json.loads((DATA/path).read_text(encoding="utf8"))
    report = build(read("conditional_minutes_fp_evaluation_research.json"),
                   read("conditional_minutes_fp_research.json"),
                   datetime.now(timezone.utc))
    target = DATA/"conditional_minutes_robustness_research.json"
    previous = read(target.name) if target.exists() else {}
    if not previous or {k:v for k,v in report.items() if k!="updated_at_utc"} != {
            k:v for k,v in previous.items() if k!="updated_at_utc"}:
        temp=target.with_suffix(".tmp")
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        temp.replace(target)
    return {**report["summary"],"adopt_on_site":False,"research_only":True}

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
