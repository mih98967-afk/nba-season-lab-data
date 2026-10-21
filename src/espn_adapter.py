"""Strict parser of ESPN's free NBA boxscore and scoreboard responses.

ESPN is a fallback only when official cdn.nba.com is unavailable.
A final game, score, complete named stat columns and both teams are required.
"""
from __future__ import annotations
import datetime as dt
import re

TEAM_MAP={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}

def club(name):
    value=str(name or "").upper()
    return TEAM_MAP.get(value,value)

def parse_time(raw):
    s=str(raw or "").strip().upper()
    if s in ("","--","DNP","DND","N/A"):return 0.
    if ":" in s:
        a,b=s.split(":",1)
        return float(a)+float(b)/60.
    if s.startswith("PT"):
        a=re.search(r"(\d+)M",s)
        b=re.search(r"(\d+(?:\.\d+)?)S",s)
        return (float(a.group(1)) if a else 0)+(float(b.group(1))/60 if b else 0)
    return float(s)

def pair(v):
    m=re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*",str(v))
    if not m:raise ValueError("Malformed ESPN shooting stats: "+str(v))
    a,b=map(int,m.groups())
    if a>b:raise ValueError("Made shots exceed attempts")
    return a,b

def number(v):
    s=str(v).strip()
    if not re.fullmatch(r"\d+(?:\.0+)?",s):raise ValueError("Malformed ESPN counting stat: "+s)
    return int(float(s))

def parse_summary(payload,game):
    """Return rows as in nba_box; reject incomplete payloads, never impute missing data."""
    box=(payload.get("boxscore") or {}).get("players") or []
    comp=((payload.get("header") or {}).get("competitions") or [{}])[0]
    competitors=comp.get("competitors") or []
    sides={}
    for c in competitors:
        side=c.get("homeAway")
        team=club((c.get("team") or {}).get("abbreviation"))
        try:score=number(c["score"])
        except (KeyError,ValueError):continue
        if side in ("home","away") and team:sides[side]=(team,score)
    if set(sides)!={"home","away"} or sides["home"][1]==sides["away"][1]:
        raise ValueError("No trustworthy final ESPN score")
    if (sides["home"][0]!=game.get("home") or
        sides["away"][0]!=game.get("away")):
        raise ValueError("ESPN game teams don't match scoreboard")
    if len(box)!=2:raise ValueError("ESPN summary must contain two teams")
    expected={"MIN","FG","FT","REB","AST","STL","BLK","TO","PF","PTS"}
    result=[];seen=set();teams_seen=set()
    for side in box:
        code=club((side.get("team") or {}).get("abbreviation"))
        if code not in (sides["home"][0],sides["away"][0]):raise ValueError("Unknown ESPN team")
        teams_seen.add(code)
        home=code==sides["home"][0]
        won=sides["home"][1]>sides["away"][1] if home else sides["home"][1]<sides["away"][1]
        for group in side.get("statistics") or []:
            names=group.get("names") or group.get("labels") or group.get("keys") or []
            name_up=[str(n).upper().strip() for n in names]
            if not expected.issubset(name_up):
                if group.get("athletes"):raise ValueError("ESPN stat schema missing mandatory columns")
                continue
            for entry in group.get("athletes") or []:
                athlete=entry.get("athlete") or {}
                name=(athlete.get("displayName") or athlete.get("fullName") or "").strip()
                if not name:continue
                if entry.get("didNotPlay"):continue
                values=entry.get("stats") or []
                if len(values)!=len(names):raise ValueError("ESPN row length inconsistent")
                v=dict(zip(name_up,values))
                minute=parse_time(v["MIN"])
                if minute<=0:continue
                fg, fga=pair(v["FG"]);ft,fta=pair(v["FT"])
                tg,tga=pair(v["3PT"]) if "3PT" in v else (0,0)
                st={"min":minute,"pts":number(v["PTS"]),"fgm":fg,"fga":fga,"ftm":ft,"fta":fta,
                    "reb":number(v["REB"]),"ast":number(v["AST"]),
                    "stl":number(v["STL"]),"blk":number(v["BLK"]),
                    "tov":number(v["TO"]),"pf":number(v["PF"]),
                    "three_m":tg,"three_a":tga}
                if st["three_m"]>fg or st["three_a"]>fga:raise ValueError("Invalid three-point line")
                # Sports.ru: extra credit for shots made and debit for attempts
                pts=(st["pts"]+st["reb"]+st["ast"]+st["stl"]+st["blk"]+fg+ft-fga-fta
                     -st["pf"]-2*st["tov"])
                pts+=2 if minute>=10 else 1
                pts+=(2 if home else 3) if won else (-3 if home else -2)
                key=(code,name)
                if key in seen:continue
                seen.add(key)
                result.append({"name":name,"espn_person_id":athlete.get("id"),"team":code,
                               "minutes":round(minute,3),"played":True,"fp":float(pts),"box":st})
    if teams_seen!={sides["home"][0],sides["away"][0]} or len(result)<10:
        raise ValueError("Too few ESPN active player rows")
    return result

def parse_scoreboard(payload):
    """Parse scheduled, live and completed NBA regular-season games."""
    out=[]
    for ev in payload.get("events") or []:
        if (ev.get("season") or {}).get("type") not in (None,2):continue
        comp=(ev.get("competitions") or [{}])[0]
        pair_map={}
        for t in comp.get("competitors") or []:
            side=t.get("homeAway")
            if side in ("home","away"):
                pair_map[side]=club((t.get("team") or {}).get("abbreviation"))
        if len(pair_map)!=2 or not pair_map["home"] or not pair_map["away"]:continue
        event_id=str(ev.get("id") or "")
        when=str(ev.get("date") or "")
        try:
            parsed=dt.datetime.fromisoformat(when.replace("Z","+00:00"))
            if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=dt.timezone.utc)
            parsed=parsed.astimezone(dt.timezone.utc)
        except ValueError:continue
        if not event_id:continue
        completed=bool(((ev.get("status") or {}).get("type") or {}).get("completed"))
        in_progress=(((ev.get("status") or {}).get("type") or {}).get("state")=="in")
        utc=parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append({"id":"espn_"+event_id,"espn_id":event_id,"utc":utc,
                    "epoch":int(parsed.timestamp()*1000),"home":pair_map["home"],
                    "away":pair_map["away"],
                    "status":"final" if completed else "live" if in_progress else "scheduled",
                    "source":"ESPN scoreboard"})
    return out
