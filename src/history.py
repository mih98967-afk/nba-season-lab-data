#!/usr/bin/env python3
"""Import three regular NBA seasons, verifying per-player FP against game results.

CC BY 4.0 data from SportsDataverse; stats originate from official NBA feeds.
Outputs only public aggregated player data, never Firebase profile information.
"""
from __future__ import annotations
import collections
import csv
import datetime as dt
import io
import json
import math
import pathlib
import statistics
import urllib.request
from src.sync import DATA, CATALOG, http_json, norm, minutes, fantasy_fp

START_YEARS = (2024, 2025, 2026) # NBA season END years
SEASONS = {2024:"2023/24",2025:"2024/25",2026:"2025/26"}
BOXSCORES="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_player_boxscores/player_boxscores_{}.csv"
SCHEDULES="https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nba_stats_schedules/nba_schedule_{}.csv"

FIELDS = {
    "game":("game_id","GAME_ID"),
    "first":("first_name","FIRST_NAME"),
    "family":("family_name","FAMILY_NAME"),
    "name":("player_name","PLAYER_NAME"),
    "team":("team_tricode","TEAM_TRICODE","team_abbreviation","TEAM_ABBREVIATION"),
    "person":("person_id","PERSON_ID","player_id","PLAYER_ID"),
    "min":("minutes","MINUTES","min","MIN"),
    "pts":("points","POINTS","pts","PTS"),
    "fgm":("field_goals_made","FGM"),
    "fga":("field_goals_attempted","FGA"),
    "ftm":("free_throws_made","FTM"),
    "fta":("free_throws_attempted","FTA"),
    "reb":("rebounds_total","REB"),
    "ast":("assists","AST"),
    "stl":("steals","STL"),
    "blk":("blocks","BLK"),
    "tov":("turnovers","TOV"),
    "pf":("fouls_personal","PF"),
}
STAT_KEYS=("pts","fgm","fga","ftm","fta","reb","ast","stl","blk","tov","pf")
def lookup(r,*names):
    for k in names:
        if k in r and r[k] is not None and str(r[k]).strip() not in ("","NA","NULL"):
            return str(r[k]).strip()
    return None

def x(r,key):
    return lookup(r,*FIELDS[key])

def get_csv(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NBA-Season-Lab/1.2 (public history research)","Accept":"text/csv"})
    with urllib.request.urlopen(req,timeout=90) as response:
        data=response.read(13_000_001)
        if len(data)>13_000_000:raise ValueError("Oversized historical response")
    return data.decode("utf-8-sig")

def parse_schedule(text):
    rows=csv.DictReader(io.StringIO(text))
    if not rows.fieldnames:raise ValueError("Empty season schedule")
    games={}
    for raw in rows:
        gid=lookup(raw,"game_id","GAME_ID")
        if not gid or not gid.startswith("002"):continue
        home=lookup(raw,"home_team_abbreviation","HOME_TEAM_ABBREVIATION","home_team_tricode")
        away=lookup(raw,"away_team_abbreviation","AWAY_TEAM_ABBREVIATION","away_team_tricode")
        hs=lookup(raw,"home_pts","HOME_PTS","home_score")
        av=lookup(raw,"away_pts","AWAY_PTS","away_score")
        date=lookup(raw,"game_date","GAME_DATE","date")
        if not (home and away and hs and av and date):continue
        h,a=int(float(hs)),int(float(av))
        if h==a:continue
        games[gid]=(date[:10],home.upper(),away.upper(),h,a)
    if len(games)<900:raise ValueError("Not enough valid regular-season final scores: "+str(len(games)))
    return games

def parse_box(text,games,season):
    reader=csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or len(reader.fieldnames)<18:raise ValueError("Boxscore columns missing")
    rejected=collections.Counter()
    rows=[];dedupe=set(); joined=0
    for raw in reader:
        gid=x(raw,"game")
        if not gid or not gid.startswith("002"):
            rejected["not_regular"]+=1
            continue
        if gid not in games:
            rejected["no_valid_final"]+=1
            continue
        first=x(raw,"first");family=x(raw,"family")
        name=x(raw,"name") or " ".join(q for q in (first,family) if q)
        if not name:
            rejected["no_name"]+=1
            continue
        team=x(raw,"team")
        day,home,away,hs,as_=games[gid]
        if not team or team.upper() not in (home,away):
            rejected["team_mismatch"]+=1
            continue
        identity=x(raw,"person") or norm(name)
        dk=(gid,identity)
        if dk in dedupe:
            rejected["duplicate"]+=1
            continue
        try:
            mins=minutes(x(raw,"min"))
            st={"min":mins}
            for k in STAT_KEYS:
                value=x(raw,k)
                if value is None:raise ValueError("Missing "+k)
                v=float(value)
                if not math.isfinite(v) or v<0:raise ValueError("Bad "+k)
                st[k]=v
            if mins<=0:
                rejected["dnp"]+=1
                continue
            is_home=team.upper()==home
            won=(hs>as_) if is_home else (as_>hs)
            fp=fantasy_fp(st,is_home,won)
        except (ValueError,TypeError) as e:
            rejected["invalid_line"]+=1
            continue
        dedupe.add(dk)
        rows.append({"name":name,"nba_id":x(raw,"person"),"game":gid,"date":day,"team":team.upper(),
                     "fp":fp,"box":st})
        joined+=1
    if joined<12000:raise ValueError(f"Season {season}: only {joined} complete regular-season player-games")
    return rows,dict(rejected)

def catalog():
    base=json.loads((DATA/"catalog.json").read_text(encoding="utf8")) if (DATA/"catalog.json").exists() and (DATA/"catalog.json").stat().st_size else http_json(CATALOG)
    players=base.get("players")
    if not isinstance(players,list) or len(players)<400:raise ValueError("Invalid player catalog")
    names=collections.defaultdict(set)
    for p in players:
        name=norm(p.get("english"))
        if name:names[name].add(p["id"])
    return {k:next(iter(v)) for k,v in names.items() if len(v)==1}

def aggregate(season_rows,name_index):
    grouped=collections.defaultdict(lambda:collections.defaultdict(list))
    unmatched=collections.Counter()
    all_rows={}
    for season,rows in season_rows.items():
        for r in rows:
            pid=name_index.get(norm(r["name"]))
            if pid is None:
                unmatched[r["name"]]+=1
                continue
            grouped[pid][season].append(r)
    players={}
    for pid,byseason in grouped.items():
        out=[]
        for season,rows in sorted(byseason.items()):
            rows.sort(key=lambda r:(r["date"],r["game"]))
            mean={k:round(statistics.fmean(r["box"][k] for r in rows),2) for k in ("min",)+STAT_KEYS}
            fps=[r["fp"] for r in rows]
            q=sorted(fps)
            # Last35 is enough for UI; backtest uses all rows in memory.
            last=[{"d":r["date"],"g":r["game"],"team":r["team"],
                   **{k:round(r["box"][k],2) for k in ("min","pts","reb","ast","stl","blk","tov","fga","fgm")},
                   "fp":r["fp"]} for r in rows[-35:]]
            out.append({"season":season,"games":len(rows),"averages":mean,
                        "fp_avg":round(statistics.fmean(fps),2),
                        "fp_q20":round(q[int((len(q)-1)*.2)],1),
                        "fp_q80":round(q[int((len(q)-1)*.8)],1),
                        "full_fp_games":len(fps),"last35":last})
        players[pid]=out
    return {"players":players,"rows":sum(len(v) for x in grouped.values() for v in x.values()),
            "unmatched":unmatched,"raw":grouped}

def backtest(grouped):
    """Train 2024/25, test 2025/26. Only previous played games inform each prediction."""
    train=[];holdout=[]
    for byseason in grouped.values():
        prior=[]
        for season in ("2023/24","2024/25","2025/26"):
            rows=sorted(byseason.get(season,[]),key=lambda r:(r["date"],r["game"]))
            for r in rows:
                if len(prior)>=10 and season in ("2024/25","2025/26"):
                    last10=statistics.fmean(prior[-10:])
                    last5=statistics.fmean(prior[-5:])
                    t=train if season=="2024/25" else holdout
                    t.append((r["fp"],last10,last5))
                prior.append(r["fp"])
    def mae(v,a):
        return statistics.fmean(abs(y-((1-a)*b+a*f)) for y,b,f in v) if v else None
    if len(train)<1000 or len(holdout)<1000:raise ValueError("Not enough chronological holdout observations")
    candidates=[0,0.2,0.4,0.6]
    winner=min(candidates,key=lambda a:mae(train,a))
    base=mae(holdout,0);cand=mae(holdout,winner)
    # Avoid adopting sophistication on weak out-of-sample evidence.
    selected=winner if winner>0 and (base-cand)/base>=0.01 else 0
    return {"schema_version":1,
            "status":"validated_for_single_game_mean" if selected else "baseline_retained",
            "train":{"n":len(train),"baseline_mae":round(mae(train,0),3),"selected_mae":round(mae(train,winner),3)},
            "holdout":{"n":len(holdout),"baseline_mae":round(base,3),"candidate_mae":round(cand,3),"delta_pct":round(100*(base-cand)/base,2)},
            "baseline":"last10 played-game FP average",
            "candidate":f"{1-winner:.1f}*last10 + {winner:.1f}*last5 played-game FP average",
            "chosen":"candidate" if selected else "baseline",
            "limitations":["MAE only for next PLAYED game, excludes DNP and weekly schedule",
                           "A retrospective single-game result is not a calibration of the 2026/27 weekly model",
                           "Team changes/role changes may make historical averages less reliable"]}

def run():
    index=catalog()
    season_rows={};checks={}
    for year in START_YEARS:
        season=SEASONS[year]
        results=parse_schedule(get_csv(SCHEDULES.format(year)))
        box,rejected=parse_box(get_csv(BOXSCORES.format(year)),results,season)
        checks[season]={"final_games":len(results),"complete_player_games":len(box),"rejected":rejected}
        season_rows[season]=box
    summary=aggregate(season_rows,index)
    report=backtest(summary["raw"])
    data={"schema_version":1,"status":"complete","source":"SportsDataverse/NBA Stats official boxscores",
          "source_url":"https://github.com/sportsdataverse/sportsdataverse-data/releases",
          "license":"CC BY 4.0",
          "updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "seasons":list(SEASONS.values()),
          "players":summary["players"],
          "qa":{"matched_players":len(summary["players"]),
                "matched_player_game_rows":summary["rows"],
                "full_fp_rows":summary["rows"],
                "unmatched_examples":summary["unmatched"].most_common(15),
                "seasons":checks}}
    if data["qa"]["matched_players"]<220 or summary["rows"]<25000:
        raise ValueError("Too few catalog-matched historical games; preserving previous snapshots")
    for name,obj in [("nba_history",data),("model_report",report)]:
        dest=DATA/(name+".json")
        tmp=DATA/(name+".tmp")
        tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf8")
        tmp.replace(dest)
    return {"history":data["qa"],"model":report}

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
