"""Audit preserved labels and build future-only catalog mapping without outcomes."""
from __future__ import annotations
import argparse
import collections
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

from position_contract import POSITIONS, normalize_name

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=RESEARCH_BASE / "source")
    ap.add_argument("--hosting-zip", type=Path)
    ap.add_argument("--catalog", type=Path, help="Existing public data/base.json; use this instead of a Hosting ZIP")
    ap.add_argument("--output", type=Path, default=Path(__file__).with_name("results"))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    names = collections.defaultdict(set)
    historical = {}
    source_hashes = {}
    for year in (2024, 2025, 2026):
        path = args.source / "upstream" / f"player_boxscores_{year}.csv"
        source_hashes[str(path.name)] = hashlib.sha256(path.read_bytes()).hexdigest()
        labels = collections.Counter()
        reg_labels = collections.Counter()
        people = set()
        with path.open() as handle:
            for row in csv.DictReader(handle):
                name = normalize_name(row["first_name"] + " " + row["family_name"])
                names[name].add(row["person_id"])
                labels[row["position"]] += 1
                if row["game_id"].startswith("002"):
                    reg_labels[row["position"]] += 1
                    people.add(row["person_id"])
        historical[str(year)] = {"raw_file_rows": sum(labels.values()), "raw_position_labels": dict(labels), "regular_season_rows": sum(reg_labels.values()), "regular_season_position_labels": dict(reg_labels), "players": len(people), "exact_pg_sg_sf_pf_rows": sum(reg_labels.get(p, 0) for p in ("PG", "SG", "SF", "PF")), "historical_verified_fantasy_position_rows": 0}
    # Current file contributes identity strings only, never current outcomes.
    current = args.source / "current" / "player_boxscores_2027.csv"
    if current.exists():
        with current.open() as handle:
            for row in csv.DictReader(handle):
                names[normalize_name(row["first_name"] + " " + row["family_name"])].add(row["person_id"])
        source_hashes[current.name] = hashlib.sha256(current.read_bytes()).hexdigest()
    if args.catalog and args.hosting_zip:
        raise ValueError("CHOOSE_ONE_CATALOG_SOURCE")
    if args.hosting_zip:
        with zipfile.ZipFile(args.hosting_zip) as archive:
            raw_catalog = archive.read("data/base.json")
        catalog_source_ref = args.hosting_zip.name + ":data/base.json"
    else:
        catalog_path = args.catalog or ROOT / "site/hosting_v620/data/base.json"
        raw_catalog = catalog_path.read_bytes()
        catalog_source_ref = "public_catalog:" + catalog_path.name
    source_sha = hashlib.sha256(raw_catalog).hexdigest()
    catalog = json.loads(raw_catalog)
    live_path = args.source / "data" / "live.json"
    live_raw = live_path.read_bytes()
    live_sha = hashlib.sha256(live_raw).hexdigest()
    live_names = collections.defaultdict(set)
    # Read public id/name strings only. Outcomes do not influence this join.
    for row in json.loads(live_raw).get("rows", []):
        if row.get("id") and row.get("name"):
            live_names[str(row["id"])].add(row["name"])
    records = []
    unresolved = []
    for player in catalog["players"]:
        alias_names = {player.get("english", "")} | live_names[player["id"]]
        candidates = set()
        for alias in alias_names:
            candidates |= names.get(normalize_name(alias or ""), set())
        if len(candidates) != 1 or player.get("pos") not in POSITIONS:
            unresolved.append({"catalog_id": player["id"], "english": player.get("english"), "candidate_person_ids": sorted(candidates), "reason": "identity_ambiguous" if len(candidates) > 1 else "identity_unmatched" if not candidates else "position_invalid"})
            continue
        records.append({"person_id": next(iter(candidates)), "catalog_id": player["id"], "english": player.get("english"), "observed_public_names": sorted(n for n in alias_names if n), "position": player["pos"], "season": catalog["season"], "identity_status": "exact_unique_normalized_name", "identity_bridge_source_ref": "source/data/live.json:id,name", "identity_bridge_sha256": live_sha, "source_kind": "fantasy_catalog_snapshot", "source_ref": catalog_source_ref, "source_sha256": source_sha, "observed_at": observed_at, "effective_from": observed_at, "effective_until": None, "independently_verified_official": False})
    mapping = {"schema": "nba-fantasy-position-snapshot-v1", "status": "future_only_catalog_mapping_not_historical_backfill", "created_at": observed_at, "declared_catalog_created_at": catalog.get("created_at_utc"), "declared_catalog_timestamp_is_not_observation_proof": True, "records": records, "unresolved": unresolved}
    report = {"status": "FIVE_POSITION_HISTORICAL_VALIDATION_BLOCKED", "adopt_on_site": False, "historical": historical, "catalog_players": len(catalog["players"]), "catalog_position_counts": dict(collections.Counter(p.get("pos") for p in catalog["players"])), "identity_resolved": len(records), "identity_unresolved": len(unresolved), "resolved_position_counts": dict(collections.Counter(r["position"] for r in records)), "source_hashes": source_hashes, "catalog_sha256": source_sha, "identity_bridge_sha256": live_sha, "observed_at": observed_at, "limits": ["NBA historical G/F/C are starter labels, not five Sports.ru positions", "Historical C starter labels do not certify fantasy C", "Current season catalog cannot validate past seasons", "No current outcomes are used in model selection", "Exact normalized-name join is reviewable but not independent official identity certification", "Mapping cannot be used before actual observation time"]}
    for name, value in [("POSITION_AUDIT.json", report), ("FUTURE_POSITION_MAPPING.json", mapping)]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "catalog_players", "identity_resolved", "identity_unresolved", "resolved_position_counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
