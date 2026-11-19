#!/usr/bin/env python3
"""Reproducible expanded-evidence model tournament; never writes production data."""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, pickle, platform, time
import numpy as np
import pandas as pd
import sklearn, lightgbm
from scipy.special import logit
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import mean_squared_error, brier_score_loss
from lightgbm import LGBMRegressor, LGBMClassifier
import run_phase1 as b
from availability import load_sources, injury_index, injury_features, mixture_quantiles

META={'pid','game','date','season','team','opp','name','exante_member','y_play','y_fp','y_minutes'}

def feature_sets(d):
    allcols=[c for c in d if c not in META]
    inj=[c for c in allcols if c.startswith('inj_')]
    context=[c for c in allcols if c.startswith(('team_','opp_','h2h_')) or c in ['home','rest_difference','win_probability_elo','calendar_month']]
    form=[c for c in allcols if c not in context+inj]
    rest=form+['home','team_days_rest','team_b2b','team_games_last4','opp_days_rest','opp_b2b','rest_difference']
    return dict(all=allcols,form=form,rest=rest,context=form+context,inj=inj)

def regression(typ):
    return make_pipeline(SimpleImputer(),StandardScaler(),Ridge(alpha=500.)) if typ=='ridge' else LGBMRegressor(**dict(b.BASE_PARAMS,num_leaves=int(typ)))

def participation_model(typ):
    if typ=='logistic':return make_pipeline(SimpleImputer(),StandardScaler(),LogisticRegression(C=.05,max_iter=1000))
    return LGBMClassifier(**b.BASE_PARAMS)

def fixed_v2(d):return (.6*d.fp10+.4*d.fp25+np.clip(.25*(d.min5-d.min10)*d.fp_per_min10.clip(0,1.5),-8,8)).clip(-5,80).to_numpy()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=True);start=time.time()
    code_dir=pathlib.Path(__file__).parent
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in code_dir.glob('*.py')}
    sources=json.loads((a.source/'upstream_manifest.json').read_text())
    cachekey=hashlib.sha256(json.dumps(dict(code=hashes,sources=[(v.get('file'),v.get('sha256')) for v in sources]),sort_keys=True).encode()).hexdigest()
    cache=out/'feature_frame.pkl';qa_path=out/'feature_qa.json'
    if cache.exists() and qa_path.exists() and json.loads(qa_path.read_text()).get('cachekey')==cachekey:
        d=pd.read_pickle(cache);intake=json.loads(qa_path.read_text())
    else:
        games,raw,sourceqa=load_sources(a.source);print('Source expanded',len(games),len(raw),flush=True)
        frame,featureqa=b.build_frame(games,raw);idx,injqa=injury_index(a.source,games);d=injury_features(frame,idx)
        intake=dict(source_qa=sourceqa,feature_qa=featureqa,injury_qa=injqa,cachekey=cachekey)
        d.to_pickle(cache);b.write_json(qa_path,intake)
    fs=feature_sets(d);fp=d[(d.exante_member==1)&(d.y_play==1)&(d.history_n>=5)].reset_index(drop=True);m=b.masks(fp);y=fp.y_fp.to_numpy();base=fp.fp10.to_numpy()
    specs={
      'ridge_form':('form','ridge'),'ridge_rest':('rest','ridge'),'ridge_context':('context','ridge'),'ridge_injury_context':('all','ridge'),
      'lgb_form':('form',15),'lgb_rest':('rest',15),'lgb_context':('context',15),'lgb_context31':('context',31),'lgb_injury_context':('all',15)}
    predictions={'last10':base,'fixed_v2':fixed_v2(fp)};fitted={}
    print('FP cohort',len(fp),'features',len(fs['all']),flush=True)
    for name,(family,typ) in specs.items():
        cols=fs[family];model=regression(typ);model.fit(fp.loc[m['train'],cols],y[m['train']]-base[m['train']]);fitted[name]=model
        predictions[name]=base+model.predict(fp[cols]);print(name,b.reg_metrics(y[m['select']],predictions[name][m['select']]),flush=True)
    predictions['blend_form_context']=(predictions['lgb_form']+predictions['lgb_context'])/2
    selection={n:b.reg_metrics(y[m['select']],p[m['select']]) for n,p in predictions.items()}
    winner=min(selection,key=lambda n:selection[n]['rmse']);print('FP FAMILY LOCKED',winner,flush=True)
    train=m['train']|m['select'];mean_models={}
    if winner in ('last10','fixed_v2'):qcols=fs['context']
    elif winner=='blend_form_context':qcols=fs['context']
    else:qcols=fs[specs[winner][0]]
    selected_components=['lgb_form','lgb_context'] if winner=='blend_form_context' else [winner] if winner in specs else []
    for name in selected_components:
        family,typ=specs[name];cols=fs[family];model=regression(typ);model.fit(fp.loc[train,cols],y[train]-base[train]);mean_models[name]=model
    def predict_mean(frame):
        if winner=='last10':return frame.fp10.to_numpy()
        if winner=='fixed_v2':return fixed_v2(frame)
        return frame.fp10.to_numpy()+np.mean([model.predict(frame[fs[specs[n][0]]]) for n,model in mean_models.items()],axis=0)
    refit=predict_mean(fp);bias_correction=float(np.mean(y[m['pcal']]-refit[m['pcal']]));point=refit+bias_correction
    report=dict(status='research_only_not_deployed',adopt_on_site=False,real_KEEP_TRANSFER_gain_proven=False,protocol='PROTOCOL_PHASE2.md',asof_semantics='Start of target NBA game date in US/Eastern',**intake,selection=selection,winner=winner,mean_bias_correction_fitted_pcal=bias_correction,features=fs,source_hashes=sources,code_hashes=hashes,protocol_sha256=hashlib.sha256((code_dir/'PROTOCOL_PHASE2.md').read_bytes()).hexdigest(),environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,sklearn=sklearn.__version__,lightgbm=lightgbm.__version__))
    report['fp_results']={split:{**{n:b.reg_metrics(y[mask],p[mask]) for n,p in predictions.items()},'selected_refit':b.reg_metrics(y[mask],refit[mask]),'selected_calibrated':b.reg_metrics(y[mask],point[mask])} for split,mask in m.items() if split in ['confirm','audit']}
    report['paired_fp_gain']={split:{baseline:{g:b.cluster_gain(y[mask],predictions[baseline][mask],point[mask],fp.loc[mask,g]) for g in ['date','pid']} for baseline in ['last10','fixed_v2']} for split,mask in m.items() if split in ['confirm','audit']}
    report['matched_context_ablations']={}
    for before,after in [('ridge_form','ridge_rest'),('ridge_rest','ridge_context'),('ridge_context','ridge_injury_context'),('lgb_form','lgb_context'),('lgb_context','lgb_injury_context')]:
        report['matched_context_ablations'][before+'__'+after]={split:b.cluster_gain(y[mask],predictions[before][mask],predictions[after][mask],fp.loc[mask,'date']) for split,mask in m.items() if split in ['confirm','audit']}
    subgroups={'under15':fp.min10<15,'15to28':(fp.min10>=15)&(fp.min10<28),'28plus':fp.min10>=28,'b2b':fp.team_b2b==1,'return7days':fp.days_since_play>=7,'questionable':fp.inj_questionable==1,'no_submitted_report':fp.inj_team_submitted==0,'large_role_change':abs(fp.minutes_trend)>=5}
    report['fp_subgroups']={n:dict(baseline=b.reg_metrics(y[m['audit']&s],base[m['audit']&s]),selected=b.reg_metrics(y[m['audit']&s],point[m['audit']&s])) for n,s in subgroups.items() if (m['audit']&s).sum()>=30}
    pp=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True);pm=b.masks(pp);known=pp.y_play.notna();py=pp.y_play.to_numpy()
    pbase=fs['form']+['home','team_days_rest','team_b2b','team_games_last4','opp_b2b'];pall=pbase+fs['inj']
    pspec={'logistic_history':('logistic',pbase),'lgb_history':('lgb',pbase),'logistic_injury':('logistic',pall),'lgb_injury':('lgb',pall)}
    pr={'constant_087':np.repeat(.87,len(pp)),'explicit_rate':pp.obs_play_rate25.to_numpy()};pmodels={}
    for name,(typ,cols) in pspec.items():
        model=participation_model(typ);ix=pm['train']&known;model.fit(pp.loc[ix,cols],py[ix]);pr[name]=model.predict_proba(pp[cols])[:,1];pmodels[name]=model
    pselect={n:b.prob_metrics(py[pm['select']&known],p[pm['select']&known]) for n,p in pr.items()};pwin=min(pselect,key=lambda n:pselect[n]['brier']);print('PPLAY FAMILY LOCKED',pwin,flush=True)
    if pwin in pspec:
        typ,pcols=pspec[pwin];pmodel=participation_model(typ);ix=(pm['train']|pm['select'])&known;pmodel.fit(pp.loc[ix,pcols],py[ix]);praw=pmodel.predict_proba(pp[pcols])[:,1]
    else:pmodel=None;pcols=[];praw=pr[pwin]
    pc=pm['pcal']&known;cal=LogisticRegression(C=100.,max_iter=500).fit(logit(np.clip(praw[pc],.001,.999)).reshape(-1,1),py[pc]);p=cal.predict_proba(logit(np.clip(praw,.001,.999)).reshape(-1,1))[:,1]
    pr['selected_refit']=praw;pr['selected_calibrated']=p
    report['participation_selection']=pselect;report['participation_winner']=pwin
    report['participation_metrics']={split:{n:b.prob_metrics(py[mask&known],v[mask&known]) for n,v in pr.items()} for split,mask in pm.items() if split in ['confirm','audit']}
    report['participation_coverage']={split:dict(opportunities=int(mask.sum()),known=int((mask&known).sum()),unknown=int((mask&~known).sum()),played=int((mask&(pp.y_play==1)).sum()),explicit_no_play=int((mask&(pp.y_play==0)).sum())) for split,mask in pm.items()}
    report['participation_missing_label_sensitivity']={}
    for baseline in ['constant_087','explicit_rate']:
        mask=pm['audit'];kn=mask&known;u=mask&~known;bp=pr[baseline];gain=((py[kn]-bp[kn])**2-(py[kn]-p[kn])**2).sum();g0=bp[u]**2-p[u]**2;g1=(1-bp[u])**2-(1-p[u])**2
        report['participation_missing_label_sensitivity'][baseline]=dict(brier_gain_lower=(gain+np.minimum(g0,g1).sum())/mask.sum(),brier_gain_upper=(gain+np.maximum(g0,g1).sum())/mask.sum())
    psub={'out':pp.inj_out==1,'questionable':pp.inj_questionable==1,'doubtful':pp.inj_doubtful==1,'probable':pp.inj_probable==1,'available':pp.inj_available==1,'not_listed':pp.inj_not_listed==1,'no_submitted_report':pp.inj_team_submitted==0,'28plus':pp.min10>=28,'return7days':pp.days_since_play>=7}
    report['participation_subgroups']={n:b.prob_metrics(py[pm['audit']&known&s],p[pm['audit']&known&s]) for n,s in psub.items() if (pm['audit']&known&s).sum()>=30}
    ppmean=predict_mean(pp)+bias_correction;ep=p*ppmean;report['unconditional_fp']={split:dict(selected=b.reg_metrics(pp.loc[mask&known,'y_fp'],ep[mask&known]),all_play=b.reg_metrics(pp.loc[mask&known,'y_fp'],pp.loc[mask&known,'fp10']),history_participation=b.reg_metrics(pp.loc[mask&known,'y_fp'],pp.loc[mask&known,'fp10']*pr['explicit_rate'][mask&known])) for split,mask in pm.items() if split in ['confirm','audit']}
    levels=[.025,.1,.25,.5,.75,.9,.975];qmods={};qfp=[];qpp=[]
    for q in levels:
        model=LGBMRegressor(**dict(b.BASE_PARAMS,objective='quantile',alpha=q));model.fit(fp.loc[train,qcols],y[train]-base[train]);qmods[q]=model
        qfp.append(base+model.predict(fp[qcols]));qpp.append(pp.fp10.to_numpy()+model.predict(pp[qcols]))
    qfp=np.sort(np.array(qfp).T,axis=1);qpp=np.sort(np.array(qpp).T,axis=1);mix=mixture_quantiles(qpp,levels,p,levels)
    report['conditional_intervals']={};report['unconditional_intervals']={};report['interval_subgroups']={};offsets={};mixoffsets={}
    for alpha in (.5,.2,.05):
        nominal=str(1-alpha);li=int(np.argmin(np.abs(np.array(levels)-alpha/2)));hi=int(np.argmin(np.abs(np.array(levels)-(1-alpha/2))));ix=m['ical']
        offset=b.conformal_offset(y[ix],qfp[ix,li],qfp[ix,hi],alpha);offsets[alpha]=offset;lo=qfp[:,li]-offset;up=qfp[:,hi]+offset
        report['conditional_intervals'][nominal]=dict(calibration_n=int(ix.sum()),offset=offset,evaluations={split:b.interval_metrics(y[mask],lo[mask],up[mask],alpha) for split,mask in m.items() if split in ['confirm','audit']})
        for name,s in subgroups.items():
            mask=m['audit']&s
            if mask.sum()>=30:report['interval_subgroups'].setdefault(name,{})[nominal]=b.interval_metrics(y[mask],lo[mask],up[mask],alpha)
        fp[f'lo{int((1-alpha)*100)}']=lo;fp[f'hi{int((1-alpha)*100)}']=up
        ci=pm['ical']&known;mo=b.conformal_offset(pp.loc[ci,'y_fp'],mix[ci,li],mix[ci,hi],alpha);mixoffsets[alpha]=mo;ml=mix[:,li]-mo;mu=mix[:,hi]+mo
        bc=pp.fp10.to_numpy()*pr['explicit_rate'];bw=float(np.quantile(np.abs(pp.loc[ci,'y_fp']-bc[ci]),1-alpha,method='higher'))
        report['unconditional_intervals'][nominal]=dict(calibration_n=int(ci.sum()),offset=mo,evaluations={split:dict(selected=b.interval_metrics(pp.loc[mask&known,'y_fp'],ml[mask&known],mu[mask&known],alpha),baseline=b.interval_metrics(pp.loc[mask&known,'y_fp'],bc[mask&known]-bw,bc[mask&known]+bw,alpha)) for split,mask in pm.items() if split in ['confirm','audit']})
        pp[f'lo{int((1-alpha)*100)}']=ml;pp[f'hi{int((1-alpha)*100)}']=mu
    for n,v in predictions.items():fp[n]=v
    fp['selected_refit']=refit;fp['selected_mean']=point
    pp['p_play']=p;pp['mean_if_play']=ppmean;pp['expected_fp']=ep;pp['median_unconditional']=mix[:,levels.index(.5)]
    fcols=['pid','game','date','season','team','opp','home','name','y_fp','min10','team_b2b']+list(predictions)+['selected_refit','selected_mean','lo50','hi50','lo80','hi80','lo95','hi95']
    pcols_out=['pid','game','date','season','team','opp','name','y_play','y_fp','min10','p_play','mean_if_play','expected_fp','median_unconditional','lo50','hi50','lo80','hi80','lo95','hi95']+fs['inj']
    fp[fcols].to_csv(out/'fp_predictions.csv.gz',index=False);pp[pcols_out].to_csv(out/'participation_predictions.csv.gz',index=False)
    model_bundle=dict(mean_winner=winner,mean_models=mean_models,specs=specs,feature_sets=fs,mean_bias_correction=bias_correction,participation_winner=pwin,participation_model=pmodel,participation_features=pcols,participation_calibrator=cal,quantile_models=qmods,quantile_features=qcols,quantile_levels=levels,conditional_offsets=offsets,mixture_offsets=mixoffsets,source_hashes=sources)
    with (out/'research_models.pkl').open('wb') as f:pickle.dump(model_bundle,f)
    report['limitations']=['Reused historical audit is not untouched or prospective','Date-as-of reconstructed final archives, not original data-vintage or schedule proof','Observed prior-club membership cohort, not full registered fantasy population','At least five previous played games required for this validation','Published injury archive identities are source-derived, not individually rechecked PDFs','Single-game intervals are not calibrated multi-game intervals','NBA FP are not official Sports.ru credited player-game FP','No independent economic transfer-utility proof; no production adoption']
    report['runtime_seconds']=time.time()-start;report['model_sha256']=hashlib.sha256((out/'research_models.pkl').read_bytes()).hexdigest();report['feature_frame_sha256']=hashlib.sha256(cache.read_bytes()).hexdigest();b.write_json(out/'MODEL_RESEARCH_REPORT.json',report)
    print('DONE',json.dumps(b.clean(dict(fp_winner=winner,pplay_winner=pwin,fp_audit=report['fp_results']['audit']['selected_calibrated'],pplay_audit=report['participation_metrics']['audit']['selected_calibrated'],runtime=report['runtime_seconds']))),flush=True)
if __name__=='__main__':main()
