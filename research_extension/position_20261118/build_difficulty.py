"""Daily read-only descriptive difficulty: fixed weights, no fitting or selection.

Inputs are the same coherent public source snapshot and future feature frame
used by the existing forecast export. A preserved historical residual anchor is
combined with current-season replay residuals from the unchanged near Ridge.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
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
POSITIONS=("PG","SG","SF","PF","C")
DAILY_ASSETS=("GENERAL_REFERENCE.json","general_ridge_reference.pkl","general_reference_covariance.npz",
              "historical_residual_anchor.csv.gz","SEASON_POSITION_MAPPING.json","POSITION_RESEARCH_REPORT.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def historical_position_digest(mapping):
    triples=sorted((r["season"],r["nba_person_id"],r["fantasy_position"]) for r in mapping["records"] if r["season"]<2027 and r["nba_person_id"])
    return hashlib.sha256(json.dumps(triples,separators=(",",":")).encode()).hexdigest()


def source_fingerprint(source,asof_date):
    files=["current/player_boxscores_2027.csv","current/game_rosters_2027.csv","current/nba_schedule_2027.csv.gz","current/injury_report_2027.csv.gz"]
    return {"asof_date":asof_date,"source_hashes":{f:sha(source/f) for f in files}}


def load_reference(asset_dir):
    metadata=json.loads((asset_dir/"GENERAL_REFERENCE.json").read_text())
    for name,expected in metadata["files"].items():
        if sha(asset_dir/name)!=expected:
            raise ValueError("REFERENCE_HASH_MISMATCH:"+name)
    reference=pickle.load((asset_dir/"general_ridge_reference.pkl").open("rb"))
    covariance=np.load(asset_dir/"general_reference_covariance.npz")
    return reference,metadata,covariance


def get_current_replay(source,work,asof_date):
    scientific=BASE/"research/match_context"
    if not scientific.exists():scientific=ROOT/"research/match_context"
    sys.path.insert(0,str(scientific))
    import current_validation
    current_validation.ASOF_DATE=asof_date
    frame,qa=current_validation.build_current_frame(source,work/"near_chunks",leads=(0,))
    frame.to_pickle(work/"current_near_replay.pkl")
    (work/"current_near_replay.pkl.source.json").write_text(json.dumps(source_fingerprint(source,asof_date),indent=2)+"\n")
    (work/"current_near_replay_qa.json").write_text(json.dumps(qa,indent=2)+"\n")
    return frame,qa


def general_deltas(future,reference,covariance):
    model,features=reference["model"],reference["features"]
    d=future.copy()
    for c in ("pid","game","date","team","opp","issue_date"):
        d[c]=d[c].astype(str)
    # One vote per current eligible NBA player. Opponent snapshots are deduped
    # by team, so a team with more future fixtures does not get more weight.
    reference_players=d.sort_values(["pid","date","game"]).drop_duplicates("pid").copy()
    strength=[f"opp_{metric}{window}" for window in (10,25) for metric in ("pts","opp_pts","poss","opp_fp","net","ortg","drtg")]+["opp_elo"]
    team_rows=d.groupby("opp",sort=True,observed=True)[strength].first()
    if len(team_rows)!=30 or team_rows.isna().any().any():
        raise ValueError("COMPLETE_30_OPPONENT_REFERENCE_REQUIRED")
    # Every strength snapshot must be the same information set even when a
    # team appears on several future dates/horizons.
    for column in strength:
        if (d.groupby("opp",observed=True)[column].nunique(dropna=False)>1).any():
            raise ValueError("INCOHERENT_OPPONENT_SNAPSHOT:"+column)
    neutral=team_rows.mean(axis=0)
    base=reference_players.copy()
    base["opp_days_rest"]=2.0;base["opp_b2b"]=0.0;base["opp_games_last4"]=2.0
    base["rest_difference"]=base.team_days_rest-2.0
    base["h2h_n"]=0.0;base["h2h_residual_shrunk"]=0.0
    for col in strength:base[col]=float(neutral[col])
    def averaged_design(frame):
        vectors=[]
        for home in (0.,1.):
            x=frame.copy();x["home"]=home
            x["win_probability_elo"]=1/(1+10**((x.opp_elo-x.team_elo-(60 if home else -60))/400))
            transformed=model[:-1].transform(x[features])
            vectors.append(np.r_[1.,transformed.mean(axis=0)])
        return np.mean(vectors,axis=0)
    neutral_design=averaged_design(base)
    coefficients=np.r_[model[-1].intercept_,model[-1].coef_]
    result={}
    for team,values in team_rows.iterrows():
        actual=base.copy()
        for col in strength:actual[col]=float(values[col])
        contrast=averaged_design(actual)-neutral_design
        delta=float(contrast@coefficients)
        standard_errors={cluster:float(np.sqrt(max(0.,contrast@covariance[cluster]@contrast))) for cluster in ("date","player")}
        se=max(standard_errors.values())
        result[team]={"delta":delta,"se":se,"interval95":[delta-1.96*se,delta+1.96*se],"cluster_se":standard_errors}
    meta={"players":len(reference_players),"teams":len(team_rows),
          "weighting":"One equal vote per current eligible NBA player; 50/50 home-away. Neutral opponent is the arithmetic mean of the 30 deduplicated team strength snapshots.",
          "changed_features":strength+["win_probability_elo"],
          "held_fixed":"Same player form, expected minutes, own-team context and issue-date availability. Opponent rest fixed at 2 days/no back-to-back/2 games in prior4 days, H2H fixed at zero in both alternatives. No future outcome or actual target-game minutes.",
          "interpretation":"Standardized conditional FP contrast of the existing Ridge matchup component. It is not a causal defense rating or a separately validated calendar score."}
    return result,meta


def residual_statistics(residuals,asof_date,prior=100.,half_life=60.):
    d=residuals.copy().reset_index(drop=True)
    if d.empty or (d.date>=asof_date).any():
        raise ValueError("RESIDUALS_MUST_PRECEDE_ASOF_DATE")
    age=(pd.Timestamp(asof_date)-pd.to_datetime(d.date)).dt.days.to_numpy()
    weights=np.exp2(-age/half_life)
    values=d.residual.to_numpy(float)
    if not np.isfinite(values).all():raise ValueError("NONFINITE_RESIDUAL")
    codes={key:pd.factorize(d[key])[0] for key in ("date","pid","game")}
    total_weight=weights.sum();global_mean=float(weights@values/total_weight)
    global_influence=weights*(values-global_mean)/total_weight
    def summary(mask):
        w=weights[mask];r=values[mask]
        if not len(w) or w.sum()==0:return None
        by_game=np.bincount(codes["game"][mask],weights=w)
        return {"mean":float(w@r/w.sum()),"weight":float(w.sum()),
                "effective_games":float(w.sum()**2/(by_game@by_game)),
                "n_games":int(d.loc[mask,"game"].nunique()),"n_players":int(d.loc[mask,"pid"].nunique()),
                "n_player_games":int(mask.sum()),"current_season_n_games":int(d.loc[mask & d.season.eq(2027).to_numpy(),"game"].nunique()),
                "current_season_player_games":int((mask & d.season.eq(2027).to_numpy()).sum()),
                "latest_game_date":str(d.loc[mask,"date"].max())}
    pos_masks={p:d.fantasy_position.eq(p).to_numpy() for p in POSITIONS}
    pos_stats={p:summary(mask) for p,mask in pos_masks.items()}
    result={}
    for opponent in sorted(d.opp.unique()):
        om=d.opp.eq(opponent).to_numpy();overall=summary(om)
        result[opponent]={"ALL":{**overall,"effect":0.,"se":0.,"shrinkage_fraction":1.}}
        for pos in POSITIONS:
            pm=pos_masks[pos];cm=om & pm;cell=summary(cm);position=pos_stats[pos]
            if not cell or not position:
                result[opponent][pos]=None;continue
            shrink=cell["weight"]/(cell["weight"]+prior)
            effect=shrink*(cell["mean"]-overall["mean"]-position["mean"]+global_mean)
            influence=global_influence.copy()
            influence[cm]+=weights[cm]*(values[cm]-cell["mean"])/cell["weight"]
            influence[om]-=weights[om]*(values[om]-overall["mean"])/overall["weight"]
            influence[pm]-=weights[pm]*(values[pm]-position["mean"])/position["weight"]
            influence*=shrink
            standard_errors={}
            for cluster in ("date","pid"):
                sums=np.bincount(codes[cluster],weights=influence)
                n=(sums!=0).sum()
                standard_errors[cluster]=float(np.sqrt(max(0.,(sums@sums)*n/max(1,n-1))))
            result[opponent][pos]={**cell,"effect":float(effect),"se":max(standard_errors.values()),
                                   "cluster_se":standard_errors,"shrinkage_fraction":float(shrink)}
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--future-frame",type=Path,required=True)
    ap.add_argument("--source",type=Path,required=True)
    ap.add_argument("--asof-date",required=True,help="NBA game-date cutoff; only strictly earlier completed games")
    ap.add_argument("--assets",type=Path,help="Decoded asset directory; otherwise verified public chunks materialize under --work")
    ap.add_argument("--mapping",type=Path,help="Explicit mapping override; historical digest must match preserved anchor")
    ap.add_argument("--current-frame",type=Path)
    ap.add_argument("--work",type=Path,default=HERE/"daily_work")
    ap.add_argument("--output",type=Path,default=HERE/"results/matchup_difficulty.json")
    args=ap.parse_args();args.work.mkdir(exist_ok=True,parents=True);args.output.parent.mkdir(exist_ok=True,parents=True)
    if args.assets is None:
        if (HERE/"PUBLIC_ASSETS_MANIFEST.json").exists():
            from packed_assets import materialize_assets
            materialize_assets(HERE,args.work/"assets",["results/"+n for n in DAILY_ASSETS])
            args.assets=args.work/"assets/results"
        else:args.assets=HERE/"results"
    if args.mapping is None:args.mapping=args.assets/"SEASON_POSITION_MAPPING.json"
    reference,refmeta,covariance=load_reference(args.assets)
    future=pd.read_pickle(args.future_frame)
    if set(future.issue_date.astype(str))!={args.asof_date}:
        raise ValueError("FUTURE_FRAME_ISSUE_DATE_MISMATCH")
    if (future.date.astype(str)<args.asof_date).any():raise ValueError("FUTURE_FRAME_CONTAINS_PAST_TARGET")
    mapping=json.loads(args.mapping.read_text())
    if historical_position_digest(mapping)!=refmeta["historical_position_identity_digest"]:
        raise ValueError("HISTORICAL_POSITION_MAPPING_CHANGED_RESEARCH_REBUILD_REQUIRED")
    positions={(r["season"],r["nba_person_id"]):r["fantasy_position"] for r in mapping["records"] if r["nba_person_id"]}
    if args.current_frame:
        sidecar=args.current_frame.with_name(args.current_frame.name+".source.json")
        if not sidecar.exists() or json.loads(sidecar.read_text())!=source_fingerprint(args.source,args.asof_date):
            raise ValueError("CURRENT_REPLAY_CACHE_SOURCE_OR_ASOF_MISMATCH")
        current=pd.read_pickle(args.current_frame);qa={"provided_current_frame":True}
    else:
        current,qa=get_current_replay(args.source,args.work,args.asof_date)
    for c in ("date","pid","game","opp"):
        current[c]=current[c].astype(str)
    if "horizon_days" in current and current.horizon_days.ne(0).any():
        raise ValueError("CURRENT_RESIDUALS_REQUIRE_NEAR_REPLAY")
    current=current[(current.date<args.asof_date)&current.y_play.eq(1)&current.y_fp.notna()].copy()
    if current.duplicated(["game","pid"]).any():raise ValueError("DUPLICATE_CURRENT_RESIDUAL")
    if set(current.season.unique())!={2027}:raise ValueError("CURRENT_REPLAY_SEASON_MISMATCH")
    current["fantasy_position"]=[positions.get((int(s),str(p)),"UNKNOWN") for s,p in zip(current.season,current.pid)]
    with threadpool_limits(limits=1):
        current["residual"]=current.y_fp-current.fp10-reference["model"].predict(current[reference["features"]])-reference["mean_bias_correction"]
        general,reference_description=general_deltas(future,reference,covariance)
    historical=pd.read_csv(args.assets/"historical_residual_anchor.csv.gz",dtype={"pid":str,"game":str})
    residuals=pd.concat([historical,current[["date","season","game","pid","opp","fantasy_position","residual"]]],ignore_index=True)
    residuals.to_csv(args.work/"current_adjusted_residuals.csv.gz",index=False,compression="gzip")
    effects=residual_statistics(residuals,args.asof_date)
    opponents={}
    for team,general_stat in general.items():
        opponents[team]={}
        for position in ("ALL",*POSITIONS):
            stats=effects.get(team,{}).get(position)
            if stats is None:
                opponents[team][position]={"status":"INSUFFICIENT_POSITION_SUPPORT","predictive_validated":False,
                    "general_delta_fp":general_stat["delta"],"position_extra_fp":None,"total_delta_fp":None,"effect_interval95":None,
                    "weighted_player_games":0.,"effective_games":0.,"n_games":0,"n_players":0}
                continue
            total=general_stat["delta"]+stats["effect"]
            # Triangle bound avoids asserting zero covariance between the
            # fitted-model contrast and descriptive current residual effect.
            total_se=general_stat["se"]+stats["se"]
            opponents[team][position]={
                "general_delta_fp":general_stat["delta"],"position_extra_fp":stats["effect"],"total_delta_fp":total,
                "general_effect_interval95":general_stat["interval95"],
                "position_effect_interval95":[stats["effect"]-1.96*stats["se"],stats["effect"]+1.96*stats["se"]],
                "effect_interval95":[total-1.96*total_se,total+1.96*total_se],
                "weighted_player_games":stats["weight"],"effective_games":stats["effective_games"],
                "n_games":stats["n_games"],"n_player_games":stats["n_player_games"],"n_players":stats["n_players"],
                "current_season_n_games":stats["current_season_n_games"],"current_season_player_games":stats["current_season_player_games"],
                "shrinkage_fraction":stats["shrinkage_fraction"],"latest_game_date":stats["latest_game_date"],
                "status":"fixed_ridge_context_descriptive" if position=="ALL" else "positional_increment_not_validated",
                "predictive_validated":False,"usable_as_forecast_multiplier":False,
                "uncertainty_method":"Approximate date/player-cluster effect standard errors, larger one-way SE; general+position SEs added conservatively. Conditional on fixed model/mapping; not a per-game prediction interval or guaranteed coverage."}
    research=json.loads((args.assets/"POSITION_RESEARCH_REPORT.json").read_text())
    derivation_path=args.source.parent/"DERIVATION.json"
    derivation=json.loads(derivation_path.read_text()) if derivation_path.exists() else {}
    generated=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    latest_date=str(current.date.max())
    output={"schema":"nba_matchup_difficulty_v1","generated_at_utc":generated,"as_of_utc":generated,
            "as_of_date_ET":args.asof_date,"latest_outcome_date":latest_date,
            "source_availability_upper_bound_utc":derivation.get("source_availability_upper_bound_utc"),
            "status":"descriptive_research_not_a_forecast_adjustment","adopt_on_site":False,
            "production_forecasts_adjusted":False,"optimizer_adjusted":False,"positions":["ALL",*POSITIONS],
            "sign_convention":"Positive delta means the opponent is easier for conditional fantasy FP; negative means harder.",
            "units":"FP per standard-reference played player-game versus neutral opponent; calendar summaries average by scheduled game, separately report game count.",
            "opponents":opponents,"reference":reference_description,
            "validation":{"general":{"whole_matchup_context_group_previously_validated":True,"standalone_calendar_score_validated":False,
                                        "extra_generic_opponent_residual_retained":False},
                          "position":{"status":"increment_not_retained","chosen_by_development_only":research["chosen_by_development_only"],
                                      "predictive_increment_supported":False,"historical_position_vintage_verified":False,
                                      "development_rmse":{k:v["pooled"]["rmse"] for k,v in research["selection"].items()},
                                      "confirmation_and_exposed_audit":research["results"]},
                          "prospective_or_economic_benefit_proven":False},
            "residual_method":{"half_life_calendar_days":60,"interaction_prior_player_games":100,
                               "prior_choice":"The larger of the two preregistered priors, used for descriptive display only; no winning positional predictor was selected.",
                               "adjustment":"Played-game residual versus monthly prequential Ridge historically and immutable near Ridge in current season; subtract opponent and position marginal means and add back global mean, then shrink interaction toward zero.",
                               "observed_target_minutes_used_as_predictor":False,"historical_residual_rows":len(historical),"current_residual_rows":len(current)},
            "position_mapping":{"source":"Four user-supplied Sports.ru season exports","observed_at_utc":mapping["observed_at_utc"],
                                "historical_point_in_time_verified":False,"source_workbooks":mapping["source_workbooks"],
                                "workbook_clock_note":"Core created timestamps are workbook metadata, not independently verified acquisition timestamps; some are ahead of observed UTC time. Use observed_at_utc for information availability.",
                                "current_nba_positions":{r["nba_person_id"]:r["fantasy_position"] for r in mapping["records"] if r["season"]==2027 and r["nba_person_id"]}},
            "source_hashes":{"future_frame":sha(args.future_frame),"season_position_mapping":sha(args.mapping),
                             "source_player_boxscores":sha(args.source/"current/player_boxscores_2027.csv"),
                             "source_schedule":sha(args.source/"current/nba_schedule_2027.csv.gz"),
                             "general_reference":sha(args.assets/"GENERAL_REFERENCE.json"),
                             "historical_residual_anchor":sha(args.assets/"historical_residual_anchor.csv.gz"),
                             "position_research_report":sha(args.assets/"POSITION_RESEARCH_REPORT.json")},
            "limitations":["Position labels are retrospective seasonal exports, not historically frozen pregame positions.",
                           "Current-season outcomes only update a descriptive state; no fitting, selection or forecast calibration used them.",
                           "Effect uncertainty is approximate and conditional on the selected model, mapping and source quality; it is not a calibrated match or multi-game FP range.",
                           "The adjusted residual is not causal defensive ability and still contains unexpected minutes and role changes.",
                           "Forecasts and KEEP/NOW/LATER must not multiply by or add these displayed descriptive position effects."]}
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (args.work/"BUILD_REPORT.json").write_text(json.dumps({"output":str(args.output),"output_sha256":sha(args.output),"teams":len(opponents),
             "positions":len(output["positions"]),"latest_outcome_date":latest_date,"source_qa":qa,"fitted":False,
             "chosen_positional_predictor":"none","current_residual_rows":len(current),"reference_players":reference_description["players"]},indent=2)+"\n")
    print("DIFFICULTY_READY",str(args.output),"teams",len(opponents),"latest",latest_date,"current_rows",len(current),flush=True)


if __name__=="__main__":main()
