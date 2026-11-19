"""Future-only day-level features, preserving the frozen source/feature semantics.

A single advance to the issue date avoids rebuilding retrospective current-season
rows on every daily run. The historical audit mode is separate and opt-in.
"""
from __future__ import annotations
import bisect
import collections
import datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
from model_store import add_research_path
add_research_path()
import run_phase1 as original
from availability import load_sources
from horizon_data import HistoryState, InjurySnapshots, status_features, compact_frame
import current_validation as cv


def rows_for_requests(games, raw, schedule, snapshots, requests, *, labels=False):
    state = HistoryState(games, raw)
    targets = {str(g): {str(r['pid']): r for r in part.to_dict('records')}
               for g, part in raw.groupby('game', sort=False)} if labels else {}
    club_games = collections.defaultdict(list)
    for row in schedule.to_dict('records'):
        g = dict(row, day=dt.date.fromisoformat(str(row['date'])).toordinal())
        for team in (g['home'], g['away']):club_games[team].append(g)
    for team in club_games:club_games[team].sort(key=lambda g:(g['day'],g['game']))
    club_days = {t:[g['day'] for g in gs] for t,gs in club_games.items()}
    result = []
    for issue, req in sorted(requests.items()):
        state.advance_before(issue)
        day = dt.date.fromisoformat(issue).toordinal()
        players = collections.defaultdict(list)
        pcache, tcache, snapcache, nextgame = {}, {}, {}, {}
        for pid, s in state.states.items():
            if day-s['last_day'] <= 45 and len(s['played']) >= 5:
                players[s['last_team']].append(pid)
        for t, gs in club_games.items():
            ix = bisect.bisect_left(club_days[t], day)
            nextgame[t] = gs[ix]['game'] if ix < len(gs) else None
        for g, lead in sorted(req, key=lambda v:(v[0]['date'],v[0]['game'],v[1])):
            target_day = dt.date.fromisoformat(g['date']).toordinal()
            for team, opp, home in ((g['home'],g['away'],1),(g['away'],g['home'],0)):
                if team not in players:continue
                for t in (team,opp):
                    if t not in tcache:tcache[t] = state.team_features(t,day)
                skey = (g['game'],team)
                if skey not in snapcache:snapcache[skey] = snapshots.before(g['game'],team,issue)
                nk = nextgame.get(team);nkey = (nk,team)
                if nkey not in snapcache:snapcache[nkey] = snapshots.before(nk,team,issue) if nk else None
                schedules = {}
                for prefix,t in [('team',team),('opp',opp)]:
                    ds = club_days[t];ix = bisect.bisect_left(ds,target_day)
                    last = ds[ix-1] if ix else target_day-8
                    schedules['target_'+prefix+'_rest'] = min(14,target_day-last-1)
                    schedules['target_'+prefix+'_b2b'] = int(target_day-last==1)
                    schedules['target_'+prefix+'_games_before'] = ix-bisect.bisect_left(ds,day)
                burden = {}
                for pid in players[team]:
                    if pid not in pcache:pcache[pid] = original.player_features(state.states[pid],day,team)
                    ss = snapcache[nkey]
                    burden[pid] = pcache[pid]['min10'] if ss and ss['submitted'] and ss['players'].get(pid)=='Out' else 0.
                total_out = sum(burden.values())
                for pid in sorted(players[team]):
                    s = state.states[pid];f = pcache[pid].copy()
                    for prefix,t in [('team_',team),('opp_',opp)]:f.update({prefix+k:v for k,v in tcache[t].items()})
                    f.update(schedules);f['home'] = home
                    f['rest_difference'] = f['team_days_rest']-f['opp_days_rest']
                    f['win_probability_elo'] = 1/(1+10**((state.elo[opp]-state.elo[team]-(60 if home else -60))/400))
                    past = list(s['h2h'].get(opp,[]));f['h2h_n'] = len(past);f['h2h_residual_shrunk'] = sum(past)/(len(past)+8)
                    f['calendar_month'] = int(g['date'][5:7]);f['horizon_days'] = int(lead)
                    f.update(status_features(snapcache[skey],pid,issue,'inj_'))
                    f.update(status_features(snapcache[nkey],pid,issue,'health_'))
                    f['health_teammate_out_minutes'] = total_out-burden[pid]
                    row = dict(pid=pid,game=g['game'],date=g['date'],issue_date=issue,season=g['season'],
                               team=team,opp=opp,name=s['listed'][-1]['name'] if s['listed'] else '',exante_member=1,
                               y_play=np.nan,y_fp=np.nan,y_minutes=np.nan,**f)
                    if labels:
                        target = targets.get(str(g['game']),{}).get(str(pid))
                        if target and target['team']==team:
                            row.update(y_play=target['played'],y_fp=target['fp'],
                                       y_minutes=target['minutes'] if target['played']==1 else 0 if target['played']==0 else np.nan)
                    result.append(row)
    d = compact_frame(result) if result else pd.DataFrame()
    return d, dict(state.qa)


def build_current(source, asof_date, max_lead=28):
    cv.ASOF_DATE = str(asof_date)
    games, raw, qa, schedule = cv.load_current_combined(Path(source))
    if not (games.date.astype(str)<asof_date).all():raise ValueError('CURRENT_HISTORY_AFTER_CUTOFF')
    snapshots = cv.CurrentSnapshots(Path(source), schedule)
    day = dt.date.fromisoformat(asof_date)
    request = []
    for g in schedule.to_dict('records'):
        lead = (dt.date.fromisoformat(g['date'])-day).days
        if g['season']==2027 and 0<=lead<=max_lead:request.append((g,lead))
    d,hqa = rows_for_requests(games,raw,schedule,snapshots,{asof_date:request})
    if d.empty:raise ValueError('NO_CURRENT_FUTURE_FEATURES')
    if d[['y_play','y_fp','y_minutes']].notna().any().any():raise ValueError('FUTURE_OUTCOME_PRESENT')
    d = d.drop(columns=['y_play','y_fp','y_minutes'])
    return d,raw,dict(source_qa=qa,injury_qa=snapshots.qa,history_qa=hqa,
                     labels_removed=True,issue_date=asof_date,leads=list(range(max_lead+1)))


def build_bucket_audit(source, issue_start='2026-03-22'):
    games,raw,qa = load_sources(Path(source))
    if games.season.max()>2026:raise ValueError('CURRENT_SEASON_AUDIT_FORBIDDEN')
    snapshots = InjurySnapshots(Path(source),games)
    requests = collections.defaultdict(list)
    for g in games.to_dict('records'):
        if g['season']!=2026:continue
        for lead in range(29):
            issue = (dt.date.fromisoformat(g['date'])-dt.timedelta(days=lead)).isoformat()
            if issue>=issue_start:requests[issue].append((g,lead))
    d,hqa = rows_for_requests(games,raw,games,snapshots,requests,labels=True)
    return d,dict(source_qa=qa,injury_qa=snapshots.qa,history_qa=hqa)
