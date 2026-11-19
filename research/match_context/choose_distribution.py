"""Independently select quantile features; do not tune against current outcomes."""
import argparse,hashlib,json,pathlib,pickle,time
import numpy as np,pandas as pd
from sklearn.metrics import mean_pinball_loss
from lightgbm import LGBMRegressor
import run_phase1 as b
import run_phase2 as t
from availability import mixture_quantiles,STATUSES

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase2',type=pathlib.Path,required=True);ap.add_argument('--near',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);start=time.time();d=pd.read_pickle(a.phase2/'feature_frame.pkl');d=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True);pl=d.y_play==1;kn=d.y_play.notna();m=b.masks(d);fs=t.feature_sets(d);base=d.fp10.to_numpy();levels=[.025,.1,.25,.5,.75,.9,.975];selection={}
    for family in ['form','context','all']:
        scores={}
        for q in levels:
            model=LGBMRegressor(**dict(b.BASE_PARAMS,n_jobs=1,objective='quantile',alpha=q));ix=m['train']&pl;model.fit(d.loc[ix,fs[family]],d.loc[ix,'y_fp']-base[ix]);ix=m['select']&pl;p=base[ix]+model.predict(d.loc[ix,fs[family]]);scores[str(q)]=float(mean_pinball_loss(d.loc[ix,'y_fp'],p,alpha=q))
        selection[family]={'by_quantile':scores,'mean_pinball':float(np.mean(list(scores.values())))};print('QUANTILE FAMILY',family,selection[family],flush=True)
    chosen=min(selection,key=lambda k:selection[k]['mean_pinball']);print('QUANTILE WINNER FROZEN',chosen,flush=True)
    with (a.near/'research_models.pkl').open('rb') as f:bundle=pickle.load(f)
    tr=(d.date<'2026-01-01')&pl;cal=(d.date>='2026-01-24')&(d.date<='2026-02-15');qmodels={};qs=[]
    for q in levels:
        model=LGBMRegressor(**dict(b.BASE_PARAMS,n_jobs=1,objective='quantile',alpha=q));model.fit(d.loc[tr,fs[chosen]],d.loc[tr,'y_fp']-base[tr]);qmodels[q]=model;qs.append(base+model.predict(d[fs[chosen]]));print('FINAL Q',q,flush=True)
    values=np.sort(np.column_stack(qs),axis=1);pc=bundle['participation_features'];raw=bundle['participation_model'].predict_proba(d[pc])[:,1]
    from scipy.special import logit
    p=bundle['participation_calibrator'].predict_proba(logit(np.clip(raw,.001,.999)).reshape(-1,1))[:,1];mix=mixture_quantiles(values,levels,p,levels);offsets={};moffsets={};groups={};groupn={}
    for status in STATUSES:groupn[status]=int((cal&pl&(d['inj_'+status.lower()]==1)).sum())
    for alpha in [.5,.2,.05]:
        lo=int(np.argmin(abs(np.array(levels)-alpha/2)));hi=int(np.argmin(abs(np.array(levels)-(1-alpha/2))));ix=cal&pl;offsets[alpha]=b.conformal_offset(d.loc[ix,'y_fp'],values[ix,lo],values[ix,hi],alpha);ix=cal&kn;moffsets[alpha]=b.conformal_offset(d.loc[ix,'y_fp'],mix[ix,lo],mix[ix,hi],alpha);groups[alpha]={}
        for status in STATUSES:
            ix=cal&pl&(d['inj_'+status.lower()]==1)
            if ix.sum()>=60:groups[alpha][status]=max(offsets[alpha],b.conformal_offset(d.loc[ix,'y_fp'],values[ix,lo],values[ix,hi],alpha))
    bundle.update(quantile_models=qmodels,quantile_features=fs[chosen],conditional_offsets=offsets,mixture_offsets=moffsets,conditional_status_offsets=groups,conditional_status_minimum_calibration_n=60)
    with (a.output/'research_models.pkl').open('wb') as f:pickle.dump(bundle,f)
    report={'status':'exploratory_distribution_followon_not_deployed','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'mean_and_pplay_weights_unchanged':True,'mean_winner':bundle['mean_winner'],'participation_winner':bundle['participation_winner'],'quantile_selection':selection,'quantile_winner':chosen,'conditional_global_offsets':offsets,'conditional_status_offsets':groups,'status_calibration_n':groupn,'model_sha256':hashlib.sha256((a.output/'research_models.pkl').read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL_DISTRIBUTION.md').read_bytes()).hexdigest(),'no_current_outcomes_used_for_parameter_fit_or_calibration':True,'current_subgroup_problem_motivated_followon':True,'runtime_seconds':time.time()-start};b.write_json(a.output/'MODEL_RESEARCH_REPORT.json',report);print('DISTRIBUTION COMPLETE',chosen,groupn,flush=True)
if __name__=='__main__':main()
