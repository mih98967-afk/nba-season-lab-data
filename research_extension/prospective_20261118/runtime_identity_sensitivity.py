"""Independent identity-audit sensitivity. Do not replace original runtime results."""
import argparse,collections,datetime as dt,json
from pathlib import Path
from compare_runtime import compare
from score_completed import sha
HERE=Path(__file__).resolve().parent
EXCLUDED={'n133','n326','n346','n406'}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--runtime-dir',type=Path,default=HERE/'baseline_results');a=ap.parse_args()
 result={'schema':'nba-runtime-independent-identity-sensitivity-v1','evaluated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'excluded_seed_catalog_ids':sorted(EXCLUDED),'reason':'Independent cross-player seed-history contamination audit, not prediction errors','original_primary_runtime_replay_unchanged':True,'no_predictions_retrained_or_retuned':True,'layers':{}}
 for layer,name in [('archive_reconciled','common_scored_records.json'),('verified_union_sensitivity','common_union_scored_records.json')]:
  p=a.runtime_dir/name;allrows=json.loads(p.read_text());output={'input_sha256':sha(p),'by_cohort_role_and_lead':{}}
  for cohort,rows in allrows.items():
   for role,lead in sorted({(r['model_role'],r['lead_days'])for r in rows}):
    group=[r for r in rows if(r['model_role'],r['lead_days'])==(role,lead)and r['outcome_archive']!='FUTURE']
    if not group:continue
    excluded=[r for r in group if r['runtime'].get('catalog_id')in EXCLUDED];retained=[r for r in group if r['runtime'].get('catalog_id')not in EXCLUDED]
    output['by_cohort_role_and_lead'][cohort+':'+role+':lead'+str(lead)]={'excluded_completed_rows':len(excluded),'excluded_rows':[{'catalog_id':r['runtime'].get('catalog_id'),'nba_game_id':r['nba_game_id'],'player_name':r['player_name'],'outcome':r['outcome_archive']}for r in excluded],'retained_comparison':compare(retained)}
  pooled=[r for r in allrows['original_20261116']if r['model_role']=='near_primary']+[r for r in allrows['paired_20261117']if r['model_role']=='near_primary_20261117']
  output['pooled_near_primary_two_dates']=compare([r for r in pooled if r['runtime'].get('catalog_id')not in EXCLUDED]);output['excluded_unique_near_player_games']=len({(r['nba_player_id'],r['nba_game_id'])for r in pooled if r['runtime'].get('catalog_id')in EXCLUDED})
  result['layers'][layer]=output
 (a.runtime_dir/'IDENTITY_EXCLUSION_SENSITIVITY.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps({k:v['pooled_near_primary_two_dates']for k,v in result['layers'].items()},indent=2))
if __name__=='__main__':main()
