"""Genuine prelock 2026/27 FP-per-minute AB test, research-only.

Follow the *first real* current-season minutes challenger issue in the same
single-writer main sync. Freeze FP/minute from 3-5 audited prior current-season
played boxscores whose archived first-seen timestamps precede the ORIGINAL
baseline issue. No historical/backdated prospective issuances, no implicit
DNP or zero FP, no calibrated P(play), no site adoption or transfers.
Historical PR #116 motivated these frozen variants; 2025/26 was NOT pristine.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite, sqrt
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp
from src.current_season_minutes_shadow_research import (
    MODEL_HASH as MINUTES_MODEL_HASH, STATUS, unique,
)

RATE_FIELDS = (
    "frozen_previous_season_FP",
    "updated_minutes_frozen_rate_FP",
    "frozen_minutes_shrunk_current_rate_5_FP",
    "updated_minutes_shrunk_current_rate_5_FP",
    "updated_minutes_shrunk_current_rate_10_FP",
    "updated_minutes_current_rate_only_FP",
)
CONTROL = "updated_minutes_frozen_rate_FP"
MODEL = {
    "name": "prospective_prelock_2026_27_current_rate_ablation_v1",
    "rate_prior_strength_games": (5, 10),
    "models_compared": RATE_FIELDS,
    "comparison_vs": CONTROL,
    "max_original_to_rate_issue_lag_seconds": 1200,
    "original_and_minutes_issues_must_be_prelock": True,
    "prior_positive_minutes_observed_by_original_issue": True,
    "posthoc_selected_on_historical_2024_25_2025_26_not_preregistered_in_2026": True,
    "unconditional_fp_allowed": False,
    "no_missing_to_negative_label": True,
    "adopt_on_site": False,
}
MODEL_HASH = canonical_hash(MODEL)


def finite(x, low=-1e12, high=1e12):
    if type(x) not in (int, float) or not isfinite(x) or not low <= x <= high:
        raise ValueError("Invalid/nonfinite FP-minute research input")
    return float(x)


def key_of(row):
    return row["game_id"], row["player_id"]


def source_fp_rows(minute_issue, live, rolling, original):
    """Re-join exact frozen minutes sample to official prior positive FP."""
    sample = minute_issue.get("source_played_rows_known_at_issue")
    if (not isinstance(sample, list) or not 3 <= len(sample) <= 5
            or len(sample) != minute_issue.get("current_same_team_played_n")
            or minute_issue.get("source_asof_sha256") != canonical_hash(sample)):
        raise ValueError("Unverified frozen current-season minutes sample")
    wanted = {(r["game_id"], minute_issue["player_id"]) for r in sample}
    if len(wanted) != len(sample):
        raise ValueError("Repeated sample game")
    matches = {}
    for row in live.get("rows", []):
        key = (row.get("game_id"), row.get("id"))
        if key in wanted:
            if key in matches:
                raise ValueError("Duplicate official boxscore player-game")
            matches[key] = row
    if len(matches) != len(sample):
        raise ValueError("Archived preissue game has no public FP boxscore")
    finals = {
        g["id"]: g for g in live.get("games", [])
        if isinstance(g, dict) and g.get("status") == "final"
    }
    if len(finals) != sum(isinstance(g, dict) and g.get("status") == "final"
                          for g in live.get("games", [])):
        raise ValueError("Duplicate final NBA fixture")
    first = rolling.get("row_first_seen_at_utc")
    hashes = rolling.get("row_hashes")
    if not isinstance(first, dict) or not isinstance(hashes, dict):
        raise ValueError("No audited first-observed row hash/clock")
    observed = []
    last_utc = None
    for item in sample:
        gid, pid = item["game_id"], minute_issue["player_id"]
        row = matches[gid, pid]
        game = finals.get(gid)
        tip = instant(item["game_utc"])
        seen = instant(item["first_seen_at_utc"])
        if (game is None or instant(game["utc"]) != tip
                or row.get("utc") != game["utc"]
                or row.get("played") is not True
                or row.get("team") != minute_issue["team"]
                or row.get("team") not in (game.get("home"), game.get("away"))
                or tip >= original or seen < tip or seen > original
                or first.get(f"{gid}|{pid}") != stamp(seen)):
            raise ValueError("FP row has no genuine pre-baseline game/clock/club evidence")
        minutes = finite(row.get("minutes"), 0.00001, 70)
        fp = finite(row.get("fp"), -150, 250)
        if minutes != finite(item["minutes"], 0.00001, 70):
            raise ValueError("Current public minutes differ from original frozen minutes")
        audited = {
            "game_id": gid, "player_id": pid,
            "team": row["team"], "fp": row["fp"],
            "minutes": row["minutes"], "utc": stamp(tip),
        }
        if hashes.get(f"{gid}|{pid}") != canonical_hash(audited):
            raise ValueError("Current FP row not reconciled to rolling observation ledger")
        if last_utc is not None and tip < last_utc:
            raise ValueError("Frozen prior sample is not in game order")
        last_utc = tip
        observed.append({
            "game_id": gid, "first_seen_at_utc": stamp(seen),
            "tipoff_utc": stamp(tip), "team": row["team"],
            "minutes": minutes, "reconstructed_FP": fp,
            "source_row_sha256": hashes[f"{gid}|{pid}"],
        })
    return observed


def freeze(minute_issue, sample, now):
    original = instant(minute_issue["original_minutes_issued_at_utc"])
    minutes_at = instant(minute_issue["challenger_issued_at_utc"])
    tip, lock = [instant(minute_issue[k]) for k in ("game_utc", "individual_lock_utc")]
    if (not original <= minutes_at <= now < lock
            or (tip-lock).total_seconds() != 1800
            or not 0 <= (now-original).total_seconds() <=
                MODEL["max_original_to_rate_issue_lag_seconds"]):
        raise ValueError("Cannot invent/backdate postlock FP-rate predictions")
    n = len(sample)
    old_rate = finite(minute_issue["historical_rate_used_unchanged"], -100, 100)
    old_min = finite(minute_issue["baseline_minutes"], 0, 70)
    current_min = finite(minute_issue["challenger_minutes"], 0, 70)
    old_fp = finite(minute_issue["baseline_decomposed_fp"])
    minute_fp = finite(minute_issue["challenger_decomposed_fp"])
    minutes = sum(r["minutes"] for r in sample)
    if minutes <= 0:
        raise ValueError("Missing verified positive-minute exposure")
    current_rate = sum(r["reconstructed_FP"] for r in sample) / minutes
    def blended(prior):
        return (prior*old_rate+n*current_rate)/(prior+n)
    variants = {
        RATE_FIELDS[0]: old_fp,
        RATE_FIELDS[1]: minute_fp,
        RATE_FIELDS[2]: round(old_min*blended(5), 5),
        RATE_FIELDS[3]: round(current_min*blended(5), 5),
        RATE_FIELDS[4]: round(current_min*blended(10), 5),
        RATE_FIELDS[5]: round(current_min*current_rate, 5),
    }
    if abs(minute_fp - current_min*old_rate) > 0.0001:
        raise ValueError("Minute-only control does not match frozen baseline")
    for val in variants.values():
        finite(val, -500, 500)
    return {
        "game_id": minute_issue["game_id"],
        "player_id": minute_issue["player_id"],
        "team": minute_issue["team"],
        "game_utc": minute_issue["game_utc"],
        "individual_lock_utc": minute_issue["individual_lock_utc"],
        "original_minutes_issued_at_utc": stamp(original),
        "minutes_challenger_issued_at_utc": stamp(minutes_at),
        "fp_rate_issued_at_utc": stamp(now),
        "source_minutes_challenger_sha256": canonical_hash(minute_issue),
        "source_minutes_model_sha256": MINUTES_MODEL_HASH,
        "model_sha256": MODEL_HASH,
        "source_previous_played_rows": sample,
        "source_asof_sha256": canonical_hash(sample),
        "source_sample_n": n,
        "old_fp_per_minute": old_rate,
        "current_fp_per_minute": round(current_rate, 8),
        "FP_variants_frozen_prelock": variants,
        "forecast_type": "conditional_on_verified_positive_minutes_NOT_unconditional",
        "outcome_at_issue": "UNKNOWN",
        "adopt_on_site": False,
    }


def variant_metrics(outcomes):
    if not outcomes:
        return {"played_scored": 0}
    count = len(outcomes)
    control = CONTROL
    result = {"played_scored": count}
    for variant in RATE_FIELDS:
        error = [
            finite(row["FP_variants_frozen_prelock"][variant]) -
            finite(row["actual_fp_reconstructed"]) for row in outcomes
        ]
        ctrl = [
            abs(finite(row["FP_variants_frozen_prelock"][control]) -
                finite(row["actual_fp_reconstructed"])) for row in outcomes
        ]
        result[variant] = {
            "MAE": round(sum(abs(e) for e in error)/count, 4),
            "RMSE": round(sqrt(sum(e*e for e in error)/count), 4),
            "prediction_minus_actual_bias": round(sum(error)/count, 4),
            "MAE_gain_over_minutes_only_positive_is_better": round(
                sum(c-abs(e) for c,e in zip(ctrl,error))/count, 4),
        }
    return result


def build(previous, minutes, frozen, evaluation, live, rolling, now):
    if now.utcoffset() is None:
        raise ValueError("FP-rate research requires a timezone-aware clock")
    now = now.astimezone(timezone.utc)
    if (minutes.get("schema_version") != 1 or minutes.get("status") != STATUS
            or minutes.get("adopt_on_site") is not False
            or minutes.get("model_sha256") != MINUTES_MODEL_HASH
            or frozen.get("status") != STATUS
            or frozen.get("adopt_on_site") is not False
            or evaluation.get("status") != STATUS
            or evaluation.get("adopt_on_site") is not False
            or live.get("schema_version") != 4
            or rolling.get("schema_version") != 1
            or rolling.get("adopt_on_site") is not False):
        raise ValueError("Research-only cohort/source provenance mismatch")
    frozen_issues = unique(frozen.get("issued"), "frozen original issues")
    if (minutes.get("source_frozen_minutes_issue_sha256") != canonical_hash(frozen["issued"])
            or evaluation.get("frozen_minutes_issue_sha256") !=
                minutes["source_frozen_minutes_issue_sha256"]):
        raise ValueError("Minutes/evaluation original provenance diverged")
    min_issue = unique(minutes.get("issued"), "verified minute challenger issues")
    if not set(min_issue).issubset(frozen_issues):
        raise ValueError("Orphan minutes challenger")
    min_observed = unique(minutes.get("observed"), "verified minute challenger played results")
    if not set(min_observed).issubset(min_issue):
        raise ValueError("Observed minutes not in original issued cohort")
    seen_dnp = unique(evaluation.get("explicit_DNP_not_in_conditional_metrics", []),
                      "verified literal DNP")
    seen_unknown = unique(evaluation.get("UNKNOWN_unscored", []), "UNKNOWN outcomes")
    if (set(min_observed)&set(seen_dnp) or set(min_observed)&set(seen_unknown)
            or set(seen_dnp)&set(seen_unknown)):
        raise ValueError("Overlapping historical outcome classes")
    if previous:
        if (previous.get("schema_version") != 1
                or previous.get("status") != STATUS
                or previous.get("model_sha256") != MODEL_HASH
                or previous.get("adopt_on_site") is not False):
            raise ValueError("FP-rate frozen experiment was modified/deployed")
    issued = unique((previous or {}).get("issued", []), "archived FP-rate issues")
    observed = unique((previous or {}).get("observed", []), "archived FP-rate outcomes")
    if not set(observed).issubset(issued):
        raise ValueError("Orphan FP-rate outcome")
    for key, item in issued.items():
        minute = min_issue.get(key)
        if (minute is None or item.get("source_minutes_challenger_sha256") !=
                canonical_hash(minute) or item.get("model_sha256") != MODEL_HASH
                or item.get("source_minutes_model_sha256") != MINUTES_MODEL_HASH
                or item.get("adopt_on_site") is not False
                or item.get("source_asof_sha256") != canonical_hash(
                    item.get("source_previous_played_rows"))):
            raise ValueError("Previously issued FP-rate forecast lost immutable provenance")
        at = instant(item["fp_rate_issued_at_utc"])
        original = instant(item["original_minutes_issued_at_utc"])
        lock = instant(item["individual_lock_utc"])
        if (at < instant(minute["challenger_issued_at_utc"]) or
                at >= lock or at < original or
                (at-original).total_seconds() >
                MODEL["max_original_to_rate_issue_lag_seconds"]):
            raise ValueError("Archived FP forecast backdated or after lock")
    qa = Counter()
    for key, minute in sorted(min_issue.items()):
        if key in issued:
            qa["existing_immutable"] += 1
            continue
        original = instant(minute["original_minutes_issued_at_utc"])
        m_issued = instant(minute["challenger_issued_at_utc"])
        lock = instant(minute["individual_lock_utc"])
        if not original <= m_issued <= now < lock:
            qa["not_current_prelock_minutes_issue"] += 1
            continue
        if (now-original).total_seconds() > MODEL["max_original_to_rate_issue_lag_seconds"]:
            qa["stale_original_issuance_no_retrospective_backfill"] += 1
            continue
        sample = source_fp_rows(minute, live, rolling, original)
        new_item = freeze(minute, sample, now)
        issued[key] = new_item
        qa["new_genuine_FP_rate_issues"] += 1
    for key, minu_outcome in sorted(min_observed.items()):
        item = issued.get(key)
        if item is None:
            continue
        seen = instant(minu_outcome["postgame_first_seen_at_utc"])
        tip = instant(item["game_utc"])
        if (seen <= tip or seen > now or
                seen < instant(item["fp_rate_issued_at_utc"]) or
                minu_outcome["team"] != item["team"]):
            raise ValueError("Outcome was not independently verified after the issue")
        outcome = {
            "game_id": key[0], "player_id": key[1],
            "et_date": minu_outcome["et_date"],
            "position": minu_outcome["position"],
            "team": item["team"],
            "postgame_first_seen_at_utc": stamp(seen),
            "actual_minutes": finite(minu_outcome["actual_minutes"], 0.00001, 70),
            "actual_fp_reconstructed": finite(
                minu_outcome["actual_fp_reconstructed"], -150, 250),
            "source_minutes_verified_outcome_sha256": canonical_hash(minu_outcome),
            "FP_variants_frozen_prelock": item["FP_variants_frozen_prelock"],
        }
        if key in observed and observed[key] != outcome:
            raise ValueError("Archived FP-rate paired outcome has changed")
        observed[key] = outcome
    if not set(observed).issubset(min_observed):
        raise ValueError("Previously observed positive FP row disappeared")
    keys = set(issued)
    if not set(observed).issubset(keys):
        raise ValueError("Outcome outside original eligible issues")
    n_dnp = len(keys & set(seen_dnp))
    n_unknown = len(keys & set(seen_unknown))
    n_pending = len(keys)-len(observed)-n_dnp-n_unknown
    if n_pending < 0:
        raise ValueError("FP-rate issue denominator drift")
    all_issued = sorted(issued.values(),key=lambda x:(x["game_utc"],x["game_id"],x["player_id"]))
    all_outcomes = sorted(observed.values(),key=lambda x:(x["et_date"],x["game_id"],x["player_id"]))
    dates = defaultdict(list)
    for item in all_outcomes:
        dates[item["et_date"]].append(item)
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "model_sha256": MODEL_HASH, "frozen_comparison_design": MODEL,
        "source_minutes_model_sha256": MINUTES_MODEL_HASH,
        "issued": all_issued, "observed": all_outcomes,
        "summary": {
            "issued_total": len(all_issued),
            "new_issued_this_run": qa["new_genuine_FP_rate_issues"],
            "played_verified": len(all_outcomes),
            "literal_DNP_not_scored": n_dnp,
            "UNKNOWN_not_imputed": n_unknown,
            "awaiting_or_unchecked": n_pending,
            "distinct_scored_ET_dates": len(dates),
            "distinct_scored_games": len({x["game_id"] for x in all_outcomes}),
        },
        "issue_QA": dict(qa),
        "played_only_paired_metrics": variant_metrics(all_outcomes),
        "by_ET_date": {k:variant_metrics(v) for k,v in sorted(dates.items())},
        "quality_gate": {
            "independent_ET_dates_at_least_8": len(dates) >= 8,
            "played_scored_at_least_100": len(all_outcomes) >= 100,
            "NBA_games_scored_at_least_24":
                len({x["game_id"] for x in all_outcomes}) >= 24,
            "rate_weights_chosen_before_2026_27_outcomes": False,
            "historical_2025_26_pristine_holdout": False,
            "selected_played_only_not_full_fantasy_population": True,
            "calibrated_unconditional_FP_allowed": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "Historical 2024/25-2025/26 motivated the variants; not prespecified at season start.",
            "Original frozen baseline and current-season minutes issue must be genuinely prelock.",
            "Current FP/minute uses only real positive boxscore rows first observed BEFORE original baseline issue.",
            "Original-source FP values are frozen at issue; later edits cannot retroactively change them.",
            "Research compares only independently verified played rows, not true population P(play).",
            "Literal DNP/UNKNOWN outcomes are counted, not scored as zero or negatives.",
            "Multiple player forecasts within an ET date are correlated; apparent gains on few dates are not proof.",
            "No trained site weights, Firebase, account prices, transfers, or personal data.",
        ],
    }


def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    dest = DATA/"current_season_fp_rate_shadow_research.json"
    prior = read(dest.name) if dest.exists() else {}
    output = build(
        prior, read("current_season_minutes_shadow_research.json"),
        read("conditional_minutes_fp_research.json"),
        read("conditional_minutes_fp_evaluation_research.json"),
        read("live.json"), read("rolling_decision_research.json"),
        datetime.now(timezone.utc),
    )
    if (not prior or {k:v for k,v in output.items() if k!="updated_at_utc"} !=
            {k:v for k,v in prior.items() if k!="updated_at_utc"}):
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
        tmp.replace(dest)
    return {"summary":output["summary"],"research_only":True,"adopt_on_site":False}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
