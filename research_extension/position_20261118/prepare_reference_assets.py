"""Package immutable reference weights and historical uncertainty; no refitting."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import pickle
import sys

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BASE=Path(os.environ.get("NBA_RESEARCH_BASE",ROOT/"research_base"))
sys.path.insert(0,str(BASE/"research/match_context"))


def clustered_covariance(design,residual,groups,bread):
    codes,labels=pd.factorize(groups)
    sums=np.zeros((len(labels),design.shape[1]))
    np.add.at(sums,codes,design*residual[:,None])
    correction=len(labels)/max(len(labels)-1,1)*(len(residual)-1)/max(len(residual)-design.shape[1],1)
    return correction*bread@(sums.T@sums)@bread


def main():
    out=HERE/"results"
    d=pd.read_pickle(ROOT/"research_extension/common/feature_frame.pkl")
    d=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True)
    assert set(d.season.unique()) <= {2024,2025,2026}
    mapping=json.loads((out/"SEASON_POSITION_MAPPING.json").read_text())
    lookup={(r["season"],r["nba_person_id"]):r["fantasy_position"] for r in mapping["records"] if r["nba_person_id"]}
    d["fantasy_position"]=[lookup.get((int(s),str(p)),"UNKNOWN") for s,p in zip(d.season,d.pid)]
    nuisance=np.load(ROOT/"research_extension/position/results/pregame_nuisance_predictions.npy")
    d["residual"]=d.y_fp-nuisance
    history=d[d.y_play.eq(1)&d.residual.notna()][["date","season","game","pid","opp","fantasy_position","residual"]]
    history.to_csv(out/"historical_residual_anchor.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    model_path=BASE/"results_near_latest/research_models.pkl"
    bundle=pickle.load(model_path.open("rb"))
    assert list(bundle["mean_models"])==["ridge_context"]
    model=bundle["mean_models"]["ridge_context"]
    features=bundle["feature_sets"][bundle["specs"]["ridge_context"][0]]
    train=d[(d.date<"2026-01-01")&d.y_play.eq(1)&d.y_fp.notna()].copy()
    transformed=model[:-1].transform(train[features])
    design=np.column_stack([np.ones(len(train)),transformed])
    target=(train.y_fp-train.fp10).to_numpy()
    pred=model.predict(train[features])
    residual=target-pred
    coef=np.r_[model[-1].intercept_,model[-1].coef_]
    penalty=np.eye(design.shape[1])*float(model[-1].alpha);penalty[0,0]=0
    with threadpool_limits(limits=1):
        normal=design.T@design+penalty
        reconstructed=np.linalg.solve(normal,design.T@target)
        difference=float(np.max(abs(reconstructed-coef)))
        if difference>1e-6:
            raise ValueError(f"FROZEN_RIDGE_TRAINING_DESIGN_MISMATCH:{difference}")
        bread=np.linalg.inv(normal)
        by_date=clustered_covariance(design,residual,train.date,bread)
        by_player=clustered_covariance(design,residual,train.pid,bread)
    np.savez_compressed(out/"general_reference_covariance.npz",date=by_date,player=by_player)
    with (out/"general_ridge_reference.pkl").open("wb") as handle:
        pickle.dump({"model":model,"features":features,"mean_bias_correction":bundle["mean_bias_correction"],
                     "source_model_sha256":hashlib.sha256(model_path.read_bytes()).hexdigest()},handle)
    meta={"schema":"fixed_ridge_effect_reference_v1","source_model_sha256":hashlib.sha256(model_path.read_bytes()).hexdigest(),
          "historical_position_identity_digest":hashlib.sha256(json.dumps(sorted((r["season"],r["nba_person_id"],r["fantasy_position"]) for r in mapping["records"] if r["season"]<2027 and r["nba_person_id"]),separators=(",",":")).encode()).hexdigest(),
          "train_rows":len(train),"train_max_date":str(train.date.max()),"date_clusters":int(train.date.nunique()),
          "player_clusters":int(train.pid.nunique()),"feature_count":len(features),
          "normal_equation_parameter_max_abs_difference":difference,
          "refit_performed":False,"current_season_outcomes_used":False,
          "method":"Ridge sandwich covariance conditional on selected model and historical design; separate date/player clusters. Daily contrasts use the larger one-way cluster standard error.",
          "limits":"Approximate effect uncertainty, not prediction intervals or guaranteed 95% coverage. Does not include selection, future source errors or all model misspecification.",
          "residual_anchor_rows":len(history),"residual_anchor_last_date":str(history.date.max()),
          "files":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [out/"general_ridge_reference.pkl",out/"general_reference_covariance.npz",out/"historical_residual_anchor.csv.gz"]}}
    (out/"GENERAL_REFERENCE.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps(meta,indent=2))


if __name__=="__main__":main()
