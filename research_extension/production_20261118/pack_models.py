"""One-time lossless packaging; no fit, no model mutation, no network."""
import argparse
import base64
import gzip
import json
from pathlib import Path
from model_store import KNOWN_MODELS, sha256


def pack(paths, output):
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema": "nba_trusted_frozen_model_chunks_v1", "encoding": "gzip_mtime0_base64_ascii_chunks",
                "chunk_payload_bytes_max": 60000, "training_current_season_used": False, "models": {}}
    for model_id, path in paths.items():
        raw = Path(path).read_bytes()
        if sha256(raw) != KNOWN_MODELS[model_id]:raise ValueError("ORIGINAL_MODEL_HASH_MISMATCH")
        zipped = gzip.compress(raw, compresslevel=9, mtime=0)
        encoded = base64.b64encode(zipped)
        chunks = []
        for n, pos in enumerate(range(0, len(encoded), 60000)):
            name = f"{model_id}.{n:03}.b64"
            blob = encoded[pos:pos + 60000] + b"\n"
            (output / name).write_bytes(blob)
            chunks.append({"file": name, "bytes": len(blob), "sha256": sha256(blob)})
        manifest["models"][model_id] = {"raw_bytes": len(raw), "raw_sha256": sha256(raw),
            "gzip_bytes": len(zipped), "gzip_sha256": sha256(zipped), "chunks": chunks,
            "role": "mean_only_shadow" if model_id == "day_ewma_shadow" else "frozen_fp_pplay_distribution"}
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {k: {x:v for x,v in m.items() if x != "chunks"} | {"chunks": len(m["chunks"])} for k,m in manifest["models"].items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser();p.add_argument("--base", type=Path, required=True)
    p.add_argument("--recency", type=Path, required=True);p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(pack({"near_latest": a.base / "results_near_latest/research_models.pkl",
                           "long_latest": a.base / "results_latest/research_models.pkl",
                           "day_ewma_shadow": a.recency}, a.out), indent=2))
