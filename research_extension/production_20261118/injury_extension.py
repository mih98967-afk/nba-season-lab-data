"""Current exact official status annotations and a named timing-shift shadow.

No base prediction is modified. The OUT overlay is a separate deterministic
public-status rule, not a recalibrated CatBoost probability.
"""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd
from model_store import add_research_path
add_research_path()
from infer_near import predict_near,near_features
from inference import check_predictions

STATUSES=('out','doubtful','questionable','probable','available')


def timestamp(value):
    stamp=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('NAIVE_OFFICIAL_STATUS_TIMESTAMP')
    return stamp.astimezone(dt.timezone.utc)


def apply_shadow(frame,bundle,artifact,issued_at,public_games):
    now=timestamp(issued_at)
    if artifact.get('schema')!='nba-fresh-official-pdf-exact-ID-status-v1' or not artifact.get('native_cells_complete'):
        raise ValueError('UNVERIFIED_OFFICIAL_STATUS_ARTIFACT')
    if timestamp(artifact['minimum_inference_issue_after_utc'])>now:raise ValueError('OFFICIAL_STATUS_NOT_YET_AVAILABLE')
    public={g['id']:g for g in public_games}
    data=frame.loc[frame.horizon_days==0].copy()
    if data.empty:return {},{}, {'status':'NO_NEAR_GAME_ROWS'}
    # Remove the old group totals so they are recomputed from the complete new team snapshot.
    data=data.drop(columns=[c for c in ('inj_teammate_out_fp','inj_teammate_out_minutes','inj_report_present','inj_team_submitted','inj_report_age_hours') if c in data])
    states={};events={};annotations={};updated=set()
    def valid_time(entry):
        available=timestamp(entry['available_at_utc']);published=timestamp(entry['report_at_utc'])
        return published<=available<=now and dt.timedelta(0)<=now-published<=dt.timedelta(hours=36)
    for state in artifact.get('team_report_states',[]):
        key=(str(state.get('nba_game_id')),state.get('team'))
        g=public.get(state.get('calendar_game_id'))
        if not g or not valid_time(state):continue
        if state.get('tipoff_utc')!=g['utc'] or state.get('home')!=g['home'] or state.get('away')!=g['away']:continue
        if key in states:raise ValueError('DUPLICATE_OFFICIAL_TEAM_GAME')
        states[key]=state
    for event in artifact.get('events',[]):
        if event.get('status') not in STATUSES or not valid_time(event):continue
        key=(str(event['nba_player_id']),str(event['nba_game_id']),event['team'])
        g=public.get(event.get('calendar_game_id'))
        if not g or event.get('tipoff_utc')!=g['utc'] or event.get('home')!=g['home'] or event.get('away')!=g['away']:continue
        if key in events:raise ValueError('DUPLICATE_OFFICIAL_PLAYER_GAME')
        events[key]=event
    for i,row in data.iterrows():
        key=(str(row.pid),str(row.game),str(row.team));state=states.get((str(row.game),str(row.team)))
        event=events.get(key)
        if not state or str(row.date)!=state.get('date_ET'):continue
        actual_home=str(row.team) if row.home else str(row.opp);actual_away=str(row.opp) if row.home else str(row.team)
        if actual_home!=state['home'] or actual_away!=state['away']:continue
        for status in (*STATUSES,'not_listed','unknown_identity'):data.loc[i,'inj_'+status]=0
        data.loc[i,'inj_present']=1
        submitted=not state.get('NOT_YET_SUBMITTED',False)
        data.loc[i,'inj_submitted']=int(submitted)
        data.loc[i,'inj_age_hours']=min(72.,(now-timestamp(state['report_at_utc'])).total_seconds()/3600)
        if event:
            data.loc[i,'inj_'+event['status']]=1
            annotations[i]={**{k:event[k] for k in ('nba_player_id','nba_game_id','calendar_game_id','team','home','away','tipoff_utc')},
                            'status':event['status'],'report_at_utc':event['report_at_utc'],
                            'available_at_utc':event['available_at_utc'],'source_url':event['source_url'],
                            'source_sha256':event['source_sha256'],'exact_player_team_game_time':True,
                            'deterministic_out_overlay':event['status']=='out'}
        elif submitted and state.get('allow_missing_player_as_NOT_LISTED_feature'):
            data.loc[i,'inj_not_listed']=1
        elif submitted:
            data.loc[i,'inj_unknown_identity']=1
        updated.add(i)
    enriched=near_features(data,complete_team_groups=True)
    predictions=predict_near(bundle,enriched)
    check_predictions(predictions)
    shadow={}
    for i in updated:
        p=predictions.loc[i]
        shadow[i]={'model_id':'near_latest_intraday_injury_shadow','timing_extension_not_validated':True,
                   'selected_for_production':False,'p_play':float(p.p_play),'mean_if_play':float(p.mean_if_play),
                   'expected_fp':float(p.expected_fp),
                   'conditional_intervals':{str(n):[float(p[f'conditional_lo{n}']),float(p[f'conditional_hi{n}'])] for n in (50,80,95)},
                   'unconditional_intervals':{str(n):[float(p[f'lo{n}']),float(p[f'hi{n}'])] for n in (50,80,95)}}
    return annotations,shadow,{'status':'ANNOTATION_PLUS_SEPARATE_SHADOW','near_feature_rows':len(data),
                              'updated_shadow_rows':len(shadow),'exact_explicit_annotations':len(annotations),
                              'deterministic_out_annotations':sum(a['status']=='out' for a in annotations.values()),
                              'base_model_changed':False,'historical_or_frozen_rows_changed':False,
                              'intraday_timing_calibrated':False}
