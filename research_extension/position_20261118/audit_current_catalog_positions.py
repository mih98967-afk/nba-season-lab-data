"""Compare site positions with the supplied current-season roster by exact ID.

This is a read-only catalog audit. It cannot infer a position from a surname,
change prices, add players, or turn unresolved identities into DNP labels.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tempfile

from ingest_positions import norm
from packed_assets import materialize_assets


def audit(catalog, identities, people, roster):
    english = defaultdict(set)
    for nba_id, person in people.items():
        for name in person["names"]:
            english[norm(name)].add(str(nba_id))
    columns = roster["columns"]
    current = defaultdict(list)
    for values in roster["rows"]:
        row = dict(zip(columns, values))
        if row.get("nba_person_id"):
            current[str(row["nba_person_id"])].append(row)
    compared, skipped, corrections = [], [], []
    for player in catalog["players"]:
        candidates = set(english.get(norm(player.get("english")), set()))
        explicit = identities.get("players", {}).get(player["id"], {})
        if explicit.get("confidence") in ("high", "medium") and str(explicit.get("nba_id")) in people:
            candidates.add(str(explicit["nba_id"]))
        if len(candidates) != 1:
            skipped.append({"player_id": player["id"], "reason": "current_NBA_identity_not_unique", "candidate_ids": sorted(candidates)})
            continue
        nba_id = next(iter(candidates))
        matches = current.get(nba_id, [])
        if len(matches) != 1:
            skipped.append({"player_id": player["id"], "nba_person_id": nba_id,
                            "reason": "no_unique_current_roster_row", "rows": len(matches)})
            continue
        row = matches[0]
        item = {"player_id": player["id"], "nba_person_id": nba_id, "catalog_position": player["pos"],
                "current_roster_position": row["position"], "source_row": row["source_row"],
                "matches": player["pos"] == row["position"]}
        compared.append(item)
        if not item["matches"]:
            corrections.append(item)
    return {"schema": "nba_current_catalog_position_audit_v1", "catalog_players": len(catalog["players"]),
            "strictly_compared": len(compared), "same_position": sum(row["matches"] for row in compared),
            "different_position": len(corrections), "skipped": skipped, "comparisons": compared,
            "corrections_proposed": corrections, "applied": False,
            "source_file": roster["source_file"], "source_sha256": roster["source_sha256"],
            "observed_at_utc": roster["observed_at_utc"], "historical_vintage_verified": False,
            "identity_policy": "Exact normalized full English NBA name and/or explicit NBA ID, no contradictory IDs; one current roster row.",
            "unknown_policy": "Unresolved identity remains UNKNOWN; not a position guess or a DNP label."}


def main():
    package = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="nba-position-audit-") as work:
        materialize_assets(package, work, ["results/NBA_IDENTITY_INDEX.json"])
        people = json.loads((Path(work) / "results/NBA_IDENTITY_INDEX.json").read_text())
    report = audit(json.loads(args.catalog.read_text()), json.loads(args.identity.read_text()), people,
                   json.loads((package / "results/CURRENT_ROSTER_COMPACT.json").read_text()))
    report["catalog_sha256"] = hashlib.sha256(args.catalog.read_bytes()).hexdigest()
    report["identity_sha256"] = hashlib.sha256(args.identity.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ["catalog_players", "strictly_compared", "same_position", "different_position", "applied"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
