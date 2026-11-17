"""Refit a previously selected multi-lead family without current-season labels."""
import argparse,gc,hashlib,json,pathlib,pickle,time
import numpy as np,pandas as pd
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from lightgbm import LGBMRegressor
from scipy.special import logit
import run_phase1 as b
from infer import load_verified,predict_frame
from availability import mixture_quantiles
from horizon_data import LEADS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--historical',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);start=time.time();old,oldreport=load_verified(a.historical);d=pd.read_pickle(a.historical/'feature_frame.pkl');day=d.date.astype(str);issue=d.issue_date.astype(str)
    train=day<'2025-12-29';pcal=(issue>='2025-12-29')&(issue<='2026-01-10')&(day<='2026-02-07');ical=(issue>='2026-02-08')&(issue<='2026-02-21')&(day<='2026-03-21');confirm=(issue>='2026-03-22');m={'train':train,'pcal':pcal,'ical':ical,'confirm':confirm}
    bounds={}
    for left,right in [('train','pcal'),('pcal','ical'),('ical','confirm')]:
        amax=day[m[left]].max();bmin=issue[m[right]].min();assert amax<bmin;(bounds.update({left+'__'+right:{'last_target':amax,'next_first_issue':bmin}}))
    fs=old['feature_sets'];winner=old['winner'];cols=fs[old['specs'][winner][0]];fp=d.y_play==1;known=d.y_play.notna();model=clone(old['mean_model']);model.fit(d.loc[train&fp,cols],d.loc[train&fp,'y_fp']-d.loc[train&fp,'fp10']);mean=d.fp10.to_numpy()+model.predict(d[cols]);lead=d.horizon_days.to_numpy(dtype=int);bias={h:float(np.mean(d.loc[pcal&fp&(lead==h),'y_fp']-mean[pcal&fp&(lead==h)])) for h in LEADS}
    pm=clone(old['participation_model']);pc=old['participation_features'];pm.fit(d.loc[train&known,pc],d.loc[train&known,'y_play']);raw=pm.predict_proba(d[pc])[:,1];calibrators={};p=np.zeros(len(d))
    for h in LEADS:
        ix=pcal&known&(lead==h);assert ix.sum()>=100;c=LogisticRegression(C=100,max_iter=500).fit(logit(np.clip(raw[ix],.001,.999)).reshape(-1,1),d.loc[ix,'y_play']);calibrators[h]=c;ix=lead==h;p[ix]=c.predict_proba(logit(np.clip(raw[ix],.001,.999)).reshape(-1,1))[:,1]
    qc=old['quantile_features'];levels=old['quantile_levels'];qmodels={};quantiles=[]
    for q in levels:
        qm=LGBMRegressor(**dict(b.BASE_PARAMS,objective='quantile',alpha=q));qm.fit(d.loc[train&fp,qc],d.loc[train&fp,'y_fp']-d.loc[train&fp,'fp10']);qmodels[q]=qm;quantiles.append(d.fp10.to_numpy()+qm.predict(d[qc]));print('LATEST quantile',q,flush=True)
    q=np.sort(np.column_stack(quantiles),axis=1);mix=mixture_quantiles(q,levels,p,levels);off={};moff={}
    for alpha in [.5,.2,.05]:
        lo=int(np.argmin(abs(np.array(levels)-alpha/2)));hi=int(np.argmin(abs(np.array(levels)-(1-alpha/2))));off[alpha]={};moff[alpha]={}
        for h in LEADS:
            ix=ical&fp&(lead==h);assert ix.sum()>=100;off[alpha][h]=b.conformal_offset(d.loc[ix,'y_fp'],q[ix,lo],q[ix,hi],alpha);ix=ical&known&(lead==h);moff[alpha][h]=b.conformal_offset(d.loc[ix,'y_fp'],mix[ix,lo],mix[ix,hi],alpha)
    bundle=dict(old,mean_model=model,mean_bias=bias,participation_model=pm,participation_calibrators=calibrators,quantile_models=qmodels,conditional_offsets=off,mixture_offsets=moff)
    with (a.output/'research_models.pkl').open('wb') as f:pickle.dump(bundle,f)
    report={'status':'refitted_current_candidate_not_deployed','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'family_source_model_sha256':oldreport['model_sha256'],'model_sha256':hashlib.sha256((a.output/'research_models.pkl').read_bytes()).hexdigest(),'no_2026_27_fit_or_calibration':True,'purged_boundaries':bounds,'training_rows':int(train.sum()),'training_unique_player_games':int(d.loc[train,['pid','game']].drop_duplicates().shape[0]),'protocol_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL_FINAL_REFIT.md').read_bytes()).hexdigest(),'confirmation':{}}
    c=d[confirm].copy();pred=predict_frame(bundle,c)
    for h in LEADS:
        ix=c.horizon_days==h;kn=ix&c.y_play.notna();pl=ix&(c.y_play==1)
        if not kn.any() or not pl.any():
            report['confirmation'][str(h)]={'status':'NO_POSTCALIBRATION_COHORT','known':int(kn.sum()),'played':int(pl.sum())};continue
        report['confirmation'][str(h)]={'fp':b.reg_metrics(c.loc[pl,'y_fp'],pred.loc[pl,'mean_if_play']),'baseline_fp':b.reg_metrics(c.loc[pl,'y_fp'],c.loc[pl,'fp10']),'p_play':b.prob_metrics(c.loc[kn,'y_play'],pred.loc[kn,'p_play']),'unconditional_fp':b.reg_metrics(c.loc[kn,'y_fp'],pred.loc[kn,'expected_fp']),'conditional80':b.interval_metrics(c.loc[pl,'y_fp'],pred.loc[pl,'conditional_lo80'],pred.loc[pl,'conditional_hi80'],.2),'unconditional80':b.interval_metrics(c.loc[kn,'y_fp'],pred.loc[kn,'lo80'],pred.loc[kn,'hi80'],.2)}
    report['runtime_seconds']=time.time()-start;b.write_json(a.output/'MODEL_RESEARCH_REPORT.json',report);print('LATEST COMPLETE',report['model_sha256'],flush=True)
if __name__=='__main__':main()
