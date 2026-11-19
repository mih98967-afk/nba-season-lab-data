"""Versioned per-game/public-window JSON from immutable fitted models.

No training, no private team/price/ownership data and no outcome scoring.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import tempfile
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from feature_build import build_current
from inference import SUPPORTED_LEADS,calibration_bucket,predict_current
from model_store import HERE,ROOT,KNOWN_MODELS,load_manifest,load_model,sha256
from catalog_identity import OVERLAY_PATH,apply_reviewed_identity

UTC=dt.timezone.utc
ET=ZoneInfo('America/New_York')
MSK=ZoneInfo('Europe/Moscow')
SEED_EXCLUSIONS={'n133','n266','n314','n326','n346','n406','n423'}  # Exact cross-player historical fingerprints; research NBA-ID features unaffected.


def utc(value):
    stamp=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('NAIVE_AVAILABILITY_TIMESTAMP')
    return stamp.astimezone(UTC)


def iso(stamp):return stamp.astimezone(UTC).isoformat().replace('+00:00','Z')


def read_json(path):return json.loads(Path(path).read_text())


def finite(value):
    try:return math.isfinite(float(value))
    except (TypeError,ValueError):return False


def schedule_key(game):
    day=game.get('et_date') or utc(game['utc']).astimezone(ET).date().isoformat()
    return day,game['home'],game['away']


def check_freshness(source,source_qa,capture,schedule,live,issued_at,asof):
    errors=[];now=utc(issued_at)
    try:
        captured=utc(capture['completed_at_utc'])
        if captured>now:errors.append('SOURCE_CAPTURE_AFTER_ISSUE')
        if now-captured>dt.timedelta(hours=36):errors.append('SOURCE_CAPTURE_STALE')
    except (ValueError,KeyError):errors.append('SOURCE_CAPTURE_TIME_UNKNOWN');captured=now
    # Recent live results do not certify the separately captured season calendar.
    for label,document in (('UTC_SCHEDULE',schedule),('PUBLIC_LIVE',live)):
        try:
            updated=utc(document.get('updated_at_utc'))
            if updated>now:errors.append(label+'_AFTER_ISSUE')
            if now-updated>dt.timedelta(hours=72):errors.append(label+'_STALE')
        except (ValueError,KeyError,TypeError):errors.append(label+'_TIME_UNKNOWN')
    if source_qa.get('status')!='INTERNAL_COHERENCE_PASS':errors.append('CURRENT_SOURCE_QA_FAILED')
    manifest=read_json(Path(source)/'current/manifest.json')
    for item in manifest:
        path=Path(source)/'current'/item.get('file','')
        if item.get('status')!='retrieved' or not path.is_file() or sha256(path.read_bytes())!=item['sha256']:
            errors.append('CURRENT_SOURCE_HASH_MISMATCH');break
    sc=pd.read_csv(Path(source)/'current/nba_schedule_2027.csv.gz',dtype=str,keep_default_na=False)
    completed=set()
    for g in sc.to_dict('records'):
        if finite(g['home_pts']) and finite(g['away_pts']) and float(g['home_pts'])!=float(g['away_pts']):
            completed.add((g['game_date'][:10],g['home_team_abbreviation'],g['away_team_abbreviation']))
    public=schedule.get('games',live.get('schedule',[]))
    expected={schedule_key(g) for g in public if g.get('status') in ('final','Final','completed') and schedule_key(g)[0]<asof}
    missing=sorted(expected-completed)
    if missing:errors.append('COMPLETED_GAMES_MISSING_FROM_MODEL_HISTORY')
    last=source_qa.get('schedule',{}).get('latest_coherent_completed_date')
    if last and (dt.date.fromisoformat(asof)-dt.date.fromisoformat(last)).days>3:errors.append('COMPLETED_GAME_CONTENT_STALE')
    return {'fresh':not errors,'failures':sorted(set(errors)),
            'missing_completed_public_games':[{'date':v[0],'home':v[1],'away':v[2]} for v in missing],
            'latest_completed_date':last,'capture_completed_at_utc':iso(captured),
            'capture_is_not_evidence_of_sporting_content_freshness':True,
            'current_manifest_sha256':sha256((Path(source)/'current/manifest.json').read_bytes()),
            'derivation_sha256':capture.get('derivation_sha256'),
            'injury_latest_report_source_naive':source_qa.get('injury',{}).get('latest_report_datetime_source'),
            'injury_report_timestamp_is_not_UTC':True,
            'injury_features_stop_before_issue_date_midnight':True}


def legacy_fallback(player,game,live,issued_at):
    """Mirror the public default prior/recent mean without private overrides.

    This is explicitly an uncalibrated fallback. Missing seed != zero FP.
    """
    if not player or not player.get('forecast') or player.get('id') in SEED_EXCLUSIONS:return None
    old=None
    for item in player.get('games',[]):
        same=(item.get('id')==game['id'])
        close=finite(item.get('epoch')) and abs(float(item['epoch'])-utc(game['utc']).timestamp()*1000)<3.1*3600*1000
        opponent=game['away'] if player.get('team')==game['home'] else game['home']
        if same or (close and item.get('opponent')==opponent):old=item;break
    prior=(old or {}).get('mu',player.get('mean_if_play'))
    if not finite(prior):return None
    values=[r for r in live.get('rows',[]) if r.get('id')==player['id'] and r.get('played') is True
            and finite(r.get('fp')) and r.get('utc') and utc(r['utc'])<utc(issued_at)]
    values=sorted(values,key=lambda r:(r['utc'],r.get('game_id','')))[-8:]
    mean=float(prior)
    if values:
        w=np.array([.87**(len(values)-i-1) for i in range(len(values))]);den=float(w.sum())
        blend=min(.42,max(0.,den/(12+den)))
        mean=(1-blend)*mean+blend*float(np.dot(w,[r['fp'] for r in values])/den)
    p=(old or {}).get('p_play')
    if not finite(p):p=min(.98,max(.5,float(player['availability_p1']))) if finite(player.get('availability_p1')) else .86
    return {'p_play':min(1.,max(0.,float(p))),'mean_if_play':mean,'expected_fp':min(1.,max(0.,float(p)))*mean}


def source_status(row):
    for value in ('Out','Doubtful','Questionable','Probable','Available'):
        if row.get('inj_'+value.lower())==1:return value
    if row.get('inj_unknown_identity')==1:return 'UNKNOWN_IDENTITY'
    if row.get('inj_not_listed')==1:return 'NOT_LISTED_IN_SUBMITTED_REPORT'
    return 'REPORT_NOT_AVAILABLE_AT_FEATURE_CUTOFF'


def bands(row,prefix=''):
    return {str(n):[float(row[f'{prefix}lo{n}']),float(row[f'{prefix}hi{n}'])] for n in (50,80,95)}


def windows_for_rows(rows,issued_at,schedule_complete=False):
    grouped={}
    for r in rows:
        if r['player_id']:grouped.setdefault(r['player_id'],[]).append(r)
    out=[];now=utc(issued_at)
    for pid,records in sorted(grouped.items()):
        for days in (7,14,21,28):
            rs=[r for r in records if now<=utc(r['game_utc'])<now+dt.timedelta(days=days)]
            valid=[r for r in rs if finite(r['expected_fp'])]
            all_complete=len(valid)==len(rs)
            out.append({'player_id':pid,'days':days,'scheduled_games':len(rs),'covered_games':len(valid),
                        'fallback_games':sum('fallback' in r['support'] for r in valid),'unavailable_games':len(rs)-len(valid),
                        'expected_fp':sum(r['expected_fp'] for r in valid) if all_complete else None,
                        'known_games_expected_fp':sum(r['expected_fp'] for r in valid),
                        'conditional_sum_if_all_play':sum(r['mean_if_play'] for r in valid) if all_complete else None,
                        'expected_games':sum(r['p_play'] for r in valid) if all_complete else None,
                        'effective_expected_fp':sum(r.get('effective_expected_fp',r['expected_fp']) for r in valid) if all_complete else None,
                        'effective_expected_games':sum(r.get('effective_p_play',r['p_play']) for r in valid) if all_complete else None,
                        'schedule_complete':bool(schedule_complete),'predictive_intervals':None,
                        'interval_reason':'Joint dependence across games has not been calibrated; endpoints must not be summed.',
                        'eligible_for_decision':all_complete and bool(schedule_complete) and all(r['eligible_for_decision'] for r in rs)})
    return out


def make_feed(frame,raw,source,source_qa,capture,snapshot,base,issued_at,bucket_report=None,site_gate=None,injury_snapshot=None):
    now=utc(issued_at);asof=now.astimezone(ET).date().isoformat()
    if not (frame.issue_date.astype(str)==asof).all():raise ValueError('FRAME_ISSUE_DATE_MISMATCH')
    if (pd.to_datetime(frame.date.astype(str))-pd.Timestamp(asof)).dt.days.ne(frame.horizon_days).any():raise ValueError('ACTUAL_HORIZON_MISMATCH')
    snapshot=Path(snapshot);live=read_json(snapshot/'live.json');schedule=read_json(snapshot/'schedule.json')
    identity=read_json(snapshot/'identity.json')['players'];catalog={p['id']:p for p in read_json(base)['players']}
    identity,identity_qa=apply_reviewed_identity(identity,catalog,issued_at,source_catalog_sha256=sha256((snapshot/'catalog.json').read_bytes()))
    public=schedule.get('games',live.get('schedule',[]))
    if len({g['id'] for g in public})!=len(public):raise ValueError('DUPLICATE_PUBLIC_SCHEDULE_ID')
    # Prefer status and exact timestamps in current live entries when schedule wrapper lags.
    live_map={g['id']:g for g in live.get('schedule',[])}
    public=[dict(g,**{k:v for k,v in live_map.get(g['id'],{}).items() if k in ('status','utc','epoch','et_date','msk_date')}) for g in public]
    schedule=dict(schedule,games=public)
    injury_data=read_json(injury_snapshot) if injury_snapshot else None
    # A newly fetched optional PDF cannot make old model-history inputs fresh.
    # Keep the core intake clock for its own freshness gate and expiry.
    fresh=check_freshness(source,source_qa,capture,schedule,live,issued_at,asof)
    fresh['reviewed_current_catalog_identity']=identity_qa
    latest_capture=utc(fresh['capture_completed_at_utc'])
    if injury_data:
        latest_capture=max(latest_capture,utc(injury_data['source_available_at_utc']))
    models={k:load_model(k) for k in ('near_latest','long_latest','day_ewma_shadow')}
    pred,valid,prepared=predict_current(frame.reset_index(drop=True),models['near_latest'],models['long_latest'])
    frame=frame.reset_index(drop=True)
    annotations,intraday_shadow,injury_qa={},{},{'status':'NO_FRESH_EXACT_OFFICIAL_ARTIFACT'}
    if injury_data:
        from injury_extension import apply_shadow
        annotations,intraday_shadow,injury_qa=apply_shadow(frame,models['near_latest'],injury_data,issued_at,public)
    joined=frame.copy()
    for c in pred:joined[c]=pred[c]
    joined['valid']=valid
    reverse={};ambiguous=set()
    for cid,info in identity.items():
        nba=info.get('nba_id')
        if not nba or info.get('confidence')!='high':continue
        nba=str(nba)
        if nba in reverse:ambiguous.add(nba)
        reverse[nba]=cid
    for nba in ambiguous:reverse.pop(nba,None)
    game_lookup={}
    for g in public:game_lookup.setdefault(schedule_key(g),[]).append(g)
    current_team={pid:p.get('team') for pid,p in catalog.items()}
    for r in sorted(live.get('rows',[]),key=lambda r:r.get('utc','')):
        if r.get('id') in catalog and r.get('team'):current_team[r['id']]=r['team']
    challenger={}
    near=frame.horizon_days==0
    if near.any():
        recency_path=ROOT/'research_extension/recency'
        sys.path.insert(0,str(recency_path))
        from features import build_recency_features
        target=prepared.loc[near].copy().reset_index(drop=True)
        # All targets are lead0; date==issue date. No future-history use is possible.
        extra=build_recency_features(target,raw)
        for c in extra:target[c]=extra[c]
        cb=models['day_ewma_shadow']
        cm=target.fp10.to_numpy()+cb['model'].predict(target[cb['features']])+cb['mean_bias']
        for i,mean in zip(frame.index[near],cm):challenger[i]=float(mean)
    rows=[];seen=set();unjoined=0
    for i,r in joined.iterrows():
        team,opp=str(r.team),str(r.opp);home=bool(r.home)
        matches=game_lookup.get((str(r.date),team if home else opp,opp if home else team),[])
        if len(matches)!=1:unjoined+=1;continue
        g=matches[0];tip=utc(g['utc'])
        if tip<now:continue
        cid=reverse.get(str(r.pid));lead=int(r.horizon_days)
        row={'player_id':cid,'nba_id':str(r.pid),'game_id':g['id'],'nba_game_id':str(r.game),
             'team':team,'opponent':opp,'home':home,'game_utc':iso(tip),'lock_utc':iso(tip-dt.timedelta(minutes=30)),
             'game_date_et':str(r.date),'game_date_msk':tip.astimezone(MSK).date().isoformat(),
             'actual_horizon_days':lead,'calibration_lead_days':calibration_bucket(lead),
             'history_n':int(r.history_n),'recent_minutes':float(r.min10),'injury_status_at_feature_cutoff':source_status(r),
             'warnings':[],'reasons':[],'challenger':None,
             'official_status':annotations.get(i),'intraday_shadow':intraday_shadow.get(i)}
        eligible=fresh['fresh'] and now<tip-dt.timedelta(minutes=30)
        identity_conflict=cid is not None and current_team.get(cid)!=team
        if identity_conflict:row['warnings'].append('CURRENT_TEAM_IDENTITY_CONFLICT');eligible=False
        if not r.valid:
            fallback=legacy_fallback(catalog.get(cid),g,live,issued_at)
            row.update(fallback or {'p_play':None,'mean_if_play':None,'expected_fp':None})
            row.update(model_id='legacy_seed_fallback' if fallback else 'unavailable',support='missing_features_fallback' if fallback else 'unavailable',
                       conditional_intervals=None,unconditional_intervals=None,interval_status='unavailable_fallback')
            row['warnings'].append('MODEL_INPUTS_INCOMPLETE')
            if cid in SEED_EXCLUSIONS:row['warnings'].append('HISTORICAL_SEED_IDENTITY_CONTAMINATION')
        else:
            row.update({c:float(r[c]) for c in ('p_play','mean_if_play','expected_fp')})
            row['model_id']='near_latest' if lead==0 else 'long_latest'
            exact=lead in SUPPORTED_LEADS
            audited=bool((bucket_report or {}).get('actual_horizons',{}).get(str(lead),{}).get('eligible'))
            row['support']='exact_lead' if exact else 'audited_lead_bucket' if audited else 'provisional_lead_bucket'
            row['interval_status']=('exact_saved_lead_limited_confirmation' if exact and lead in (21,28) else 'historically_calibrated_exact_lead') if exact else 'historically_audited_bucket' if audited else 'provisional_bucket_no_coverage_claim'
            row['conditional_intervals']=bands(r,'conditional_');row['unconditional_intervals']=bands(r)
            if not exact:row['warnings'].append('ACTUAL_DAY_USES_FROZEN_NEXT_LEAD_CALIBRATION')
            if not exact and not audited:row['warnings'].append('INTERVAL_COVERAGE_AT_THIS_DAY_NOT_VALIDATED')
            if lead>=21:row['warnings'].append('LONG_LEAD_HISTORICAL_CONFIRMATION_LIMITED')
            if i in challenger:
                mean=challenger[i];row['challenger']={'model_id':'day_ewma_shadow','mean_if_play':mean,'expected_fp':row['p_play']*mean,'selected_for_production':False}
        row['reasons']=[f"Последние игры: {row['recent_minutes']:.1f} мин в среднем; история {row['history_n']} выходов.",
                        injury_reason(row['injury_status_at_feature_cutoff']),
                        'Матч сегодня: отдельная near-game модель.' if lead==0 else f"Горизонт {lead} дн.; калибровка сохранённого lead {row['calibration_lead_days']} дн."]
        if not fresh['fresh']:row['warnings'].extend(fresh['failures'])
        if now>=tip-dt.timedelta(minutes=30):row['warnings'].append('T_MINUS_30_LOCK_PASSED')
        row['effective_p_play']=0. if row['official_status'] and row['official_status']['deterministic_out_overlay'] else row['p_play']
        row['effective_expected_fp']=0. if row['official_status'] and row['official_status']['deterministic_out_overlay'] else row['expected_fp']
        row['effective_unconditional_intervals']={str(n):[0.,0.] for n in (50,80,95)} if row['official_status'] and row['official_status']['deterministic_out_overlay'] else row['unconditional_intervals']
        if row['injury_status_at_feature_cutoff']=='Questionable' or (row['official_status'] or {}).get('status')=='questionable':
            row['warnings'].append('QUESTIONABLE_INTERVAL_COVERAGE_LIMITED')
        if row['official_status']:
            row['reasons'][1]=official_reason(row['official_status']['status'])
        row['eligible_for_decision']=bool(eligible and cid and row['model_id'] in ('near_latest','long_latest') and row['support']!='provisional_lead_bucket' and finite(row['expected_fp']))
        rows.append(row)
        if cid:seen.add((cid,g['id']))
    # Explicit catalog fallbacks make absent cold starts visible rather than silent omissions.
    for cid,player in catalog.items():
        team=current_team.get(cid)
        for g in public:
            tip=utc(g['utc']);day=schedule_key(g)[0];lead=(dt.date.fromisoformat(day)-dt.date.fromisoformat(asof)).days
            if team not in (g['home'],g['away']) or tip<now or not 0<=lead<=28 or (cid,g['id']) in seen:continue
            fallback=legacy_fallback(player,g,live,issued_at)
            nid=identity.get(cid,{}).get('nba_id');supported_identity=nid and str(nid) in reverse
            row={'player_id':cid,'nba_id':str(nid) if supported_identity else None,'game_id':g['id'],'nba_game_id':None,
                 'team':team,'opponent':g['away'] if team==g['home'] else g['home'],'home':team==g['home'],
                 'game_utc':iso(tip),'lock_utc':iso(tip-dt.timedelta(minutes=30)),'game_date_et':day,
                 'game_date_msk':tip.astimezone(MSK).date().isoformat(),'actual_horizon_days':lead,'calibration_lead_days':None,
                 'model_id':'legacy_seed_fallback' if fallback else 'unavailable',
                 'support':('cold_start_fallback' if supported_identity else 'identity_fallback') if fallback else 'unavailable',
                 'p_play':None,'mean_if_play':None,'expected_fp':None,'conditional_intervals':None,'unconditional_intervals':None,
                 'interval_status':'unavailable_fallback','history_n':None,'recent_minutes':None,
                 'injury_status_at_feature_cutoff':'UNKNOWN','challenger':None,'official_status':None,'intraday_shadow':None,
                 'reasons':['Нет поддержанного модельного ряда на этот матч.','Сохранён прежний прогноз сайта; диапазон модели недоступен.'],
                 'warnings':['UNVALIDATED_LEGACY_FALLBACK'],
                 'eligible_for_decision':False}
            if fallback:row.update(fallback)
            row['effective_p_play']=row['p_play'];row['effective_expected_fp']=row['expected_fp'];row['effective_unconditional_intervals']=None
            if cid in SEED_EXCLUSIONS:row['warnings'].append('HISTORICAL_SEED_IDENTITY_CONTAMINATION')
            if not fresh['fresh']:row['warnings'].extend(fresh['failures'])
            rows.append(row)
    rows.sort(key=lambda r:(r['game_utc'],r['game_id'],r['player_id'] or '~'+str(r['nba_id'])))
    manifest,model_sha=load_manifest()
    input_manifest={
        'current_archive_manifest':fresh['current_manifest_sha256'],
        'historical_source_manifest':sha256((Path(source)/'upstream_manifest.json').read_bytes()),
        'live_snapshot':sha256((snapshot/'live.json').read_bytes()),
        'UTC_schedule_snapshot':sha256((snapshot/'schedule.json').read_bytes()),
        'identity_snapshot':sha256((snapshot/'identity.json').read_bytes()),
        'catalog_identity_overlay':sha256(OVERLAY_PATH.read_bytes()),
        'catalog_identity_source':sha256((snapshot/'catalog.json').read_bytes()),
        'catalog_seed':sha256(Path(base).read_bytes()),
        'fresh_official_status':sha256(Path(injury_snapshot).read_bytes()) if injury_snapshot else None,
        'feature_builder_code':sha256((HERE/'feature_build.py').read_bytes()),
        'exporter_code':sha256(Path(__file__).read_bytes())}
    input_manifest_sha=sha256(json.dumps(input_manifest,sort_keys=True,separators=(',',':')).encode())
    # Site gate must be a concrete report from root's exact-deployed baseline review.
    site_default=verify_site_gate(site_gate)
    return {'schema_version':1,'kind':'nba_per_game_model_forecasts','issued_at_utc':iso(now),'asof_date_et':asof,
            'source_capture_completed_at_utc':iso(latest_capture),'core_source_capture_completed_at_utc':fresh['capture_completed_at_utc'],
            'source_manifest_sha256':input_manifest_sha,'input_manifest':input_manifest,
            'model_manifest_sha256':model_sha,'model_sha256':KNOWN_MODELS,
            'valid_until_utc':iso(min(now+dt.timedelta(hours=24),utc(fresh['capture_completed_at_utc'])+dt.timedelta(hours=36))),
            'status':'ready' if fresh['fresh'] else 'stale_inputs','source_quality':fresh,'fresh_official_status_qa':injury_qa,
            'fresh_official_snapshot_ready_at_utc':injury_data.get('minimum_inference_issue_after_utc') if injury_data else None,
            'fresh_official_status_sha256':sha256(Path(injury_snapshot).read_bytes()) if injury_snapshot else None,
            'model_policy':{'site_default':site_default,'forecast_inputs_for_advisory_comparisons':site_default,'economic_gain_proven':False,
                            'day_ewma_selected':False,'fit_current_season':False,'optimizer_policy_validated':False,
                            'intraday_injury_model_selected':False,'uncertainty':'per-game predictive intervals; no calibrated joint window intervals'},
            'coverage':{'rows':len(rows),'model_rows':sum(r['model_id'] in ('near_latest','long_latest') for r in rows),
                        'fallback_rows':sum(r['model_id']=='legacy_seed_fallback' for r in rows),'unavailable_rows':sum(r['model_id']=='unavailable' for r in rows),
                        'players_with_catalog_id':len({r['player_id'] for r in rows if r['player_id']}),'source_feature_rows':len(frame),
                        'feature_rows_without_exact_utc_game_join':unjoined,'calendar_complete':False},
            'rows':rows,'windows':windows_for_rows(rows,iso(now),schedule_complete=False)}



def verify_source_inputs(source):
    source=Path(source)
    for item in read_json(source/'current/manifest.json'):
        path=source/'current'/item['file']
        if item.get('status')!='retrieved' or not path.is_file() or sha256(path.read_bytes())!=item['sha256']:
            raise ValueError('CURRENT_SOURCE_HASH_MISMATCH')
    for item in read_json(source/'current/injury_conversion_manifest.json'):
        if sha256((source/'current'/item['source_file']).read_bytes())!=item['source_sha256'] or sha256((source/'current'/item['derived_file']).read_bytes())!=item['derived_sha256']:
            raise ValueError('INJURY_DERIVATION_HASH_MISMATCH')
    for item in read_json(HERE/'HISTORICAL_SOURCE_MANIFEST.json'):
        if sha256((source/'upstream'/item['file']).read_bytes())!=item['sha256']:
            raise ValueError('HISTORICAL_SOURCE_HASH_MISMATCH')


def finalize_issuance(feed,now):
    if now.astimezone(ET).date().isoformat()!=feed['asof_date_et']:raise ValueError('NBA_DATE_CHANGED_DURING_BUILD')
    feed['issued_at_utc']=iso(now)
    core_capture=feed.get('core_source_capture_completed_at_utc',feed['source_capture_completed_at_utc'])
    feed['valid_until_utc']=iso(min(now+dt.timedelta(hours=24),utc(core_capture)+dt.timedelta(hours=36)))
    feed['rows']=[r for r in feed['rows'] if utc(r['game_utc'])>=now]
    for row in feed['rows']:
        if now>=utc(row['lock_utc']):
            row['eligible_for_decision']=False
            if 'T_MINUS_30_LOCK_PASSED' not in row['warnings']:row['warnings'].append('T_MINUS_30_LOCK_PASSED')
    feed['windows']=windows_for_rows(feed['rows'],iso(now),False)
    feed['coverage']['rows']=len(feed['rows'])
    return feed



def injury_reason(status):
    return {'Out':'В отчёте на срезе признаков игрок исключён из матча.',
            'Doubtful':'На срезе признаков выход игрока маловероятен.',
            'Questionable':'На срезе признаков участие игрока под вопросом.',
            'Probable':'На срезе признаков участие вероятно.',
            'Available':'На срезе признаков игрок доступен.',
            'NOT_LISTED_IN_SUBMITTED_REPORT':'Игрок не указан в поданном отчёте; это не гарантия выхода.'}.get(status,
            'Свежего статуса на момент расчёта нет; вероятность основана на истории.')


def official_reason(status):
    return {'out':'Свежий официальный отчёт: игрок пропустит этот матч; итоговое ожидание равно нулю.',
            'doubtful':'Свежий официальный отчёт: выход маловероятен; базовая вероятность сохранена.',
            'questionable':'Свежий официальный отчёт: участие под вопросом; базовая вероятность сохранена.',
            'probable':'Свежий официальный отчёт: участие вероятно; базовая вероятность сохранена.',
            'available':'Свежий официальный отчёт: игрок доступен; выход не гарантирован.'}[status]



def verify_site_gate(gate):
    if not gate:return False
    if gate.get('site_default_gate_passed') is not True or gate.get('exact_deployed_default_replay') is not True:return False
    relative=Path(gate['baseline_replay_report'])
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('GATE_EVIDENCE_PATH_REJECTED')
    report=ROOT/relative
    if not report.is_file() or sha256(report.read_bytes())!=gate['baseline_replay_sha256']:
        raise ValueError('GATE_EVIDENCE_HASH_MISMATCH')
    if not gate.get('exact_runtime_state_includes_updatePlayerTeams'):raise ValueError('INCOMPLETE_RUNTIME_BASELINE_GATE')
    return True



def live_payload(full):
    feed=dict(full)
    # The complete scientific export is separately retained in the run artifact.
    rows=[]
    for source in full['rows']:
        if not source.get('player_id'):continue
        row={k:v for k,v in source.items() if k not in ('intraday_shadow','challenger')}
        if row.get('effective_unconditional_intervals')==row.get('unconditional_intervals'):
            row.pop('effective_unconditional_intervals',None)
        rows.append(row)
    feed['rows']=rows
    feed['coverage']=dict(full['coverage'],rows=len(rows),
                          model_rows=sum(r['model_id'] in ('near_latest','long_latest') for r in rows),
                          fallback_rows=sum(r['model_id']=='legacy_seed_fallback' for r in rows),
                          unavailable_rows=sum(r['model_id']=='unavailable' for r in rows),
                          full_research_population_rows=len(full['rows']),catalog_mapped_only=True)
    feed['model_policy']=dict(full['model_policy'],shadow_variants=['day_ewma_shadow','near_latest_intraday_injury_shadow'])
    return feed


def publish_live_feed(feed,path,now=None):
    """Replace a public feed only after readiness/expiry/serialization succeed."""
    now=now or dt.datetime.now(UTC)
    if feed.get('status')!='ready' or feed.get('source_quality',{}).get('fresh') is not True:
        raise ValueError('REFUSE_TO_PUBLISH_STALE_INPUTS')
    if utc(feed['valid_until_utc'])<=now or utc(feed['source_capture_completed_at_utc'])>now:
        raise ValueError('REFUSE_TO_PUBLISH_EXPIRED_OR_FUTURE_INPUTS')
    raw=json.dumps(feed,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()+b'\n'
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(prefix=path.name+'.',suffix='.tmp',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()
    return raw


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--source-qa',type=Path,required=True);p.add_argument('--snapshot-data',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--asof-date');p.add_argument('--out',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--bucket-report',type=Path);p.add_argument('--site-gate',type=Path);p.add_argument('--injury-snapshot',type=Path);a=p.parse_args()
    a.work.mkdir(parents=True,exist_ok=True)
    asof=a.asof_date or dt.datetime.now(UTC).astimezone(ET).date().isoformat()
    if asof!=dt.datetime.now(UTC).astimezone(ET).date().isoformat():raise ValueError('LIVE_EXPORT_REQUIRES_TODAYS_ASOF')
    verify_source_inputs(a.source)
    frame,raw,qa=build_current(a.source,asof)
    frame.to_pickle(a.work/'future_features.pkl')
    (a.work/'FEATURE_QA.json').write_text(json.dumps(qa,indent=2,default=int)+'\n')
    feed=make_feed(frame,raw,a.source,read_json(a.source_qa),read_json(a.capture),a.snapshot_data,a.base,iso(dt.datetime.now(UTC)),
                   read_json(a.bucket_report) if a.bucket_report else None,read_json(a.site_gate) if a.site_gate else None,a.injury_snapshot)
    finalize_issuance(feed,dt.datetime.now(UTC))
    research_raw=json.dumps(feed,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()+b'\n'
    (a.work/'full_research_forecasts.json').write_bytes(research_raw)
    feed=live_payload(feed)
    if (ROOT/'data/live.json').exists() and a.snapshot_data.resolve()==(ROOT/'data').resolve():
        from refresh_decision import fingerprint
        feed['refresh_fingerprint']=fingerprint(ROOT,utc(feed['issued_at_utc']))
    raw=json.dumps(feed,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()+b'\n'
    report={'feed_sha256':sha256(raw),'feed_bytes':len(raw),'coverage':feed['coverage'],'status':feed['status'],'source_quality':feed['source_quality']}
    (a.work/'EXPORT_REPORT.json').write_text(json.dumps(report,indent=2)+'\n')
    publish_live_feed(feed,a.out)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
