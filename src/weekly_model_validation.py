"""Historical player-week NBA Fantasy forecast backtest (not a live model).

All features are computed BEFORE the forecast week. The calendar is 1,230
completed regular-season games per year. We infer team tenure only from past
played games and never interpret unknown/ambiguous names as DNP.
Development 2024/25, untouched holdout 2025/26.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from statistics import fmean,stdev
import csv,io,json,math,random,pathlib
from src.history import get_csv,SCHEDULES
from src.sync import DATA
ET=ZoneInfo("America/New_York")
MSK=ZoneInfo("Europe/Moscow")
SEASONS={"2024/25":2025,"2025/26":2026}

def get(d,*keys):
    for k in keys:
        if d.get(k) not in ("",None):return str(d[k]).strip()
    return None

def timestamp(raw,zone=None):
    if not raw:return None
    try:
        x=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        if x.tzinfo is None and zone:x=x.replace(tzinfo=zone)
        return x.astimezone(timezone.utc) if x.tzinfo else None
    except ValueError:return None

def schedule(text,season,utc_map=None):
    reader=csv.DictReader(io.StringIO(text))
    out=[];missing=0
    for r in reader:
        game=get(r,"game_id","GAME_ID")
        if not game or not game.startswith("002"):continue
        home=get(r,"home_team_abbreviation","HOME_TEAM_ABBREVIATION")
        away=get(r,"away_team_abbreviation","AWAY_TEAM_ABBREVIATION")
        hs=get(r,"home_pts","HOME_PTS");a=get(r,"away_pts","AWAY_PTS")
        if not home or not away or hs is None or a is None:continue
        try:
            if float(hs)==float(a):continue
        except ValueError:continue
        text_date=get(r,"game_date","GAME_DATE")
        if not text_date:continue
        try:day=date.fromisoformat(text_date[:10])
        except ValueError:continue
        mapped=(utc_map or {}).get(game)
        if mapped and (mapped.get("home")!=home or mapped.get("away")!=away or mapped.get("et_date")!=str(day)):
            raise ValueError("Historical UTC reconciliation mismatch: "+game)
        utc=(timestamp(get(r,"game_date_time_utc","GAME_DATE_TIME_UTC"))
             or timestamp(get(r,"game_date_time_est","GAME_DATE_TIME_EST"),ET)
             or timestamp(mapped.get("utc") if mapped else None))
        if utc is None:missing+=1
        out.append({"id":game,"home":home,"away":away,"day":day,"utc":utc})
    if len(out)<1100 or len({r["id"] for r in out})!=len(out):
        raise ValueError("Bad final regular-season schedule: "+season+" "+str(len(out)))
    precision="moscow_start" if missing==0 else "US_date_proxy"
    for g in out:
        d=g["utc"].astimezone(MSK).date() if precision=="moscow_start" else g["day"]
        g["week"]=d-timedelta(days=d.weekday())
    return out,{"games":len(out),"missing_utc_tipoffs":missing,"week_semantics":precision,
                "fields_available":reader.fieldnames}

def joined(history,fixtures,season):
    all_games={g["id"]:g for g in fixtures}
    player=defaultdict(list);team_games=defaultdict(list)
    for g in fixtures:
        team_games[g["home"]].append(g);team_games[g["away"]].append(g)
    for gs in team_games.values():gs.sort(key=lambda g:(g["day"],g["id"]))
    rejected=Counter()
    for pid,seasons in history.items():
        for item in seasons:
            if item.get("season")!=season:continue
            if "game_log" not in item:raise ValueError("Truncated history; complete game_log required")
            for v in item["game_log"]:
                g=all_games.get(str(v.get("g")))
                if not g or v.get("team") not in (g["home"],g["away"]):
                    rejected["bad_match_or_team"]+=1;continue
                player[pid].append({"id":g["id"],"day":g["day"],"week":g["week"],
                                    "team":v["team"],"fp":float(v["fp"]),"min":float(v["min"])})
    for logs in player.values():logs.sort(key=lambda r:(r["day"],r["id"]))
    return player,team_games,rejected

def cohort(fixtures,history,season):
    player,team_games,rejected=joined(history,fixtures,season)
    weeks=sorted({g["week"] for g in fixtures});samples=[];excluded=Counter()
    for week in weeks[1:-1]:  # Exclude partial boundary weeks.
        upcoming={t:[g for g in gs if g["week"]==week] for t,gs in team_games.items()}
        for pid,logs in player.items():
            before=[r for r in logs if r["week"]<week]
            if len(before)<14:excluded["short_player_history"]+=1;continue
            last=before[-1];team=last["team"]
            future=upcoming.get(team,[])
            if not future:continue
            if (week-last["day"]).days>16:
                excluded["no_recent_team_activity"]+=1;continue
            past_team=[g for g in team_games[team] if g["week"]<week]
            if len(past_team)<12:excluded["short_team_history"]+=1;continue
            tenure=[]
            for r in reversed(before):
                if r["team"]!=team:break
                tenure.append(r)
            tenure.reverse()
            if len(tenure)<8:excluded["new_team_tenure"]+=1;continue
            since=tenure[0]["day"]
            eligible=[g for g in past_team if g["day"]>=since]
            if len(eligible)<10:excluded["short_team_tenure"]+=1;continue
            have={r["id"] for r in tenure}
            twenty=eligible[-20:];five=eligible[-5:]
            played=[r for r in logs if r["week"]==week and r["team"]==team]
            mu10=fmean(r["fp"] for r in before[-10:])
            mu25=fmean(r["fp"] for r in before[-25:]) if len(before)>=25 else mu10
            mu_minutes=fmean(r["min"] for r in before[-10:])
            diff_minutes=fmean(r["min"] for r in before[-5:])-mu_minutes
            per_min=sum(r["fp"] for r in before[-10:])/max(75.,sum(r["min"] for r in before[-10:]))
            sigma=stdev(r["fp"] for r in before[-25:]) if len(before)>=2 else 9.
            samples.append({"pid":pid,"team":team,"week":str(week),
              "games":len(future),"actual":sum(r["fp"] for r in played),"played":len(played),
              "mu10":mu10,"mu25":mu25,"min_diff":diff_minutes,"per_min":per_min,
              "sigma":max(3.,sigma),"played20":sum(g["id"] in have for g in twenty),
              "team20":len(twenty),"played5":sum(g["id"] in have for g in five),
              "team5":len(five)})
    if len(samples)<1200:raise ValueError("Too few as-of player-weeks: "+str(len(samples)))
    return samples,{"player_weeks":len(samples),"players":len({r["pid"] for r in samples}),
      "scheduled_player_games":sum(r["games"] for r in samples),
      "zero_appearance_pct":round(100*sum(r["played"]==0 for r in samples)/len(samples),2),
      "excluded":dict(excluded),"rejected_historical_lines":dict(rejected)}

def forecast(r,params):
    k,recency,mu_model=params
    p20=(r["played20"]+.87*k)/(r["team20"]+k)
    p5=(r["played5"]+.87*k)/(r["team5"]+k)
    p=max(.03,min(.99,(1-recency)*p20+recency*p5))
    mu=r["mu10"]
    if mu_model:
        trend=max(-8.,min(8.,.25*r["min_diff"]*max(0.,min(1.5,r["per_min"]))))
        mu=max(-5.,min(80.,.6*r["mu10"]+.4*r["mu25"]+trend))
    mean=r["games"]*p*mu
    sigma=math.sqrt(max(0.,r["games"]*p*(r["sigma"]**2+(1-p)*mu**2)))
    return mean,max(4.,sigma)

def scores(rows,params):
    losses=[r["actual"]-forecast(r,params)[0] for r in rows]
    return {"mae":round(fmean(abs(e) for e in losses),3),
      "rmse":round(math.sqrt(fmean(e*e for e in losses)),3),
      "bias_prediction_minus_actual":round(-fmean(losses),3)}

def gain_cluster_bootstrap(rows,best,base,seed=20261022):
    by_player=defaultdict(list)
    for r in rows:
        b=forecast(r,base)[0];x=forecast(r,best)[0]
        by_player[r["pid"]].append(abs(r["actual"]-b)-abs(r["actual"]-x))
    rng=random.Random(seed);keys=sorted(by_player);boot=[]
    for i in range(500):
        selected=[keys[rng.randrange(len(keys))] for _ in keys]
        boot.append(fmean(e for k in selected for e in by_player[k]))
    boot.sort()
    return [round(boot[int(.025*(len(boot)-1))],3),
            round(boot[int(.975*(len(boot)-1))],3)]

def quantile(values,prob):
    x=sorted(values)
    return x[int(prob*(len(x)-1))]

def coverage(rows,params,limits):
    inrange=0;width=0;groups=defaultdict(lambda:[0,0])
    for r in rows:
        pred,scale=forecast(r,params)
        low,high=pred+limits[0]*scale,pred+limits[1]*scale
        yes=low<=r["actual"]<=high
        inrange+=yes;width+=high-low
        key=str(r["games"])+" games"
        groups[key][0]+=yes;groups[key][1]+=1
    return {"coverage_pct":round(inrange*100/len(rows),1),
      "avg_width_fp":round(width/len(rows),1),
      "by_games":{k:round(v[0]*100/v[1],1) for k,v in groups.items() if v[1]>=50}}

def execute(input_file=None,output_file=None,schedule_loader=None):
    root=json.loads((pathlib.Path(input_file) if input_file else DATA/"nba_history.json").read_text())
    if root.get("status")!="complete" or len(root.get("players",{}))<200:
        raise ValueError("Audited full three-season history required")
    if schedule_loader is None:
        schedule_loader=lambda season:get_csv(SCHEDULES.format(SEASONS[season]))
    utc_file=DATA/"historical_tipoffs.json"
    historical_utc=json.loads(utc_file.read_text(encoding="utf8")) if utc_file.exists() else {}
    if historical_utc and historical_utc.get("calendar_status")!="fully_matched_historical_tipoffs":
        raise ValueError("Historical tipoffs are incomplete; refuse exact-week claims")
    data={};checks={}
    for period in SEASONS:
        fixture,clock=schedule(schedule_loader(period),period,
                               (historical_utc.get("seasons") or {}).get(period))
        rows,stats=cohort(fixture,root["players"],period)
        data[period]=rows;checks[period]={**clock,**stats}
    dev=data["2024/25"];test=data["2025/26"]
    baseline=(10,0.,False)
    options=[(k,recent,m) for k in (0,5,10,20) for recent in (0.,.25,.5) for m in (False,True)]
    best=min(options,key=lambda p:(scores(dev,p)["mae"],p))
    base_scores=scores(test,baseline);candidate=scores(test,best)
    improvement=round(100*(base_scores["mae"]-candidate["mae"])/base_scores["mae"],2)
    bounds=gain_cluster_bootstrap(test,best,baseline)
    passed=best!=baseline and improvement>=1. and bounds[0]>0
    active=best if passed else baseline
    zdev=[(r["actual"]-forecast(r,active)[0])/forecast(r,active)[1] for r in dev]
    limits=[quantile(zdev,.1),quantile(zdev,.9)]
    interval=coverage(test,active,limits)
    exact=all(checks[y]["week_semantics"]=="moscow_start" for y in SEASONS)
    ready=passed and 75<=interval["coverage_pct"]<=87 and exact
    report={"schema_version":1,
      "status":"research_weekly_validated_for_eligible_cohort" if ready else "research_only_not_deployed",
      "updated_at_utc":datetime.now(timezone.utc).isoformat(),
      "development":"2024/25","holdout":"2025/26",
      "scope":"Player-week NBA games, inferred team tenure; not an optimized Sports.ru fantasy roster",
      "eligibility":"At least 14 previous appearances, >=12 team games, recent appearance <=16 days, established team tenure",
      "calendar_week":"Moscow based on UTC tipoffs" if exact else "US calendar date proxy; not exact Sports.ru week",
      "qa":checks,
      "models":{
        "naive_all_play":{"formula":"last10 FP x team games","test_mae":round(fmean(abs(r["actual"]-r["mu10"]*r["games"]) for r in test),3)},
        "availability_baseline":{"params":baseline,"dev":scores(dev,baseline),"test":base_scores},
        "development_selected":{"params":best,"dev":scores(dev,best),"test":candidate,
            "test_improvement_pct":improvement,"gain_95pct_player_bootstrap":bounds,"adoption_gate_passed":passed},
        "prediction_interval":{"applied_params":active,"train_standardized_P10_P90":[round(v,4) for v in limits],
            "holdout":interval}
      },
      "historical_utc_source":historical_utc.get("source") if historical_utc else None,
      "limitations":[
        "Exact weekly Moscow boundary cannot be claimed if archived schedule lacks tipoff UTC.",
        "Team membership is inferred from player appearances, not historical active/injured rosters.",
        "Long-term injured players and some trades are excluded by recent-appearance eligibility.",
        "Future known games from final-season calendar may include rescheduling not known at prediction time.",
        "No Sports.ru prices, transfers, individual matchup adjustments or lineups in evaluation.",
        "Empirical 80pct interval is measured for this cohort only; not guaranteed for 2026/27."],
      "adopt_on_site":False
    }
    file=pathlib.Path(output_file) if output_file else DATA/"weekly_model_validation.json"
    file.parent.mkdir(parents=True,exist_ok=True)
    tmp=file.with_suffix(".tmp");tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.replace(file)
    return report

if __name__=="__main__":
    out=execute()
    print(json.dumps({"status":out["status"],"calendar_week":out["calendar_week"],
        "qa":out["qa"],"models":out["models"]},ensure_ascii=False,indent=2))
