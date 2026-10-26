"""PIT independent ESPN team roster evidence, research-only.

Public ESPN team roster membership is not game-day active eligibility. Missing
players and failed sources remain UNKNOWN. Only verified matching ESPN athlete
IDs from independent, named, active NBA boxscores are considered high confidence.
No account/Firestore, prices, or model publication.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from urllib.request import Request, urlopen
import json, re
from src.sync import DATA
from src.espn_adapter import club
from src.explicit_dnp_research import norm, identity_aliases, observed_active_espn_ids
from src.rolling_decision_research import stamp, instant, canonical_hash
from src.live_calendar_fallback import TEAMS

URL="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{}/roster"
STATUS="research_only_not_deployed"
ESPN_TEAMS={"ATL":"1","BOS":"2","BKN":"17","CHA":"30","CHI":"4","CLE":"5",
 "DAL":"6","DEN":"7","DET":"8","GSW":"9","HOU":"10","IND":"11","LAC":"12",
 "LAL":"13","MEM":"29","MIA":"14","MIL":"15","MIN":"16","NOP":"3",
 "NYK":"18","OKC":"25","ORL":"19","PHI":"20","PHX":"21","POR":"22",
 "SAC":"23","SAS":"24","TOR":"28","UTA":"26","WAS":"27"}
assert set(ESPN_TEAMS)==TEAMS and len(set(ESPN_TEAMS.values()))==30

def fetch(url):
    if url not in {URL.format(i) for i in ESPN_TEAMS.values()}:
        raise ValueError("Unknown public roster source")
    req=Request(url,headers={"User-Agent":"NBA-Season-Lab/1.8 noncommercial research"})
    with urlopen(req,timeout=12) as response:
        raw=response.read(1000001)
    if len(raw)>1000000:
        raise ValueError("Oversized public roster response")
    return json.loads(raw)

def athletes(payload):
    """ESPN v2 roster may use flat athletes or grouped positions."""
    value=payload.get("athletes")
    if not isinstance(value,list) or not value:
        raise ValueError("Missing ESPN athletes")
    out=[]
    for entry in value:
        if not isinstance(entry,dict):raise ValueError("Malformed ESPN roster")
        group=entry.get("items")
        if isinstance(group,list):out.extend(group)
        else:out.append(entry)
    if not 8<=len(out)<=35:
        raise ValueError("Implausible ESPN team roster size")
    seen=set()
    clean=[]
    for p in out:
        ident=str(p.get("id") or "")
        name=p.get("displayName") or p.get("fullName") or ""
        if not ident.isdigit() or not norm(name) or ident in seen:
            raise ValueError("Invalid or repeated ESPN person ID")
        seen.add(ident)
        clean.append({"espn_person_id":ident,"display_name":str(name).strip()})
    return sorted(clean,key=lambda x:x["espn_person_id"])

def capture(catalog, identity, live, provider, now):
    if now.utcoffset() is None:raise ValueError("Aware capture required")
    now=now.astimezone(timezone.utc)
    if (live.get("schema_version")!=4 or
        live.get("schedule_quality",{}).get("freshness")!="fresh" or
        not live.get("games") or not live.get("rows")):
        raise ValueError("No independently validated live source")
    if instant(live["updated_at_utc"])>now or now-instant(live["updated_at_utc"])>timedelta(hours=8):
        raise ValueError("Live input stale/future")
    aliases,_=identity_aliases(identity,catalog)
    links=observed_active_espn_ids(live,identity,catalog)
    cat={p["id"]:p for p in catalog["players"]}
    if len(cat)<400:raise ValueError("Full catalog missing")
    out=[]; qa=Counter();all_matches=[]
    for team,tid in sorted(ESPN_TEAMS.items()):
        url=URL.format(tid)
        try:
            raw=provider(url)
            reported=((raw.get("team") or {}).get("abbreviation") or "")
            if reported and club(reported)!=team:
                raise ValueError("Team roster source mismatch")
            items=athletes(raw)
        except (KeyError,TypeError,ValueError,OSError,TimeoutError) as exc:
            qa["unavailable_or_invalid_team"]+=1
            out.append({"club":team,"url":url,"source_status":"invalid_or_unavailable",
                        "source_first_seen_at_utc":stamp(now),"athletes":[]})
            continue
        team_rows=[]
        for a in items:
            en=norm(a["display_name"])
            named=aliases.get(en)
            from_id=links.get(a["espn_person_id"])
            evidence=None
            pid=None
            if from_id:
                if named and named[0]!=from_id:
                    qa["independent_ID_name_conflict"]+=1
                elif not named or named[0]==from_id:
                    pid=from_id;evidence="previously_named_played_ESPN_person_ID"
            elif named:
                pid=named[0];evidence="unique_english_name_only"
            if pid not in cat:pid=None;evidence=None
            row={**a,"sportsru_player_id":pid,"identity_method":evidence,
                 "catalog_team_at_capture":cat[pid]["team"] if pid else None}
            if pid and cat[pid]["team"]!=team:
                qa["catalog_team_conflict"]+=1
            if pid:
                qa[evidence]+=1
                all_matches.append({"club":team,**row})
            else:qa["identity_unknown"]+=1
            team_rows.append(row)
        out.append({"club":team,"url":url,"source_status":"parsed_not_game_day_eligibility",
                    "source_first_seen_at_utc":stamp(now),"athletes":team_rows})
        qa["teams_parsed"]+=1
    # Never claim full official coverage when even one team endpoint failed.
    duplicates=defaultdict(set)
    for row in all_matches:
        duplicates[row["sportsru_player_id"]].add(row["club"])
    disputed={p for p,clubs in duplicates.items() if len(clubs)>1}
    if disputed:
        for team in out:
            for a in team["athletes"]:
                if a["sportsru_player_id"] in disputed:
                    a["identity_method"]="conflicting_ESPN_roster_teams_excluded"
                    a["sportsru_player_id"]=None
        qa["cross_team_player_identity_conflict"]=len(disputed)
    result={"schema_version":1,"status":STATUS,"model_status":STATUS,"adopt_on_site":False,
            "captured_at_utc":stamp(now),"source":"ESPN public team roster current snapshot",
            "publication_time_unknown":True,"game_day_eligibility_verified":False,
            "all_teams_available":qa["teams_parsed"]==30,
            "teams":out,"qa":dict(qa),
            "limitations":["Current team roster is not confirmed active players for any scheduled match.",
             "An unlisted player is UNKNOWN, never a DNP, injury or ineligibility.",
             "Endpoint errors are retained explicitly, never silently skipped.",
             "Only athlete identity from named active player-game is independently linked; names are weaker.",
             "First observed clock is not the original ESPN publication clock."]}
    result["snapshot_hash_sha256"]=canonical_hash({"teams":result["teams"],"captured":result["captured_at_utc"]})
    return result

def run():
    from zoneinfo import ZoneInfo
    now=datetime.now(timezone.utc);day=now.astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()
    directory=DATA/"espn_roster_pit";target=directory/(day+".json")
    if target.exists():
        return {"status":STATUS,"capture":"already_exists_not_overwritten","day":day}
    def load(n):return json.loads((DATA/n).read_text(encoding="utf8"))
    value=capture(load("catalog.json"),load("identity.json"),load("live.json"),fetch,now)
    directory.mkdir(parents=True,exist_ok=True)
    tmp=target.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(target)
    return {"status":STATUS,"day":day,"capture":"created","qa":value["qa"],
            "all_teams_available":value["all_teams_available"],
            "adopt_on_site":False}

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
