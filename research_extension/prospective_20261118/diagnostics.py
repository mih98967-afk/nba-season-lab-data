"""Exploratory subgroup/coverage diagnostics; immutable pregame feature provenance only."""
from pathlib import Path
import collections,datetime as dt,json
import numpy as np
import pandas as pd
from score_completed import BASE,KNOWN,SEED,DRAWS,prob_metrics,sha
from score_evidence_union import union_metric_rows
HERE=Path(__file__).resolve().parent

def coverage(rows,conditional,n):
 rs=[r for r in rows if r['outcome_archive']=='PLAYED']if conditional else[r for r in rows if r['outcome_archive']in KNOWN]
 if not rs:return {'n':0}
 prefix='conditional_'if conditional else'';groups=sorted({r['nba_game_id']for r in rs});ix={g:i for i,g in enumerate(groups)};total=np.zeros(len(groups));hit=np.zeros(len(groups))
 for r in rs:
  i=ix[r['nba_game_id']];total[i]+=1;hit[i]+=r[prefix+'lo'+str(n)]<=r['y_fp']<=r[prefix+'hi'+str(n)]
 rng=np.random.default_rng(SEED);picks=rng.integers(len(groups),size=(DRAWS,len(groups)));boot=hit[picks].sum(axis=1)/total[picks].sum(axis=1)
 return {'n':len(rs),'games':len(groups),'nominal':n/100,'coverage':float(hit.sum()/total.sum()),'game_cluster_95CI':np.quantile(boot,[.025,.975]).tolist(),'date_cluster_CI':None,'small_cluster_inference_caveat':True}

def main():
 result={'schema':'nba-prospective-subgroup-diagnostics-v1','created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'exploratory_subgroups_no_selection_or_tuning':True,'current_statuses_not_backfilled':True,'cohorts':{}}
 for cohort,path in [('original_20261116',BASE/'results_current/feature_frame.pkl'),('paired_20261117',HERE.parent/'fresh_20261117/feature_frame.pkl')]:
  frame=pd.read_pickle(path);frame=frame[frame.y_play.isna()&frame.y_fp.isna()];ix={(str(r.pid),str(r.game),int(r.horizon_days),str(r.issue_date)):r for r in frame.itertuples()}
  rows=union_metric_rows(json.loads((HERE/'results_verified_union'/(cohort+'_scored_records.json')).read_text()));allrows=[]
  for r in rows:
   if r['outcome_archive']=='FUTURE':continue
   f=ix[(r['nba_player_id'],r['nba_game_id'],r['lead_days'],r['feature_date_ET'])];states=[s for s in ['out','doubtful','questionable','probable','available','not_listed','unknown_identity']if getattr(f,'inj_'+s)==1]
   status=states[0]if len(states)==1 else('REPORT_UNAVAILABLE'if not f.inj_present else'UNKNOWN')
   hist=float(f.history_n);allrows.append({**r,'frozen_injury_status':status,'frozen_history_n':hist,'history_bucket':'5_to24'if hist<25 else'25_to99'if hist<100 else'100_plus'})
  out={'frozen_feature_frame_sha256':sha(path),'by_role_lead':{}}
  for role,lead in sorted({(r['model_role'],r['lead_days'])for r in allrows}):
   rs=[r for r in allrows if(r['model_role'],r['lead_days'])==(role,lead)];entry={'by_frozen_status':{},'by_history_n':{},'interval_coverage':{}}
   for field,key in [('frozen_injury_status','by_frozen_status'),('history_bucket','by_history_n')]:
    for bucket in sorted({r[field]for r in rs}):
     group=[r for r in rs if r[field]==bucket];known=[r for r in group if r['participation_verified']is not None]
     entry[key][bucket]={'total':len(group),'known':len(known),'UNKNOWN':len(group)-len(known),'candidate':prob_metrics([r['participation_verified']for r in known],[r['p_play']for r in known]),'historical_baseline':prob_metrics([r['participation_verified']for r in known],[r['baseline_p_play']for r in known])}
   for n in [50,80,95]:entry['interval_coverage'][str(n)]={str(conditional):coverage(rs,conditional,n)for conditional in [True,False]}
   out['by_role_lead'][role+':lead'+str(lead)]=entry
  result['cohorts'][cohort]=out
 (HERE/'results_verified_union/DIAGNOSTICS.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
