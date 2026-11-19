"""Paired comparison of locked candidate predictions with exact pregame app replay."""
import argparse, collections, datetime as dt, json
from pathlib import Path
from score_completed import clustered_difference, metrics, prob_metrics, sha, KNOWN, unique_index
HERE=Path(__file__).resolve().parent

def compare(rows):
 completed=[r for r in rows if r['outcome_archive']!='FUTURE']
 common=[r for r in completed if r['runtime']['baseline_status']=='AVAILABLE']
 played=[r for r in common if r['outcome_archive']=='PLAYED'];fp=[r for r in common if r['outcome_archive']in KNOWN];part=[r for r in common if r['participation_verified']is not None]
 out={'completed_candidate_rows':len(completed),'runtime_common_rows':len(common),'runtime_unavailable_reasons':dict(collections.Counter(r['runtime'].get('reason')for r in completed if r['runtime']['baseline_status']!='AVAILABLE')),'FP_counts':dict(collections.Counter(r['outcome_archive']for r in common)),'participation_counts':{'known':len(part),'played':sum(r['participation_verified']for r in part),'explicit_nonplay':sum(1-r['participation_verified']for r in part),'UNKNOWN':len(common)-len(part)},'conditional':{'runtime':metrics([r['y_fp']for r in played],[r['runtime']['mean_if_play']for r in played]),'frozen_candidate':metrics([r['y_fp']for r in played],[r['mean_if_play']for r in played])},'unconditional':{'runtime':metrics([r['y_fp']for r in fp],[r['runtime']['expected_fp']for r in fp]),'frozen_candidate':metrics([r['y_fp']for r in fp],[r['expected_fp']for r in fp])},'participation':{'runtime':prob_metrics([r['participation_verified']for r in part],[r['runtime']['p_play']for r in part]),'frozen_candidate':prob_metrics([r['participation_verified']for r in part],[r['p_play']for r in part])},'paired_uncertainty':{}}
 for name,group,field,label,metric in [('conditional_mae',played,'mean_if_play','y_fp','mae'),('conditional_rmse',played,'mean_if_play','y_fp','rmse'),('unconditional_mae',fp,'expected_fp','y_fp','mae'),('unconditional_rmse',fp,'expected_fp','y_fp','rmse'),('participation_brier',part,'p_play','participation_verified','brier')]:
  out['paired_uncertainty'][name]=clustered_difference(group,lambda r:r['runtime'][field],lambda r:r[field],lambda r:r[label],metric)
 known_gain=sum((r['runtime']['p_play']-r['participation_verified'])**2-(r['p_play']-r['participation_verified'])**2 for r in part)
 tails=[[(r['runtime']['p_play']-y)**2-(r['p_play']-y)**2 for y in [0,1]]for r in common if r['participation_verified']is None]
 out['UNKNOWN_label_paired_Brier_gain_bounds']=[(known_gain+sum(min(v)for v in tails))/len(common),(known_gain+sum(max(v)for v in tails))/len(common)]if common else None
 out['UNKNOWN_bounds_not_confidence_intervals']=True
 return out

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--verified-union',action='store_true');ap.add_argument('--runtime-dir',type=Path,default=HERE/'baseline_results');a=ap.parse_args();resultdir='results_verified_union'if a.verified_union else'results_official_supplement';reportname='PROSPECTIVE_UNION_REPORT.json'if a.verified_union else'PROSPECTIVE_REPORT.json'
 allrows={};report={'schema':'nba-exact-deployed-public-runtime-comparison-v1','evaluated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'comparison_predefined_without_current_outcome_tuning':True,'new_models_prospectively_frozen':True,'runtime_baseline_reconstructed_after_outcomes_from_preserved_pregame_inputs':True,'runtime_baseline_originally_frozen':False,'user_private_manual_settings_replayed':False,'Sports_ru_credited_FP_verified':False,'real_KEEP_TRANSFER_gain_proven':False,'source_metadata_sha256':sha(a.runtime_dir/'REPLAY_METADATA.json'),'outcome_report_sha256':sha(HERE/resultdir/reportname),'cohorts':{},'limitations':['Only two NBA dates; game-level bootstrap is descriptive and date uncertainty remains unmeasured','Canonical public/default modelMode=current/riskMode=baseline/medical={} may differ from actual owner settings','Runtime is reconstructed after outcomes from unchanged pregame inputs; it was not separately frozen prospectively','No model or gate threshold was tuned to outcomes','Exact two-source FP conflicts excluded; participation retained when agreed','Only common high-confidence IDs and same seed-team are compared; missing baseline is not zero','No financial or fantasy-transfer utility proven']}
 for cohort in ['original_20261116','paired_20261117']:
  scored=json.loads((HERE/resultdir/(cohort+'_scored_records.json')).read_text());runtime=json.loads((a.runtime_dir/(cohort+'_runtime_predictions.json')).read_text());ix=unique_index(runtime,['model_role','nba_player_id','nba_game_id','lead_days']);rows=[]
  if a.verified_union:
   from score_evidence_union import union_metric_rows
   scored=union_metric_rows(scored)
  for r in scored:
   key=tuple(str(r[k])for k in ['model_role','nba_player_id','nba_game_id','lead_days']);rows.append({**r,'runtime':ix[key]})
  allrows[cohort]=rows
  report['cohorts'][cohort]={}
  for role,lead in sorted({(r['model_role'],r['lead_days'])for r in rows}):
   rs=[r for r in rows if (r['model_role'],r['lead_days'])==(role,lead)]
   if all(r['outcome_archive']=='FUTURE'for r in rs):continue
   report['cohorts'][cohort][role+':lead'+str(lead)]=compare(rs)
 pooled=[r for r in allrows['original_20261116']if r['model_role']=='near_primary']+[r for r in allrows['paired_20261117']if r['model_role']=='near_primary_20261117']
 report['pooled_near_primary_two_dates_unique_forecast_per_player_game']=compare(pooled)
 report['outcome_evidence_layer']='verified_union_sensitivity'if a.verified_union else'archive_reconciled'
 out=a.runtime_dir;(out/('DEPLOYED_RUNTIME_UNION_COMPARISON.json'if a.verified_union else'DEPLOYED_RUNTIME_COMPARISON.json')).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');(out/('common_union_scored_records.json'if a.verified_union else'common_scored_records.json')).write_text(json.dumps(allrows,ensure_ascii=False,allow_nan=False)+'\n')
 print(json.dumps({'cohorts':report['cohorts'],'pooled':report['pooled_near_primary_two_dates_unique_forecast_per_player_game']},indent=2))
if __name__=='__main__':main()
