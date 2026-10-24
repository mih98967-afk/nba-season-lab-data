"""NBA participation research v3: point-in-time boxscore DNP labels and trade-aware gaps.

Do NOT deploy this study as a medical probability model. A boxscore listing is
a verified roster appearance; a missing boxscore row is not proof of either
injury or club membership. Bracketed unlisted games are SENSITIVITY ONLY.

Seasons: 2023/24 population prior; 2024/25 development; 2025/26 untouched
holdout. Sources: SportsDataverse NBA Stats player boxscores + regular schedules.
All predictive features use only earlier observations from the same NBA team.
"""
from __future__ import annotations
import collections
import csv
import datetime as dt
import io
import json
import math
import statistics
from src.history import BOXSCORES,SCHEDULES,get_csv,parse_schedule,lookup
from src.sync import DATA,minutes

YEARS=(2024,2025,2026)
PERIOD={2024:"2023/24",2025:"2024/25",2026:"2025/26"}
NAMES=("game_id","GAME_ID")
TEAM_KEYS=("team_tricode","TEAM_TRICODE","team_abbreviation","TEAM_ABBREVIATION")
ID_KEYS=("person_id","PERSON_ID","player_id","PLAYER_ID")
MIN_KEYS=("minutes","MINUTES","min","MIN")
COMMENT_KEYS=("comment","COMMENT","status","STATUS")

def box_min(value,comment):
    s=str(value or "").strip()
    if s:
        try:return max(0.,minutes(s))
        except (ValueError,TypeError):pass
    c=str(comment or "").upper()
    if any(tag in c for tag in ("DNP","DND","INACTIVE","DID NOT PLAY","NOT WITH TEAM","NOT DRESS")):
        return 0.
    return None

def extract(season,boxcsv,schedulecsv):
    games=parse_schedule(schedulecsv)
    if len(games)!=1230:raise ValueError("Expected 1230 final regular-season games in "+str(season))
    observed={};bad=collections.Counter();dnp_reasons=collections.Counter()
    reader=csv.DictReader(io.StringIO(boxcsv))
    if not reader.fieldnames or "game_id" not in [c.lower() for c in reader.fieldnames]:
        raise ValueError("Missing boxscore keys")
    by_player=collections.defaultdict(list)
    for raw in reader:
        gid=lookup(raw,*NAMES)
        if gid not in games:continue
        pid=lookup(raw,*ID_KEYS);team=lookup(raw,*TEAM_KEYS)
        if not pid or not team:
            bad["missing_identity_or_team"]+=1;continue
        team=team.upper()
        day,home,away,_,_=games[gid]
        if team not in (home,away):
            bad["team_mismatch"]+=1;continue
        comment=lookup(raw,*COMMENT_KEYS) or ""
        mins=box_min(lookup(raw,*MIN_KEYS),comment)
        if mins is None:
            bad["unknown_minutes"]+=1;continue
        key=(pid,team,gid)
        if key in observed:
            bad["duplicate"]+=1;continue
        played=int(mins>0.)
        if not played:dnp_reasons[comment[:65] or "zero_minutes_blank_reason"]+=1
        row={"pid":pid,"team":team,"gid":gid,"day":day,"played":played,"mins":mins,
             "comment":comment[:80]}
        observed[key]=row
        by_player[pid].append(row)
    for rows in by_player.values():
        rows.sort(key=lambda r:(r["day"],r["gid"]))
    return games,observed,by_player,{"season":PERIOD[season],"observed_rows":len(observed),
                 "played_rows":sum(x["played"] for x in observed.values()),
                 "listed_dnp_rows":sum(not x["played"] for x in observed.values()),
                 "dnp_reasons":dnp_reasons.most_common(12),"excluded":dict(bad),
                 "unique_players":len(by_player)}

def panel(games,observed,by_player,min_history=4):
    # An event is an *observed* boxscore listing, never a fictional roster entry.
    team_games=collections.defaultdict(list)
    game_sort={}
    for gid,(day,home,away,_,_) in games.items():
        game_sort[gid]=day
        team_games[home].append((day,gid));team_games[away].append((day,gid))
    for team in team_games:team_games[team].sort()
    team_previous={}
    for team,seq in team_games.items():
        for i,(day,gid) in enumerate(seq):
            prev=seq[i-1][0] if i else None
            team_previous[(team,gid)]=bool(prev and (dt.date.fromisoformat(day)-dt.date.fromisoformat(prev)).days==1)
    by_stint=collections.defaultdict(list)
    for row in observed.values():by_stint[(row["pid"],row["team"])].append(row)
    strict=[];bracketed=[];coverage=collections.Counter()
    for (pid,team),rows in by_stint.items():
        rows.sort(key=lambda r:(r["day"],r["gid"]))
        first,last=rows[0]["day"],rows[-1]["day"]
        other_team_days=[r["day"] for r in by_player[pid] if r["team"]!=team]
        hist=[];idx={r["gid"]:r for r in rows}
        for day,gid in team_games[team]:
            if day<first or day>last:continue
            if day in other_team_days:
                coverage["other_team_day_excluded"]+=1;continue
            current=idx.get(gid)
            label="boxscore_listed" if current else "inferred_between_same_team"
            if len(hist)>=min_history:
                last20=hist[-20:];last5=hist[-5:]
                last_play=next((x for x in reversed(hist) if x["played"]),None)
                gap=(dt.date.fromisoformat(day)-dt.date.fromisoformat(hist[-1]["day"])).days
                gap_play=(dt.date.fromisoformat(day)-dt.date.fromisoformat(last_play["day"])).days if last_play else 365
                streak=0
                for h in reversed(hist):
                    if h["played"]:break
                    streak+=1
                item={"pid":pid,"team":team,"gid":gid,"day":day,
                      "played":current["played"] if current else 0,
                      "n20":len(last20),"played20":sum(x["played"] for x in last20),
                      "n5":len(last5),"played5":sum(x["played"] for x in last5),
                      "gap_days":gap,"since_played_days":gap_play,"prior_dnp_streak":streak,
                      "b2b":team_previous[(team,gid)],
                      "label":label}
                (strict if current else bracketed).append(item)
            coverage[label]+=1
            # Only verified as-of listings update features; inferred hindsight
            # is deliberately NEVER written into the predictive history.
            if current:hist.append(current)
        coverage["stints"]+=1
    if len(strict)<1000:raise ValueError("Too few verified player-game labels")
    return strict,bracketed,dict(coverage)

def predict(row,par,prior):
    k,w,gap_pen,b2b_pen=par
    v20=(row["played20"]+k*prior)/(row["n20"]+k)
    k5=k/2
    v5=(row["played5"]+k5*prior)/(row["n5"]+k5)
    p=(1-w)*v20+w*v5
    p-=gap_pen*max(0,min(60,row["gap_days"]-3))
    if row["b2b"]:p-=b2b_pen
    return min(.995,max(.005,p))

def scoring(rows,par,prior):
    if not rows:return None
    p=[predict(r,par,prior) for r in rows]
    y=[r["played"] for r in rows]
    brier=statistics.fmean((a-b)**2 for a,b in zip(p,y))
    logloss=-statistics.fmean(b*math.log(a)+(1-b)*math.log(1-a) for a,b in zip(p,y))
    bins={}
    for i in range(10):
        ix=[j for j,v in enumerate(p) if min(9,int(v*10))==i]
        if ix:
            bins[str(i)]={"n":len(ix),"mean_pred":round(statistics.fmean(p[j] for j in ix),3),
                         "observed":round(statistics.fmean(y[j] for j in ix),3)}
    return {"n":len(rows),"play_pct":round(100*statistics.fmean(y),2),
            "brier":round(brier,5),"logloss":round(logloss,5),
            "prediction_mean":round(statistics.fmean(p),4),"reliability_deciles":bins}

def strata(rows,par,prior):
    categories={
      "b2b":[r for r in rows if r["b2b"]],
      "non_b2b":[r for r in rows if not r["b2b"]],
      "long_gap_14d_plus":[r for r in rows if r["gap_days"]>=14],
      "recent_gap_under_14d":[r for r in rows if r["gap_days"]<14],
      "prior_multiple_dnp":[r for r in rows if r["prior_dnp_streak"]>=2],
      "return_after_14d":[r for r in rows if r["since_played_days"]>=14],
    }
    return {k:scoring(v,par,prior) for k,v in categories.items()}

def execute(fetch=get_csv):
    audit={};series={};unknown={}
    for yr in YEARS:
        games,obs,players,qa=extract(yr,fetch(BOXSCORES.format(yr)),fetch(SCHEDULES.format(yr)))
        s,u,counts=panel(games,obs,players)
        series[yr]=s;unknown[yr]=u
        audit[PERIOD[yr]]={**qa,"roster_label_coverage":counts,
                           "evaluation_verified":len(s),"sensitivity_inferred":len(u)}
    prior=audit["2023/24"]["played_rows"]/audit["2023/24"]["observed_rows"]
    dev=series[2025];hold=series[2026]
    simple=(10,0.,0.,0.)
    candidates=[(k,w,g,b) for k in (5,10,20) for w in (0.,.25,.5)
                for g in (0.,.003,.007) for b in (0.,.02,.05)]
    best=min(candidates,key=lambda par:(scoring(dev,par,prior)["brier"],par))
    strict_base=scoring(hold,simple,prior);strict_cand=scoring(hold,best,prior)
    # Unlisted team games have UNKNOWN participation, not negative labels.
    # Report only how many predictions fall outside the verified population.
    inferred_unknown={"n":len(unknown[2026]),"label":"unknown_not_scored",
                      "prediction_mean":round(statistics.fmean(predict(r,best,prior) for r in unknown[2026]),4) if unknown[2026] else None}
    improvement=round(100*(strict_base["brier"]-strict_cand["brier"])/strict_base["brier"],2)
    report={"schema_version":1,"status":"research_only_not_deployed",
      "updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
      "model_scope":"Participation conditional on NBA boxscore listing; NOT every scheduled player-game",
      "development":"2024/25","holdout":"2025/26","population_prior":"2023/24 observed boxscore listings",
      "population_prior_play_pct":round(prior*100,2),"data_qa":audit,
      "baseline":{"parameters":simple,"holdout_verified":strict_base,
                  "holdout_unlisted_unknown":inferred_unknown},
      "candidate":{"parameters":best,"development":scoring(dev,best,prior),
                   "holdout_verified":strict_cand,
                   "holdout_unlisted_unknown":inferred_unknown,
                   "brier_improvement_pct_on_listed":improvement,
                   "holdout_strata":strata(hold,best,prior)},
      "limitations":[
          "Missing boxscore row is UNKNOWN membership, not DNP or an injury diagnosis.",
          "Inferred between-stint gaps are unknown and never scored as ground-truth DNP.",
          "Only within-team past boxscore listings become as-of features.",
          "Historical final game schedules are not contemporaneous schedule snapshots.",
          "True whole-roster fantasy p_play cannot be calibrated from listings alone.",
          "Holdout labels may be selection-biased, especially prolonged injuries.",
          "Do not apply numeric candidate probabilities to real-user transfers."],
      "adopt_on_site":False}
    outfile=DATA/"dnp_audit_v3.json";tmp=outfile.with_suffix(".tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8");tmp.replace(outfile)
    return report

if __name__=="__main__":
    v=execute()
    print(json.dumps({"status":v["status"],"prior":v["population_prior_play_pct"],
          "data_qa":v["data_qa"],"baseline_holdout":v["baseline"]["holdout_verified"],
          "candidate_params":v["candidate"]["parameters"],
          "candidate_holdout":v["candidate"]["holdout_verified"],
          "sensitivity":v["candidate"]["holdout_inferred_sensitivity"],
          "improvement_pct":v["candidate"]["brier_improvement_pct_on_listed"]},ensure_ascii=False,indent=2))
