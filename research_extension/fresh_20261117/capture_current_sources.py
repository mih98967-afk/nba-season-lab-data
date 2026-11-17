"""Bounded read-only snapshot using the preserved four-source collector."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))
CODE = BASE / "research/match_context"
if not (CODE / "run_phase1.py").is_file():
    CODE = ROOT / "research/match_context"
sys.path.insert(0, str(CODE))
from collect_sources import collect

out = Path(__file__).resolve().parent
current = out / "source/current"
started = dt.datetime.now(dt.timezone.utc).isoformat()
manifest = collect((2027,), current)
(current / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
summary = {
    "started_at_utc": started,
    "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    "collector_sha256": hashlib.sha256((CODE / "collect_sources.py").read_bytes()).hexdigest(),
    "expected_sources": 4,
    "retrieved_sources": sum(r["status"] == "retrieved" for r in manifest),
    "manifest": manifest,
    "original_sources_modified": False,
    "training_or_selection_performed": False,
    "atomic_upstream_snapshot_guaranteed": False,
}
(out / "CAPTURE_SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
