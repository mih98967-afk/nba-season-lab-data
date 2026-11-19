"""Freeze public research forecasts, excluding locked/ambiguous fixtures.

A published hash is a commitment to these bytes, not evidence of useful forecasts.
The feature cutoff and actual issue time are distinct and are never backdated.
"""
import argparse,collections,datetime,hashlib,json,pathlib
from zoneinfo import ZoneInfo
import pandas as pd
UTC=datetime.timezone.utc

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=pathlib.Path,default=pathlib.Path('.'));ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();root=a.root;a.output.mkdir(parents=True,exist_ok=True)
    if (a.output/'forecasts.json').exists():raise ValueError('IMMUTABLE_FREEZE_ALREADY_EXISTS')
    now=datetime.datetime.now(UTC);idx=collections.defaultdict(list)
    schedule_path=root/'source/data/live.json';live=json.loads(schedule_path.read_text())
    for g in live['schedule']:
        t=datetime.datetime.fromisoformat(g['utc'].replace('Z','+00:00'))
        key=(str(t.astimezone(ZoneInfo('America/New_York')).date()),frozenset([g['home'],g['away']]))
        idx[key].append(g)
    cases=[('near_primary','results_current_near_latest','results_near_latest'),('near_interval_challenger','results_current_distribution','results_near_distribution'),('long_lead_primary','results_current_latest','results_latest')]
    forecasts=[];rejected=collections.Counter();model_hashes={};input_hashes={}
    for name,folder,modeldir in cases:
        path=root/folder/'RESEARCH_ONLY_preview.csv';data=pd.read_csv(path,dtype={'pid':str,'game':str});card=json.loads((root/modeldir/'MODEL_RESEARCH_REPORT.json').read_text());model_hashes[name]=card['model_sha256'];input_hashes[name]=digest(path)
        if name=='long_lead_primary':data=data[data.horizon_days>0]
        for r in data.to_dict('records'):
            matches=idx.get((r['date'],frozenset([r['team'],r['opp']])),[])
            if len(matches)!=1:rejected['no_unique_schedule_join']+=1;continue
            g=matches[0];tip=datetime.datetime.fromisoformat(g['utc'].replace('Z','+00:00'))
            if tip<=now+datetime.timedelta(minutes=30) or g['status']!='scheduled':rejected['locked_or_started']+=1;continue
            if pd.notna(r['y_play']) or pd.notna(r['y_fp']):raise ValueError('FUTURE_TARGET_OUTCOME_PRESENT')
            preds={k:float(r[k]) for k in r if k in ['p_play','mean_if_play','expected_fp'] or k.startswith(('lo','hi','conditional_lo','conditional_hi'))}
            forecasts.append({'model_role':name,'nba_player_id':r['pid'],'nba_game_id':r['game'],'calendar_game_id':g['id'],'tipoff_utc':g['utc'],'date_ET':r['date'],'team':r['team'],'opponent':r['opp'],'player_name':r['name'],'lead_days':int(r['horizon_days']),'feature_date_ET':r['issue_date'],'model_sha256':card['model_sha256'],**preds})
    payload={'schema':'nba-public-research-forecast-freeze-v1','issued_at_utc':now.isoformat(),'feature_cutoff_utc':'2026-11-16T05:00:00Z','adopt_on_site':False,'official_sportsru_credit_verified':False,'real_KEEP_TRANSFER_gain_proven':False,'owner_data_used':False,'status':'prospective_public_shadow_only','sources':{'calendar_sha256':digest(schedule_path),'current_manifest_sha256':digest(root/'source/current/manifest.json'),'preview_sha256':input_hashes},'models':model_hashes,'rejections':dict(rejected),'records':forecasts,'limitations':['Feature cutoff is morning ET, not a fresh injury refresh at issue time','Incomplete schedule and exact identity coverage; only unique joins admitted','No owner roster, prices, transfer quota, executions or Sports.ru credits','Intervals are per-game only; interval challenger is exploratory after retrospective diagnostics']}
    p=a.output/'forecasts.json';p.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    commitment={'schema':'nba-public-research-freeze-commitment-v1','issued_at_utc':payload['issued_at_utc'],'feature_cutoff_utc':payload['feature_cutoff_utc'],'file':'forecasts.json','sha256':digest(p),'bytes':p.stat().st_size,'records':len(forecasts),'distinct_player_games':len({(r['nba_player_id'],r['nba_game_id']) for r in forecasts}),'distinct_games':len({r['nba_game_id'] for r in forecasts}),'minimum_tipoff_utc':min((r['tipoff_utc'] for r in forecasts),default=None),'roles':dict(collections.Counter(r['model_role'] for r in forecasts)),'model_hashes':model_hashes,'rejections':dict(rejected),'adopt_on_site':False,'owner_data_used':False,'hash_commitment_is_not_validation':True}
    (a.output/'COMMITMENT.json').write_text(json.dumps(commitment,indent=2)+'\n');print(json.dumps(commitment,indent=2))
if __name__=='__main__':main()
