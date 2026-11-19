"""Rebuild the retained historical feature contract without changing source bytes."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base")).resolve()
CODE = ORIGINAL / "research/match_context"
if not (CODE / "run_phase1.py").is_file():
    CODE = ROOT / "research/match_context"
sys.path.insert(0, str(CODE))
import run_phase1 as base
from availability import load_sources, injury_index, injury_features

def main():
    start = time.time()
    out = Path(__file__).resolve().parent
    source = ORIGINAL / "source"
    games, raw, source_qa = load_sources(source)
    games.to_pickle(out / "games.pkl")
    raw.to_pickle(out / "raw.pkl")
    print(f"Loaded {len(games)} games, {len(raw)} source rows", flush=True)
    frame, feature_qa = base.build_frame(games, raw)
    print(f"Built {len(frame)} feature rows", flush=True)
    index, injury_qa = injury_index(source, games)
    frame = injury_features(frame, index)
    frame.to_pickle(out / "feature_frame.pkl")
    sources = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (source / "upstream").iterdir() if p.is_file()}
    code = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in CODE.glob("*.py")}
    qa = {"source_qa": source_qa, "feature_qa": feature_qa,
          "injury_qa": injury_qa, "source_sha256": sources, "original_code_sha256": code,
          "feature_frame_sha256": hashlib.sha256((out / "feature_frame.pkl").read_bytes()).hexdigest(),
          "rows": len(frame), "columns": len(frame.columns), "seconds": time.time() - start,
          "no_2026_27_inputs": True, "source_vintage": "retrospective_archive"}
    base.write_json(out / "feature_qa.json", qa)
    print(json.dumps({k: qa[k] for k in ("rows", "columns", "seconds", "feature_frame_sha256")}), flush=True)

if __name__ == "__main__":
    main()
