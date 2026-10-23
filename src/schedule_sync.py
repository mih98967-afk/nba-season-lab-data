"""Public NBA 2026/27 calendar with UTC tipoff and Moscow week boundaries.
ESPN is an unofficial free fallback. Unassigned NBA Cup fixtures are NEVER fabricated.
No private credentials, profiles, Sports.ru prices or fantasy rosters.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"data"/"schedule.json"
ESPN="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
FIRST,LAST=dt.date(2026,10,20),dt.date(2027,4,11)
UTC,MSK,ET=dt.timezone.utc,ZoneInfo("Europe/Moscow"),ZoneInfo("America/New_York")
TEAMS=set("ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split())
ALIASES={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}

def fetch_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.2 (noncommercial public schedule)","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as response:
        raw=response.read(14_000_001)
        if len(raw)>14_000_000:raise ValueError("Oversized ESPN response")
        return json.loads(raw)

def moscow_week(utc):
    """Calendar Monday 00:00 MSK; separate from Monday 15:00 transfer deadline."""
    value=dt.datetime.fromisoformat(utc.replace("Z","+00:00"))
    if value.utcoffset()!=dt.timedelta(0):raise ValueError("Expected UTC game time")
    local=value.astimezone(MSK).date()
    return (local-dt.timedelta(days=local.weekday())).isoformat()

def parse_events(payload):
    if not isinstance(payload.get("events"),list):raise ValueError("Missing ESPN events")
    out=[]
    for event in payload["events"]:
        if (event.get("season") or {}).get("type")!=2:continue
        ident=str(event.get("id") or "")
        if not ident.isdigit():continue
        competitors=((event.get("competitions") or [{}])[0]).get("competitors") or []
        clubs={}
        for competitor in competitors:
            code=str((competitor.get("team") or {}).get("abbreviation") or "").upper()
            clubs[competitor.get("homeAway")]=ALIASES.get(code,code)
        if clubs.get("home") not in TEAMS or clubs.get("away") not in TEAMS or clubs["home"]==clubs["away"]:continue
        try:
            start=dt.datetime.fromisoformat(str(event["date"]).replace("Z","+00:00"))
            if start.tzinfo is None:raise ValueError("Naive time")
            start=start.astimezone(UTC)
        except (KeyError,ValueError,TypeError):continue
        east=start.astimezone(ET).date()
        if not FIRST<=east<=LAST:continue
        state=((event.get("status") or {}).get("type") or {})
        name=str(state.get("name") or "").lower()
        status=("canceled" if "cancel" in name else
                "postponed" if "postpon" in name else
                "final" if state.get("completed") else
                "live" if state.get("state")=="in" else "scheduled")
        iso=start.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"id":"espn_"+ident,"espn_id":ident,"utc":iso,"epoch":int(start.timestamp()*1000),
                    "home":clubs["home"],"away":clubs["away"],"status":status,
                    "source":"ESPN public scoreboard","url":ESPN+"?dates="+east.strftime("%Y%m%d"),
                    "msk_date":start.astimezone(MSK).date().isoformat(),
                    "msk_week":moscow_week(iso),"et_date":east.isoformat()})
    return out

def segments(first=FIRST,last=LAST,length=12):
    day=first
    while day<=last:
        end=min(last,day+dt.timedelta(days=length-1))
        yield day,end
        day=end+dt.timedelta(days=1)

def assemble(batches,now=None):
    now=now or dt.datetime.now(UTC)
    items={}
    for batch in batches:
        for game in parse_events(batch):
            previous=items.get(game["id"])
            if previous and (previous["home"],previous["away"])!=(game["home"],game["away"]):
                raise ValueError("ESPN event ID changed matchup: "+game["id"])
            items[game["id"]]=game
    games=sorted(items.values(),key=lambda g:(g["epoch"],g["id"]))
    active=[g for g in games if g["status"]!="canceled"]
    counts=Counter(t for g in active for t in (g["home"],g["away"]))
    pair_keys=set()
    team_games=defaultdict(list)
    for g in active:
        signature=(g["et_date"],g["home"],g["away"])
        if signature in pair_keys:raise ValueError("Duplicate matchup "+str(signature))
        pair_keys.add(signature)
        for team in (g["home"],g["away"]):team_games[team].append(g)
    for team,team_list in team_games.items():
        team_list.sort(key=lambda g:g["epoch"])
        previous=None
        for g in team_list:
            consecutive=(previous is not None and
                         (dt.date.fromisoformat(g["et_date"])-dt.date.fromisoformat(previous)).days==1)
            g["home_b2b" if g["home"]==team else "away_b2b"]=consecutive
            previous=g["et_date"]
    for g in games:
        g.setdefault("home_b2b",False)
        g.setdefault("away_b2b",False)
    quality={
        "scheduled_or_played_games":len(active),"teams":len(counts),
        "team_games_min":min(counts.values(),default=0),
        "team_games_max":max(counts.values(),default=0),
        "unassigned_or_unavailable_games":max(0,1230-len(active)),
        "last_known_game_utc":active[-1]["utc"] if active else None,
        "utc_timestamps":all(g["utc"].endswith("Z") for g in games),
        "week_timezone":"Europe/Moscow","week_starts":"Monday 00:00 MSK",
        "transfer_deadline":"Monday 15:00 MSK (not calendar week boundary)",
        "cup_window_requires_review":"2026-12-04..2026-12-10",
        "coverage":"Some NBA Cup games have unassigned opponents until group play ends"}
    if len(active)<1100 or len(counts)!=30 or min(counts.values())<70 or len(active)>1230:
        raise ValueError("ESPN full-calendar validation failed: "+json.dumps(quality))
    if not quality["utc_timestamps"]:raise ValueError("Non-UTC start time")
    return {"schema_version":1,"status":"verified_public_calendar_with_known_gaps",
            "updated_at_utc":now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source":ESPN,
            "source_policy":"ESPN unofficial; full-source check daily; NBA.com schedule for independent QA",
            "timezone":"UTC","fantasy_timezone":"Europe/Moscow",
            "regular_season_start_et":FIRST.isoformat(),"regular_season_end_et":LAST.isoformat(),
            "completeness":quality,"games":games}

def refresh(fetch=fetch_json,now=None,force=False):
    now=now or dt.datetime.now(UTC)
    old=None
    if OUTPUT.exists():
        try:old=json.loads(OUTPUT.read_text(encoding="utf8"))
        except (OSError,ValueError):pass
    if not force and old and old.get("status")=="verified_public_calendar_with_known_gaps":
        try:
            age=now-dt.datetime.fromisoformat(old["updated_at_utc"].replace("Z","+00:00"))
            if dt.timedelta(0)<=age<dt.timedelta(hours=20):
                return {"result":"fresh_cache","games":len(old.get("games",[]))}
        except (KeyError,ValueError,TypeError):pass
    batches=[]
    for first,last in segments(length=1):
        query=urllib.parse.urlencode({"dates":first.strftime("%Y%m%d"),"limit":100})
        batches.append(fetch(ESPN+"?"+query))
    result=assemble(batches,now)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    tmp=OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(OUTPUT)
    return {"result":"updated","games":len(result["games"]),"quality":result["completeness"]}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args()
    print(json.dumps(refresh(force=args.force),ensure_ascii=False,indent=2))
