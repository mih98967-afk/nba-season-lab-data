"""Score an already frozen candidate on reusable current-season features; no fit."""
import argparse,json,pathlib
import pandas as pd
import numpy as np
import run_phase1 as b
from infer import load_verified,predict_frame
from infer_near import predict_near

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--features',type=pathlib.Path,required=True);ap.add_argument('--models',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);bundle,modelcard=load_verified(a.models);d=pd.read_pickle(a.features);near='leads' not in bundle
    if near:d=d[d.horizon_days==0].copy()
    pred=predict_near(bundle,d,complete_team_groups=True) if near else predict_frame(bundle,d);report={'status':'additional_current_season_replay_not_prospective','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'no_2026_27_fit_or_calibration':True,'model_sha256':modelcard['model_sha256'],'model_directory':a.models.name,'per_lead':{},'subgroups':{}};finished=d.date.astype(str)<'2026-11-16';known=d.y_play.notna()
    for h in sorted(d.horizon_days.unique()):
        allrows=finished&(d.horizon_days==h);kn=allrows&known;pl=kn&(d.y_play==1)
        if not kn.any():report['per_lead'][str(int(h))]={'status':'NO_FINISHED_TEST_COHORT','known':0};continue
        entry={'opportunities':int(allrows.sum()),'known':int(kn.sum()),'unknown':int((allrows&~known).sum()),'played':int(pl.sum()),'fp_conditional':{'baseline_last10':b.reg_metrics(d.loc[pl,'y_fp'],d.loc[pl,'fp10']),'selected':b.reg_metrics(d.loc[pl,'y_fp'],pred.loc[pl,'mean_if_play'])},'p_play':{'history_baseline':b.prob_metrics(d.loc[kn,'y_play'],d.loc[kn,'obs_play_rate25']),'selected':b.prob_metrics(d.loc[kn,'y_play'],pred.loc[kn,'p_play'])},'unconditional_fp':{'history_baseline':b.reg_metrics(d.loc[kn,'y_fp'],d.loc[kn,'fp10']*d.loc[kn,'obs_play_rate25']),'selected':b.reg_metrics(d.loc[kn,'y_fp'],pred.loc[kn,'expected_fp'])},'intervals':{},'paired_fp_gain_by_date':b.cluster_gain(d.loc[pl,'y_fp'].to_numpy(),d.loc[pl,'fp10'].to_numpy(),pred.loc[pl,'mean_if_play'].to_numpy(),d.loc[pl,'date'])}
        for n in [50,80,95]:entry['intervals'][str(n)]={'conditional':b.interval_metrics(d.loc[pl,'y_fp'],pred.loc[pl,f'conditional_lo{n}'],pred.loc[pl,f'conditional_hi{n}'],1-n/100),'unconditional':b.interval_metrics(d.loc[kn,'y_fp'],pred.loc[kn,f'lo{n}'],pred.loc[kn,f'hi{n}'],1-n/100)}
        report['per_lead'][str(int(h))]=entry
    for name,sel in [('prior_minutes_28plus',d.min10>=28),('prior_minutes_15to28',(d.min10>=15)&(d.min10<28)),('prior_minutes_under15',d.min10<15),('questionable',d.inj_questionable==1),('no_report',d.inj_submitted==0)]:
        kn=finished&known&(d.horizon_days==0)&sel;pl=kn&(d.y_play==1)
        if pl.sum()<20:continue
        report['subgroups'][name]={'known':int(kn.sum()),'played':int(pl.sum()),'fp_baseline':b.reg_metrics(d.loc[pl,'y_fp'],d.loc[pl,'fp10']),'fp_selected':b.reg_metrics(d.loc[pl,'y_fp'],pred.loc[pl,'mean_if_play']),'participation':b.prob_metrics(d.loc[kn,'y_play'],pred.loc[kn,'p_play']),'conditional80':b.interval_metrics(d.loc[pl,'y_fp'],pred.loc[pl,'conditional_lo80'],pred.loc[pl,'conditional_hi80'],.2)}
    pred.to_csv(a.output/'predictions.csv.gz',index=False);preview=pred[~finished].copy();preview.to_csv(a.output/'RESEARCH_ONLY_preview.csv',index=False);report['preview_rows']=len(preview);report['limitations']=['Current-season retrospective replay, not an issued-before-lock record','Feature/source/schedule vintage caveats remain','Prior observed membership and >=5 previous appearances; cold starts excluded','Per-game prediction intervals, no aggregate-week interval claim','No official Sports.ru credited FP or transfer/price verification'];b.write_json(a.output/'CURRENT_SEASON_REPORT.json',report)
    print('SCORED',a.models.name,{h:dict(n=v.get('known'),fp=v.get('fp_conditional',{}).get('selected',{}).get('mae'),p=v.get('p_play',{}).get('selected',{}).get('brier')) for h,v in report['per_lead'].items()},flush=True)
if __name__=='__main__':main()
