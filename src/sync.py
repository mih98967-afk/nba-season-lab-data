#!/usr/bin/env python3
"""NBA Season Lab: public official NBA game feed. No private accounts or tokens."""
from __future__ import annotations
import datetime as dt
from collections import Counter
import json
import pathlib
import re
import unicodedata
import urllib.request
from zoneinfo import ZoneInfo
from src.espn_adapter import parse_summary, parse_scoreboard
from src.live_calendar_fallback import verified_fallback, TEAMS

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
NBA_SCHEDULE="https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
NBA_BOX="https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{}.json"
ESPN="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={}&limit=100"
CATALOG="https://nba-season-lab.web.app/data/base.json"
ET=ZoneInfo("America/New_York")
START=dt.date(2026,10,20)
CLUBS={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}

def http_json(url,timeout=22):
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.1 (noncommercial public statistics)","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        b=r.read(14_000_001)
        if len(b)>14_000_000: raise ValueError("Response too large")
        return json.loads(b)

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def abbr(t): return CLUBS.get(str(t or "").upper(),str(t or "").upper())

def iso(s):
    if not s: raise ValueError("Missing date")
    v=dt.datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if v.tzinfo is None:v=v.replace(tzinfo=ET)
    return v.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def epoch(s):return int(dt.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()*1000)

def minutes(s):
    if isinstance(s,(float,int)):return float(s)
    s=str(s or "").upper()
    if s.startswith("PT"):
        m=re.search(r"(\d+)M",s);v=re.search(r"(\d+(?:\.\d+)?)S",s)
        return (int(m.group(1)) if m else 0)+(float(v.group(1))/60 if v else 0)
    if ":" in s:
        m,v=s.split(":",1);return float(m)+float(v)/60
    return float(s) if s else 0.

REQ={"points":"pts","fieldGoalsMade":"fgm","fieldGoalsAttempted":"fga",
     "freeThrowsMade":"ftm","freeThrowsAttempted":"fta","reboundsTotal":"reb",
     "assists":"ast","steals":"stl","blocks":"blk","turnovers":"tov","foulsPersonal":"pf"}

def fantasy_fp(box,home,won):
    b={k:float(box[k]) for k in ("pts","fgm","fga","ftm","fta","reb","ast","stl","blk","tov","pf")}
    if any(x<0 for x in b.values()) or b["fgm"]>b["fga"] or b["ftm"]>b["fta"]:
        raise ValueError("Invalid basketball stat line")
    if float(box["min"])<=0:return 0.
    score=(b["pts"]+b["reb"]+b["ast"]+b["stl"]+b["blk"]+b["fgm"]+b["ftm"]
          -b["fga"]-b["fta"]-b["pf"]-2*b["tov"])
    score+=2 if float(box["min"])>=10 else 1
    score+=(2 if home else 3) if won else (-3 if home else -2)
    return round(score,2)

def nba_schedule(payload):
    sched=(payload.get("leagueSchedule") or payload.get("scheduleLeagueV2") or {})
    dates=sched.get("gameDates")
    if not isinstance(dates,list):raise ValueError("NBA schedule schema missing gameDates")
    out=[]
    for day in dates:
        for g in day.get("games") or []:
            gid=str(g.get("gameId",""))
            if not re.fullmatch(r"002\d{7}",gid):continue
            h=abbr((g.get("homeTeam") or {}).get("teamTricode"))
            a=abbr((g.get("awayTeam") or {}).get("teamTricode"))
            if not h or not a:continue
            try:t=iso(g.get("gameDateTimeUTC") or g.get("gameDateTimeEst"))
            except Exception:continue
            if not START<=dt.date.fromisoformat(t[:10])<=dt.date(2027,5,10):continue
            status=int(g.get("gameStatus") or 1)
            out.append({"id":gid,"nba_game_id":gid,"utc":t,"epoch":epoch(t),
                        "home":h,"away":a,"status":"final" if status==3 else "live" if status==2 else "scheduled",
                        "source":"NBA official schedule","url":NBA_SCHEDULE})
    if len(out)<500:raise ValueError("Suspiciously short NBA schedule")
    return out

def nba_box(payload):
    g=payload.get("game") or {}
    if int(g.get("gameStatus") or 0)!=3:raise ValueError("Boxscore not final")
    h=g.get("homeTeam") or {};a=g.get("awayTeam") or {}
    hs=h.get("score");as_=a.get("score")
    if hs is None or as_ is None or int(hs)==int(as_):raise ValueError("Missing final score")
    rows=[]
    for team,home in ((h,True),(a,False)):
        players=team.get("players")
        if not isinstance(players,list) or not players:raise ValueError("Incomplete NBA boxscore")
        for p in players:
            st=p.get("statistics")
            if not isinstance(st,dict):continue
            m=minutes(st.get("minutes") or st.get("minutesCalculated"))
            if m<=0:continue
            if not set(REQ).issubset(st):raise ValueError("NBA stat keys changed; rejecting game")
            box={"min":m,**{v:st[k] for k,v in REQ.items()},
                 "three_m":st.get("threePointersMade",0),"three_a":st.get("threePointersAttempted",0)}
            if any(box[k] is None for k in REQ.values()):raise ValueError("Null NBA stats")
            name=(p.get("name") or (str(p.get("firstName") or "")+" "+str(p.get("familyName") or ""))).strip()
            if not name:continue
            won=int(hs)>int(as_) if home else int(as_)>int(hs)
            rows.append({"name":name,"nba_person_id":p.get("personId"),"team":abbr(team.get("teamTricode")),
                         "minutes":round(m,2),"played":True,"fp":fantasy_fp(box,home,won),"box":box})
    if len(rows)<10:raise ValueError("Too few active players in NBA game")
    return rows

def scoreboard(payload):
    out=[]
    for e in payload.get("events") or []:
        if (e.get("season") or {}).get("type") not in (None,2):continue
        if not ((e.get("status") or {}).get("type") or {}).get("completed"):continue
        comp=(e.get("competitions") or [{}])[0];clubs={}
        for t in comp.get("competitors") or []:clubs[t.get("homeAway")]=abbr((t.get("team") or {}).get("abbreviation"))
        if not clubs.get("home") or not clubs.get("away"):continue
        try:t=iso(e["date"])
        except Exception:continue
        out.append({"id":"espn_"+str(e.get("id")),"espn_id":str(e.get("id")),"utc":t,"epoch":epoch(t),
                    "home":clubs["home"],"away":clubs["away"],"status":"final","source":"ESPN scoreboard"})
    return out

def load(path,default):
    try:return json.loads(path.read_text(encoding="utf8"))
    except (FileNotFoundError,json.JSONDecodeError):return default

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value,ensure_ascii=False,separators=(",",":")),encoding="utf8");tmp.replace(path)


def official_calendar_quality(games, now):
    """Validate a full NBA CDN regular-season schedule before replacing a known calendar.

    'validated_at_utc' is the time *we checked* the feed, not an asserted
    original NBA publication time.
    """
    if not 1100 <= len(games) <= 1230:
        raise ValueError("NBA CDN calendar lacks full-season coverage")
    ids=set(); matchups=set(); appearances=Counter()
    for g in games:
        gid=g.get("id")
        if not isinstance(gid,str) or not re.fullmatch(r"002\\d{7}",gid) or gid in ids:
            raise ValueError("Duplicate/invalid official NBA game ID")
        ids.add(gid)
        home,away=g.get("home"),g.get("away")
        if home not in TEAMS or away not in TEAMS or home==away:
            raise ValueError("Invalid official NBA matchup")
        if g.get("status") not in ("scheduled","live","final"):
            raise ValueError("Invalid official NBA game status")
        moment=dt.datetime.fromisoformat(g["utc"].replace("Z","+00:00"))
        if moment.utcoffset()!=dt.timedelta(0) or g.get("epoch")!=epoch(g["utc"]):
            raise ValueError("Invalid official NBA UTC time/epoch")
        matchup=(moment.astimezone(ET).date().isoformat(),home,away)
        if matchup in matchups:raise ValueError("Duplicate same-day official NBA fixture")
        matchups.add(matchup);appearances.update((home,away))
    if set(appearances)!=TEAMS or min(appearances.values())<70:
        raise ValueError("Official NBA calendar has missing clubs/season coverage")
    gaps=max(0,1230-len(games))
    stamp=now.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
    return {"source":NBA_SCHEDULE,"validated_at_utc":stamp,"checked_at_utc":stamp,
            "source_published_at_utc":None,"age_hours":0.0,"freshness":"fresh",
            "games":len(games),"teams":len(appearances),"unassigned_games":gaps,
            "complete":not gaps,"warning":"Unscheduled NBA Cup games are never invented"}


def select_live_schedule(fetch, now, old, verified_calendar):
    """Prefer current validated sources over nonempty old live.schedule.

    Selection is read-only with respect to data/schedule.json. On total source
    failure, keep the last known fixture list but explicitly mark it unverified.
    """
    warnings=[]
    try:
        official=nba_schedule(fetch(NBA_SCHEDULE))
        quality=official_calendar_quality(official,now)
        return official,NBA_SCHEDULE,quality,f"ok: {len(official)}",warnings
    except Exception as exc:
        warnings.append("NBA schedule: "+str(exc)[:150])
    try:
        verified,quality=verified_fallback(verified_calendar,now)
        warnings.append("NBA CDN unavailable: validated ESPN calendar; age "
                        +str(quality["age_hours"])+"h; NBA Cup gaps "
                        +str(quality["unassigned_games"]))
        return verified,"data/schedule.json",quality,"fallback: verified ESPN full-season calendar",warnings
    except (ValueError,KeyError,TypeError) as exc:
        warnings.append("Full-season fallback rejected: "+str(exc)[:160])
    cached=old.get("schedule")
    if not isinstance(cached,list):cached=[]
    quality={"source":"prior live.json (unverified cache)","validated_at_utc":None,
             "age_hours":None,"freshness":"stale_unverified",
             "games":len(cached),"teams":None,"unassigned_games":None,
             "complete":False,"warning":"No validated current calendar; cached fixtures may be stale"}
    warnings.append("Using unverified last-known calendar; do not infer schedule freshness")
    return list(cached),"last known",quality,"unavailable",warnings


def refresh(fetch=http_json,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    today=now.astimezone(ET).date()
    old=load(DATA/"live.json",{})
    base=load(DATA/"catalog.json",{})
    if not (isinstance(base.get("players"),list) and len(base["players"])>=400):
        base=fetch(CATALOG)
        if not isinstance(base.get("players"),list) or len(base["players"])<400:raise ValueError("Catalog invalid")
        # A stable identity catalog, not a list of private user rosters.
        save(DATA/"catalog.json",base)
    ids={};ambiguous=set()
    for p in base["players"]:
        key=norm(p.get("english"))
        if not key:continue
        if key in ids:ambiguous.add(key)
        ids[key]=p["id"]
    for k in ambiguous:ids.pop(k,None)
    # History matching resolved missing Russian-English identities.
    # Only confirmed high/medium-confidence mappings may reach live feed.
    identity=load(DATA/"identity.json",{})
    for key,metadata in (identity.get("players") or {}).items():
        english=norm(metadata.get("english"))
        if english and key in {p["id"] for p in base["players"]} and metadata.get("confidence") in ("high","medium"):
            if english not in ambiguous and (english not in ids or ids[english]==key):
                ids[english]=key
    warnings=[];providers={"nba_schedule":"unavailable","espn_scoreboard":"unavailable","nba_boxscores":0}
    future,schedule_source,schedule_quality,providers["nba_schedule"],calendar_warnings=select_live_schedule(
        fetch,now,old,load(DATA/"schedule.json",{}))
    warnings.extend(calendar_warnings)
    sched={g["id"]:g for g in future}
    games={g["id"]:g for g in old.get("games") or []}
    for g in future:
        if g["status"]=="final":games[g["id"]]={**games.get(g["id"],{}),**g}
    pair={}
    for g in future:
        etdate=dt.datetime.fromisoformat(g["utc"].replace("Z","+00:00")).astimezone(ET).date().isoformat()
        pair[(etdate,g["home"],g["away"])]=g
    # ESPN is an independent final-status check for the latest NBA dates.
    count=0
    dates=[today-dt.timedelta(days=k) for k in range(10)]
    for day in dates:
        if day<START:continue
        try:
            for g in scoreboard(fetch(ESPN.format(day.strftime("%Y%m%d")))):
                key=(dt.datetime.fromisoformat(g["utc"].replace("Z","+00:00")).astimezone(ET).date().isoformat(),
                     g["home"],g["away"])
                native=pair.get(key)
                if native:
                    g["id"]=native["id"];g["nba_game_id"]=native["id"]
                    sched[g["id"]]={**native,"status":"final","espn_id":g["espn_id"]}
                games[g["id"]]={**games.get(g["id"],{}),**g}
            count+=1
        except Exception as e:
            if len(warnings)<8:warnings.append("ESPN "+str(day)+": "+str(e)[:110])
    if count:providers["espn_scoreboard"]=f"ok: {count} dates"
    stored={(r["game_id"],r["id"]):r for r in old.get("rows") or [] if "game_id" in r and "id" in r}
    unseen=[]
    finals=[g for g in games.values() if g.get("status")=="final" and
            START<=dt.datetime.fromisoformat(g["utc"].replace("Z","+00:00")).date()<=today]
    finals.sort(key=lambda g:g["epoch"],reverse=True)
    complete={gid for gid,pid in stored if pid and gid}
    # Catch up on uncached finals, and recheck recent matches for corrections.
    needs=[g for g in finals if g["id"] not in complete or g["epoch"]>epoch(iso(now.isoformat()))-3*86400000]
    providers["espn_boxscores"]=0
    for g in needs[:42]:
        gid=g.get("nba_game_id") or (g["id"] if re.fullmatch(r"002\d{7}",g["id"]) else None)
        box=None
        source=None
        source_url=None
        if gid:
            try:
                box=nba_box(fetch(NBA_BOX.format(gid)))
                source="NBA official boxscore"
                source_url=NBA_BOX.format(gid)
                providers["nba_boxscores"]+=1
            except Exception as e:
                if len(warnings)<12:warnings.append("Official boxscore "+str(gid)+": "+str(e)[:110])
        if box is None and g.get("espn_id"):
            source_url="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="+str(g["espn_id"])
            try:
                box=parse_summary(fetch(source_url),g)
                source="ESPN final boxscore (fallback)"
                providers["espn_boxscores"]+=1
            except Exception as e:
                if len(warnings)<12:warnings.append("ESPN boxscore "+str(g["espn_id"])+": "+str(e)[:110])
        if box is None:continue
        matched=[]
        for b in box:
            pid=ids.get(norm(b["name"]))
            if not pid:
                if len(unseen)<20:unseen.append(b["name"])
                continue
            matched.append({**b,"id":pid,"game_id":g["id"],"utc":g["utc"],
                            "source":source,"source_url":source_url})
        if not matched:continue
        for k in list(stored):
            if k[0]==g["id"]:del stored[k]
        for row in matched:stored[row["game_id"],row["id"]]=row
        g["matched_count"]=len(matched);g["source"]=source;g["url"]=source_url
    rows=sorted(stored.values(),key=lambda r:(r.get("utc",""),r["id"]))
    sources={"nba_schedule":NBA_SCHEDULE,"nba_boxscore":NBA_BOX.format("{gameId}"),"espn":ESPN.format("{YYYYMMDD}")}
    if not future and not count and not providers["nba_boxscores"] and not rows:
        raise RuntimeError("All NBA sources unavailable; refusing empty replacement")
    is_live=bool(rows and len(rows)>2 and (providers["nba_boxscores"] or providers["espn_boxscores"]))
    stamp=now.isoformat(timespec="seconds").replace("+00:00","Z")
    result={"schema_version":4,"updated_at_utc":stamp if count or providers["nba_boxscores"] or providers["espn_boxscores"] else old.get("updated_at_utc",""),
            "mode":"live_sync" if is_live else "schedule_sync_only",
            "scoreboard_checked_at_utc":stamp if count else old.get("scoreboard_checked_at_utc"),
            "source_status":providers,"schedule_source":schedule_source,
            "schedule_quality":schedule_quality,
            "schedule":sorted(sched.values(),key=lambda g:g["epoch"]),
            "games":sorted(games.values(),key=lambda g:g["epoch"]),"rows":rows,
            "injuries":old.get("injuries",[]),"unmatched":unseen,
            "warnings":warnings[:25],"sources":sources}
    save(DATA/"live.json",result)
    return {"mode":result["mode"],"schedule_quality":schedule_quality,"games":len(games),"rows":len(rows),
            "calendar":len(sched),"providers":providers,"warnings":warnings[:3]}

if __name__=="__main__":
    print(json.dumps(refresh(),ensure_ascii=False,indent=2))
