"""Research-only, time-correct injury-status backtest for Sports.ru NBA Fantasy.

Prediction unit is a player explicitly appearing in an official NBA injury-report
snapshot BEFORE that game's Sports.ru lock (tipoff - 30 minutes).
The outcome is a played NBA boxscore row. Where absent, a player with an
unambiguous season-wide NBA ID and an explicit team/game injury-report listing
is eligible for a negative participation label. This is NOT full-roster coverage.

Development: 2024/25 official report snapshots; untouched holdout: 2025/26.
No commercial APIs, Firebase data, user accounts, or live model adjustments.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,date,time,timedelta,timezone
from zoneinfo import ZoneInfo
import csv,io,json,math,pathlib,re,statistics,unicodedata,urllib.request
from src.history import get_csv,BOXSCORES,SCHEDULES,parse_schedule,lookup
from src.sync import DATA,minutes

ET=ZoneInfo("America/New_York")
REPORTS={
 "2024/25":"https://raw.githubusercontent.com/Professor-Pete/2024-2025-injury_analysis/main/data/season_rows.csv",
 "2025/26":"https://raw.githubusercontent.com/Torgo28/NBA_AI_Player_Analysis/main/data/rag/processed/injury_reports.csv"
}
END_YEAR={"2024/25":2025,"2025/26":2026}
TEAM={"BRK":"BKN","CHO":"CHA","PHO":"PHX","NY":"NYK","GS":"GSW","SA":"SAS","NO":"NOP","UTAH":"UTA","WSH":"WAS"}
STATUS={"out","doubtful","questionable","probable","available"}
TARGET_SNAPSHOT_HOUR=13
LOCK_BUFFER=timedelta(minutes=30)
MIN_PRIOR=3

def name_key(value):
    s=str(value or "").strip()
    if "," in s:
        last,first=s.split(",",1)
        s=first.strip()+" "+last.strip()
    s=unicodedata.normalize("NFKD",s)
    s="".join(c for c in s if not unicodedata.combining(c))
    s=re.sub(r"\b(jr|sr|ii|iii|iv)\b"," ",s.lower())
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9 ]"," ",s)).strip()

def team_code(value):
    s=str(value or "").upper().strip()
    return TEAM.get(s,s)

FULL_TEAMS={
 "Atlanta Hawks":"ATL","Boston Celtics":"BOS","Brooklyn Nets":"BKN",
 "Charlotte Hornets":"CHA","Chicago Bulls":"CHI","Cleveland Cavaliers":"CLE",
 "Dallas Mavericks":"DAL","Denver Nuggets":"DEN","Detroit Pistons":"DET",
 "Golden State Warriors":"GSW","Houston Rockets":"HOU","Indiana Pacers":"IND",
 "Los Angeles Clippers":"LAC","LA Clippers":"LAC",
 "Los Angeles Lakers":"LAL","Memphis Grizzlies":"MEM","Miami Heat":"MIA",
 "Milwaukee Bucks":"MIL","Minnesota Timberwolves":"MIN","New Orleans Pelicans":"NOP",
 "New York Knicks":"NYK","Oklahoma City Thunder":"OKC","Orlando Magic":"ORL",
 "Philadelphia 76ers":"PHI","Phoenix Suns":"PHX","Portland Trail Blazers":"POR",
 "Sacramento Kings":"SAC","San Antonio Spurs":"SAS","Toronto Raptors":"TOR",
 "Utah Jazz":"UTA","Washington Wizards":"WAS"
}
FULL_TEAMS={name_key(k):v for k,v in FULL_TEAMS.items()}

def report_type(reason):
    s=str(reason or "").lower()
    if "g league" in s or "two-way" in s:return "g_league"
    if "injury/illness" in s:return "medical_report"
    if any(w in s for w in ("suspension","personal","not with team","reconditioning")):
        return "administrative"
    if "rest" in s:return "rest"
    return "other"

def record_2024(row):
    # A nominal 1 PM ET archived snapshot, not a reconstructed final status.
    if row.get("snapshot_time")!="01PM":return None
    try:
        game_day=datetime.strptime(row["game_date"],"%m/%d/%Y").date()
        snapshot_day=date.fromisoformat(row["snapshot_date"])
    except (KeyError,ValueError):return None
    if snapshot_day!=game_day:return None
    fixture=str(row.get("matchup","")).upper().strip().split("@")
    if len(fixture)!=2:return None
    away,home=map(team_code,fixture)
    team=FULL_TEAMS.get(name_key(row.get("team")))
    player=name_key(row.get("player"))
    status=str(row.get("status","")).lower().strip()
    if team not in (away,home) or not player or status not in STATUS:return None
    snapshot=datetime.combine(snapshot_day,time(TARGET_SNAPSHOT_HOUR),ET).astimezone(timezone.utc)
    return {"day":game_day.isoformat(),"home":home,"away":away,"team":team,
            "name":player,"status":status,"reason":report_type(row.get("reason")),
            "timestamp":snapshot}

def record_2025(row):
    try:
        stamp=datetime.fromisoformat(row["REPORT_TIMESTAMP"])
        if stamp.utcoffset() is None:return None
        game_day=date.fromisoformat(row["GAME_DATE"])
    except (ValueError,KeyError,TypeError):return None
    stamp=stamp.astimezone(timezone.utc)
    if stamp.astimezone(ET).date()!=game_day or stamp.astimezone(ET).hour!=TARGET_SNAPSHOT_HOUR:
        return None
    fixture=str(row.get("MATCHUP","")).upper().strip().split("@")
    if len(fixture)!=2:return None
    away,home=map(team_code,fixture)
    team=team_code(row.get("TEAM_ABBREVIATION"))
    player=name_key(row.get("PLAYER_NAME"))
    status=str(row.get("STATUS","")).lower().strip()
    if team not in (home,away) or not player or status not in STATUS:return None
    return {"day":game_day.isoformat(),"home":home,"away":away,"team":team,
            "name":player,"status":status,"reason":report_type(row.get("REASON")),
            "timestamp":stamp}

def index_boxscores(raw,valid_games):
    names=defaultdict(set)
    played=set()
    listed=set()
    byperson=defaultdict(list)
    rejected=Counter()
    for row in csv.DictReader(io.StringIO(raw)):
        gid=lookup(row,"game_id","GAME_ID")
        if gid not in valid_games:continue
        team=team_code(lookup(row,"team_tricode","TEAM_TRICODE",
                              "team_abbreviation","TEAM_ABBREVIATION"))
        pid=lookup(row,"person_id","PERSON_ID","player_id","PLAYER_ID")
        first=lookup(row,"player_name","PLAYER_NAME")
        if not first:
            first=" ".join(s for s in (
                lookup(row,"first_name","FIRST_NAME") or "",
                lookup(row,"family_name","FAMILY_NAME") or "") if s)
        key=name_key(first)
        if not key or not pid or team not in valid_games[gid][1:3]:
            rejected["no_unique_identity_or_team"]+=1;continue
        names[key].add(str(pid))
        listed.add((gid,team,str(pid)))
        minute=lookup(row,"minutes","MINUTES","min","MIN")
        played_now=False
        if minute:
            try:played_now=minutes(minute)>0
            except (ValueError,TypeError):rejected["unknown_minutes"]+=1
        if played_now:
            played.add((gid,team,str(pid)))
            byperson[(str(pid),team)].append(valid_games[gid][0])
    byperson={k:sorted(set(v)) for k,v in byperson.items()}
    unique={k:next(iter(v)) for k,v in names.items() if len(v)==1}
    return unique,played,listed,byperson,rejected

def index_games(schedule_csv,historical):
    games=parse_schedule(schedule_csv)
    archived=(historical.get("seasons") or {})
    if historical.get("calendar_status")!="fully_matched_historical_tipoffs":
        raise ValueError("Historical UTC must be independently verified")
    season=historical["season"]
    tipoffs=archived.get(season)
    if not isinstance(tipoffs,dict) or len(tipoffs)!=1230 or len(games)!=1230:
        raise ValueError("Exact 1230 regular-season games missing for "+season)
    keys={};valid={}
    for gid,g in games.items():
        day,home,away=g[:3]
        tip=tipoffs.get(gid)
        if not tip or any(tip.get(k)!=value for k,value in [
            ("home",home),("away",away),("et_date",day)]):
            raise ValueError("Game/UTC mismatch "+gid)
        stamp=datetime.fromisoformat(tip["utc"].replace("Z","+00:00"))
        if stamp.utcoffset()!=timedelta(0):raise ValueError("UTC offset not zero")
        keys[(day,home,away)]=(gid,stamp)
        valid[gid]=g
    return valid,keys

def player_panel(season,report_csv,box_csv,sched_csv,utc_history):
    historical={"calendar_status":utc_history["calendar_status"],
                "seasons":utc_history["seasons"],"season":season}
    valid,keys=index_games(sched_csv,historical)
    names,played,listed,past_played,boxreject=index_boxscores(box_csv,valid)
    report_parser=record_2024 if season=="2024/25" else record_2025
    selected={};reasons=Counter()
    for raw in csv.DictReader(io.StringIO(report_csv)):
        e=report_parser(raw)
        if e is None:
            reasons["non_eligible_snapshot_or_schema"]+=1;continue
        game=keys.get((e["day"],e["home"],e["away"]))
        if game is None:
            reasons["not_regular_game"]+=1;continue
        gid,tipoff=game
        if e["timestamp"]>tipoff-LOCK_BUFFER:
            reasons["after_30min_lock"]+=1;continue
        pid=names.get(e["name"])
        if not pid:
            reasons["unresolved_or_ambiguous_player"]+=1;continue
        key=(gid,e["team"],pid)
        e={**e,"gid":gid,"pid":pid}
        if key in selected:
            if selected[key]["status"]!=e["status"]:
                reasons["same_snapshot_status_conflict"]+=1
                selected[key]=None
            else:reasons["duplicated_source_record"]+=1
        else:selected[key]=e
    out=[];prior_availability=Counter();crossclub=Counter()
    team_games=defaultdict(list)
    for gid,(day,home,away,*_) in valid.items():
        team_games[home].append((day,gid))
        team_games[away].append((day,gid))
    for key in team_games:team_games[key].sort()
    for key,e in selected.items():
        if e is None:continue
        gid,team,pid=key
        # A player may be named on a report even after a trade: reject if he
        # appeared in the *opponent* or another team at this exact game.
        other=[t for t in (e["home"],e["away"]) if t!=team]
        if any((gid,t,pid) in played for t in other):
            crossclub["conflicting_team_same_game"]+=1;continue
        y=int(key in played)
        # Grounded negative: explicitly named on a pregame official report,
        # person ID unique across season, complete regular-season final game,
        # and no positive minutes for this game. Do not impute generic gaps.
        rows=team_games[team]
        last_games=[d for d,_ in rows if d<e["day"]][-10:]
        past=past_played.get((pid,team),[])
        previous=sum(d in past for d in last_games)
        # Prior appearances describe a possible team-tenure history, but
        # trade/onboarding gaps remain uncertain and are flagged.
        had_recent=any((date.fromisoformat(e["day"])-date.fromisoformat(d)).days<=35
                       for d in past if d<e["day"])
        if not had_recent:prior_availability["not_recently_played_for_this_club"]+=1
        out.append({**e,"actual":y,"label_source":"explicit_official_report_plus_complete_boxscore",
                    "listed_in_boxscore":key in listed,
                    "recent_team_presence":had_recent,
                    "last10_team_games":len(last_games),"played_last10":previous})
    if len(out)<150:raise ValueError(season+": too few eligible report rows "+str(len(out)))
    out.sort(key=lambda e:(e["timestamp"],e["gid"],e["pid"]))
    quality={"rows":len(out),"positive":sum(e["actual"] for e in out),
             "negative":sum(not e["actual"] for e in out),
             "listed_rows":sum(e["listed_in_boxscore"] for e in out),
             "report_grounded_absence_not_boxscore":sum(not e["listed_in_boxscore"] for e in out),
             "first_snapshot_utc":out[0]["timestamp"].isoformat(),
             "last_snapshot_utc":out[-1]["timestamp"].isoformat(),
             "unique_games":len({e["gid"] for e in out}),
             "unique_players":len({e["pid"] for e in out}),
             "status_counts":dict(Counter(e["status"] for e in out)),
             "reason_categories":dict(Counter(e["reason"] for e in out)),
             "rejected":dict(reasons),
             "crossclub":dict(crossclub),
             "prior_availability":dict(prior_availability),
             "boxscore_rejected":dict(boxreject)}
    return out,quality

def group_probabilities(development,smoothing=20):
    mean=statistics.fmean(r["actual"] for r in development)
    groups=defaultdict(list)
    for r in development:
        groups[(r["status"],r["reason"])].append(r["actual"])
    statuses=defaultdict(list)
    for r in development:statuses[r["status"]].append(r["actual"])
    group={}
    for (status,reason),values in groups.items():
        parent=(sum(statuses[status])+smoothing*mean)/(len(statuses[status])+smoothing)
        group[(status,reason)]=(sum(values)+smoothing*parent)/(len(values)+smoothing)
    bystatus={status:(sum(values)+smoothing*mean)/(len(values)+smoothing)
              for status,values in statuses.items()}
    return mean,bystatus,group

def features_blend(r,overall):
    # No price/roster access. Baseline from same-team played games with shrinkage.
    # This is only a proxy if a player changed clubs inside the lookback.
    if not r["recent_team_presence"] or r["last10_team_games"]<MIN_PRIOR:return overall
    return (r["played_last10"]+8*overall)/(r["last10_team_games"]+8)

def metrics(rows,probs):
    if len(rows)!=len(probs) or not rows:raise ValueError("Invalid scoring cohort")
    p=[min(.999,max(.001,float(z))) for z in probs]
    y=[int(r["actual"]) for r in rows]
    return {"n":len(y),"played_pct":round(100*statistics.fmean(y),2),
            "predicted_pct":round(100*statistics.fmean(p),2),
            "brier":round(statistics.fmean((pi-yi)**2 for pi,yi in zip(p,y)),5),
            "logloss":round(-statistics.fmean(yi*math.log(pi)+(1-yi)*math.log(1-pi) for pi,yi in zip(p,y)),5),
            "mae_probability":round(statistics.fmean(abs(pi-yi) for pi,yi in zip(p,y)),5)}

def evaluate(dev,hold):
    if len(dev)<500 or len(hold)<250:raise ValueError("Insufficient split for status holdout")
    overall,status,groups=group_probabilities(dev)
    # All calibrations fit development season ONLY, frozen before holdout.
    models={
      "global_prior":[overall]*len(hold),
      "last10_with_shrinkage":[features_blend(r,overall) for r in hold],
      "status_only":[status.get(r["status"],overall) for r in hold],
      "status_and_reason":[groups.get((r["status"],r["reason"]),
                           status.get(r["status"],overall)) for r in hold]
    }
    results={name:metrics(hold,p) for name,p in models.items()}
    by_status={}
    for s in sorted(STATUS):
        group=[r for r in hold if r["status"]==s]
        if group:
            pred=[groups.get((r["status"],r["reason"]),status.get(r["status"],overall)) for r in group]
            by_status[s]={"observed":metrics(group,pred),"train_count":sum(r["status"]==s for r in dev)}
    return {"training_prior":round(overall,4),
            "status_development_rates":{s:{"n":sum(r["status"]==s for r in dev),
                                           "calibrated_probability":round(v,4)}
                                        for s,v in sorted(status.items())},
            "holdout":results,"holdout_by_status":by_status,
            "holdout_explicit_report_coverage_only":True}

def pull_csv(url):
    if url.startswith("https://raw.githubusercontent.com/"):
        req=urllib.request.Request(url,headers={"Accept":"text/csv",
                 "User-Agent":"NBA-Season-Lab/1.5 noncommercial-research"})
        with urllib.request.urlopen(req,timeout=95) as resp:
            data=resp.read(16_000_001)
            if len(data)>16_000_000:raise ValueError("Report exceeds size limit")
        return data.decode("utf-8-sig")
    return get_csv(url)

def execute(fetch=pull_csv):
    path=DATA/"historical_tipoffs.json"
    obj=json.loads(path.read_text(encoding="utf8"))
    if obj.get("calendar_status")!="fully_matched_historical_tipoffs":
        raise ValueError("Exact historical calendar required")
    cohorts={};qa={}
    for season in ("2024/25","2025/26"):
        yr=END_YEAR[season]
        cohorts[season],qa[season]=player_panel(
            season,fetch(REPORTS[season]),fetch(BOXSCORES.format(yr)),
            fetch(SCHEDULES.format(yr)),obj)
    scored=evaluate(cohorts["2024/25"],cohorts["2025/26"])
    result={
        "schema_version":1,
        "status":"research_only_not_deployed",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "development":"2024/25",
        "holdout":"2025/26",
        "scope":"Official-injury-report-listed players only; not all fantasy roster players",
        "prediction_time":"1PM Eastern on game's US date, only when before 30-min game lock",
        "qa":qa,"evaluation":scored,
        "input_sources":REPORTS,
        "limits":[
            "Report publication timestamps are nominal archived snapshots, not independently audited first-seen logs.",
            "This pregame study cannot be reused for Sports.ru Monday 15:00 MSK weekly locks (1PM ET occurs later).",
            "Absence is inferred only when a unique NBA person ID and explicit official team/game injury listing are available.",
            "Players absent the entire season without a resolvable NBA ID remain unmodeled.",
            "Full roster and transaction windows have not been independently reconstructed.",
            "Historical final schedule may differ from the as-published schedule at decision time.",
            "Some source-derived name strings may not match NBA Stats IDs; unmatched are excluded.",
            "This does not test whether Telegram improves Sports.ru weekly FP or lineup transfer decisions.",
        ],
        "adopt_on_site":False
    }
    dest=DATA/"injury_status_holdout.json"
    temp=dest.with_suffix(".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf8")
    temp.replace(dest)
    return result

if __name__=="__main__":
    out=execute()
    print(json.dumps({"status":out["status"],"qa":out["qa"],
                      "evaluation":out["evaluation"],"adopt_on_site":out["adopt_on_site"]},
                      ensure_ascii=False,indent=2))
