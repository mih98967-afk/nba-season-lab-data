"""Publish small cacheable history shards for the public site.

Instead of downloading a single multi-megabyte history JSON on every visit,
clients first load a small index and then one ~200 KB shard on player selection.
No Firebase user documents or private data are present in these files.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import zlib

from src.sync import DATA

PARTITIONS=32
def shard_for(pid: str) -> int:
    if not re.fullmatch(r"n\d{3,5}",pid):
        raise ValueError("Unexpected Sports.ru player ID: "+str(pid))
    return zlib.crc32(pid.encode("ascii"))%PARTITIONS

def export(source=None,destination=None):
    source=pathlib.Path(source or DATA/"nba_history.json")
    dest=pathlib.Path(destination or DATA/"history")
    obj=json.loads(source.read_text(encoding="utf8"))
    players=obj.get("players")
    qa=obj.get("qa")
    if not isinstance(players,dict) or not isinstance(qa,dict) or obj.get("status")!="complete":
        raise ValueError("Historical source has not passed validation")
    count=int(qa.get("matched_players",0))
    if count < 200 or len(players)!=count:raise ValueError("Player count mismatch")
    raw=source.read_bytes()
    version=hashlib.sha256(raw).hexdigest()[:16]
    buckets=[{} for _ in range(PARTITIONS)]
    player_shards={}
    season_sizes={}
    for pid,history in players.items():
        if not isinstance(history,list) or not history:raise ValueError("Empty player history: "+pid)
        for season in history:
            if not {"season","games","fp_avg","averages"}.issubset(season):
                raise ValueError("Incomplete player history for "+pid)
        shard=shard_for(pid)
        buckets[shard][pid]=history
        player_shards[pid]=f"shard_{shard:02d}.json"
        season_sizes[pid]=sum(int(x["games"]) for x in history)
    if sum(season_sizes.values())!=qa["matched_player_game_rows"]:
        raise ValueError("Summed season games do not match audited player-game rows")
    dest.mkdir(parents=True,exist_ok=True)
    manifest={
        "schema_version":1,"format":"by_shard","status":"complete",
        "version":version,"updated_at_utc":obj.get("updated_at_utc"),
        "qa":qa,"source":obj.get("source"),"source_url":obj.get("source_url"),
        "license":obj.get("license"),"player_shards":player_shards
    }
    saved=[]
    for i,bucket in enumerate(buckets):
        if not bucket:continue
        name=f"shard_{i:02d}.json"
        payload={"schema_version":1,"status":"complete",
                 "version":version,"players":bucket}
        dest.joinpath(name).write_text(json.dumps(payload,ensure_ascii=False,separators=(",",":")),encoding="utf8")
        saved.append({"file":name,"players":len(bucket),"size":dest.joinpath(name).stat().st_size})
    manifest["shards"]=saved
    dest.joinpath("index.json").write_text(json.dumps(manifest,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    check_ids={pid for b in buckets for pid in b}
    if check_ids!=set(players):raise ValueError("Lost or duplicated player during publish")
    if not all(s["size"]<900_000 for s in saved):
        raise ValueError("A history shard is too large to fetch quickly")
    return {"version":version,"players":len(players),
            "shards":len(saved),"max_shard_bytes":max(x["size"] for x in saved),
            "total_bytes":sum(x["size"] for x in saved)}

if __name__=="__main__":
    print(json.dumps(export(),ensure_ascii=False,indent=2))
