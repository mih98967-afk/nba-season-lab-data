"""Conservative explicit ESPN boxscore DNP research. Never infer from missing rows."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
from urllib.request import Request,urlopen
import json,unicodedata,re
from src.sync import DATA
from src.rolling_decision_research import stamp,instant
from src.espn_adapter import club

URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="
def norm(x):
    x=unicodedata.normalize("NFKD",str(x or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",x).strip()

def identity_map(identity):
    names=defaultdict(set)
    for pid,e in identity.get("players",{}).items():
        if e.get("english"):names[norm(e["english"])].add(pid)
    return {n:next(iter(ids)) for n,ids in names.items() if len(ids)==1}

def explicit_rows(payload,game,identity,observed_at):
    if game.get("status")!="final" or not game.get("espn_id"):
        raise ValueError("Only verified completed ESPN games")
    comp=((payload.get("header") or {}).get("competitions") or [{}])[0]
    sides={}
    for side in comp.get("competitors") or []:
        code=club((side.get("team") or {}).get("abbreviation"))
        if side.get("homeAway") in ("home","away"):sides[side["homeAway"]]=code
    if sides!={"home":game["home"],"away":game["away"]}:
        raise ValueError("ESPN matchup not verified")
    entries=(payload.get("boxscore") or {}).get("players") or []
    if len(entries)!=2:raise ValueError("Both club boxscores required")
    aliases=identity_map(identity);qa=Counter();out={};team_seen=set()
    for side in entries:
        team=club((side.get("team") or {}).get("abbreviation"))
        if team not in (game["home"],game["away"]) or team in team_seen:
            raise ValueError("Duplicate or unknown boxscore club")
        team_seen.add(team)
        for group in side.get("statistics") or []:
            for row in group.get("athletes") or []:
                if row.get("didNotPlay") is not True:continue
                name=(row.get("athlete") or {}).get("displayName") or (row.get("athlete") or {}).get("fullName")
                pid=aliases.get(norm(name))
                if not pid:qa["unmatched_or_ambiguous_name"]+=1;continue
                key=(game["id"],pid)
                if key in out:
                    qa["duplicate_dnp_identity"]+=1
                    out.pop(key,None)
                    continue
                out[key]={"game_id":game["id"],"player_id":pid,"team":team,
                          "home":game["home"],"away":game["away"],
                          "game_utc":game["utc"],"observed_at_utc":stamp(observed_at),
                          "evidence":"explicit_espn_didNotPlay_true",
                          "source_url":URL+str(game["espn_id"])}
    if team_seen!={game["home"],game["away"]}:raise ValueError("Incomplete club evidence")
    return list(out.values()),dict(qa)

def gather(live,identity,prior,fetch,now,max_games=12):
    if now.utcoffset() is None:raise ValueError("Aware capture clock required")
    prev=prior or {}
    if prev and (prev.get("schema_version")!=1 or prev.get("adopt_on_site") is not False):
        raise ValueError("Unexpected prior archive")
    retained={(x["game_id"],x["player_id"]):x for x in prev.get("events",[])}
    checked=set(prev.get("checked_final_game_ids",[]))
    qa=Counter();processed=0
    final=sorted((g for g in live.get("games",[]) if g.get("status")=="final"
                  and g.get("espn_id") and g["id"] not in checked),
                 key=lambda g:(g.get("utc",""),g["id"]))
    for game in final[:max_games]:
        try:
            payload=fetch(URL+str(game["espn_id"]))
            entries,flags=explicit_rows(payload,game,identity,now)
            for k,v in flags.items():qa[k]+=v
        except (ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
            qa["unverified_boxscore"]+=1
            continue
        for e in entries:
            key=(e["game_id"],e["player_id"])
            if key not in retained:retained[key]=e
        checked.add(game["id"]);processed+=1
    # A contradictory active appearance is never silently labeled DNP.
    played={(r.get("game_id"),r.get("id")) for r in live.get("rows",[])
            if isinstance(r,dict) and r.get("played") is True}
    conflict=played.intersection(retained)
    if conflict:raise ValueError("Explicit DNP conflicts with played FP: "+str(len(conflict)))
    return {"schema_version":1,"status":"research_only_not_deployed",
       "adopt_on_site":False,"updated_at_utc":stamp(now),
       "checked_final_game_ids":sorted(checked),
       "events":sorted(retained.values(),key=lambda e:(e["game_id"],e["player_id"])),
       "qa":dict(qa),"source":"ESPN full game summary; only explicit didNotPlay true",
       "warning":"Unlisted players remain UNKNOWN; DNP is NOT a medical diagnosis; no fantasy FP mutation"},{
       "new_games_checked":processed,"confirmed_explicit_dnp_total":len(retained),"qa":dict(qa)}

def fetch_json(url):
    if not url.startswith(URL) or not url[len(URL):].isdigit():
        raise ValueError("Unexpected endpoint")
    req=Request(url,headers={"User-Agent":"NBA-Season-Lab/1.6 public-research"})
    with urlopen(req,timeout=20) as res:
        raw=res.read(2000001)
        if len(raw)>2000000:raise ValueError("Oversized ESPN boxscore")
    return json.loads(raw)

def run():
    read=lambda p:json.loads((DATA/p).read_text(encoding="utf8"))
    path=DATA/"explicit_dnp_research.json"
    old=read(path.name) if path.exists() else {}
    result,summary=gather(read("live.json"),read("identity.json"),old,
                          fetch_json,datetime.now(timezone.utc))
    if result!=old:
        tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(result,ensure_ascii=False,
              separators=(",",":")),encoding="utf8");tmp.replace(path)
    return summary
if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
