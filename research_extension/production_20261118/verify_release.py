"""Independent release checks against the immutable weights and exact inputs.

This validates an inference result; it never trains, rewrites the scientific
forecast, or upgrades a predictive gate into fantasy-economic evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import re
from urllib.parse import urlparse
import numpy as np
import pandas as pd
from export_feed import ET,MSK,utc,iso,live_payload,windows_for_rows,SEED_EXCLUSIONS
from inference import predict_current,SUPPORTED_LEADS
from model_store import HERE,KNOWN_MODELS,load_model,load_manifest,sha256
from catalog_identity import OVERLAY_PATH,apply_reviewed_identity


def require(condition,message):
    if not condition:raise ValueError(message)


def verify_annotation(row,issued):
    annotation=row.get('official_status')
    if not annotation:return False
    require(bool(re.fullmatch(r'[1-9]\d*',str(row.get('nba_id','')))),'INVALID_ANNOTATED_PLAYER_ID')
    require(bool(re.fullmatch(r'002\d{7}',str(row.get('nba_game_id','')))),'INVALID_ANNOTATED_GAME_ID')
    require(annotation.get('exact_player_team_game_time') is True,'UNVERIFIED_ANNOTATION')
    require(str(annotation.get('nba_player_id'))==row['nba_id'],'ANNOTATED_PLAYER_MISMATCH')
    require(str(annotation.get('nba_game_id'))==row['nba_game_id'],'ANNOTATED_GAME_MISMATCH')
    require(annotation.get('calendar_game_id')==row['game_id'],'ANNOTATED_CALENDAR_MISMATCH')
    require(annotation.get('team')==row['team'],'ANNOTATED_TEAM_MISMATCH')
    require(annotation.get('home')==(row['team'] if row['home'] else row['opponent']),'ANNOTATED_HOME_MISMATCH')
    require(annotation.get('away')==(row['opponent'] if row['home'] else row['team']),'ANNOTATED_AWAY_MISMATCH')
    require(utc(annotation['tipoff_utc'])==utc(row['game_utc']),'ANNOTATED_TIME_MISMATCH')
    require(annotation.get('status') in ('out','doubtful','questionable','probable','available'),'INVALID_STATUS')
    require(annotation.get('deterministic_out_overlay')==(annotation['status']=='out'),'INVALID_OUT_OVERLAY')
    url=urlparse(annotation.get('source_url',''))
    require(url.scheme=='https' and url.hostname=='ak-static.cms.nba.com'
            and url.path.startswith('/referee/injury/Injury-Report_') and url.path.endswith('.pdf'),'UNTRUSTED_OFFICIAL_SOURCE')
    require(bool(re.fullmatch(r'[a-f0-9]{64}',annotation.get('source_sha256',''))),'INVALID_OFFICIAL_SOURCE_HASH')
    published,available=utc(annotation['report_at_utc']),utc(annotation['available_at_utc'])
    require(published<=available<=issued and dt.timedelta(0)<=issued-published<=dt.timedelta(hours=36),'STALE_OR_FUTURE_ANNOTATION')
    return annotation['status']=='out'


def verify(feed_path,research_path,features_path,snapshot_data,base_path,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    feed_path,research_path,features_path,snapshot_data,base_path=map(Path,(feed_path,research_path,features_path,snapshot_data,base_path))
    feed_raw=feed_path.read_bytes();feed=json.loads(feed_raw);full=json.loads(research_path.read_text())
    require(feed.get('schema_version')==1 and feed.get('kind')=='nba_per_game_model_forecasts','INVALID_FEED_SCHEMA')
    require(feed.get('status')=='ready' and feed['source_quality'].get('fresh') is True,'SOURCE_NOT_READY')
    require(not feed['source_quality'].get('failures') and not feed['source_quality'].get('missing_completed_public_games'),'SOURCE_FAILURES')
    issued,expires=utc(feed['issued_at_utc']),utc(feed['valid_until_utc'])
    capture=utc(feed['source_capture_completed_at_utc']);core=utc(feed['core_source_capture_completed_at_utc'])
    require(core<=capture<=issued<=now and now<expires,'INVALID_RELEASE_TIMING')
    require(expires<=issued+dt.timedelta(hours=24) and expires<=core+dt.timedelta(hours=36),'EXPIRY_EXCEEDS_INPUT_LIFETIME')
    require(issued.astimezone(ET).date().isoformat()==feed['asof_date_et'],'ASOF_DATE_MISMATCH')
    policy=feed['model_policy']
    require(policy.get('site_default') is True and policy.get('forecast_inputs_for_advisory_comparisons') is True,'DEFAULT_GATE_NOT_PASSED')
    for field in ('economic_gain_proven','optimizer_policy_validated','day_ewma_selected','fit_current_season','intraday_injury_model_selected'):
        require(policy.get(field) is False,'UNSUPPORTED_POLICY_PROMOTION:'+field)
    _,model_manifest_sha=load_manifest()
    require(feed['model_manifest_sha256']==model_manifest_sha,'MODEL_MANIFEST_MISMATCH')
    require(feed['model_sha256']==KNOWN_MODELS,'MODEL_WEIGHTS_CHANGED')
    effective_inputs=feed['input_manifest']
    require(sha256(json.dumps(effective_inputs,sort_keys=True,separators=(',',':')).encode())==feed['source_manifest_sha256'],'INPUT_MANIFEST_HASH_MISMATCH')
    for key,path in [('live_snapshot',snapshot_data/'live.json'),('UTC_schedule_snapshot',snapshot_data/'schedule.json'),
                     ('identity_snapshot',snapshot_data/'identity.json'),('catalog_seed',base_path),
                     ('catalog_identity_overlay',OVERLAY_PATH),
                     ('catalog_identity_source',snapshot_data/'catalog.json'),
                     ('feature_builder_code',HERE/'feature_build.py'),('exporter_code',HERE/'export_feed.py')]:
        require(sha256(path.read_bytes())==effective_inputs[key],'SOURCE_CHANGED_AFTER_INFERENCE:'+key)
    expected_client=live_payload(full)
    comparable={k:v for k,v in feed.items() if k!='refresh_fingerprint'}
    require(comparable==expected_client,'LIVE_FEED_DIFFERS_FROM_PRESERVED_SCIENTIFIC_RESULT')
    require(feed['coverage']['feature_rows_without_exact_utc_game_join']==0,'UNJOINED_FEATURE_ROWS')
    catalog={r['id']:r for r in json.loads(base_path.read_text())['players']}
    effective_identity,identity_qa=apply_reviewed_identity(json.loads((snapshot_data/'identity.json').read_text())['players'],
        catalog,feed['issued_at_utc'],source_catalog_sha256=sha256((snapshot_data/'catalog.json').read_bytes()))
    frame=pd.read_pickle(features_path).reset_index(drop=True)
    require(frame.issue_date.astype(str).eq(feed['asof_date_et']).all(),'FEATURE_ISSUE_DATE_MISMATCH')
    near,long=load_model('near_latest'),load_model('long_latest')
    predicted,valid,_=predict_current(frame,near,long)
    indices={(str(row.pid),str(row.game)):i for i,row in frame.iterrows()}
    require(len(indices)==len(frame),'DUPLICATE_FEATURE_KEYS')
    keys=set();counts={'model_rows':0,'fallback_rows':0,'unavailable_rows':0,'official_annotations':0,'official_out':0,
                       'supported_decision_rows':0,'provisional_rows':0,'model_rows_all_research':0}
    largest_delta=0.
    # Validate all scientific rows, including NBA IDs missing from the smaller UI catalog.
    for row in full['rows']:
        tip=utc(row['game_utc']);lock=utc(row['lock_utc'])
        require(tip-lock==dt.timedelta(minutes=30) and tip>=issued,'INVALID_GAME_LOCK')
        require(tip.astimezone(ET).date().isoformat()==row['game_date_et'],'NBA_DATE_MISMATCH')
        require(tip.astimezone(MSK).date().isoformat()==row['game_date_msk'],'MOSCOW_DATE_MISMATCH')
        actual=(dt.date.fromisoformat(row['game_date_et'])-dt.date.fromisoformat(feed['asof_date_et'])).days
        require(actual==row['actual_horizon_days'],'ACTUAL_LEAD_MISMATCH')
        out=verify_annotation(row,issued)
        if row.get('official_status'):counts['official_annotations']+=1
        if out:counts['official_out']+=1
        require(row.get('effective_p_play')==(0. if out else row['p_play']),'EFFECTIVE_PROBABILITY_MISMATCH')
        require(row.get('effective_expected_fp')==(0. if out else row['expected_fp']),'EFFECTIVE_EXPECTATION_MISMATCH')
        effective_bands=row.get('effective_unconditional_intervals',row.get('unconditional_intervals'))
        require(effective_bands==({str(n):[0.,0.] for n in (50,80,95)} if out else row.get('unconditional_intervals')),'EFFECTIVE_INTERVAL_MISMATCH')
        model=row['model_id'] in ('near_latest','long_latest')
        if model:
            counts['model_rows_all_research']+=1
            index=indices.get((row['nba_id'],row['nba_game_id']))
            require(index is not None and valid[index],'MODEL_ROW_NOT_SUPPORTED_BY_FEATURES')
            source=frame.iloc[index];expected=predicted.iloc[index]
            require(str(source.team)==row['team'] and str(source.opp)==row['opponent'] and bool(source.home)==row['home'],'MODEL_FIXTURE_MISMATCH')
            pairs=[(row[key],float(expected[key])) for key in ('p_play','mean_if_play','expected_fp')]
            for prefix,target in [('conditional_','conditional_intervals'),('','unconditional_intervals')]:
                for n in (50,80,95):
                    pairs.extend(zip(row[target][str(n)],[float(expected[f'{prefix}lo{n}']),float(expected[f'{prefix}hi{n}'])]))
            delta=max(abs(a-b) for a,b in pairs);largest_delta=max(largest_delta,delta)
            require(delta<=1e-8,'SELECTED_BASE_FORECAST_CHANGED')
            require(row['model_id']==('near_latest' if actual==0 else 'long_latest'),'WRONG_MODEL_BY_ACTUAL_LEAD')
            if actual in SUPPORTED_LEADS:require(row['support']=='exact_lead','EXACT_LEAD_MISLABELLED')
        elif row['model_id']=='legacy_seed_fallback':
            require(row['player_id'] not in SEED_EXCLUSIONS,'CONTAMINATED_SEED_FALLBACK')
            require(row['conditional_intervals'] is None and row['unconditional_intervals'] is None,'FABRICATED_FALLBACK_INTERVAL')
        else:
            require(row['model_id']=='unavailable','UNKNOWN_MODEL')
            require(all(row[k] is None for k in ('p_play','mean_if_play','expected_fp')),'UNKNOWN_AS_ZERO')
        if row['eligible_for_decision']:
            require(model and row['player_id'] in catalog and row['support']!='provisional_lead_bucket' and issued<lock,'UNSUPPORTED_DECISION_ELIGIBILITY')
        if row.get('intraday_shadow'):require(row['intraday_shadow']['selected_for_production'] is False,'SHADOW_PROMOTED')
        if row.get('challenger'):require(row['challenger']['selected_for_production'] is False,'CHALLENGER_PROMOTED')
    for row in feed['rows']:
        key=(row['player_id'],row['game_id'])
        require(key not in keys and row['player_id'] in catalog,'DUPLICATE_OR_UNKNOWN_CATALOG_KEY');keys.add(key)
        require('intraday_shadow' not in row and 'challenger' not in row,'SCIENTIFIC_SHADOW_LEAKED_TO_CLIENT')
        if row.get('nba_id'):
            require(str(effective_identity[row['player_id']]['nba_id'])==row['nba_id']
                    and effective_identity[row['player_id']]['confidence']=='high','UNREVIEWED_CATALOG_NBA_IDENTITY')
        if row['model_id'] in ('near_latest','long_latest'):counts['model_rows']+=1
        elif row['model_id']=='legacy_seed_fallback':counts['fallback_rows']+=1
        else:counts['unavailable_rows']+=1
        counts['supported_decision_rows']+=int(row['eligible_for_decision'])
        counts['provisional_rows']+=int(row['support']=='provisional_lead_bucket')
    for kind in ('model_rows','fallback_rows','unavailable_rows'):
        require(counts[kind]==feed['coverage'][kind],'COVERAGE_MISMATCH:'+kind)
    require(len(keys)==feed['coverage']['rows'],'TOTAL_COVERAGE_MISMATCH')
    require(feed['windows']==windows_for_rows(feed['rows'],feed['issued_at_utc'],False),'WINDOW_EXPECTATION_MISMATCH')
    require(all(w.get('predictive_intervals') is None for w in feed['windows']),'UNVALIDATED_JOINT_INTERVAL')
    return {'schema':'nba_frozen_release_qa_v1','status':'PASS','verified_at_utc':iso(now),
            'feed_sha256':sha256(feed_raw),'feed_bytes':len(feed_raw),'model_manifest_sha256':model_manifest_sha,
            'source_manifest_sha256':feed['source_manifest_sha256'],'feed_issued_at_utc':feed['issued_at_utc'],
            'feed_valid_until_utc':feed['valid_until_utc'],'full_research_sha256':sha256(research_path.read_bytes()),
            'feature_frame_sha256':sha256(features_path.read_bytes()),'counts':counts,
            'max_abs_base_prediction_delta':largest_delta,'original_model_sha256':KNOWN_MODELS,
            'reviewed_current_catalog_identity':identity_qa,'blocked_contaminated_seed_ids':sorted(SEED_EXCLUSIONS),
            'checks':{'unchanged_selected_base_predictions':True,'exact_official_status_identity_and_source':True,
                      'independent_core_source_expiry':True,'no_unknown_as_zero':True,'no_shadow_variant_selected':True,
                      'catalog_only_client':True,'no_joint_interval_endpoint_sums':True,'input_hashes_match':True},
            'training_performed':False,'optimizer_policy_validated':False,'economic_gain_proven':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--feed',type=Path,required=True)
    p.add_argument('--research-feed',type=Path,required=True);p.add_argument('--features',type=Path,required=True)
    p.add_argument('--snapshot-data',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    try:
        report=verify(a.feed,a.research_feed,a.features,a.snapshot_data,a.base)
    except Exception as exc:
        report={'schema':'nba_frozen_release_qa_v1','status':'FAIL','verified_at_utc':iso(dt.datetime.now(dt.timezone.utc)),
                'error':str(exc),'feed_sha256':sha256(a.feed.read_bytes()) if a.feed.exists() else None}
        a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
        raise
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
