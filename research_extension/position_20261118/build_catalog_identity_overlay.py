"""Publishable exact-identity overlay from already preserved source snapshots.

No model fitting, new player creation, quote update or historical PIT claim.
Existing medium statistical matches alone are never promoted to high confidence.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from ingest_positions import norm
from packed_assets import materialize_assets


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(catalog, identities, live, people, mapping):
    english, observed_names = defaultdict(set), defaultdict(set)
    latest_team = {}
    for nba_id, person in people.items():
        for name in person["names"]:
            english[norm(name)].add(str(nba_id))
    for row in sorted(live["rows"], key=lambda item: item["utc"]):
        if row.get("name"):
            observed_names[row["id"]].add(row["name"])
        if row.get("team"):
            latest_team[row["id"]] = row["team"]
    current = [row for row in mapping["records"] if row["season"] == 2027]
    source_history = {(row["season"], row["source_row"]): row for row in mapping["records"]}
    players, unresolved, differences, conflicts, history_corrections = {}, [], [], [], []
    for player in catalog["players"]:
        cid, old = player["id"], identities.get("players", {}).get(player["id"], {})
        team = latest_team.get(cid) or player["team"]
        names = set(observed_names[cid])
        if player.get("english"):
            names.add(player["english"])
        full_ids = set().union(*(english[norm(name)] for name in names)) if names else set()
        matching = [row for row in current if norm(row["russian_name"]) == norm(player["name"])
                    and row["fantasy_team"] == team and row["fantasy_position"] == player["pos"]
                    and row.get("nba_person_id") and row["season_team_consistent"]]
        current_row = matching[0] if len(matching) == 1 else None
        method, nba_id = None, None
        if current_row and current_row["identity_method"].startswith("explicit_reviewed_alias"):
            nba_id, method = current_row["nba_person_id"], "reviewed_current_roster_name_team_position"
            if full_ids and full_ids != {nba_id}:
                raise ValueError("CURRENT_ROSTER_CONTRADICTS_EXACT_FULL_NAME:" + cid)
        elif len(full_ids) == 1:
            nba_id, method = next(iter(full_ids)), "exact_full_english_NBA_name"
        elif len(full_ids) > 1:
            unresolved.append({"player_id": cid, "reason": "conflicting_observed_full_names", "candidate_ids": sorted(full_ids)})
            continue
        elif old.get("confidence") == "high" and str(old.get("nba_id")) in people:
            nba_id, method = str(old["nba_id"]), "preserved_existing_high_identity"
        if nba_id is None:
            unresolved.append({"player_id": cid, "name": player["name"], "team": team, "position": player["pos"],
                               "reason": "no_new_exact_identity_evidence", "existing_confidence": old.get("confidence"),
                               "unknown_not_DNP": True})
            continue
        if old.get("nba_id") and str(old["nba_id"]) != nba_id:
            # Both exceptions have an explicit reviewed current-roster alias,
            # matching name/team/position, and a demonstrably different old ID.
            if (cid, str(old["nba_id"]), nba_id) not in {
                ("n266", "1641816", "1642281"), ("n314", "201567", "1631126")
            }:
                raise ValueError("UNREVIEWED_IDENTITY_CONFLICT:" + cid)
            conflicts.append({"player_id": cid, "old_nba_id": str(old["nba_id"]), "new_nba_id": nba_id,
                              "old_confidence": old.get("confidence"), "resolution": "reviewed_current_roster_exact_name_team_position"})
        item = {"nba_id": nba_id, "confidence": "high", "method": method,
                "english": people[nba_id]["name"], "catalog_name": player["name"],
                "catalog_team": player["team"], "catalog_position": player["pos"],
                "observed_current_team": team, "full_names_observed": sorted(names),
                "historical_vintage_verified": False}
        if current_row:
            item["current_roster_evidence"] = {key: current_row[key] for key in
                ["source_file", "sheet", "source_row", "russian_name", "fantasy_team", "fantasy_position",
                 "nba_person_id", "identity_method", "season_team_consistent"]}
        players[cid] = item
        if old.get("confidence") != "high" or str(old.get("nba_id")) != nba_id:
            differences.append({"player_id": cid, "nba_id": nba_id, "old_nba_id": old.get("nba_id"),
                                "old_confidence": old.get("confidence"), "method": method})
        for history in player.get("history", []):
            year = int("20" + history["season"].split("/")[1])
            old_row = source_history.get((year, history.get("row")))
            if not old_row or not old_row.get("nba_person_id") or old_row["nba_person_id"] == nba_id:
                continue
            if not (history.get("games") == old_row["games"] and history.get("total") == old_row["total_fp"]
                    and norm(history.get("team")) == norm(old_row["fantasy_team_ru"])):
                continue
            history_corrections.append({"player_id": cid, "player_name": player["name"], "season": history["season"],
                                        "current_nba_person_id": nba_id, "current_english_name": people[nba_id]["name"],
                                        "wrong_history_nba_person_id": old_row["nba_person_id"],
                                        "wrong_history_english_name": old_row["english_name"],
                                        "wrong_history_source": {key: old_row[key] for key in ["source_file", "sheet", "source_row", "russian_name", "fantasy_team_ru", "games", "total_fp"]},
                                        "action": "remove_wrong_history", "legacy_seed_use_allowed": False,
                                        "nba_id_boxscore_model_features_affected": False})
    reverse = defaultdict(list)
    for cid, item in players.items():
        reverse[item["nba_id"]].append(cid)
    duplicate = {pid: cids for pid, cids in reverse.items() if len(cids) > 1}
    if duplicate:
        raise ValueError("DUPLICATE_CATALOG_NBA_IDS:" + json.dumps(duplicate))
    return {"schema": "nba_catalog_identity_overlay_v1", "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "historical_vintage_verified": False, "purpose": "Current release identity only; immutable prior forecasts and trained weights unchanged.",
            "players": players, "unresolved": unresolved, "differences_from_existing_high_only": differences,
            "reviewed_identity_conflicts": conflicts, "history_corrections": history_corrections,
            "coverage": {"catalog_players": len(catalog["players"]), "exact_or_preserved_high_ids": len(players),
                         "unresolved": len(unresolved), "added_or_upgraded": len(differences),
                         "identity_conflicts_corrected": len(conflicts), "wrong_history_rows": len(history_corrections),
                         "methods": dict(Counter(item["method"] for item in players.values()))},
            "restrictions": ["Do not infer current price or start_price from this identity file.",
                             "Do not replace explicit user team overrides.", "Do not convert unresolved cards to DNP.",
                             "Roster positions are retrospective labels; current observation is not historical pregame proof."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="nba-current-identity-") as work:
        materialize_assets(package, work, ["results/NBA_IDENTITY_INDEX.json", "results/SEASON_POSITION_MAPPING.json"])
        work = Path(work) / "results"
        report = build(json.loads(args.catalog.read_text()), json.loads(args.identity.read_text()), json.loads(args.live.read_text()),
                       json.loads((work / "NBA_IDENTITY_INDEX.json").read_text()), json.loads((work / "SEASON_POSITION_MAPPING.json").read_text()))
        report["source_sha256"] = {"catalog": digest(args.catalog), "identity": digest(args.identity), "live": digest(args.live),
                                   "NBA_IDENTITY_INDEX": digest(work / "NBA_IDENTITY_INDEX.json"), "SEASON_POSITION_MAPPING": digest(work / "SEASON_POSITION_MAPPING.json")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["coverage"]))
    print("HISTORY_CORRECTIONS", json.dumps({cid: [row["season"] for row in report["history_corrections"] if row["player_id"] == cid]
                                             for cid in sorted({row["player_id"] for row in report["history_corrections"]})}))
    print("OUTPUT_SHA256", digest(args.output))


if __name__ == "__main__":
    main()
