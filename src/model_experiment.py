"""Season Lab conditional FP forecast experiment v2.

Scope: forecast next PLAYED NBA game only. DNP/schedule probabilities are not
trained here. This report must not be conflated with validated weekly FP.

Development: 2024/25; out-of-sample final test: 2025/26.
Each feature observes only that player's earlier played games.
No third-party machine learning dependencies or random training splits.
"""
from __future__ import annotations
import collections
import datetime as dt
import json
import math
import pathlib
import random
import statistics
from src.sync import DATA

TRAIN="2024/25"
TEST="2025/26"
MIN_GAMES=25
RECENCIES=(0.0,0.15,0.30,0.45)
LONG_WEIGHTS=(0.0,0.20,0.40)
MINUTE_WEIGHTS=(0.0,0.25,0.50)
BASELINE=(0.,0.,0.)
SEASON_ORDER=("2023/24","2024/25","2025/26")

def mean(values):
    return sum(values)/len(values)

def quantile(values,q):
    if not values:raise ValueError("Empty quantile")
    sorted_v=sorted(values)
    return sorted_v[int(round((len(sorted_v)-1)*q))]

def prior_features(rows):
    # "rows" includes only observed outcomes of prior played games.
    if len(rows)<MIN_GAMES:raise ValueError("Insufficient history")
    scores=[float(r["fp"]) for r in rows]
    mins=[float(r["min"]) for r in rows]
    base=mean(scores[-10:])
    recent=mean(scores[-5:])
    long=mean(scores[-25:])
    momentum=mean(mins[-5:])-mean(mins[-10:])
    # Use a per-minute scaling derived solely from prior games; guard tiny denominators.
    rate=sum(scores[-10:])/max(75.,sum(mins[-10:]))
    return base,recent,long,momentum,rate

def predict(features,params):
    base,recent,long,momentum,rate=features
    recency,old_weight,minutes_weight=params
    blend=(1-old_weight)*base+old_weight*long
    forecast=(1-recency)*blend+recency*recent
    # Extreme minutes regressions should never extrapolate without bounds.
    min_effect=max(-8.,min(8.,minutes_weight*momentum*max(0.,min(1.5,rate))))
    return max(-5.,min(80.,forecast+min_effect))

def collect(history):
    samples={TRAIN:[],TEST:[]}
    for pid,seasons in history.items():
        season_map={s.get("season"):s for s in seasons}
        prior=[]
        for season in SEASON_ORDER:
            rows=sorted(season_map.get(season,{}).get("game_log",[]),key=lambda r:(str(r.get("d","")),str(r.get("g",""))))
            for row in rows:
                fp=row.get("fp");minute=row.get("min")
                if fp is None or minute is None:continue
                y=float(fp);m=float(minute)
                if not (math.isfinite(y) and math.isfinite(m) and m>0):continue
                if season in samples and len(prior)>=MIN_GAMES:
                    samples[season].append((pid,y,prior_features(prior)))
                prior.append({"fp":y,"min":m})
    if len(samples[TRAIN])<5000 or len(samples[TEST])<5000:
        raise ValueError("Historical sample size too small for claimed test")
    return samples

def evaluate(samples,params):
    diffs=[]
    per_person=collections.defaultdict(list)
    for pid,y,f in samples:
        base=f[0]
        candidate=predict(f,params)
        e0=abs(y-base);e1=abs(y-candidate)
        diffs.append((e0,e1))
        per_person[pid].append(e0-e1)
    n=len(samples)
    return {"n":n,"player_count":len(per_person),
            "baseline_mae":sum(a for a,b in diffs)/n,
            "candidate_mae":sum(b for a,b in diffs)/n,
            "paired_gain":sum(a-b for a,b in diffs)/n,
            "abs_err_baseline":[a for a,b in diffs],
            "abs_err_candidate":[b for a,b in diffs],
            "per_person":per_person}

def bootstrap_gain(eval_,seed=20261022,rounds=400):
    # Cluster bootstrap by NBA player, not independent game observations.
    players=list(eval_["per_person"])
    if not players:return None
    rng=random.Random(seed)
    diffs=[]
    for _ in range(rounds):
        picked=[players[rng.randrange(len(players))] for __ in range(len(players))]
        vals=[d for p in picked for d in eval_["per_person"][p]]
        diffs.append(mean(vals))
    return (quantile(diffs,.025),quantile(diffs,.975))

def run(input_file=None,output_file=None):
    path=pathlib.Path(input_file or DATA/"nba_history.json")
    data=json.loads(path.read_text(encoding="utf-8"))
    if data.get("status")!="complete" or not data.get("players"):
        raise ValueError("Full audited history required")
    history=data["players"]
    for pid,seasons in history.items():
        if any("game_log" not in season for season in seasons):
            raise ValueError("Game logs missing; do not substitute last35")
    samples=collect(history)
    grid=[(r,l,m) for r in RECENCIES for l in LONG_WEIGHTS for m in MINUTE_WEIGHTS]
    dev={}
    for param in grid:dev[param]=evaluate(samples[TRAIN],param)
    # Parameter selection uses ONLY 2024/25.
    winner=min(grid,key=lambda p:dev[p]["candidate_mae"])
    train=dev[winner]
    final=evaluate(samples[TEST],winner)
    low,high=bootstrap_gain(final)
    raw_gain=final["paired_gain"]
    pct=100*raw_gain/final["baseline_mae"]
    adopted=(pct>=1.0 and low>0 and winner!=BASELINE)
    chosen=winner if adopted else BASELINE
    residuals_dev=[abs(y-predict(f,chosen)) for _,y,f in samples[TRAIN]]
    width80=quantile(residuals_dev,.80)
    coverage=sum(abs(y-predict(f,chosen))<=width80 for _,y,f in samples[TEST])/len(samples[TEST])
    abs_holdout=[abs(y-predict(f,chosen)) for _,y,f in samples[TEST]]
    top=sorted(dev.items(),key=lambda z:z[1]["candidate_mae"])[:6]
    report={
        "schema_version":2,
        "status":"validated_for_conditional_game" if adopted else "baseline_retained",
        "updated_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source":"Audited NBA game logs, full 2023/24-2025/26",
        "scope":"Next played game, not next scheduled game or fantasy week",
        "baseline":"Previous 10 played-game FP average",
        "development_year":TRAIN,
        "test_year":TEST,
        "min_previous_played_games":MIN_GAMES,
        "candidate_formula":"(1-recency)*[(1-old_weight)*last10_fp+old_weight*last25_fp]+recency*last5_fp + bounded minutes_weight*(last5_minutes-last10_minutes)*last10_fp_per_minute",
        "best_development_params":{"recency":winner[0],"old_weight":winner[1],"minutes_weight":winner[2]},
        "chosen_params":{"recency":chosen[0],"old_weight":chosen[1],"minutes_weight":chosen[2]},
        "development":{"observations":train["n"],"players":train["player_count"],"mae_baseline":round(train["baseline_mae"],3),
                       "mae_candidate":round(train["candidate_mae"],3)},
        "holdout":{"observations":final["n"],"players":final["player_count"],
                    "mae_baseline":round(final["baseline_mae"],3),
                    "mae_candidate":round(final["candidate_mae"],3),
                    "relative_improvement_pct":round(pct,2),
                    "cluster_bootstrap_gain_95pct_fp":[round(low,3),round(high,3)],
                    "interval_type":"Symmetric absolute-error 80% threshold from development",
                    "interval_half_width_fp":round(width80,2),
                    "interval_holdout_coverage_pct":round(100*coverage,1)},
        "development_top_candidates":[{"params":p,"mae":round(v["candidate_mae"],3)} for p,v in top],
        "adoption_reason":"Only if >=1% holdout gain AND cluster-bootstrap lower CI positive; otherwise retain baseline",
        "limitations":[
          "Test covers playing-game FP, not DNP probabilities or NBA team schedule",
          "Same player can appear many times, so uncertainty is clustered by player",
          "Current-week injuries, roster changes and Sports.ru position/price not modeled",
          "An 80% residual band is not calibrated for a future whole season or a weekly sum"
        ]
    }
    out=pathlib.Path(output_file or DATA/"model_experiment_v2.json")
    tmp=out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    tmp.replace(out)
    return report

if __name__=="__main__":
    out=run()
    print(json.dumps(out,ensure_ascii=False,indent=2))
