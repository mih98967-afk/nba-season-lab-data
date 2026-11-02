#!/usr/bin/env python3
"""Recover exact public Hosting v6.16 assets from user ZIP, with SHA-256 proof.

Offline, no GitHub, Firebase, user accounts, credentials or network access.
The archive is deliberately not committed automatically: review before git add.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HASH_LOCK = ROOT / "docs" / "HOSTING_V616_SOURCE_HASH_LOCK.json"
PREFIX = "nba-season-lab-v616/"
DENY = ("..", ".git", ".env", "credentials", "private", "backup", "account", "personal", "secret")
def sha(blob):
    return hashlib.sha256(blob).hexdigest()
def recover(archive, destination, write=False):
    spec = json.loads(HASH_LOCK.read_text("utf-8"))["files"]
    found = {}
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError("Corrupt ZIP")
        names = set(z.namelist())
        if len(names) != len(z.namelist()):
            raise ValueError("Duplicate archive paths")
        for filename in names:
            norm = PurePosixPath(filename)
            if norm.is_absolute() or any(x in norm.parts for x in DENY) or "\\" in filename:
                raise ValueError("Unsafe archive path")
        for relative, hashes in sorted(spec.items()):
            path = PREFIX + relative
            if path not in names:
                raise ValueError("Missing public Hosting file: " + relative)
            data = z.read(path)
            if sha(data) != hashes["v616"]:
                raise ValueError("v6.16 SHA mismatch: " + relative)
            found[relative] = data
        # Strict allowlist: never stage any user private backup, token or personal JSON.
        unmatched = [x for x in names if x.startswith(PREFIX) and not x.endswith("/")
                     and x[len(PREFIX):] not in spec and not x.endswith((".md", ".cjs"))]
        if unmatched:
            raise ValueError("Unexpected unverified Hosting asset: " + repr(unmatched[:3]))
    if write:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Destination must be empty")
        destination.mkdir(parents=True, exist_ok=True)
        for relative, data in found.items():
            to = destination / relative
            to.parent.mkdir(parents=True, exist_ok=True)
            to.write_bytes(data)
    return {"files": len(found), "verified": True, "written": bool(write),
            "destination": str(destination) if write else None}
def main():
    p = argparse.ArgumentParser()
    p.add_argument("zip", type=Path)
    p.add_argument("--output", type=Path, default=ROOT / "site" / "hosting_v616")
    p.add_argument("--write", action="store_true", help="Actually write verified public assets")
    args = p.parse_args()
    try:
        print(json.dumps(recover(args.zip, args.output, args.write), indent=2))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, KeyError) as exc:
        print("BLOCKED:", exc, file=sys.stderr)
        return 2
if __name__ == "__main__":
    sys.exit(main())
