"""Read-only progress report for frozen 21 Nov–8 Dec NBA minutes study.

Original preregistered evaluator remains authoritative. No model training,
personal data, backfill, fantasy credits, adoption, or deployment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.evaluate_minutes_prereg_v623 import evaluate, key, utc

NBA_ET = ZoneInfo("America/New_York")


def report(shadow, contract, source_sha256="", contract_sha256=""):
    original = evaluate(shadow, contract)
    start = utc(contract["start_inclusive_utc"])
    end = utc(contract["end_exclusive_utc"])
    selected = {key(r): r for r in shadow["issued"]
                if start <= utc(r["challenger_issued_at_utc"]) < end}

    played = []
    for row in shadow["observed"]:
        issue = selected.get(key(row))
        if issue is None:
            continue
        expected_date = utc(issue["game_utc"]).astimezone(NBA_ET).date().isoformat()
        if row.get("et_date") != expected_date:
            raise ValueError("NBA ET date disagrees with genuine game_utc")
        played.append(row)

    actual = {"ET_dates": len({r["et_date"] for r in played}),
              "NBA_games": len({r["game_id"] for r in played}),
              "positive_minute_pairs": len(played)}
    cohort = original["cohort"]
    if (len(selected), actual["positive_minute_pairs"], actual["NBA_games"],
        actual["ET_dates"]) != (
        cohort["issued"], cohort["verified_played"], cohort["NBA_games"],
        cohort["ET_dates"]):
        raise ValueError("Cohort differs from original frozen evaluator")

    snapshot_at = shadow.get("updated_at_utc")
    if snapshot_at is not None:
        updated = utc(snapshot_at)
        if any(utc(r["postgame_first_seen_at_utc"]) > updated for r in played):
            raise ValueError("Observed outcome first seen after source snapshot")
    if original["site_adoption_allowed"] is not False or original["change_FP_or_P_play_allowed"] is not False:
        raise ValueError("Read-only research admission restrictions altered")
    thresholds = contract["thresholds"]
    progress = {k: {"actual": actual[k], "preregistered_minimum": thresholds[k],
                    "remaining": max(0, thresholds[k]-actual[k]),
                    "met": actual[k]>=thresholds[k]}
                for k in ("ET_dates", "NBA_games", "positive_minute_pairs")}
    return {
        "schema": "nba_minutes_future_readonly_progress_v628",
        "status": original["status"],
        "source_updated_at_utc": snapshot_at,
        "study_window_utc": [contract["start_inclusive_utc"], contract["end_exclusive_utc"]],
        "frozen_model_sha256": contract["model_sha256"],
        "source_blob_sha256": source_sha256,
        "contract_blob_sha256": contract_sha256,
        "cohort": cohort,
        "preregistered_progress": progress,
        "unscored_issued_cases_not_assumed_DNP": len(selected)-len(played),
        "scored_ET_dates": sorted({r["et_date"] for r in played}),
        "paired_minutes": original["conditional_played_only"],
        "bootstrap95_only_after_predeclared_gates": original["ET_date_bootstrap95"],
        "subgroups": {
            "by_frozen_predicted_minutes_group": original["per_baseline_minutes_group"],
            "by_prior_verified_played_games": original["per_previous_played_n"]},
        "limits": {
            "independent_window_for_replication_not_new_parameter_selection": True,
            "positive_minutes_only_selected_cohort": True,
            "unscored_cannot_be_imputed_as_DNP_or_zero": True,
            "personal_account_or_credits_used": False,
            "new_weights_trained": False, "adopt_on_site": False,
            "change_FP_or_P_play": False,
            "individual_minute_intervals_certified": False,
            "fantasy_KEEPNOWLATER_economics_validated": False},
        "interpretation": (
            "A prospective played-only comparison on a selected cohort does not establish "
            "representative P(play), DNP labels, unconditional FP, or Sports.ru transfer gains.")
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--contract", type=Path,
                        default=Path("docs/NBA_MINUTES_FUTURE_PREREG_20261120.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_bytes = (args.data_root/"current_season_minutes_shadow_research.json").read_bytes()
    contract_bytes = args.contract.read_bytes()
    result = report(json.loads(source_bytes), json.loads(contract_bytes),
                    hashlib.sha256(source_bytes).hexdigest(),
                    hashlib.sha256(contract_bytes).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "cohort": result["cohort"],
                      "progress": result["preregistered_progress"],
                      "adopt_on_site": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
