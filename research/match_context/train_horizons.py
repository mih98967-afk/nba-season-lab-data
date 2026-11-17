#!/usr/bin/env python3
"""Purged chronological model selection for per-game forecasts at several leads."""
import argparse,gc,hashlib,json,pathlib,pickle,time
import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.linear_model import LogisticRegression
from lightgbm import LGBMRegressor
import run_phase1 as b
import run_phase2 as t
from availability import mixture_quantiles
from horizon_data import build_horizons,horizon_masks,LEADS,META

def sets(d):
    allcols=[c for c in d if c not in META];inj=[c for c in allcols if c.startswith(('inj_','health_'))]
    context=[c for c in allcols if c.startswith(('team_','opp_','target_','h2h_')) or c in ['home','rest_difference','win_probability_elo','calendar_month']]
    form=[c for c in allcols if c not in inj+context]
    return dict(all=allcols,form=form,context=form+context,inj=inj)

def boundary_checks(d,m):
    out={}
    for left,right in [('train','select'),('select','pcal'),('pcal','ical'),('ical','confirm'),('ical','audit')]:
        max_target=d.loc[m[left],'date'].astype(str).max();min_issue=d.loc[m[right],'issue_date'].astype(str).min()
        assert max_target<min_issue,(left,right,max_target,min_issue)
        out[left+'__'+right]=dict(latest_fitted_target=max_target,earliest_next_issue=min_issue,pass_no_overlap=True)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=True);start=time.time()
    code=pathlib.Path(__file__).parent;sources=json.loads((a.source/'upstream_manifest.json').read_text());datahash=hashlib.sha256(''.join(hashlib.sha256((code/n).read_bytes()).hexdigest() for n in ['horizon_data.py','availability.py','run_phase1.py']).encode()+json.dumps([(x.get('file'),x.get('sha256')) for x in sources],sort_keys=True).encode()).hexdigest()
    cache=out/'feature_frame.pkl';manifest=out/'feature_qa.json'
    if cache.exists() and manifest.exists() and json.loads(manifest.read_text()).get('cachekey')==datahash:d=pd.read_pickle(cache);intake=json.loads(manifest.read_text())
    else:
        d,intake=build_horizons(a.source,out/'chunks');intake['cachekey']=datahash;d.to_pickle(cache);b.write_json(manifest,intake)
    fs=sets(d);dm=horizon_masks(d);checks=boundary_checks(d,dm);print('HORIZON FRAME',len(d),checks,flush=True)
    fp=d[d.y_play==1].copy().reset_index(drop=True);m=horizon_masks(fp);y=fp.y_fp.to_numpy();base=fp.fp10.to_numpy();h=fp.horizon_days.to_numpy();pred={'last10':base,'fixed_v2':t.fixed_v2(fp)}
    specs={'ridge_form':('form','ridge'),'ridge_context':('context','ridge'),'lgb_form':('form',15),'lgb_context':('context',15),'lgb_injury_context':('all',15)}
    selection={};fitted={}
    for name,(family,typ) in specs.items():
        model=t.regression(typ);model.fit(fp.loc[m['train'],fs[family]],y[m['train']]-base[m['train']]);pred[name]=base+model.predict(fp[fs[family]]);fitted[name]=model
        print('FP candidate',name,b.reg_metrics(y[m['select']],pred[name][m['select']]),flush=True)
    for name,p in pred.items():
        perlead={str(lead):b.reg_metrics(y[m['select']&(h==lead)],p[m['select']&(h==lead)]) for lead in LEADS};selection[name]=dict(by_lead=perlead,balanced_rmse=float(np.mean([v['rmse'] for v in perlead.values()])))
    winner=min(selection,key=lambda n:selection[n]['balanced_rmse']);print('HORIZON FP WINNER',winner,flush=True);train=m['train']|m['select'];qcols=fs[specs[winner][0]] if winner in specs else fs['context'];model=None
    if winner in specs:
        family,typ=specs[winner];model=t.regression(typ);model.fit(fp.loc[train,fs[family]],y[train]-base[train])
    def mu(frame):
        if winner=='last10':return frame.fp10.to_numpy()
        if winner=='fixed_v2':return t.fixed_v2(frame)
        return frame.fp10.to_numpy()+model.predict(frame[fs[specs[winner][0]]])
    rawmu=mu(fp);bias={lead:float(np.mean(y[m['pcal']&(h==lead)]-rawmu[m['pcal']&(h==lead)])) for lead in LEADS};point=rawmu+np.array([bias[int(v)] for v in h])
    report=dict(status='research_only_not_deployed',adopt_on_site=False,real_KEEP_TRANSFER_gain_proven=False,per_game_not_weekly_interval=True,issue_leads=list(LEADS),purged_boundaries=checks,fp_selection=selection,fp_winner=winner,mean_bias_corrections=bias,features=fs,**intake)
    report['fp_results']={split:{str(lead):{**{n:b.reg_metrics(y[mask&(h==lead)],p[mask&(h==lead)]) for n,p in pred.items()},'selected':b.reg_metrics(y[mask&(h==lead)],point[mask&(h==lead)])} for lead in LEADS if (mask&(h==lead)).sum()>0} for split,mask in m.items() if split in ['confirm','audit']}
    pp=d.copy().reset_index(drop=True);del d;gc.collect();pm=horizon_masks(pp);ph=pp.horizon_days.to_numpy();known=pp.y_play.notna();py=pp.y_play.to_numpy()
    pbase=fs['form']+['home','team_days_rest','team_b2b','team_games_last4','opp_b2b']+[c for c in fs['context'] if c.startswith('target_')]
    pspec={'logistic_history':('logistic',pbase),'lgb_history':('lgb',pbase),'logistic_injury':('logistic',pbase+fs['inj']),'lgb_injury':('lgb',pbase+fs['inj'])}
    pr={'constant_087':np.full(len(pp),.87),'explicit_rate':pp.obs_play_rate25.to_numpy()};psel={}
    for name,(typ,cols) in pspec.items():
        pmode=t.participation_model(typ);mask=pm['train']&known;pmode.fit(pp.loc[mask,cols],py[mask]);pr[name]=pmode.predict_proba(pp[cols])[:,1]
        print('P candidate',name,b.prob_metrics(py[pm['select']&known],pr[name][pm['select']&known])['brier'],flush=True)
    for name,p in pr.items():
        perlead={str(lead):b.prob_metrics(py[pm['select']&known&(ph==lead)],p[pm['select']&known&(ph==lead)]) for lead in LEADS};psel[name]=dict(by_lead=perlead,balanced_brier=float(np.mean([v['brier'] for v in perlead.values()])))
    pwin=min(psel,key=lambda n:psel[n]['balanced_brier']);print('HORIZON P WINNER',pwin,flush=True)
    if pwin in pspec:
        typ,pcols=pspec[pwin];pmodel=t.participation_model(typ);mask=(pm['train']|pm['select'])&known;pmodel.fit(pp.loc[mask,pcols],py[mask]);praw=pmodel.predict_proba(pp[pcols])[:,1]
    else:pmodel=None;pcols=[];praw=pr[pwin]
    p=np.zeros(len(pp));calibrators={}
    for lead in LEADS:
        pc=pm['pcal']&known&(ph==lead);c=LogisticRegression(C=100.,max_iter=500).fit(logit(np.clip(praw[pc],.001,.999)).reshape(-1,1),py[pc]);calibrators[lead]=c;mask=ph==lead;p[mask]=c.predict_proba(logit(np.clip(praw[mask],.001,.999)).reshape(-1,1))[:,1]
    pr['selected']=p;report['participation_selection']=psel;report['participation_winner']=pwin
    report['participation_results']={split:{str(lead):{n:b.prob_metrics(py[mask&known&(ph==lead)],v[mask&known&(ph==lead)]) for n,v in pr.items()} for lead in LEADS if (mask&known&(ph==lead)).sum()>0} for split,mask in pm.items() if split in ['confirm','audit']}
    report['coverage_by_lead']={str(lead):dict(opportunities=int((pm['audit']&(ph==lead)).sum()),known=int((pm['audit']&(ph==lead)&known).sum()),unknown=int((pm['audit']&(ph==lead)&~known).sum()),played=int((pm['audit']&(ph==lead)&(pp.y_play==1)).sum())) for lead in LEADS}
    report['missing_label_bounds']={}
    for lead in LEADS:
        mask=pm['audit']&(ph==lead);kn=mask&known;u=mask&~known;bp=pr['explicit_rate'];gain=((py[kn]-bp[kn])**2-(py[kn]-p[kn])**2).sum();g0=bp[u]**2-p[u]**2;g1=(1-bp[u])**2-(1-p[u])**2
        report['missing_label_bounds'][str(lead)]=dict(gain_lower=(gain+np.minimum(g0,g1).sum())/mask.sum(),gain_upper=(gain+np.maximum(g0,g1).sum())/mask.sum())
    ppmu=mu(pp)+np.array([bias[int(v)] for v in ph]);efp=p*ppmu;availabilitybaseline=pp.fp10.to_numpy()*pr['explicit_rate']
    report['unconditional_fp']={split:{str(lead):dict(selected=b.reg_metrics(pp.loc[mask&known&(ph==lead),'y_fp'],efp[mask&known&(ph==lead)]),history_baseline=b.reg_metrics(pp.loc[mask&known&(ph==lead),'y_fp'],availabilitybaseline[mask&known&(ph==lead)])) for lead in LEADS if (mask&known&(ph==lead)).sum()>0} for split,mask in pm.items() if split in ['confirm','audit']}
    levels=[.025,.1,.25,.5,.75,.9,.975];qmodels={};qfp=[];qpp=[]
    for q in levels:
        qm=LGBMRegressor(**dict(b.BASE_PARAMS,objective='quantile',alpha=q));qm.fit(fp.loc[train,qcols],y[train]-base[train]);qmodels[q]=qm;qfp.append(base+qm.predict(fp[qcols]));qpp.append(pp.fp10.to_numpy()+qm.predict(pp[qcols]));print('Quantile',q,flush=True)
    qfp=np.sort(np.array(qfp).T,axis=1);qpp=np.sort(np.array(qpp).T,axis=1);mix=mixture_quantiles(qpp,levels,p,levels);del qpp;gc.collect()
    report['conditional_intervals']={};report['unconditional_intervals']={};offsets={};mixoffsets={}
    for alpha in (.5,.2,.05):
        li=int(np.argmin(np.abs(np.array(levels)-alpha/2)));hi=int(np.argmin(np.abs(np.array(levels)-(1-alpha/2))));key=str(1-alpha)
        lo=np.zeros(len(fp));up=np.zeros(len(fp));ml=np.zeros(len(pp));muq=np.zeros(len(pp));offsets[alpha]={};mixoffsets[alpha]={}
        for lead in LEADS:
            mask=h==lead;cal=m['ical']&mask;o=b.conformal_offset(y[cal],qfp[cal,li],qfp[cal,hi],alpha);offsets[alpha][lead]=o;lo[mask]=qfp[mask,li]-o;up[mask]=qfp[mask,hi]+o
            pmask=ph==lead;ci=pm['ical']&known&pmask;mo=b.conformal_offset(pp.loc[ci,'y_fp'],mix[ci,li],mix[ci,hi],alpha);mixoffsets[alpha][lead]=mo;ml[pmask]=mix[pmask,li]-mo;muq[pmask]=mix[pmask,hi]+mo
        report['conditional_intervals'][key]={str(lead):{split:b.interval_metrics(y[mask&(h==lead)],lo[mask&(h==lead)],up[mask&(h==lead)],alpha) for split,mask in m.items() if split in ['confirm','audit'] and (mask&(h==lead)).sum()>0} for lead in LEADS}
        report['unconditional_intervals'][key]={str(lead):{split:b.interval_metrics(pp.loc[mask&known&(ph==lead),'y_fp'],ml[mask&known&(ph==lead)],muq[mask&known&(ph==lead)],alpha) for split,mask in pm.items() if split in ['confirm','audit'] and (mask&known&(ph==lead)).sum()>0} for lead in LEADS}
        pp[f'lo{int((1-alpha)*100)}']=ml;pp[f'hi{int((1-alpha)*100)}']=muq
    pp['p_play']=p;pp['mean_if_play']=ppmu;pp['expected_fp']=efp
    columns=['pid','game','date','issue_date','season','team','opp','name','horizon_days','y_play','y_fp','min10','p_play','mean_if_play','expected_fp','lo50','hi50','lo80','hi80','lo95','hi95']
    pp[columns].to_csv(out/'predictions.csv.gz',index=False)
    model_bundle=dict(winner=winner,mean_model=model,specs=specs,feature_sets=fs,mean_bias=bias,participation_winner=pwin,participation_model=pmodel,participation_features=pcols,participation_calibrators=calibrators,quantile_models=qmodels,quantile_features=qcols,quantile_levels=levels,conditional_offsets=offsets,mixture_offsets=mixoffsets,leads=LEADS)
    with (out/'research_models.pkl').open('wb') as f:pickle.dump(model_bundle,f)
    report['limitations']=['Retrospective source vintages and final schedules, not exact historical publication proof','Reused historical audit, not untouched holdout','Morning day-level replay; previous NBA-date boxscores assumed available','Per-game lead-time intervals, not aggregate-week intervals','Prior observed membership only; trades and unobserved players can leave UNKNOWN','No official Sports.ru credit reconciliation or economic optimizer proof','No automatic adoption']
    report['protocol_sha256']=hashlib.sha256((code/'PROTOCOL_HORIZONS.md').read_bytes()).hexdigest();report['code_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code.glob('*.py')};report['source_hashes']=sources;report['runtime_seconds']=time.time()-start;report['model_sha256']=hashlib.sha256((out/'research_models.pkl').read_bytes()).hexdigest();b.write_json(out/'MODEL_RESEARCH_REPORT.json',report)
    print('COMPLETE',winner,pwin,report['runtime_seconds'],flush=True)
if __name__=='__main__':main()
