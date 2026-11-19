"""Fixed follow-on candidate challenge, no promotion and no current-season tuning."""
import argparse,gc,hashlib,pathlib,pickle,time
import numpy as np,pandas as pd
from catboost import CatBoostRegressor,CatBoostClassifier
from xgboost import XGBRegressor,XGBClassifier
from lightgbm import LGBMRegressor
import run_phase1 as b
import run_phase2 as t

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase2',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);start=time.time()
    d=pd.read_pickle(a.phase2/'feature_frame.pkl');fs=t.feature_sets(d);cols=fs['context'];fp=d[(d.exante_member==1)&(d.history_n>=5)&(d.y_play==1)].reset_index(drop=True);m=b.masks(fp);y=fp.y_fp.to_numpy();base=fp.fp10.to_numpy();models={};pred={};fail={}
    models['ridge_context']=t.regression('ridge')
    for depth in [4,6]:models[f'catboost_{depth}']=CatBoostRegressor(iterations=600,depth=depth,learning_rate=.035,l2_leaf_reg=10,loss_function='RMSE',random_seed=b.SEED,thread_count=1,verbose=False,allow_writing_files=False)
    for depth in [3,5]:models[f'xgboost_{depth}']=XGBRegressor(n_estimators=400,max_depth=depth,learning_rate=.035,min_child_weight=30,reg_lambda=20,n_jobs=1,random_state=b.SEED,objective='reg:squarederror',tree_method='hist')
    for leaves in [7,31]:models[f'lightgbm_{leaves}']=LGBMRegressor(**dict(b.BASE_PARAMS,n_estimators=600,learning_rate=.025,num_leaves=leaves,reg_lambda=20,n_jobs=1))
    for name,model in models.items():
        try:model.fit(fp.loc[m['train'],cols],y[m['train']]-base[m['train']]);pred[name]=base+model.predict(fp[cols]);print(name,b.reg_metrics(y[m['select']],pred[name][m['select']]),flush=True)
        except Exception as exc:fail[name]=str(exc)
    pred['blend_ridge_cat4']=(pred['ridge_context']+pred['catboost_4'])/2
    mm=LGBMRegressor(**dict(b.BASE_PARAMS,n_jobs=1));mm.fit(fp.loc[m['train'],cols],fp.loc[m['train'],'y_minutes']-fp.loc[m['train'],'min10']);minhat=np.clip(fp.min10.to_numpy()+mm.predict(fp[cols]),.5,48.)
    rm=LGBMRegressor(**dict(b.BASE_PARAMS,n_jobs=1));rt=m['train']&(fp.y_minutes>=5);rate=fp.y_fp/fp.y_minutes;rm.fit(fp.loc[rt,cols],rate[rt]-fp.loc[rt,'fp_per_min10']);pred['minutes_times_rate']=minhat*(fp.fp_per_min10.to_numpy()+rm.predict(fp[cols]))
    selection={n:b.reg_metrics(y[m['select']],p[m['select']]) for n,p in pred.items()};winner=min(selection,key=lambda n:selection[n]['rmse']);report={'status':'exploratory_family_challenge_not_adopted','fp_selection':selection,'fp_winner':winner,'failures':fail,'fp_audit':{n:b.reg_metrics(y[m['audit']],p[m['audit']]) for n,p in pred.items()}}
    report['fp_gain_vs_ridge']={n:b.cluster_gain(y[m['audit']],pred['ridge_context'][m['audit']],p[m['audit']],fp.loc[m['audit'],'date']) for n,p in pred.items() if n!='ridge_context'}
    pp=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True);pm=b.masks(pp);known=pp.y_play.notna();py=pp.y_play.to_numpy();pc=fs['form']+['home','team_days_rest','team_b2b','team_games_last4','opp_b2b']+fs['inj'];pr={};pmodels={'lgb_injury':t.participation_model('lgb')}
    for depth in [4,6]:pmodels[f'catboost_{depth}']=CatBoostClassifier(iterations=600,depth=depth,learning_rate=.035,l2_leaf_reg=10,loss_function='Logloss',random_seed=b.SEED,thread_count=1,verbose=False,allow_writing_files=False)
    for depth in [3,5]:pmodels[f'xgboost_{depth}']=XGBClassifier(n_estimators=400,max_depth=depth,learning_rate=.035,min_child_weight=30,reg_lambda=20,n_jobs=1,random_state=b.SEED,objective='binary:logistic',tree_method='hist')
    for name,model in pmodels.items():
        try:model.fit(pp.loc[pm['train']&known,pc],py[pm['train']&known]);pr[name]=model.predict_proba(pp[pc])[:,1];print('P',name,b.prob_metrics(py[pm['select']&known],pr[name][pm['select']&known])['brier'],flush=True)
        except Exception as exc:fail['p_'+name]=str(exc)
    report['p_selection']={n:b.prob_metrics(py[pm['select']&known],p[pm['select']&known]) for n,p in pr.items()};report['p_winner']=min(report['p_selection'],key=lambda n:report['p_selection'][n]['brier']);report['p_uncalibrated_audit']={n:b.prob_metrics(py[pm['audit']&known],p[pm['audit']&known]) for n,p in pr.items()}
    report['protocol_sha256']=hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL_EXTENDED.md').read_bytes()).hexdigest();report['runtime_seconds']=time.time()-start;b.write_json(a.output/'CHALLENGE_REPORT.json',report)
    with (a.output/'development_models.pkl').open('wb') as f:pickle.dump({'fp_models':models,'p_models':pmodels,'fp_features':cols,'p_features':pc,'fp_winner':winner,'p_winner':report['p_winner']},f)
    print('COMPLETE',winner,report['p_winner'],flush=True)
if __name__=='__main__':main()
