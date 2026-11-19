"""Prove legacy namesake history errors without modifying catalog or models."""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from ingest_positions import norm, ROOT, HERE


def same_number(a,b):
    try:
        return abs(float(a)-float(b)) < 1e-6
    except (TypeError,ValueError):
        return False


def main():
    repo=ROOT/"nba-release-20261118"
    catalog=json.loads((repo/"data/catalog.json").read_text())["players"]
    identity=json.loads((repo/"data/identity.json").read_text())["players"]
    people=json.loads((HERE/"results/NBA_IDENTITY_INDEX.json").read_text())
    mapping=json.loads((HERE/"results/SEASON_POSITION_MAPPING.json").read_text())
    records=mapping["records"]
    english=defaultdict(set)
    for pid,person in people.items():
        for name in person["names"]:
            english[norm(name)].add(pid)
    by_source={(r["season"],r["source_row"]):r for r in records}
    by_nba={(r["season"],r["nba_person_id"]):r for r in records if r["nba_person_id"]}
    corrections=[];unchecked=[];checked=0
    for player in catalog:
        candidates=set(english.get(norm(player.get("english")),set()))
        official=identity.get(player["id"],{})
        if official.get("confidence") in ("high","medium") and str(official.get("nba_id")) in people:
            candidates.add(str(official["nba_id"]))
        if len(candidates)!=1:
            unchecked.append({"player_id":player["id"],"reason":"current_NBA_identity_not_unique","candidate_ids":sorted(candidates)})
            continue
        pid=next(iter(candidates))
        for history in player.get("history",[]):
            season=int("20"+history["season"].split("/")[1])
            source=by_source.get((season,history.get("row")))
            if not source or not source["nba_person_id"]:
                unchecked.append({"player_id":player["id"],"season":history["season"],"reason":"source_row_or_identity_unresolved"})
                continue
            # Source row alone can shift between exports. Require a complete
            # historical fingerprint before calling a stored history wrong.
            if not (same_number(history.get("games"),source["games"]) and same_number(history.get("total"),source["total_fp"]) and norm(history.get("team"))==norm(source["fantasy_team_ru"])):
                unchecked.append({"player_id":player["id"],"season":history["season"],"reason":"source_fingerprint_not_identical"})
                continue
            checked+=1
            if source["nba_person_id"]==pid:
                continue
            correct=by_nba.get((season,pid))
            item={"player_id":player["id"],"player_name":player["name"],"season":history["season"],"season_end_year":season,
                  "current_nba_person_id":pid,"current_english_name":people[pid]["name"],
                  "action":"replace_with_exact_season_row" if correct else "remove_wrong_history",
                  "wrong_history_nba_person_id":source["nba_person_id"],"wrong_history_english_name":source["english_name"],
                  "wrong_history_source":{"file":source["source_file"],"sheet":source["sheet"],"row":source["source_row"],"russian_name":source["russian_name"],"team":source["fantasy_team_ru"],"games":source["games"],"total":source["total_fp"]},
                  "evidence":"Exact stored history season+worksheet row+team+games+total fingerprint matches a different NBA ID resolved from the supplied season roster. Current player identity separately uses exact English NBA name and/or existing explicit NBA ID.",
                  "legacy_seed_contaminated":True,"legacy_seed_use_allowed":False,
                  "nba_id_boxscore_model_features_affected":False}
            if correct:
                item["replacement"]={"season":history["season"],"team":correct["fantasy_team_ru"],"games":correct["games"],"total":correct["total_fp"],"fp_avg":correct["avg_fp"],"source":"Sports.ru fantasy user upload 18 Nov 2026; exact NBA identity matched", "row":correct["source_row"],"source_file":correct["source_file"],"nba_person_id":pid,"log":[],"log_valid":False,"log_count":0,"note":"Исправлена чужая история однофамильца по точному NBA ID; поматчевый ряд здесь не восстанавливался."}
            corrections.append(item)
    report={"schema":"catalog_history_identity_corrections_v1","catalog_sha256":hashlib.sha256((repo/"data/catalog.json").read_bytes()).hexdigest(),
            "position_mapping_sha256":hashlib.sha256((HERE/"results/SEASON_POSITION_MAPPING.json").read_bytes()).hexdigest(),
            "current_identity_policy":"exact NBA ID; never transfer by surname", "history_fingerprint_checked":checked,
            "correction_count":len(corrections),"affected_player_count":len({r["player_id"] for r in corrections}),
            "corrections":corrections,"unchecked":unchecked,
            "scope":"Read-only release overlay proposal. Preserved source files/frozen forecasts/research models unchanged. Research Ridge/CatBoost historical features use NBA-ID-keyed boxscores, not catalog.history."}
    (HERE/"results/catalog_history_corrections.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"checked":checked,"corrections":len(corrections),"players":report["affected_player_count"],"unchecked":len(unchecked)},ensure_ascii=False))
    for r in corrections:
        print(r["player_id"],r["current_english_name"],r["season"],r["wrong_history_english_name"],r["action"])


if __name__=="__main__":main()
