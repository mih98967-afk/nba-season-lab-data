"""Build unchanged day-level features from fresh inputs; no model fit or scoring."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))
OUT = Path(__file__).resolve().parent
SOURCE = OUT / "source"
ASOF = "2026-11-17"
LEADS = (0, 1, 3, 7, 14, 21, 28)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    qa = json.loads((OUT / "SOURCE_QA.json").read_text())
    if qa["status"] != "INTERNAL_COHERENCE_PASS":raise ValueError("SOURCE_QA_FAILED")
    capture = json.loads((OUT / "CAPTURE_SUMMARY.json").read_text())
    upstream = SOURCE / "upstream"
    if not upstream.exists():upstream.symlink_to((BASE / "source/upstream").resolve(), target_is_directory=True)
    if upstream.resolve() != (BASE / "source/upstream").resolve():raise ValueError("UNEXPECTED_HISTORICAL_SOURCE")
    shutil.copyfile(BASE / "source/upstream_manifest.json", SOURCE / "upstream_manifest.json")
    data = SOURCE / "data";data.mkdir(exist_ok=True)
    live_source = ROOT / "research_extension/prospective/current_snapshot/data/live.json"
    shutil.copyfile(live_source, data / "live.json")
    live = json.loads(live_source.read_text())
    # Exact entry copy from the newer captured public live schedule. Wrapper explicitly
    # identifies derivation; it is not relabelled as the older repository schedule file.
    schedule = {"schema_version": 1, "status": "derived_exact_entries_from_public_live_snapshot",
                "updated_at_utc": live.get("updated_at_utc"), "timezone": "UTC",
                "fantasy_timezone": "Europe/Moscow", "games": live["schedule"],
                "source": "public live.json schedule field", "source_file_sha256": sha(live_source),
                "source_schedule_quality": live.get("schedule_quality"),
                "complete": False}
    (data / "schedule.json").write_text(json.dumps(schedule, indent=2) + "\n")
    inputs = {"historical_upstream_manifest_sha256": sha(SOURCE / "upstream_manifest.json"),
              "current_manifest_sha256": sha(SOURCE / "current/manifest.json"),
              "public_live_source_sha256": sha(live_source), "public_live_updated_at_utc": live.get("updated_at_utc"),
              "derived_schedule_sha256": sha(data / "schedule.json"), "utc_schedule_games": len(live["schedule"])}
    code = BASE / "research/match_context"
    if not (code / "run_phase1.py").is_file():
        code = ROOT / "research/match_context"
    sys.path.insert(0, str(code))
    import current_validation as cv
    cv.ASOF_DATE = ASOF
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    d, frameqa = cv.build_current_frame(SOURCE, OUT / "feature_chunks", leads=LEADS)
    d.to_pickle(OUT / "feature_frame.pkl")
    future = d[(d.date.astype(str) >= ASOF) & (d.issue_date.astype(str) == ASOF)].copy().reset_index(drop=True)
    if future.empty:raise ValueError("NO_FUTURE_FEATURE_ROWS")
    if future[["y_play", "y_fp", "y_minutes"]].notna().any().any():raise ValueError("FUTURE_LABELS_PRESENT")
    future = future.drop(columns=["y_play", "y_fp", "y_minutes"])
    future.to_pickle(OUT / "future_feature_frame.pkl")
    report = {"status": "FRESH_DAY_LEVEL_FEATURES_ONLY_NO_FIT_NO_SCORE", "inputs": inputs,
              "started_at_utc": started, "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "availability_verified_by_capture_utc": capture["completed_at_utc"],
              "feature_history_date_rule": "strictly earlier NBA game dates than issue_date",
              "literal_midnight_input_availability_not_claimed": True,
              "asof_date_ET_feature_semantics": ASOF, "lead_days": list(LEADS),
              "full_feature_frame_sha256": sha(OUT / "feature_frame.pkl"), "full_rows": len(d),
              "future_feature_frame_sha256": sha(OUT / "future_feature_frame.pkl"), "future_rows": len(future),
              "future_rows_by_lead": {str(int(k)): int(v) for k, v in future.groupby("horizon_days", observed=True).size().items()},
              "future_games": future.game.nunique(), "future_players": future.pid.nunique(),
              "future_dates": sorted(future.date.astype(str).unique().tolist()),
              "future_labels_removed": True,
              "full_frame_contains_reconstructed_past_outcomes": True,
              "score_or_fit_or_calibration_performed": False, "original_files_changed": False,
              "source_qa": frameqa}
    (OUT / "FEATURE_BUILD_QA.json").write_text(json.dumps(report, indent=2, default=int) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "source_qa"}, indent=2, default=int))


if __name__ == "__main__":main()
