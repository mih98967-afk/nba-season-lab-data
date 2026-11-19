"""Independent read-only gate for conditional minutes before any NBA Season Lab UI promotion.

Inputs are *genuinely issued* paired current-season research snapshots. This
script never trains, reissues, changes predictions, publishes data or infers
DNP from a missing boxscore. It creates a compact, reviewable evidence report.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import statistics

EXPECTED_STATUS = "research_only_not_deployed"
BOOTSTRAP_SEED = 20261119
RESAMPLES = 1200


def instant(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Missing original UTC timezone")
    return stamp.astimezone(timezone.utc)


def number(value):
    if type(value) not in (float, int) or not -1000 <= value <= 1000:
        raise ValueError("Non-finite or implausible signed measurement")
    return float(value)


def key(row):
    game, player = row.get("game_id"), row.get("player_id")
    if not isinstance(game, str) or not isinstance(player, str) or not game or not player:
        raise ValueError("Missing exact player-game identity")
    return (game, player)


def audit(shadow, baseline, robustness=None):
    if any(x.get("status") != EXPECTED_STATUS or x.get("adopt_on_site") is not False
           for x in (shadow, baseline)):
        raise ValueError("Unreviewed minutes model requested for production")
    if shadow.get("quality_gate", {}).get("adopt_on_site") is not False:
        raise ValueError("Frozen research safety gate was altered")
    if shadow.get("source_frozen_minutes_issue_sha256") != baseline.get("frozen_minutes_issue_sha256"):
        raise ValueError("Minute baseline evidence source mismatch")
    issued = shadow.get("issued")
    observed = shadow.get("observed")
    if not isinstance(issued, list) or not isinstance(observed, list):
        raise ValueError("Paired current-season issue/outcome sets required")
    index = {}
    for row in issued:
        k = key(row)
        if k in index:
            raise ValueError("Duplicate immutable issued minute forecast")
        if not (instant(row["original_minutes_issued_at_utc"])
                <= instant(row["challenger_issued_at_utc"])
                < instant(row["individual_lock_utc"])
                < instant(row["game_utc"])):
            raise ValueError("Minutes research issue was not genuinely before lock")
        if row.get("source_all_current_minutes_first_seen_pre_issue") is not True:
            raise ValueError("Prospective feature-time proof missing")
        if (not 0 <= number(row["baseline_minutes"]) <= 48
                or not 0 <= number(row["challenger_minutes"]) <= 48):
            raise ValueError("Invalid conditional minutes projection")
        index[k] = row
    group = defaultdict(list)
    seen = set()
    diffs, baseline_errors, challenger_errors, baseline_signed, challenger_signed = [], [], [], [], []
    for row in observed:
        k = key(row)
        if k not in index or k in seen:
            raise ValueError("Orphan/duplicate independently observed outcome")
        seen.add(k)
        issue = index[k]
        if row.get("team") != issue.get("team") or row.get("game_utc") != issue.get("game_utc"):
            raise ValueError("Observed player-game identity/club differs from issued forecast")
        if instant(row["postgame_first_seen_at_utc"]) <= instant(issue["game_utc"]):
            raise ValueError("Outcome first seen before game tipoff")
        if instant(row["postgame_first_seen_at_utc"]) <= instant(issue["challenger_issued_at_utc"]):
            raise ValueError("Postgame result used before prospective issuance")
        actual = number(row["actual_minutes"])
        if not 0 < actual <= 70:
            raise ValueError("Only verified positive-minute appearances are scored")
        base = number(issue["baseline_minutes"])
        candidate = number(issue["challenger_minutes"])
        g = abs(base-actual)-abs(candidate-actual)
        if not isinstance(row.get("et_date"), str) or len(row["et_date"]) != 10:
            raise ValueError("Missing scored NBA ET date")
        group[row["et_date"]].append(g)
        diffs.append(g)
        baseline_errors.append(abs(base-actual))
        challenger_errors.append(abs(candidate-actual))
        baseline_signed.append(base-actual)
        challenger_signed.append(candidate-actual)

    summary = shadow.get("summary") or {}
    n = len(observed)
    dnp = summary.get("literal_DNP_excluded", -1)
    unknown = summary.get("UNKNOWN_not_imputed", -1)
    awaiting = summary.get("awaiting_or_unchecked", -1)
    if any(type(v) is not int or v < 0 for v in (dnp, unknown, awaiting)):
        raise ValueError("Invalid nonplayed/unknown denominators")
    if len(issued) != n + dnp + unknown + awaiting:
        raise ValueError("Frozen issue denominator does not reconcile")
    if summary.get("issued_total") != len(issued) or summary.get("played_verified") != n:
        raise ValueError("Published prospective issue summary differs from original rows")

    mean = lambda values: sum(values)/len(values) if values else None
    effect = mean(diffs)
    ci = None
    if len(group) >= 8 and n >= 100:
        rng = random.Random(BOOTSTRAP_SEED)
        dates = sorted(group)
        results = []
        for _ in range(RESAMPLES):
            sampled = [rng.choice(dates) for __ in dates]
            errors = [g for date in sampled for g in group[date]]
            results.append(sum(errors)/len(errors))
        results.sort()
        ci = [round(results[int(0.025*(RESAMPLES-1))], 4),
              round(results[int(0.975*(RESAMPLES-1))], 4)]

    if robustness:
        if robustness.get("adopt_on_site") is not False:
            raise ValueError("Related robustness report wrongly promoted")
        if robustness.get("summary", {}).get("frozen_issues_total") != len(issued):
            raise ValueError("Robustness report built from a different minute cohort")

    return {
        "schema": "nba_conditional_minutes_promotion_gate_v623",
        "status": "PASS_RESEARCH_ONLY_NO_PROMOTION",
        "original_research_status": EXPECTED_STATUS,
        "frozen_source_sha256": shadow["source_frozen_minutes_issue_sha256"],
        "sample": {
            "issued": len(issued),
            "verified_played": n,
            "verified_explicit_DNP_excluded": dnp,
            "UNKNOWN_not_imputed": unknown,
            "awaiting": awaiting,
            "distinct_scored_ET_dates": len(group),
            "distinct_scored_NBA_games": len({r["game_id"] for r in observed}),
        },
        "conditional_minutes_on_verified_played_ONLY": {
            "original_frozen_minutes_MAE": round(mean(baseline_errors), 4) if n else None,
            "same_season_challenger_MAE": round(mean(challenger_errors), 4) if n else None,
            "MAE_gain_positive_favors_challenger": round(effect, 4) if n else None,
            "original_prediction_minus_actual_bias": round(mean(baseline_signed), 4) if n else None,
            "challenger_prediction_minus_actual_bias": round(mean(challenger_signed), 4) if n else None,
            "exploratory_95pct_ET_date_cluster_interval_gain": ci,
            "bootstrap_dates_not_player_rows": True,
        },
        "release_gate": {
            "eligible_for_scientific_review": len(group)>=8 and n>=100,
            "full_fantasy_population_coverage_proven": False,
            "independent_model_selection_after_2026_27_outcomes": False,
            "individual_minute_intervals_calibrated": False,
            "optimizer_value_proven": False,
            "promote_as_expected_minutes_on_site": False,
            "change_FPs_or_P_play": False,
        },
        "decision": (
            "Do not display this research challenger as an adopted per-game expected-minutes "
            "forecast. Its verified played-only error is descriptive. Continue independent "
            "genuine prelock observation and an explicit preregistered acceptance gate."
        ),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    def read(n):
        return json.loads((a.data_root/n).read_text(encoding="utf-8"))
    result = audit(read("current_season_minutes_shadow_research.json"),
                   read("conditional_minutes_fp_evaluation_research.json"),
                   read("conditional_minutes_robustness_research.json"))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n",encoding="utf8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
