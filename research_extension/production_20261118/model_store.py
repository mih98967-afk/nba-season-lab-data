"""Hash-pinned, bounded assembler for trusted repository model payloads.

The browser never loads these weights. Only the pinned Actions Python environment
unpickles original locally trained models after checking a code-pinned SHA256.
"""
from __future__ import annotations
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pickle
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
KNOWN_MODELS = {
    "near_latest": "70d288d753184916f354e3916016c7c6b0907da32bfcbf92ddcdcb22fb536c25",
    "long_latest": "ee2fc118be2de60dd118cc5227ef519e699e3ed640b25a83816ba8e198140ea9",
    "day_ewma_shadow": "a76fdf1dc1d6d53a7abb008bc386f43dac942ce4aa1996cbf721635dd71c2012",
}
MAX_MODEL_BYTES = 12_000_000
MAX_CHUNK_BYTES = 60_001


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def add_research_path():
    base = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))
    choices = [Path(os.environ["NBA_RESEARCH_CODE"])] if "NBA_RESEARCH_CODE" in os.environ else []
    choices += [ROOT / "research/match_context", base / "research/match_context"]
    for path in choices:
        if (path / "infer_near.py").is_file():
            if str(path) not in sys.path:sys.path.insert(0, str(path))
            return path
    raise FileNotFoundError("PRESERVED_RESEARCH_CODE_NOT_FOUND")


def load_manifest(directory=HERE / "models"):
    path = Path(directory) / "MANIFEST.json"
    raw = path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("schema") != "nba_trusted_frozen_model_chunks_v1":
        raise ValueError("UNSUPPORTED_MODEL_MANIFEST")
    return manifest, sha256(raw)


def assemble_model_bytes(model_id, directory=HERE / "models"):
    if model_id not in KNOWN_MODELS:raise ValueError("UNKNOWN_TRUSTED_MODEL")
    directory = Path(directory)
    manifest, _ = load_manifest(directory)
    item = manifest["models"][model_id]
    if item["raw_sha256"] != KNOWN_MODELS[model_id]:raise ValueError("UNTRUSTED_MODEL_DIGEST")
    if not 0 < item["raw_bytes"] <= MAX_MODEL_BYTES:raise ValueError("MODEL_SIZE_LIMIT")
    chunks = []
    for entry in item["chunks"]:
        name = entry["file"]
        if Path(name).name != name or not name.startswith(model_id + "."):
            raise ValueError("MODEL_CHUNK_PATH_REJECTED")
        blob = (directory / name).read_bytes()
        if len(blob) != entry["bytes"] or len(blob) > MAX_CHUNK_BYTES or sha256(blob) != entry["sha256"]:
            raise ValueError("MODEL_CHUNK_HASH_MISMATCH")
        chunks.append(blob.strip())
    compressed = base64.b64decode(b"".join(chunks), validate=True)
    if len(compressed) != item["gzip_bytes"] or sha256(compressed) != item["gzip_sha256"]:
        raise ValueError("COMPRESSED_MODEL_HASH_MISMATCH")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as f:
        raw = f.read(MAX_MODEL_BYTES + 1)
    if len(raw) != item["raw_bytes"] or sha256(raw) != KNOWN_MODELS[model_id]:
        raise ValueError("MODEL_HASH_MISMATCH")
    return raw


def load_model(model_id, directory=HERE / "models"):
    add_research_path()
    return pickle.loads(assemble_model_bytes(model_id, directory))
