"""Hash-verified materialization of reviewable UTF-8 research asset chunks."""
from __future__ import annotations
import base64
import gzip
import hashlib
import json
from pathlib import Path


def safe_relative(value):
    path=Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("UNSAFE_PACKED_ASSET_PATH")
    return path


def materialize_assets(package,destination,names=None):
    package,destination=Path(package),Path(destination)
    manifest=json.loads((package/"PUBLIC_ASSETS_MANIFEST.json").read_text())
    if manifest.get("schema")!="nba-position-public-assets-v1":
        raise ValueError("PACKED_ASSET_SCHEMA_MISMATCH")
    files=manifest["files"]
    targets=list(files) if names is None else list(names)
    for name in targets:
        relative=safe_relative(name)
        if name not in files:raise ValueError("UNDECLARED_PACKED_ASSET:"+name)
        item=files[name];target=destination/relative
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item["sha256"]:
            continue
        payload=[]
        for part in item["storage"]:
            content=(package/safe_relative(part["path"])).read_bytes()
            if hashlib.sha256(content).hexdigest()!=part["sha256"]:
                raise ValueError("PACKED_CHUNK_HASH_MISMATCH:"+part["path"])
            payload.append(content)
        if item["encoding"]=="plain":
            data=b"".join(payload)
        elif item["encoding"] in ("base64","gzip+base64"):
            encoded=b"".join(p.strip() for p in payload)
            data=base64.b64decode(encoded,validate=True)
            if item["encoding"]=="gzip+base64":data=gzip.decompress(data)
        else:raise ValueError("UNSUPPORTED_PACKED_ENCODING")
        if len(data)!=item["size_bytes"] or hashlib.sha256(data).hexdigest()!=item["sha256"]:
            raise ValueError("PACKED_ASSET_HASH_MISMATCH:"+name)
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+".verified_tmp")
        temporary.write_bytes(data);temporary.replace(target)
    return destination
