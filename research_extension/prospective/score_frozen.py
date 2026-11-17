"""Evaluate immutable public forecasts against separately versioned outcomes.
No training, calibration, source mutation, or automatic promotion is performed.
"""
from __future__ import annotations
import argparse, collections, csv, datetime as dt, hashlib, json, math, os
from pathlib import Path
import numpy as np
import pandas as pd

EXPECTED_SHA='5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb'
SNAPSHOT_COMMIT='11d89bb61b56460d8f1d7aaa4214c9a12b77503a'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def utc(value): return dt.datetime.fromisoformat(value.replace('Z','+00:00'))
def unique_index(rows, keys):
    out={}
    for row in rows:
        k=tuple(str(row[x]) for x in keys)
        if k in out: raise ValueError('DUPLICATE_KEY:'+str(k))
        out[k]=row
    return out

def load_frozen(path):
    if sha(path)!=EXPECTED_SHA: raise ValueError('FROZEN_HASH_MISMATCH')
    j=json.loads(path.read_text()); issued=utc(j['issued_at_utc'])
    unique_index(j['records'],['model_role','nba_player_id','nba_game_id','lead_days'])
    for row in j['records']:
        if utc(row['tipoff_utc'])-dt.timedelta(minutes=30)<=issued:
            raise ValueError('NOT_PRELOCK')
        if row['model_sha256']!=j['models'][row['model_role']]:
            raise ValueError('MODEL_HASH_MISMATCH')
        if not 0<=row['p_play']<=1: raise ValueError('INVALID_PPLAY')
        for n in (50,80,95):
            for prefix in ('','conditional_'):
                if not row[prefix+'lo'+str(n)]<=row[prefix+'hi'+str(n)]:
                    raise ValueError('CROSSED_INTERVAL')
    return j

def identity_crosswalk(identity):
    out=collections.defaultdict(list)
    for catalog_id,r in identity['players'].items():
        if r.get('confidence')=='high' and str(r.get('nba_id','')).isdigit():
            out[str(r['nba_id'])].append(catalog_id)
    return {k:v[0] for k,v in out.items() if len(v)==1}

def outcome_for(f, live, dnp, official, idmap, now):
    """Return two separately identified labels; never infer a negative from absence."""
    base={'outcome_espn':'UNKNOWN','outcome_augmented':'UNKNOWN','y_fp':None,
          'reason':'no_matching_evidence','source_url':None,'official_source_url':None,
          'official_source_sha256':None}
    if utc(f['tipoff_utc'])>now:
        return {**base,'outcome_espn':'FUTURE','outcome_augmented':'FUTURE','reason':'future_tipoff'}
    game=live['game_index'].get((f['calendar_game_id'],))
    if not game or game.get('status')!='final':
        return {**base,'reason':'game_not_proven_final'}
    if (game.get('utc')!=f['tipoff_utc'] or
        {game.get('home'),game.get('away')}!={f['team'],f['opponent']}):
        return {**base,'reason':'fixture_conflict'}
    cid=idmap.get(f['nba_player_id'])
    if not cid: return {**base,'reason':'no_unique_high_confidence_identity'}
    key=(f['calendar_game_id'],cid)
    p=live['row_index'].get(key); n=dnp['event_index'].get(key)
    o=official.get(key)
    if p and (p.get('team')!=f['team'] or p.get('utc')!=f['tipoff_utc']):
        return {**base,'reason':'positive_team_time_conflict'}
    if n and (n.get('team')!=f['team'] or n.get('game_utc')!=f['tipoff_utc']):
        return {**base,'reason':'negative_team_time_conflict'}
    pos=bool(p and p.get('played') is True and float(p.get('minutes',0))>0 and
             isinstance(p.get('fp'),(int,float)) and math.isfinite(p['fp']))
    chk=dnp.get('checked_game_evidence',{}).get(f['calendar_game_id'],{})
    neg=bool(n and n.get('evidence')=='explicit_espn_didNotPlay_true' and
             chk.get('game_utc')==f['tipoff_utc'] and
             {chk.get('home'),chk.get('away')}=={f['team'],f['opponent']} and
             utc(n['observed_at_utc'])<=now and utc(chk['verified_at_utc'])<=now)
    off=bool(o and o.get('independent_NBA_verdict') in ('VERIFIED_GAME_DAY_INACTIVE','VERIFIED_ACTIVE_NONPLAY') and
             o.get('historical_identity_strength')=='high' and o.get('historical_nba_id_if_high')==f['nba_player_id'] and
             o.get('team')==f['team'] and o.get('game_utc')==f['tipoff_utc'] and
             o.get('source_game_id')==f['nba_game_id'] and
             o.get('source_url')=='https://cdn.nba.com/static/json/liveData/boxscore/boxscore_'+f['nba_game_id']+'.json' and
             isinstance(o.get('source_canonical_sha256'),str) and len(o['source_canonical_sha256'])==64 and
             o.get('official_game_day_team_membership_verified') is True and
             o.get('conflict_requires_review') is False and utc(o['source_first_observed_at_utc'])<=now)
    if pos and (neg or off): return {**base,'reason':'positive_negative_conflict'}
    if pos:
        return {**base,'outcome_espn':'PLAYED','outcome_augmented':'PLAYED','y_fp':float(p['fp']),
                'reason':'positive_minutes_exact_game','source_url':p.get('source_url'),'catalog_id':cid}
    if neg:
        return {**base,'outcome_espn':'EXPLICIT_DNP','outcome_augmented':'EXPLICIT_DNP','y_fp':0.,
                'reason':'explicit_espn_didNotPlay_true','source_url':n.get('source_url'),'catalog_id':cid}
    if off:
        return {**base,'outcome_augmented':'OFFICIAL_INACTIVE','y_fp':0.,'reason':'supplementary_official_game_day_evidence',
                'official_source_url':o['source_url'],'official_source_sha256':o['source_canonical_sha256'],'catalog_id':cid}
    return {**base,'catalog_id':cid}

def metrics(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float)
    if not len(y):return {'n':0}
    e=p-y
    return {'n':len(y),'mae':float(np.abs(e).mean()),'rmse':float(np.sqrt((e*e).mean())),'bias_prediction_minus_actual':float(e.mean())}

def prob_metrics(y,p):
    y=np.asarray(y,float);p=np.asarray(p,float)
    if not len(y):return {'n':0}
    q=np.clip(p,1e-9,1-1e-9)
    return {'n':len(y),'brier':float(((p-y)**2).mean()),'log_loss':float(-(y*np.log(q)+(1-y)*np.log1p(-q)).mean()),'predicted_mean':float(p.mean()),'observed_play_fraction':float(y.mean())}

def intervals(rows,n,conditional):
    if not rows:return {'n':0}
    p='conditional_' if conditional else '';y=np.array([x['y_fp'] for x in rows]);lo=np.array([x[p+'lo'+str(n)] for x in rows]);hi=np.array([x[p+'hi'+str(n)] for x in rows]);a=1-n/100
    return {'n':len(rows),'coverage':float(((y>=lo)&(y<=hi)).mean()),'width':float((hi-lo).mean()),'interval_score':float(((hi-lo)+2/a*np.maximum(lo-y,0)+2/a*np.maximum(y-hi,0)).mean())}

def evaluate(rows,field):
    done=[x for x in rows if x[field]!='FUTURE']; known=[x for x in done if x[field] in ('PLAYED','EXPLICIT_DNP','OFFICIAL_INACTIVE')];played=[x for x in known if x[field]=='PLAYED'];unknown=[x for x in done if x[field]=='UNKNOWN']
    labels=[int(x[field]=='PLAYED') for x in known]
    out={'counts':dict(collections.Counter(x[field] for x in rows)),
         'conditional':{'baseline_last10':metrics([x['y_fp'] for x in played],[x['baseline_fp10'] for x in played]),'frozen_candidate':metrics([x['y_fp'] for x in played],[x['mean_if_play'] for x in played])},
         'participation':{'baseline_history':prob_metrics(labels,[x['baseline_p_play'] for x in known]),'frozen_candidate':prob_metrics(labels,[x['p_play'] for x in known])},
         'unconditional':{'baseline_history':metrics([x['y_fp'] for x in known],[x['baseline_fp10']*x['baseline_p_play'] for x in known]),'frozen_candidate':metrics([x['y_fp'] for x in known],[x['expected_fp'] for x in known])},
         'intervals':{str(n):{'conditional':intervals(played,n,True),'unconditional':intervals(known,n,False)} for n in (50,80,95)}}
    if done:
        gain=sum((x['baseline_p_play']-int(x[field]=='PLAYED'))**2-(x['p_play']-int(x[field]=='PLAYED'))**2 for x in known)
        g=[[x['baseline_p_play']**2-x['p_play']**2,(1-x['baseline_p_play'])**2-(1-x['p_play'])**2] for x in unknown]
        out['missing_label_paired_brier_gain_bounds']=[(gain+sum(min(x) for x in g))/len(done),(gain+sum(max(x) for x in g))/len(done)]
        out['bounds_are_partial_identification_not_confidence_interval']=True
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path(os.environ.get('NBA_RESEARCH_BASE','research_base')));ap.add_argument('--snapshot',type=Path,default=Path('research_extension/prospective/current_snapshot'));ap.add_argument('--output',type=Path,default=Path('research_extension/prospective/results'));ap.add_argument('--evaluated-at');a=ap.parse_args();a.evaluated_at=a.evaluated_at or dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ');now=utc(a.evaluated_at)
    frozen=load_frozen(a.base/'prospective_20261116/forecasts.json');data=a.snapshot/'data'; load=lambda n:json.loads((data/n).read_text())
    live=load('live.json');identity=load('identity.json');dnp=load('explicit_dnp_research.json');official=load('official_nba_nonout_unknown_research.json')
    if utc(live['updated_at_utc'])>now:raise ValueError('SOURCE_AFTER_EVALUATION')
    live['game_index']=unique_index(live['games'],['id']);live['row_index']=unique_index(live['rows'],['game_id','id']);dnp['event_index']=unique_index(dnp['events'],['game_id','player_id']);off=unique_index(official['records'],['game_id','player_id'])
    idmap=identity_crosswalk(identity)
    frame=pd.read_pickle(a.base/'results_current/feature_frame.pkl')
    frame=frame[frame.y_play.isna()&frame.y_fp.isna()]
    ix={ (str(r.pid),str(r.game),int(r.horizon_days),str(r.issue_date)):r for r in frame.itertuples() }
    results=[]
    for f in frozen['records']:
        k=(f['nba_player_id'],f['nba_game_id'],f['lead_days'],f['feature_date_ET'])
        baseline=ix.get(k)
        if baseline is None: raise ValueError('MISSING_FROZEN_BASELINE:'+str(k))
        o=outcome_for(f,live,dnp,off,idmap,now)
        results.append({**f,**o,'baseline_fp10':float(baseline.fp10),'baseline_p_play':float(baseline.obs_play_rate25)})
    done=[x for x in results if x['outcome_espn']!='FUTURE']
    report={'schema':'nba-frozen-prospective-evaluation-v1','evaluated_at_utc':a.evaluated_at,'source_commit':SNAPSHOT_COMMIT,
            'forecast_sha256':EXPECTED_SHA,'original_issued_at_utc':frozen['issued_at_utc'],
            'adopt_on_site':False,'official_sportsru_credit_verified':False,'real_KEEP_TRANSFER_gain_proven':False,
            'primary_outcome_source':'ESPN final fallback and explicit didNotPlay archive',
            'supplementary_source':'archived official NBA exact-game inactive evidence; evaluation only',
            'known_fp_source':'reconstructed NBA-style FP, not official Sports.ru',
            'original_records':len(results),'original_distinct_player_games':len({(x['nba_player_id'],x['nba_game_id']) for x in results}),
            'elapsed_records':len(done),'elapsed_distinct_player_games':len({(x['nba_player_id'],x['nba_game_id']) for x in done}),
            'elapsed_games':len({x['nba_game_id'] for x in done}),'elapsed_ET_dates':sorted({x['date_ET'] for x in done}),
            'by_role':{},'sources':{},'limitations':['One completed NBA date cannot establish prospective superiority or date-cluster confidence','Selected cohort excludes many cold starts and unmapped identities','UNKNOWN is never zero; primary and supplementary outcomes are separate','Forecast feature cutoff preceded issue by about 14 hours; no late injury refresh','No owner prices, quota, locks, ownership or official credited points; not transfer utility','No tuning or recalibration was performed']}
    for role in sorted({x['model_role'] for x in results}):
        rs=[x for x in results if x['model_role']==role];report['by_role'][role]={'espn_only':evaluate(rs,'outcome_espn'),'supplementary_official_inactive':evaluate(rs,'outcome_augmented'),'unknown_reasons':dict(collections.Counter(x['reason'] for x in rs if x['outcome_augmented']=='UNKNOWN'))}
    for p in [data/'live.json',data/'identity.json',data/'explicit_dnp_research.json',data/'official_nba_nonout_unknown_research.json',a.base/'results_current/feature_frame.pkl']:
        report['sources'][p.name]={'sha256':sha(p),'bytes':p.stat().st_size}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'PROSPECTIVE_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    (a.output/'scored_records.json').write_text(json.dumps(results,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({k:report[k] for k in ['elapsed_records','elapsed_distinct_player_games','elapsed_games','elapsed_ET_dates','by_role']},indent=2))
if __name__=='__main__':main()
