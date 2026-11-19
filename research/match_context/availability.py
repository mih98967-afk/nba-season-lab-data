"""Exact inactive labels and conservative date-as-of published injury features."""
from __future__ import annotations
import collections
import numpy as np
import pandas as pd
import run_phase1 as base
STATUSES=('Out','Doubtful','Questionable','Probable','Available')

def merge_inactive(games,raw,inactive):
    """A missing row is never a negative. Quarantine positive/inactive conflict."""
    gm={g['game']:g for g in games.to_dict('records')}
    rows=raw.to_dict('records');idx={(r['game'],r['pid']):i for i,r in enumerate(rows)}
    qa=collections.Counter();seen=set()
    for r in inactive.to_dict('records'):
        gid=str(r['game_id']);pid=str(r['player_id']);team=r['team_abbreviation']
        if gid not in gm:continue
        g=gm[gid];key=(gid,pid)
        if key in seen:raise ValueError('DUPLICATE_INACTIVE_IDENTITY')
        seen.add(key)
        if team not in (g['home'],g['away']):raise ValueError('INACTIVE_TEAM_MISMATCH')
        if key in idx:
            old=rows[idx[key]]
            if old['team']!=team or old['played']==1:
                old['played']=np.nan;old['fp']=np.nan;old['comment']='SOURCE_CONFLICT';qa['quarantined_conflict']+=1
            elif old['played']==0:qa['duplicate_explicit_negative']+=1
            else:old['played']=0.;old['fp']=0.;old['comment']='EXPLICIT_INACTIVE_LIST';qa['unknown_resolved']+=1
            continue
        h=team==g['home'];row=dict(pid=pid,game=gid,season=g['season'],date=g['date'],team=team,opp=g['away'] if h else g['home'],home=int(h),minutes=0.,played=0.,fp=0.,comment='EXPLICIT_INACTIVE_LIST',position='',name=(str(r.get('first_name',''))+' '+str(r.get('last_name',''))).strip(),**{v:0. for v in base.STAT.values()})
        idx[key]=len(rows);rows.append(row);qa['new_explicit_inactive']+=1
    return pd.DataFrame(rows),dict(qa)

def load_sources(root):
    games,raw,qa=base.load_sources(root);inactive=[]
    for year in (2024,2025,2026):
        d=pd.read_csv(root/'upstream'/f'game_rosters_{year}.csv',dtype=str,keep_default_na=False)
        d=d[d.game_id.isin(games.loc[games.season==year,'game'])]
        qa[str(year)]['explicit_inactive_rows']=len(d);qa[str(year)]['inactive_games']=d.game_id.nunique();inactive.append(d)
    raw,joinqa=merge_inactive(games,raw,pd.concat(inactive,ignore_index=True));qa['inactive_join']=joinqa
    return games,raw,qa

def injury_index(root,games):
    game_map={g['game']:g for g in games.to_dict('records')};index={};qa={}
    for year in (2024,2025,2026):
        sc=pd.read_csv(root/'upstream'/f'nba_schedule_{year}.csv.gz',dtype=str,keep_default_na=False)
        teams={}
        for side in ('home','away'):
            for tid,t in zip(sc[side+'_team_id'],sc[side+'_team_abbreviation']):teams[str(tid)]=t
        r=pd.read_csv(root/'upstream'/f'injury_report_{year}.csv.gz',dtype=str,keep_default_na=False)
        counts=collections.Counter(raw_version_rows=len(r));r=r[r.game_id.isin(game_map)].copy()
        r['team_code']=r.team_id.map(teams);r['actual_date']=r.game_id.map(lambda v:game_map[v]['date'])
        valid=(r.game_date==r.actual_date)&(r.report_datetime.str[:10]<r.actual_date)&r.team_code.notna()
        r=r[valid].copy();counts['strictly_before_game_date_rows']=len(r)
        valid_team=[t in (game_map[g]['home'],game_map[g]['away']) for g,t in zip(r.game_id,r.team_code)]
        r=r[valid_team]
        # Resolve one snapshot of the whole team, not a stale per-player last mention.
        latest=r.groupby(['game_id','team_code']).report_datetime.transform('max')
        r=r[r.report_datetime==latest].drop_duplicates()
        for (gid,team),s in r.groupby(['game_id','team_code'],sort=False):
            issue=s.report_datetime.iloc[0];submitted=not s.reason.str.contains('NOT YET SUBMITTED',case=False,regex=False).any()
            pmap={};uncertain=set()
            for v in s.to_dict('records'):
                pid=v['person_id'];status=v['current_status'].strip()
                if not pid:continue
                if v['match_method'] not in ('exact','roster') or status not in STATUSES:
                    uncertain.add(pid);counts['excluded_weak_or_invalid_identity']+=1;continue
                if pid in pmap and pmap[pid]!=status:uncertain.add(pid)
                pmap[pid]=status
            for pid in uncertain:pmap.pop(pid,None)
            index[(gid,team)]=dict(issue=issue,submitted=bool(submitted),players=pmap,uncertain=uncertain)
            counts['team_snapshots']+=1;counts['submitted_team_snapshots']+=int(submitted)
        qa[str(year)]=dict(counts)
    return index,qa

def injury_features(frame,index):
    rows=[]
    for v in frame[['game','pid','team','date']].itertuples(index=False):
        s=index.get((v.game,v.team));submitted=bool(s and s['submitted']);status='unobserved'
        if submitted:status=s['players'].get(v.pid,'unknown_identity' if v.pid in s['uncertain'] else 'not_listed')
        age=(pd.Timestamp(v.date)-pd.Timestamp(s['issue'])).total_seconds()/3600 if s else 72.
        rows.append(dict(inj_report_present=int(bool(s)),inj_team_submitted=int(submitted),inj_report_age_hours=min(72.,age),**{'inj_'+k.lower():int(status==k) for k in STATUSES},inj_not_listed=int(status=='not_listed'),inj_unknown_identity=int(status=='unknown_identity')))
    a=frame.copy();extra=pd.DataFrame(rows,index=a.index);a=pd.concat([a,extra],axis=1)
    # Only previously observed members can contribute to teammate burden.
    eligible=(a.exante_member==1)&(a.history_n>=5)
    a['_out_minutes']=a.min10*a.inj_out*eligible;a['_out_fp']=a.fp10*a.inj_out*eligible
    a['inj_teammate_out_minutes']=a.groupby(['game','team'])._out_minutes.transform('sum')-a._out_minutes
    a['inj_teammate_out_fp']=a.groupby(['game','team'])._out_fp.transform('sum')-a._out_fp
    a=a.drop(columns=['_out_minutes','_out_fp']);return a

def mixture_quantiles(qvalues,levels,p_play,targets):
    """Quantiles of a point mass at zero plus an interpolated played distribution.
    Negative played FP are retained; zero is not necessarily the lowest outcome.
    """
    qvalues=np.sort(np.asarray(qvalues,float),axis=1);levels=np.asarray(levels,float);p_play=np.asarray(p_play,float)
    if np.any(~np.isfinite(qvalues)) or np.any((p_play<0)|(p_play>1)):raise ValueError('INVALID_DISTRIBUTION')
    result=np.zeros((len(p_play),len(targets)))
    for i,(xs,p) in enumerate(zip(qvalues,p_play)):
        if p==0:continue
        fzero=float(np.interp(0.,xs,levels,left=0.,right=1.))
        a=p*fzero;b=a+1-p
        for j,t in enumerate(targets):
            if t<a:u=t/p
            elif t<=b:result[i,j]=0.;continue
            else:u=(t-(1-p))/p
            result[i,j]=np.interp(np.clip(u,0,1),levels,xs)
    return result
