"""Research-only historical NBA tipoff times: ESPN UTC verified against SportsDataverse
regular-season final-game IDs, date and teams. No fabricated tipoffs or Firestore use.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,date,timedelta,timezone
from zoneinfo import ZoneInfo
import json,pathlib,time,urllib.parse,urllib.request
from src.history import get_csv,parse_schedule,SCHEDULES
from src.sync import DATA

ESPN="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ET=ZoneInfo("America/New_York")
MSK=ZoneInfo("Europe/Moscow")
PERIODS={
    "2024/25":(2025,date(2024,10,22),date(2025,4,13)),
    "2025/26":(2026,date(2025,10,21),date(2026,4,12))
}
ALIASES={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}
OUT=DATA/"historical_tipoffs.json"

def public_json(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.3 (noncommercial, historical validation)",
                                             "Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=28) as res:
        raw=res.read(10_000_001)
        if len(raw)>10_000_000:raise ValueError("ESPN response too large")
    return json.loads(raw)

def days(first,last):
    while first<=last:
        yield first
        first+=timedelta(days=1)

def iso_parse(raw):
    value=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    if value.tzinfo is None:raise ValueError("Time has no timezone")
    return value.astimezone(timezone.utc)

def week_msk(instant):
    local=instant.astimezone(MSK).date()
    return (local-timedelta(days=local.weekday())).isoformat()

def games_espn(payload):
    events=payload.get("events")
    if not isinstance(events,list):raise ValueError("ESPN scoreboard schema missing events")
    found=[]
    for ev in events:
        if (ev.get("season") or {}).get("type")!=2:continue
        if not ((ev.get("status") or {}).get("type") or {}).get("completed"):continue
        teams={}
        for item in ((ev.get("competitions") or [{}])[0]).get("competitors") or []:
            side=item.get("homeAway")
            code=str((item.get("team") or {}).get("abbreviation") or "").upper()
            if side in ("home","away"):teams[side]=ALIASES.get(code,code)
        if not teams.get("home") or not teams.get("away"):continue
        # ESPN sometimes marks All-Star events as season type 2; exclude non-NBA clubs.
        from src.schedule_sync import TEAMS
        if teams["home"] not in TEAMS or teams["away"] not in TEAMS or teams["home"]==teams["away"]:continue
        try:t=iso_parse(ev.get("date"))
        except (ValueError,TypeError):continue
        event_id=str(ev.get("id") or "")
        if not event_id.isdigit():continue
        east=t.astimezone(ET).date().isoformat()
        found.append({"espn_id":event_id,"utc":t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "et_date":east,"home":teams["home"],"away":teams["away"],
                      "msk_week":week_msk(t),
                      "msk_date":t.astimezone(MSK).date().isoformat()})
    return found

def reconcile(sportsdataverse,espn_rows,period):
    independent=parse_schedule(sportsdataverse)
    if len(independent)!=1230:raise ValueError(period+": SportsDataverse schedule not 1230 regular final games")
    idx={};dupes=[]
    for g in espn_rows:
        key=(g["et_date"],g["home"],g["away"])
        if key in idx:dupes.append(key)
        idx[key]=g
    if dupes:raise ValueError(period+": duplicate ESPN events: "+str(dupes[:3]))
    matches={};not_found=[];used=set()
    for gid,(day,home,away,hs,as_) in independent.items():
        # The independent game date is a US/ET date only, never assign it to UTC.
        event=idx.get((day,home,away))
        if event is None:
            not_found.append({"game_id":gid,"us_date":day,"home":home,"away":away})
            continue
        if event["espn_id"] in used:raise ValueError("ESPN ID re-used")
        used.add(event["espn_id"])
        matches[gid]={"utc":event["utc"],"msk_week":event["msk_week"],
                      "msk_date":event["msk_date"],"et_date":event["et_date"],
                      "espn_id":event["espn_id"],"home":home,"away":away}
    if len(matches)<1100:
        raise ValueError(period+": historical schedule coverage under 1100: "+str(len(matches)))
    precision=("exact_msk_complete" if len(matches)==1230 else "partial_utc_not_eligible_for_weekly")
    return matches,{"sportsdataverse_games":len(independent),"espn_completed_unique":len(idx),
                    "matched_utc_tipoffs":len(matches),"missing_utc_tipoffs":len(not_found),
                    "precision":precision,"unmatched_examples":not_found[:25],
                    "calendar_semantics":"UTC to Europe/Moscow, Monday 00:00 MSK"}

def collect(fetch=public_json,get_schedule=None):
    if get_schedule is None:get_schedule=lambda yr:get_csv(SCHEDULES.format(yr))
    report={"schema_version":1,"status":"research_only_not_deployed",
            "updated_at_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "scope":"historical completed NBA regular season games; no live schedule modifications",
            "source":"ESPN public scoreboard, independently matched by date and both teams to SportsDataverse NBA schedule",
            "limitation":"This is retrospective true tipoff, NOT evidence the final dates were known before each forecast",
            "seasons":{},"qa":{}}
    for period,(year,start,end) in PERIODS.items():
        events=[]
        for day in days(start,end):
            query=urllib.parse.urlencode({"dates":day.strftime("%Y%m%d"),"limit":100})
            error=None
            for attempt in range(3):
                try:
                    events.extend(games_espn(fetch(ESPN+"?"+query)))
                    error=None
                    break
                except Exception as exc:
                    error=exc
                    if attempt<2:time.sleep(1+attempt*2)
            if error:raise RuntimeError("ESPN "+str(day)+": "+str(error)) from error
        fixtures,qa=reconcile(get_schedule(year),events,period)
        report["seasons"][period]=fixtures
        report["qa"][period]=qa
    if all(report["qa"][k]["precision"]=="exact_msk_complete" for k in PERIODS):
        report["calendar_status"]="fully_matched_historical_tipoffs"
    else:
        report["calendar_status"]="partial_historical_tipoffs_do_not_run_weekly_as_exact"
    return report

def execute():
    v=collect()
    OUT.parent.mkdir(exist_ok=True,parents=True)
    tmp=OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(v,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    tmp.replace(OUT)
    return {"calendar_status":v["calendar_status"],"qa":v["qa"],"file":str(OUT)}

if __name__=="__main__":print(json.dumps(execute(),ensure_ascii=False,indent=2))
