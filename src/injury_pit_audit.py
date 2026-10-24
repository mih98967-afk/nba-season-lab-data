"""Strict, read-only NBA injury-report point-in-time QA.

Public upstream official-NBA-PDF derived source. Research only. Does NOT assume
unlisted players are healthy or treat the report's final status as outcome.
Assesses coverage, timing, deduplication and identity/fixture match quality.
"""
from __future__ import annotations
import collections,csv,datetime as dt,io,json,re,unicodedata,urllib.request
from src.history import get_csv,BOXSCORES,SCHEDULES,lookup
from zoneinfo import ZoneInfo
from src.sync import DATA

URL="https://raw.githubusercontent.com/Torgo28/NBA_AI_Player_Analysis/main/data/rag/processed/injury_reports.csv"
ET=ZoneInfo("America/New_York")
ALIASES={"NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}

def norm(s):
    s=str(s or "").strip()
    if "," in s:
        last,first=s.split(",",1)
        s=first.strip()+" "+last.strip()
    s=unicodedata.normalize("NFKD",s)
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]"," ",s.lower())).strip()

def event(row):
    try:
        timestamp=dt.datetime.fromisoformat(row["REPORT_TIMESTAMP"])
        if timestamp.utcoffset() is None:return None
        if not row["GAME_DATE"] or len(row["GAME_DATE"])!=10:return None
        day=dt.date.fromisoformat(row["GAME_DATE"])
    except (ValueError,TypeError,KeyError):return None
    raw=row.get("MATCHUP","").upper()
    if "@" not in raw:return None
    away,home=raw.split("@",1)
    team=ALIASES.get(row.get("TEAM_ABBREVIATION","").upper(),row.get("TEAM_ABBREVIATION","").upper())
    away=ALIASES.get(away,away);home=ALIASES.get(home,home)
    if team not in (home,away):return None
    person=norm(row.get("PLAYER_NAME",""))
    if len(person.split())<2:return None
    status=str(row.get("STATUS","")).strip().lower()
    if status not in {"out","questionable","probable","doubtful","available"}:return None
    return {"ts":timestamp.astimezone(dt.timezone.utc),"day":str(day),
            "team":team,"home":home,"away":away,"name":person,
            "status":status,"reason":str(row.get("REASON",""))[:160]}

def audit(ir_text,game_csv,box_csv):
    games={}
    for r in csv.DictReader(io.StringIO(game_csv)):
        gid=lookup(r,"game_id","GAME_ID")
        day=lookup(r,"game_date","GAME_DATE")
        home=lookup(r,"home_team_abbreviation","HOME_TEAM_ABBREVIATION")
        away=lookup(r,"away_team_abbreviation","AWAY_TEAM_ABBREVIATION")
        if gid and day and home and away and gid.startswith("002"):
            games[(day[:10],home.upper(),away.upper())]=gid
    listings=collections.defaultdict(set)
    listed=collections.defaultdict(dict)
    for r in csv.DictReader(io.StringIO(box_csv)):
        gid=lookup(r,"game_id","GAME_ID")
        team=lookup(r,"team_tricode","TEAM_TRICODE","team_abbreviation","TEAM_ABBREVIATION")
        if not gid or not team:continue
        name=lookup(r,"player_name","PLAYER_NAME")
        if not name:
            first=lookup(r,"first_name","FIRST_NAME") or ""
            last=lookup(r,"family_name","FAMILY_NAME") or ""
            name=(first+" "+last).strip()
        if name:
            key=(gid,team.upper(),norm(name))
            listings[(gid,team.upper())].add(norm(name))
            if key not in listed:
                minutes=lookup(r,"minutes","MINUTES","min","MIN")
                comment=lookup(r,"comment","COMMENT") or ""
                listed[key]="played" if minutes and minutes not in ("0","0:00","00:00") else ("listed_dnp" if comment or minutes else "listed_minutes_unknown")
    selected={};reasons=collections.Counter();counts=collections.Counter()
    for raw in csv.DictReader(io.StringIO(ir_text)):
        item=event(raw)
        if not item:counts["schema_rejected"]+=1;continue
        key=(item["day"],item["home"],item["away"])
        gid=games.get(key)
        if not gid:counts["fixture_unmatched"]+=1;continue
        # Exact UTC tipoff from season fixture is required separately for any
        # decision-time evaluation. Here only same-day reports are allowed;
        # report earlier/later than game date cannot be called same-day.
        if item["ts"].astimezone(ET).date().isoformat()!=item["day"]:
            counts["not_same_day"]+=1;continue
        rowkey=(gid,item["team"],item["name"])
        prev=selected.get(rowkey)
        if prev is None or item["ts"]<prev["ts"]:
            selected[rowkey]={**item,"gid":gid}
    groups=collections.Counter()
    for (gid,team,name),item in selected.items():
        groups[item["status"]]+=1
        outcome=listed.get((gid,team,name))
        if outcome is None:counts["unlisted_unknown"]+=1
        else:
            counts["boxscore_"+outcome]+=1
            counts["matched_"+item["status"]]+=1
            if outcome=="played":counts["played_"+item["status"]]+=1
        if item["status"]=="out" and "g league" in item["reason"].lower():
            reasons["out_g_league"]+=1
        if item["status"]=="out" and "injury" in item["reason"].lower():
            reasons["out_injury_or_illness"]+=1
    if len(selected)<1000:raise ValueError("Too few historical injury rows matched to NBA games")
    return {
      "schema_version":1,"status":"research_only_not_deployed",
      "source":"Official NBA reports as parsed by Torgo28/NBA_AI_Player_Analysis",
      "source_uri":URL,
      "study":"2025/26 single 1PM ET pregame snapshot; only recorded fixture/day pair",
      "fixture_matches":len(selected),
      "status_counts":dict(groups),
      "qa_counts":dict(counts),"reason_audit":dict(reasons),
      "warnings":[
        "Same-day 1PM ET is not a complete evaluation of earlier fantasy deadlines.",
        "Unlisted boxscore players have UNKNOWN membership/outcome, not confirmed DNP.",
        "This source lacks full October-December 2025 coverage.",
        "Name joins are exact normalized strings; unmatched rows are never imputed.",
        "Do not infer medical probabilities or optimize on this selected subset."],
      "adopt_on_site":False}

def execute(fetch=None):
    if fetch is None:
        def fetch(url):
            if url==URL:
                req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.4 public-injury-audit"})
                with urllib.request.urlopen(req,timeout=90) as resp:
                    data=resp.read(15_000_001)
                    if len(data)>15_000_000:raise ValueError("injury CSV too large")
                    return data.decode("utf-8-sig")
            return get_csv(url)
    z=audit(fetch(URL),fetch(SCHEDULES.format(2026)),fetch(BOXSCORES.format(2026)))
    p=DATA/"injury_pit_audit.json"
    tmp=p.with_suffix(".tmp");tmp.write_text(json.dumps(z,ensure_ascii=False,indent=2),encoding="utf8");tmp.replace(p)
    return z

if __name__=="__main__":print(json.dumps(execute(),ensure_ascii=False,indent=2))
