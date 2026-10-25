"""Prospective paired played-game FP shadow predictions, Sports.ru scoring only.

Never predicts DNP from missing active boxscore rows. Never uses a future
result in a forecast. All feature observations must be captured before issue
time; historical aggregates are prior-season only. No roster/transfer writes.
"""
from __future__ import annotations
from collections import defaultdict,Counter
from datetime import datetime,timedelta,timezone
import json,math,hashlib
from src.sync import DATA
from src.rolling_decision_research import instant,stamp

UTC=timezone.utc
HORIZON=timedelta(hours=72)
LIMIT=12000

def read(name):
    return json.loads((DATA/name).read_text(encoding="utf8"))

def history_means(index):
    """Only audited previous seasons; use 2025/26 as baseline, no current result."""
    if index.get("status")!="complete" or len(index.get("player_shards",{}))<200:
        raise ValueError("Historical coverage missing")
    out={}
    files=sorted({v for v in index["player_shards"].values()})
    for file in files:
        if not file.startswith("shard_") or "/" in file:raise ValueError("Bad history shard")
        blob=read("history/"+file)
        if blob.get("version")!=index.get("version"):raise ValueError("History version mismatch")
        for pid,seasons in blob["players"].items():
            last=next((s for s in seasons if s.get("season")=="2025/26"),None)
            if not last or last.get("games",0)<10:continue
            seq=last.get("game_log")
            if not isinstance(seq,list) or len(seq)!=last["games"]:continue
            fps=[float(r["fp"]) for r in seq]
            if not all(math.isfinite(x) for x in fps):continue
            out[pid]=round(sum(fps[-20:])/len(fps[-20:]),4)
    return out

def issue(prior,live,catalog,history,rolling,now):
    if now.utcoffset() is None:raise ValueError("Aware issue time needed")
    now=now.astimezone(UTC)
    if (live.get("schedule_quality") or {}).get("freshness")!="fresh":
        raise ValueError("Only validated fresh schedule can issue forecasts")
    if (rolling or {}).get("schema_version")!=1 or not rolling.get("snapshots"):
        raise ValueError("No prospective observation archive")
    if instant(rolling["updated_at_utc"])>now:raise ValueError("Future snapshot")
    prior=prior or {"schema_version":1,"status":"research_only_not_deployed",
                    "adopt_on_site":False,"issued":[]}
    if prior.get("schema_version")!=1 or prior.get("adopt_on_site") is not False:
        raise ValueError("Invalid prior shadow archive")
    observations=defaultdict(list)
    seen=(rolling.get("row_first_seen_at_utc") or {})
    for r in live.get("rows",[]):
        key=str(r.get("game_id"))+"|"+str(r.get("id"))
        first=seen.get(key)
        if not first or instant(first)>now:continue
        try:
            t=instant(r["utc"]);fp=float(r["fp"])
        except (KeyError,TypeError,ValueError):continue
        if t>=now or r.get("played") is not True or not math.isfinite(fp):continue
        observations[r["id"]].append((t,fp))
    for seq in observations.values():seq.sort()
    players=defaultdict(list)
    for p in catalog.get("players",[]):
        if p.get("team") and p.get("id"):players[p["team"]].append(p)
    existing={(x["game_id"],x["player_id"]) for x in prior["issued"]}
    issued=list(prior["issued"])
    counts=Counter()
    for g in live["schedule"]:
        if g.get("status") in ("canceled","cancelled","postponed"):continue
        t=instant(g["utc"])
        if not now+timedelta(minutes=30)<t<=now+HORIZON:continue
        for team in (g["home"],g["away"]):
            for p in players[team]:
                pid=p["id"];key=(g["id"],pid)
                if key in existing:continue
                baseline=history.get(pid)
                if baseline is None:
                    counts["without_verified_prior_season"]+=1;continue
                logs=[fp for time,fp in observations.get(pid,[]) if time<now]
                weighted=round((baseline*10+sum(logs[-5:]))/(10+len(logs[-5:])),4)
                item={"game_id":g["id"],"player_id":pid,"team":team,
                      "game_utc_at_issue":g["utc"],"issued_at_utc":stamp(now),
                      "baseline_fp_if_play":baseline,
                      "candidate_fp_if_play":weighted,
                      "observed_current_played_games":len(logs),
                      "historical_source":"2025/26 verified FP last20 (played only)",
                      "club_evidence":"current_Sports_ru_catalog_not_historical_roster_verified",
                      "no_play_probability":True}
                issued.append(item);existing.add(key);counts["new_predictions"]+=1
                if len(issued)>LIMIT:raise ValueError("Prediction archive size safety")
    result={**prior,"updated_at_utc":stamp(now),"issued":issued,
           "status":"research_only_not_deployed","adopt_on_site":False,
           "prediction_semantics":"FP conditional on playing; no p_play; Sports.ru formula",
           "first_observed_current_results_source":"rolling_decision_research.row_first_seen_at_utc",
           "candidate_not_tuned_to_2026_27_outcomes":True}
    return result,dict(counts)

def audit(pred,live,now):
    rows=defaultdict(list)
    finals={g["id"]:g for g in live.get("games",[]) if g.get("status")=="final"}
    for r in live.get("rows",[]):rows[(r.get("game_id"),r.get("id"))].append(r)
    matched=[];qa=Counter()
    for p in pred.get("issued",[]):
        try:
            issued=instant(p["issued_at_utc"]);tip=instant(p["game_utc_at_issue"])
        except (ValueError,KeyError,TypeError):
            qa["invalid_prediction"]+=1;continue
        if issued>=tip-timedelta(minutes=30):
            qa["after_lock"]+=1;continue
        if tip>now:
            qa["future"]+=1;continue
        g=finals.get(p["game_id"])
        if not g:
            qa["not_confirmed_final"]+=1;continue
        if g.get("utc")!=p["game_utc_at_issue"]:
            qa["rescheduled_or_tipoff_changed"]+=1;continue
        r=rows.get((p["game_id"],p["player_id"]),[])
        if len(r)!=1 or r[0].get("team")!=p["team"] or r[0].get("played") is not True:
            qa["unknown_unmatched_or_dnp"]+=1;continue
        if not isinstance(r[0].get("minutes"),(int,float)) or r[0]["minutes"]<=0:
            qa["invalid_played_minutes"]+=1;continue
        actual=float(r[0]["fp"])
        if not math.isfinite(actual):continue
        matched.append((actual,p["baseline_fp_if_play"],p["candidate_fp_if_play"]))
    n=len(matched)
    def metric(k):
        return round(sum(abs(v[0]-v[k]) for v in matched)/n,3) if n else None
    return {"status":"research_only_not_deployed","evaluated_at_utc":stamp(now),
            "paired_played_games":n,"baseline_mae":metric(1),"candidate_mae":metric(2),
            "qa":dict(qa),"adopt_on_site":False,
            "warning":"Conditional played-only, selected coverage; no DNP/Brier, transfer value, or deployment claims"}

def run():
    now=datetime.now(UTC)
    prior_path=DATA/"played_fp_shadow_predictions.json"
    old=json.loads(prior_path.read_text()) if prior_path.exists() else None
    live=read("live.json")
    issued,counts=issue(old,live,read("catalog.json"),history_means(read("history/index.json")),
                        read("rolling_decision_research.json"),now)
    audit_result=audit(issued,live,now)
    for p,val in [(prior_path,issued),(DATA/"played_fp_shadow_audit.json",audit_result)]:
        tmp=p.with_suffix(".tmp")
        tmp.write_text(json.dumps(val,ensure_ascii=False,separators=(",",":")),encoding="utf8")
        tmp.replace(p)
    return {"issue":counts,"audit":audit_result}

if __name__=="__main__":print(json.dumps(run(),ensure_ascii=False,indent=2))
