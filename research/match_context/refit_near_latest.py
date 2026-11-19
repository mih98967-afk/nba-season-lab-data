"""Latest historical refit of the already selected near-game recipe."""
import argparse,hashlib,json,pathlib,pickle,time
import numpy as np,pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from scipy.special import logit
from lightgbm import LGBMRegressor
import run_phase1 as b
from availability import mixture_quantiles

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase2',type=pathlib.Path,required=True);ap.add_argument('--selected',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);start=time.time()
    with (a.selected/'research_models.pkl').open('rb') as f:bundle=pickle.load(f)
    d=pd.read_pickle(a.phase2/'feature_frame.pkl');d=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True);day=d.date;train=day<'2026-01-01';pcal=(day>='2026-01-01')&(day<='2026-01-23');ical=(day>='2026-01-24')&(day<='2026-02-15');confirm=day>='2026-02-16';pl=d.y_play==1;kn=d.y_play.notna();base=d.fp10.to_numpy();models={};means=[]
    for name,old in bundle['mean_models'].items():
        cols=bundle['feature_sets'][bundle['specs'][name][0]];model=clone(old);model.fit(d.loc[train&pl,cols],d.loc[train&pl,'y_fp']-d.loc[train&pl,'fp10']);models[name]=model;means.append(model.predict(d[cols]))
    mu=base+np.mean(means,axis=0);bias=float((d.loc[pcal&pl,'y_fp']-mu[pcal&pl]).mean());mu+=bias
    pc=bundle['participation_features'];pm=clone(bundle['participation_model']);pm.fit(d.loc[train&kn,pc],d.loc[train&kn,'y_play']);raw=pm.predict_proba(d[pc])[:,1];cal=LogisticRegression(C=100,max_iter=500).fit(logit(np.clip(raw[pcal&kn],.001,.999)).reshape(-1,1),d.loc[pcal&kn,'y_play']);p=cal.predict_proba(logit(np.clip(raw,.001,.999)).reshape(-1,1))[:,1];qcols=bundle['quantile_features'];levels=bundle['quantile_levels'];qmodels={};qs=[]
    for v in levels:
        model=LGBMRegressor(**dict(b.BASE_PARAMS,n_jobs=1,objective='quantile',alpha=v));model.fit(d.loc[train&pl,qcols],d.loc[train&pl,'y_fp']-d.loc[train&pl,'fp10']);qmodels[v]=model;qs.append(base+model.predict(d[qcols]));print('NEAR LATEST quantile',v,flush=True)
    q=np.sort(np.column_stack(qs),axis=1);mix=mixture_quantiles(q,levels,p,levels);off={};moff={};intervals={}
    for alpha in [.5,.2,.05]:
        lo=int(np.argmin(abs(np.array(levels)-alpha/2)));hi=int(np.argmin(abs(np.array(levels)-(1-alpha/2))));ix=ical&pl;off[alpha]=b.conformal_offset(d.loc[ix,'y_fp'],q[ix,lo],q[ix,hi],alpha);ix=ical&kn;moff[alpha]=b.conformal_offset(d.loc[ix,'y_fp'],mix[ix,lo],mix[ix,hi],alpha);ix=confirm&pl;ix2=confirm&kn;intervals[str(1-alpha)]={'conditional':b.interval_metrics(d.loc[ix,'y_fp'],q[ix,lo]-off[alpha],q[ix,hi]+off[alpha],alpha),'unconditional':b.interval_metrics(d.loc[ix2,'y_fp'],mix[ix2,lo]-moff[alpha],mix[ix2,hi]+moff[alpha],alpha)}
    bundle.update(mean_models=models,mean_bias_correction=bias,participation_model=pm,participation_calibrator=cal,quantile_models=qmodels,conditional_offsets=off,mixture_offsets=moff)
    with (a.output/'research_models.pkl').open('wb') as f:pickle.dump(bundle,f)
    ix=confirm&pl;ix2=confirm&kn;report={'status':'refitted_near_game_candidate_not_deployed','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'no_2026_27_fit_or_calibration':True,'mean_winner':bundle['mean_winner'],'participation_winner':bundle['participation_winner'],'train_last_date':day[train].max(),'probability_calibration':['2026-01-01','2026-01-23'],'interval_calibration':['2026-01-24','2026-02-15'],'confirmation':{'fp':b.reg_metrics(d.loc[ix,'y_fp'],mu[ix]),'baseline_fp':b.reg_metrics(d.loc[ix,'y_fp'],base[ix]),'p_play':b.prob_metrics(d.loc[ix2,'y_play'],p[ix2]),'unconditional_fp':b.reg_metrics(d.loc[ix2,'y_fp'],p[ix2]*mu[ix2]),'intervals':intervals},'model_sha256':hashlib.sha256((a.output/'research_models.pkl').read_bytes()).hexdigest(),'protocol_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL_FINAL_REFIT.md').read_bytes()).hexdigest(),'runtime_seconds':time.time()-start};b.write_json(a.output/'MODEL_RESEARCH_REPORT.json',report);print('NEAR LATEST COMPLETE',report['model_sha256'],flush=True)
if __name__=='__main__':main()
