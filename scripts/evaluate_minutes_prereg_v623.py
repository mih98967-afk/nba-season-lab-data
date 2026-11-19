"""Forward-only, frozen conditional-minutes evaluation. Read-only and no deployment."""
import argparse,json,math,random
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path

def utc(v):
    x=datetime.fromisoformat(v.replace("Z","+00:00"))
    if x.tzinfo is None: raise ValueError("timestamp without timezone")
    return x.astimezone(timezone.utc)
def number(v):
    if type(v) not in (float,int) or not math.isfinite(v): raise ValueError("invalid numeric value")
    return float(v)
def key(row):
    result=(row.get("game_id"),row.get("player_id"))
    if not all(isinstance(x,str) and x for x in result): raise ValueError("missing identity")
    return result
def mean(v): return sum(v)/len(v) if v else None

def evaluate(shadow,contract):
    if shadow.get("status")!="research_only_not_deployed" or shadow.get("adopt_on_site") is not False:
        raise ValueError("original research-only safety gate changed")
    if shadow.get("model_sha256")!=contract["model_sha256"] or contract["status"]!="PREREGISTERED_FUTURE_ONLY":
        raise ValueError("preregistered frozen model mismatch")
    start,end=utc(contract["start_inclusive_utc"]),utc(contract["end_exclusive_utc"])
    if not start<end: raise ValueError("invalid evaluation cutoff")
    issued={}
    for r in shadow["issued"]:
        k=key(r)
        if k in issued: raise ValueError("duplicate issue")
        issued[k]=r
    outcomes={}
    for r in shadow["observed"]:
        k=key(r)
        if k in outcomes or k not in issued: raise ValueError("duplicate or orphan outcome")
        outcomes[k]=r
    selected={}
    for k,r in issued.items():
        t=utc(r["challenger_issued_at_utc"])
        if not start<=t<end: continue
        if r.get("model_sha256")!=contract["model_sha256"]: raise ValueError("postcutoff model drift")
        if not utc(r["original_minutes_issued_at_utc"])<=t<utc(r["individual_lock_utc"])<utc(r["game_utc"]):
            raise ValueError("invalid T-30 provenance")
        if r.get("source_all_current_minutes_first_seen_pre_issue") is not True:
            raise ValueError("missing pre-issue source proof")
        if r.get("current_same_team_played_n") not in contract["prior_verified_games"]:
            raise ValueError("unverified sample count")
        if not all(0<=number(r[k])<=48 for k in ("baseline_minutes","challenger_minutes")):
            raise ValueError("invalid conditional minutes")
        selected[k]=r
    scored=[]
    bins=defaultdict(list)
    dates=defaultdict(list)
    prior=defaultdict(list)
    for k,r in outcomes.items():
        if k not in selected: continue
        issued_row=selected[k]
        if r.get("team")!=issued_row.get("team") or (r.get("game_utc") is not None and r["game_utc"]!=issued_row["game_utc"]):
            raise ValueError("player-game identity mismatch")
        if utc(r["postgame_first_seen_at_utc"])<=utc(issued_row["game_utc"]):
            raise ValueError("postgame outcome leaked before tipoff")
        actual=number(r["actual_minutes"])
        if not 0<actual<=70: raise ValueError("only positive-minute verified appearances")
        base=number(issued_row["baseline_minutes"])
        alt=number(issued_row["challenger_minutes"])
        date=r.get("et_date")
        if not isinstance(date,str) or len(date)!=10: raise ValueError("missing ET date")
        record={"game_id":k[0],"gain":abs(base-actual)-abs(alt-actual),
                "base_error":abs(base-actual),"alt_error":abs(alt-actual),
                "base_bias":base-actual,"alt_bias":alt-actual}
        scored.append(record)
        dates[date].append(record)
        prior[str(issued_row["current_same_team_played_n"])].append(record)
        edges=contract["minutes_groups"]
        for i in range(len(edges)-1):
            if edges[i]<=base<edges[i+1]:
                bins[str(edges[i])+"-"+str(edges[i+1])].append(record)
                break
        else: raise ValueError("predeclared minutes strata invalid")
    def metrics(rows):
        if not rows:return {"n":0}
        return {"n":len(rows),"baseline_MAE":round(mean([x["base_error"] for x in rows]),4),
            "challenger_MAE":round(mean([x["alt_error"] for x in rows]),4),
            "paired_MAE_gain":round(mean([x["gain"] for x in rows]),4),
            "baseline_bias":round(mean([x["base_bias"] for x in rows]),4),
            "challenger_bias":round(mean([x["alt_bias"] for x in rows]),4)}
    gate=contract["thresholds"]
    complete=(len(dates)>=gate["ET_dates"] and len(scored)>=gate["positive_minute_pairs"]
              and len({r["game_id"] for r in scored})>=gate["NBA_games"])
    ci=None
    if complete:
        rng=random.Random(contract["seed"]);names=sorted(dates)
        boot=[]
        for _ in range(contract["resamples"]):
            gain=[r["gain"] for date in (rng.choice(names) for __ in names) for r in dates[date]]
            boot.append(mean(gain))
        boot.sort();n=len(boot)
        ci=[round(boot[int(.025*(n-1))],4),round(boot[int(.975*(n-1))],4)]
    v=metrics(scored)
    success=bool(complete and ci and ci[0]>0 and v["paired_MAE_gain"]>=contract["exploratory_threshold_minutes_gain"])
    return {"schema":"nba_minutes_future_prereg_v1","status":"EXPLORATORY_PASS_NOT_DEPLOYABLE" if success else
        "INSUFFICIENT_FUTURE_SAMPLE" if not complete else "NO_CLEAR_ADVANTAGE",
        "first_issue_window":[contract["start_inclusive_utc"],contract["end_exclusive_utc"]],
        "model_sha256":contract["model_sha256"],
        "cohort":{"issued":len(selected),"verified_played":len(scored),"not_scored_as_dnp_or_zero":len(selected)-len(scored),
            "NBA_games":len({r["game_id"] for r in scored}),"ET_dates":len(dates)},
        "conditional_played_only":v,"per_baseline_minutes_group":{k:metrics(v) for k,v in bins.items()},
        "per_previous_played_n":{k:metrics(v) for k,v in prior.items()},
        "ET_date_bootstrap95":ci,"exploratory_sample_gate":complete,
        "site_adoption_allowed":False,"change_FP_or_P_play_allowed":False,
        "warning":"Played-only selection is not representative full-roster P(play) or certified individual minutes intervals."}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--data-root",type=Path,default=Path("data"))
    a.add_argument("--contract",type=Path,default=Path("docs/NBA_MINUTES_FUTURE_PREREG_20261120.json"))
    a.add_argument("--output",type=Path,required=True)
    x=a.parse_args()
    contract=json.loads(x.contract.read_text())
    shadow=json.loads((x.data_root/"current_season_minutes_shadow_research.json").read_text())
    report=evaluate(shadow,contract)
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"status":report["status"],"cohort":report["cohort"],"site_adoption_allowed":False}))
if __name__=="__main__":main()
