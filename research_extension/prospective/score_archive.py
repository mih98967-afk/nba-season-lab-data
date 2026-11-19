"""Supplementary exact-NBA-ID outcome audit; original frozen/ESPN files unchanged."""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, json, math, os, re, sys
from pathlib import Path
import pandas as pd
from score_frozen import EXPECTED_SHA, load_frozen, unique_index, evaluate, prob_metrics, sha, utc

def archive_outcome(f, games, rows, now):
    out={'outcome_archive':'UNKNOWN','y_fp':None,'archive_reason':'missing_exact_player_game','source_comment':None}
    if utc(f['tipoff_utc'])>now:return {**out,'outcome_archive':'FUTURE','archive_reason':'future_tipoff'}
    g=games.get((f['nba_game_id'],))
    if not g:return {**out,'archive_reason':'game_not_final_in_archive'}
    if g['date']!=f['date_ET'] or {g['home'],g['away']}!={f['team'],f['opponent']}:
        return {**out,'archive_reason':'fixture_date_or_team_conflict'}
    r=rows.get((f['nba_game_id'],f['nba_player_id']))
    if not r:return out
    if r['team']!=f['team'] or r['opp']!=f['opponent'] or r['date']!=f['date_ET']:
        return {**out,'archive_reason':'player_team_or_date_conflict'}
    comment=str(r.get('comment',''));out['source_comment']=comment
    if r['played']==1 and r['minutes']>0 and math.isfinite(r['fp']):
        return {**out,'outcome_archive':'PLAYED','y_fp':float(r['fp']),'archive_reason':'positive_minutes_exact_NBA_ID'}
    if r['played']==0 and comment=='EXPLICIT_INACTIVE_LIST':
        return {**out,'outcome_archive':'OFFICIAL_INACTIVE','y_fp':0.,'archive_reason':'explicit_archive_inactive_list'}
    if r['played']==0 and re.match(r'^(DNP|DND|NWT)(?:\b|_|-)',comment.upper()):
        return {**out,'outcome_archive':'EXPLICIT_DNP','y_fp':0.,'archive_reason':'explicit_archive_nonplay_comment'}
    return {**out,'archive_reason':'unresolved_or_conflicting_archive_label'}

def quarantine_overlap(row, old):
    """Compare independently sourced known outcomes; never pick the nicer outcome."""
    result=dict(row);known={'PLAYED','EXPLICIT_DNP','OFFICIAL_INACTIVE'}
    result['participation_verified']=int(row['outcome_archive']=='PLAYED') if row['outcome_archive'] in known else None
    if old['outcome_espn'] not in known or row['outcome_archive'] not in known:
        result['espn_archive_overlap']='not_both_known';return result
    participation=(old['outcome_espn']=='PLAYED')==(row['outcome_archive']=='PLAYED')
    fp_agrees=math.isclose(float(old['y_fp']),float(row['y_fp']),rel_tol=0.,abs_tol=1e-9)
    if participation and fp_agrees:
        result['espn_archive_overlap']='exact_agreement';return result
    if not participation:result['participation_verified']=None
    result.update(espn_archive_overlap='CONFLICT',archive_outcome_before_quarantine=row['outcome_archive'],archive_fp_before_quarantine=row['y_fp'],espn_outcome=old['outcome_espn'],espn_fp=old['y_fp'],outcome_archive='UNKNOWN',y_fp=None,archive_reason='ESPN_archive_disagreement')
    return result

def participation_only(rows):
    completed=[r for r in rows if r['outcome_archive']!='FUTURE']
    known=[r for r in completed if r['participation_verified'] is not None]
    unknown=[r for r in completed if r['participation_verified'] is None]
    y=[r['participation_verified'] for r in known]
    gain=sum((r['baseline_p_play']-r['participation_verified'])**2-(r['p_play']-r['participation_verified'])**2 for r in known)
    tails=[[r['baseline_p_play']**2-r['p_play']**2,(1-r['baseline_p_play'])**2-(1-r['p_play'])**2] for r in unknown]
    return {'known':len(known),'played':sum(y),'explicit_nonplay':len(y)-sum(y),'UNKNOWN':len(unknown),
            'FP_conflicts_do_not_erase_confirmed_participation':True,
            'baseline_history':prob_metrics(y,[r['baseline_p_play'] for r in known]),
            'frozen_candidate':prob_metrics(y,[r['p_play'] for r in known]),
            'missing_label_paired_brier_gain_bounds':[(gain+sum(min(v) for v in tails))/len(completed),(gain+sum(max(v) for v in tails))/len(completed)] if completed else None,
            'bounds_are_partial_identification_not_confidence_interval':True}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=Path(os.environ.get('NBA_RESEARCH_BASE','research_base')));ap.add_argument('--source',type=Path,default=Path('research_extension/fresh_20261117/source'));ap.add_argument('--previous-results',type=Path,default=Path('research_extension/prospective/results/scored_records.json'));ap.add_argument('--output',type=Path,default=Path('research_extension/prospective/results'));a=ap.parse_args()
    now=dt.datetime.now(dt.timezone.utc);manifest=json.loads((a.source/'current/manifest.json').read_text())
    for item in manifest:
        p=a.source/'current'/item['file']
        if sha(p)!=item['sha256'] or p.stat().st_size!=item['bytes']:raise ValueError('SOURCE_HASH_MISMATCH:'+item['file'])
        if utc(item['fetched_at_utc'])>now:raise ValueError('SOURCE_CAPTURE_IN_FUTURE')
    frozen=load_frozen(a.base/'prospective_20261116/forecasts.json')
    code = a.base / 'research/match_context'
    if not (code / 'run_phase1.py').is_file():
        code = Path(__file__).resolve().parents[2] / 'research/match_context'
    sys.path.insert(0, str(code.resolve()))
    import current_validation
    current_validation.ASOF_DATE='2026-11-17'
    games,raw,qa,schedule=current_validation.load_current_combined(a.source)
    games=games[games.season==2027];raw=raw[raw.season==2027]
    gi=unique_index(games.to_dict('records'),['game']);ri=unique_index(raw.to_dict('records'),['game','pid'])
    old=json.loads(a.previous_results.read_text());oi=unique_index(old,['model_role','nba_player_id','nba_game_id','lead_days'])
    frame=pd.read_pickle(a.base/'results_current/feature_frame.pkl');frame=frame[frame.y_play.isna()&frame.y_fp.isna()]
    bi={(str(r.pid),str(r.game),int(r.horizon_days),str(r.issue_date)):r for r in frame.itertuples()}
    output=[]
    for f in frozen['records']:
        key=tuple(str(f[k]) for k in ['model_role','nba_player_id','nba_game_id','lead_days']);prev=oi[key]
        if any(prev[k]!=v for k,v in f.items()):raise ValueError('ORIGINAL_RECORD_CHANGED')
        b=bi[(f['nba_player_id'],f['nba_game_id'],f['lead_days'],f['feature_date_ET'])]
        if not (float(b.fp10)==prev['baseline_fp10'] and float(b.obs_play_rate25)==prev['baseline_p_play']):raise ValueError('BASELINE_CHANGED')
        row={**f,**archive_outcome(f,gi,ri,now),'baseline_fp10':float(b.fp10),'baseline_p_play':float(b.obs_play_rate25)}
        output.append(quarantine_overlap(row,prev))
    elapsed=[r for r in output if r['outcome_archive']!='FUTURE'];primary=[r for r in elapsed if r['model_role']=='near_primary']
    report={'schema':'nba-frozen-archive-supplement-evaluation-v1','evaluated_at_utc':now.isoformat(),'evaluation_only':True,'adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'official_Sports_ru_credits_proven':False,
            'source_kind':'NBA-derived SportsDataverse archives, retrieved after outcomes','same_primary_cohort_as_previous':True,'original_ESPN_report_unchanged':True,'forecast_sha256':EXPECTED_SHA,'baseline_sha256':sha(a.base/'results_current/feature_frame.pkl'),'previous_scored_data_sha256':sha(a.previous_results),'source_manifest_sha256':sha(a.source/'current/manifest.json'),'source_manifest':manifest,
            'game_time_evidence':'Exact NBA game ID, ET date and team pair checked. Archive has no UTC tipoff field; use original frozen tipoff and source-calendar crosswalk, not a reconstructed timing claim.',
            'elapsed_unique_player_games':len({(r['nba_player_id'],r['nba_game_id']) for r in elapsed}),'elapsed_games':len({r['nba_game_id'] for r in elapsed}),'elapsed_ET_dates':sorted({r['date_ET'] for r in elapsed}),
            'source_qa_2027':qa['2027'],'by_role':{},'source_overlap_primary':dict(collections.Counter(r['espn_archive_overlap'] for r in primary)),
            'conflicts_primary':[r for r in primary if r['espn_archive_overlap']=='CONFLICT'],
            'limitations':['One NBA date and 8 games remain an early diagnostic, not stable prospective proof','NBA-derived archives may incorporate postgame revisions and do not prove exact source vintage','Outcomes are not official Sports.ru credited FP; no owner transfer utility is tested','Conditional and unconditional metrics use their own explicit denominators','Missing/ambiguous/conflicting evidence stays UNKNOWN; no parameters were tuned']}
    for role in sorted({r['model_role'] for r in output}):
        rs=[r for r in output if r['model_role']==role];report['by_role'][role]=evaluate(rs,'outcome_archive');report['by_role'][role]['participation_independent_of_FP_reconciliation']=participation_only(rs);report['by_role'][role]['unknown_reasons']=dict(collections.Counter(r['archive_reason'] for r in rs if r['outcome_archive']=='UNKNOWN'))
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'ARCHIVE_AUGMENTED_REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    (a.output/'archive_augmented_scored_records.json').write_text(json.dumps(output,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({'counts':report['by_role']['near_primary']['counts'],'overlap':report['source_overlap_primary'],'conflicts':len(report['conflicts_primary']),'metrics':{k:report['by_role']['near_primary'][k] for k in ('conditional','participation','unconditional','missing_label_paired_brier_gain_bounds')}},indent=2))
if __name__=='__main__':main()
