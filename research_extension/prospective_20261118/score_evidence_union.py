"""Symmetric evidence union sensitivity: accept every additional explicit ESPN label.
Archive/official conflicts remain quarantined. Missing NBA reason is not a negative.
Original archive-only scored files are never overwritten.
"""
import collections,datetime as dt,json
from pathlib import Path
from score_completed import KNOWN,describe,pair_comparison,sha
HERE=Path(__file__).resolve().parent

def union_evidence(row):
 out=dict(row)
 out['outcome_evidence_union']=row['outcome_archive'];out['union_y_fp']=row['y_fp'];out['union_participation_verified']=row['participation_verified']
 out['union_evidence_source']='archive_or_direct_official_NBA'
 if row['espn_archive_overlap']=='CONFLICT':out['union_evidence_source']='unresolved_source_conflict';return out
 if row['outcome_archive']=='UNKNOWN'and row['outcome_espn']in KNOWN:
  out['outcome_evidence_union']=row['outcome_espn'];out['union_y_fp']=row['espn_y_fp'];out['union_participation_verified']=int(row['outcome_espn']=='PLAYED');out['union_evidence_source']='independent_exact_ESPN_label_additional_to_unknown_NBA'
 return out

def union_metric_rows(rows):
 return [{**r,'outcome_archive':r['outcome_evidence_union'],'y_fp':r['union_y_fp'],'participation_verified':r['union_participation_verified']}for r in rows]

def main():
 source=HERE/'results_official_supplement';out=HERE/'results_verified_union';out.mkdir(exist_ok=True)
 report={'schema':'nba-verified-source-union-sensitivity-v1','evaluated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'evaluation_only':True,'rule':'Use all exact ESPN known labels when archive/direct NBA label UNKNOWN and no explicit source conflict. Keep every known archive label. Never replace an explicit disagreement. No prediction/error-dependent inclusion.','original_source_report_sha256':sha(source/'PROSPECTIVE_REPORT.json'),'original_archive_report_unchanged':True,'training_or_tuning_performed':False,'official_Sports_ru_credits_proven':False,'cohorts':{}}
 for cohort in ['original_20261116','paired_20261117']:
  original=json.loads((source/(cohort+'_scored_records.json')).read_text());rows=[union_evidence(r)for r in original];metricrows=union_metric_rows(rows);entry={'additional_record_labels':sum(r['union_evidence_source']=='independent_exact_ESPN_label_additional_to_unknown_NBA'for r in rows),'additional_unique_player_games':len({(r['nba_player_id'],r['nba_game_id'])for r in rows if r['union_evidence_source']=='independent_exact_ESPN_label_additional_to_unknown_NBA'}),'by_role_and_lead':{},'additional_evidence':[r for r in rows if r['union_evidence_source']=='independent_exact_ESPN_label_additional_to_unknown_NBA']}
  for role,lead in sorted({(r['model_role'],r['lead_days'])for r in rows}):
   group=[r for r in metricrows if(r['model_role'],r['lead_days'])==(role,lead)]
   if all(r['outcome_archive']=='FUTURE'for r in group):continue
   entry['by_role_and_lead'][role+':lead'+str(lead)]=describe(group)
  if cohort=='paired_20261117':entry['paired_mean_challenger_comparison']=pair_comparison(metricrows)
  report['cohorts'][cohort]=entry
  (out/(cohort+'_scored_records.json')).write_text(json.dumps(rows,ensure_ascii=False,allow_nan=False)+'\n')
 (out/'PROSPECTIVE_UNION_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
 print(json.dumps({k:{'additional_unique_player_games':v['additional_unique_player_games']}for k,v in report['cohorts'].items()},indent=2))
if __name__=='__main__':main()
