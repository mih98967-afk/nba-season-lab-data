"""Read user XLSX position snapshots and resolve identities with explicit provenance.

No workbook is modified. Season rosters are retrospective labels; they are not
pretended to have been captured before historical games.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
POSITION = {"Ц": "C", "РЗащ": "PG", "АЗащ": "SG", "ЛФ": "SF", "ТФ": "PF"}
YEARS = {2024: "NBA_2324.xlsx", 2025: "NBA_2425.xlsx", 2026: "NBA_2526.xlsx", 2027: "NBA_2627.xlsx"}
TEAMS = {
    "Атланта":"ATL", "Бостон":"BOS", "Бруклин":"BKN", "Шарлотт":"CHA", "Чикаго":"CHI", "Кливленд":"CLE", "Даллас":"DAL", "Денвер":"DEN", "Детройт":"DET", "Голден Стэйт":"GSW", "Голден Стейт":"GSW", "Хьюстон":"HOU", "Индиана":"IND", "Клипперс":"LAC", "Лейкерс":"LAL", "Мемфис":"MEM", "Майами":"MIA", "Милуоки":"MIL", "Миннесота":"MIN", "Нью-Орлеан":"NOP", "Нью-Йорк":"NYK", "Оклахома-Сити":"OKC", "Орландо":"ORL", "Филадельфия":"PHI", "Финикс":"PHX", "Портленд":"POR", "Сакраменто":"SAC", "Сан-Антонио":"SAS", "Торонто":"TOR", "Юта":"UTA", "Вашингтон":"WAS",
}
TEAMS["Новый Орлеан"] = "NOP"


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or "")).casefold().replace("ё", "е")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-zа-я0-9 ]", " ", value).split())


def num(value):
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def read_roster(path, year):
    records, sheets = [], []
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(x.itertext()) for x in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", NS)]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet_labels = [s.attrib.get("name") for s in workbook.findall("m:sheets/m:sheet", NS)]
        for index, name in enumerate(sorted(n for n in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))):
            rows = ET.fromstring(archive.read(name)).findall("m:sheetData/m:row", NS)
            accepted = 0
            for row in rows:
                cells = {}
                for c in row:
                    v, inline = c.find("m:v", NS), c.find("m:is", NS)
                    value = v.text if v is not None else "".join(inline.itertext()) if inline is not None else ""
                    if c.attrib.get("t") == "s": value = strings[int(value)]
                    cells[re.sub(r"\d", "", c.attrib.get("r", ""))] = str(value or "").strip()
                if cells.get("B") not in POSITION or not cells.get("D"):
                    continue
                accepted += 1
                records.append(dict(season=year, season_label=f"{year-1}/{str(year)[2:]}", source_file=path.name, sheet=sheet_labels[index], source_row=int(row.attrib["r"]), russian_name=cells["D"], fantasy_position=POSITION[cells["B"]], source_position=cells["B"], fantasy_team_ru=cells.get("C"), fantasy_team=TEAMS.get(cells.get("C", "")), games=num(cells.get("M")), total_fp=num(cells.get("L")), avg_fp=num(cells.get("O"))))
            sheets.append(dict(name=sheet_labels[index], xml=name, physical_rows=len(rows), roster_rows=accepted))
        core = archive.read("docProps/core.xml").decode() if "docProps/core.xml" in archive.namelist() else ""
        created = re.search(r"<dcterms:created[^>]*>([^<]+)", core)
    return records, dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), sheets=sheets, workbook_created_at=created.group(1) if created else None, historical_vintage_verified=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uploads", type=Path, default=ROOT / "upload")
    ap.add_argument("--repo", type=Path, default=ROOT / "nba-season-lab-data")
    ap.add_argument("--source", type=Path, default=ROOT / "research_base/source")
    ap.add_argument("--aliases", type=Path, default=HERE / "reviewed_aliases.json")
    ap.add_argument("--output", type=Path, default=HERE / "results")
    args = ap.parse_args(); args.output.mkdir(exist_ok=True, parents=True)
    records, source_metadata = [], []
    for year, name in YEARS.items():
        rows, meta = read_roster(args.uploads / name, year)
        records += rows; source_metadata.append(meta)
    nba = pd.read_pickle(ROOT / "research_extension/common/raw.pkl")
    current = pd.read_csv(args.source / "current/player_boxscores_2027.csv", dtype={"person_id":str, "game_id":str})
    current_names = current[["person_id", "first_name", "family_name", "team_tricode"]].drop_duplicates().to_dict("records")
    people, season_people = {}, defaultdict(set)
    for row in nba[["pid", "name", "team", "season"]].drop_duplicates().to_dict("records"):
        pid = str(row["pid"]); people.setdefault(pid, dict(name=row["name"], names=set(), teams=defaultdict(set)))
        people[pid]["names"].add(row["name"]); people[pid]["teams"][int(row["season"])].add(row["team"])
        season_people[int(row["season"])].add(pid)
    for row in current_names:
        pid = str(row["person_id"]); name = row["first_name"] + " " + row["family_name"]
        people.setdefault(pid, dict(name=name, names=set(), teams=defaultdict(set)))
        people[pid]["names"].add(name); people[pid]["teams"][2027].add(row["team_tricode"]); season_people[2027].add(pid)
    english = defaultdict(set)
    for pid, info in people.items():
        for name in info["names"]: english[norm(name)].add(pid)
    identity_path = args.repo / "data/identity.json"
    catalog_path = args.repo / "data/catalog.json"
    identity = json.loads(identity_path.read_text())["players"]
    catalog = json.loads(catalog_path.read_text())["players"]
    live = json.loads((args.source / "data/live.json").read_text())
    live_names = defaultdict(set)
    for r in live.get("rows", []):
        if r.get("id") and r.get("name"): live_names[r["id"]].add(r["name"])
    bridge = defaultdict(dict)
    for row in catalog:
        candidates = set(); item = identity.get(row["id"], {})
        if item.get("confidence") in {"high", "medium"} and str(item.get("nba_id")) in people:
            candidates.add(str(item["nba_id"]))
        for name in {row.get("english")} | live_names[row["id"]]:
            candidates |= english.get(norm(name), set())
        for pid in candidates:
            bridge[norm(row["name"])][pid] = dict(catalog_id=row["id"], identity_method=item.get("method"), identity_confidence=item.get("confidence"), evidence="existing_public_catalog_identity_and_exact_name")
    aliases = json.loads(args.aliases.read_text()) if args.aliases.exists() else []
    alias_index = defaultdict(list)
    for alias in aliases: alias_index[norm(alias["russian_name"])].append(alias)
    out = []
    for row in records:
        choices = bridge.get(norm(row["russian_name"]), {})
        candidates = set(choices) & season_people[row["season"]]
        method = "exact_existing_russian_name_bridge"
        reviewed = [a for a in alias_index[norm(row["russian_name"])]
                    if (not a.get("seasons") or row["season"] in a["seasons"])
                    and ("source_keys" not in a or [row["season"], row["source_row"]] in a["source_keys"])]
        if reviewed:
            ids = {str(a["nba_person_id"]) for a in reviewed}
            if len(ids) == 1:
                candidates = ids & season_people[row["season"]]
                method = "explicit_reviewed_alias"
        if len(candidates) > 1 and row.get("fantasy_team"):
            by_team = {p for p in candidates if row["fantasy_team"] in people[p]["teams"][row["season"]]}
            if len(by_team) == 1:
                candidates = by_team; method += "_season_team_disambiguation"
        pid = next(iter(candidates)) if len(candidates) == 1 else None
        out.append(dict(row, nba_person_id=pid, english_name=people[pid]["name"] if pid else None, identity_status="resolved" if pid else "unresolved", identity_method=method if pid else None, candidate_ids=sorted(candidates), candidate_names=[people[p]["name"] for p in sorted(candidates)], season_team_consistent=bool(pid and row.get("fantasy_team") in people[pid]["teams"][row["season"]]), position_vintage="retrospective_season_snapshot" if row["season"] < 2027 else "current_user_supplied_snapshot", independently_official_verified=False))
    # Repeated NBA IDs with different positions cannot silently overwrite one another.
    grouped = defaultdict(list)
    for row in out:
        if row["nba_person_id"]: grouped[(row["season"],row["nba_person_id"])].append(row)
    conflicts = []
    for key, rows in grouped.items():
        if len(rows) > 1:
            conflicts.append({"season":key[0],"nba_person_id":key[1],"rows":[r["source_row"] for r in rows]})
            for row in rows:row.update(identity_status="duplicate_identity_conflict",nba_person_id=None)
    observed = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    result = dict(schema="season_fantasy_positions_v1", observed_at_utc=observed, historical_point_in_time_verified=False, source_workbooks=source_metadata, identity_sources={str(p.relative_to(args.repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [identity_path,catalog_path]}, records=out, conflicts=conflicts)
    (args.output / "SEASON_POSITION_MAPPING.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    pd.DataFrame(out).to_csv(args.output / "season_positions.csv",index=False)
    unresolved = pd.DataFrame([r for r in out if not r["nba_person_id"]]).sort_values(["games","season"],ascending=False)
    unresolved.to_csv(args.output / "unresolved_positions.csv",index=False)
    people_dump = {pid:dict(name=i["name"],names=sorted(i["names"]),teams={str(y):sorted(t) for y,t in i["teams"].items()}) for pid,i in people.items()}
    (args.output / "NBA_IDENTITY_INDEX.json").write_text(json.dumps(people_dump,ensure_ascii=False,indent=2)+"\n")
    summary = {str(y):dict(rows=sum(r["season"]==y for r in out),resolved=sum(r["season"]==y and r["nba_person_id"] is not None for r in out),unknown=sum(r["season"]==y and r["nba_person_id"] is None for r in out),unresolved_with_games=sum(r["season"]==y and r["nba_person_id"] is None and (r["games"] or 0)>0 for r in out)) for y in YEARS}
    (args.output / "MAPPING_COVERAGE.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__": main()
