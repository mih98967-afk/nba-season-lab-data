"""Point-in-time day-level inputs for forecasts issued 0-28 days before a game."""
from __future__ import annotations
import bisect,collections,datetime as dt,gc,pathlib
import numpy as np
import pandas as pd
import run_phase1 as b
from availability import STATUSES, load_sources
LEADS=(0,1,3,7,14,21,28)
META={'pid','game','date','issue_date','season','team','opp','name','exante_member','y_play','y_fp','y_minutes'}

class InjurySnapshots:
    def __init__(self,root,games):
        self.data={};self.qa={};gmap={g['game']:g for g in games.to_dict('records')}
        for year in (2024,2025,2026):
            sc=pd.read_csv(root/'upstream'/f'nba_schedule_{year}.csv.gz',dtype=str,keep_default_na=False);teams={}
            for side in ('home','away'):teams.update(zip(sc[side+'_team_id'],sc[side+'_team_abbreviation']))
            r=pd.read_csv(root/'upstream'/f'injury_report_{year}.csv.gz',dtype=str,keep_default_na=False);total=len(r)
            r=r[r.game_id.isin(gmap)].copy();r['team_code']=r.team_id.map(teams);r['actual_date']=r.game_id.map(lambda x:gmap[x]['date'])
            r=r[(r.game_date==r.actual_date)&(r.report_datetime.str[:10]<r.actual_date)&r.team_code.notna()]
            r=r[[t in (gmap[g]['home'],gmap[g]['away']) for g,t in zip(r.game_id,r.team_code)]]
            n=0
            for (gid,team,stamp),part in r.groupby(['game_id','team_code','report_datetime'],sort=True):
                players={};bad=set();submitted=not part.reason.str.contains('NOT YET SUBMITTED',case=False,regex=False).any()
                for v in part[['person_id','current_status','match_method']].itertuples(index=False):
                    if not v.person_id:continue
                    if v.match_method not in ('exact','roster') or v.current_status not in STATUSES:bad.add(v.person_id);continue
                    if v.person_id in players and players[v.person_id]!=v.current_status:bad.add(v.person_id)
                    players[v.person_id]=v.current_status
                for pid in bad:players.pop(pid,None)
                rec=dict(stamp=stamp,submitted=bool(submitted),players=players,bad=bad)
                self.data.setdefault((gid,team),[]).append(rec);n+=1
            self.qa[str(year)]=dict(raw_rows=total,eligible_rows=len(r),snapshots=n)
            del r;gc.collect()
        self.times={k:[x['stamp'] for x in values] for k,values in self.data.items()}
    def before(self,game,team,issue_date):
        key=(game,team);times=self.times.get(key,[]);i=bisect.bisect_left(times,issue_date+' 00:00:00')-1
        return self.data[key][i] if i>=0 else None

def status_features(snapshot,pid,issue_date,prefix):
    submitted=bool(snapshot and snapshot['submitted']);status='missing'
    if submitted:status=snapshot['players'].get(pid,'unknown_identity' if pid in snapshot['bad'] else 'not_listed')
    age=(pd.Timestamp(issue_date)-pd.Timestamp(snapshot['stamp'])).total_seconds()/3600 if snapshot else 72.
    return {prefix+'present':int(bool(snapshot)),prefix+'submitted':int(submitted),prefix+'age_hours':min(72.,age),**{prefix+k.lower():int(status==k) for k in STATUSES},prefix+'not_listed':int(status=='not_listed'),prefix+'unknown_identity':int(status=='unknown_identity')}

class HistoryState:
    def __init__(self,games,raw):
        self.states=collections.defaultdict(b.state_new);self.teams=collections.defaultdict(list);self.elo=collections.defaultdict(lambda:1500.)
        self.rows={k:v.to_dict('records') for k,v in raw.groupby('game',sort=False)}
        self.days=[(d,g.to_dict('records')) for d,g in games.groupby('date',sort=True)];self.cursor=0;self.qa=collections.Counter()
    def advance_before(self,issue_date):
        while self.cursor<len(self.days) and self.days[self.cursor][0]<issue_date:
            daystr,gs=self.days[self.cursor];day=dt.date.fromisoformat(daystr).toordinal();pending=[]
            for g in gs:
                rs=self.rows.get(g['game'],[])
                # UNKNOWN opportunity coverage for each formerly observed team member.
                actual={r['pid']:r for r in rs}
                for pid,s in self.states.items():
                    if s['last_team'] in (g['home'],g['away']) and day-s['last_day']<=45:
                        rr=actual.get(pid);label=rr['played'] if rr and rr['team']==s['last_team'] else np.nan
                        pending.append(('op',pid,label))
                for r in rs:pending.append(('player',r,day))
                by={t:[r for r in rs if r['team']==t and r['played']==1] for t in (g['home'],g['away'])};valid=True
                for t,rows in by.items():
                    expected=g['home_pts'] if t==g['home'] else g['away_pts']
                    if abs(sum(r['pts'] for r in rows)-expected)>.01 or sum(r['minutes'] for r in rows)<235:valid=False
                if valid:
                    for t,opp in ((g['home'],g['away']),(g['away'],g['home'])):
                        rr=by[t];other=by[opp];poss=max(50.,(sum(r['fga']+.44*r['fta']-r['orb']+r['tov'] for r in rr)+sum(r['fga']+.44*r['fta']-r['orb']+r['tov'] for r in other))/2)
                        pts=g['home_pts'] if t==g['home'] else g['away_pts'];against=g['away_pts'] if t==g['home'] else g['home_pts']
                        pending.append(('team',t,dict(day=day,pts=pts,opp_pts=against,poss=poss,opp_fp=sum(r['fp'] for r in other),net=pts-against,ortg=100*pts/poss,drtg=100*against/poss)))
                else:self.qa['incomplete_team_game_skipped']+=1
                exp=1/(1+10**((self.elo[g['away']]-self.elo[g['home']]-60)/400));delta=20*(int(g['home_pts']>g['away_pts'])-exp)
                pending.extend([('elo',g['home'],delta),('elo',g['away'],-delta)])
            for typ,a,c in pending:
                if typ=='op':self.states[a]['opportunities'].append(c)
                elif typ=='elo':self.elo[a]+=c
                elif typ=='team':self.teams[a].append(c)
                else:
                    r=a;s=self.states[r['pid']]
                    if r['played']==1:
                        prior=b.player_features(s,day,r['team'])['fp10'];s['h2h'][r['opp']].append(r['fp']-prior);s['played'].append(dict(r,day=day))
                    if np.isfinite(r['played']):s['listed'].append(dict(r,day=day))
                    s['last_team']=r['team'];s['last_day']=day
            self.cursor+=1
    def team_features(self,team,day):
        h=self.teams[team];out={};defaults=dict(pts=112.,opp_pts=112.,poss=100.,opp_fp=145.,net=0.,ortg=112.,drtg=112.)
        for w in (10,25):
            q=h[-w:]
            for key,prior in defaults.items():out[f'{key}{w}']=(sum(r[key] for r in q)+5*prior)/(len(q)+5)
        out['days_rest']=min(14,day-h[-1]['day']-1) if h else 7;out['b2b']=int(out['days_rest']==0);out['games_last4']=sum(0<day-r['day']<=4 for r in h[-5:]);out['elo']=self.elo[team]
        return out

def compact_frame(rows):
    d=pd.DataFrame(rows)
    for c in d:
        if c not in META:d[c]=d[c].astype('float32')
    for c in ['y_play','y_fp','y_minutes']:d[c]=d[c].astype('float32')
    for c in ['pid','game','team','opp','name','date','issue_date']:d[c]=d[c].astype('category')
    return d

def build_horizons(root,output,leads=LEADS):
    games,raw,sourceqa=load_sources(root);inj=InjurySnapshots(root,games);state=HistoryState(games,raw)
    targets={g:rows.to_dict('records') for g,rows in raw.groupby('game',sort=False)}
    targetmap={g:{r['pid']:r for r in rows} for g,rows in targets.items()}
    club_games=collections.defaultdict(list);requests=collections.defaultdict(list)
    for g in games.to_dict('records'):
        day=dt.date.fromisoformat(g['date']).toordinal();g['day']=day
        for team in (g['home'],g['away']):club_games[team].append(g)
        for lead in leads:requests[(dt.date.fromordinal(day)-dt.timedelta(days=int(lead))).isoformat()].append((g,lead))
    club_days={t:[g['day'] for g in gs] for t,gs in club_games.items()};chunks=[];buffer=[];qa=collections.Counter();output.mkdir(parents=True,exist_ok=True)
    def flush():
        if not buffer:return
        p=output/f'features_{len(chunks):03d}.pkl';compact_frame(buffer).to_pickle(p);chunks.append(p);buffer.clear();gc.collect()
    for issue,req in sorted(requests.items()):
        state.advance_before(issue);day=dt.date.fromisoformat(issue).toordinal();players=collections.defaultdict(list);pcache={};tcache={};snapcache={};nextgame={}
        for pid,s in state.states.items():
            if day-s['last_day']<=45 and len(s['played'])>=5:players[s['last_team']].append(pid)
        for t,gs in club_games.items():
            ix=bisect.bisect_left(club_days[t],day);nextgame[t]=gs[ix]['game'] if ix<len(gs) else None
        for g,lead in req:
            for team,opp,h in ((g['home'],g['away'],1),(g['away'],g['home'],0)):
                if team not in players:continue
                for t in (team,opp):
                    if t not in tcache:tcache[t]=state.team_features(t,day)
                skey=(g['game'],team)
                if skey not in snapcache:snapcache[skey]=inj.before(g['game'],team,issue)
                nk=nextgame.get(team);nkey=(nk,team)
                if nkey not in snapcache:snapcache[nkey]=inj.before(nk,team,issue) if nk else None
                schedules={}
                for prefix,t in [('team',team),('opp',opp)]:
                    ds=club_days[t];targetidx=bisect.bisect_left(ds,g['day']);last=ds[targetidx-1] if targetidx else g['day']-8
                    schedules['target_'+prefix+'_rest']=min(14,g['day']-last-1);schedules['target_'+prefix+'_b2b']=int(g['day']-last==1)
                    schedules['target_'+prefix+'_games_before']=bisect.bisect_left(ds,g['day'])-bisect.bisect_left(ds,day)
                burden={}
                for pid in players[team]:
                    if pid not in pcache:pcache[pid]=b.player_features(state.states[pid],day,team)
                    ss=snapcache[nkey];burden[pid]=pcache[pid]['min10'] if ss and ss['submitted'] and ss['players'].get(pid)=='Out' else 0.
                total_out=sum(burden.values())
                for pid in sorted(players[team]):
                    s=state.states[pid];f=pcache[pid].copy();r=targetmap[g['game']].get(pid);match=bool(r and r['team']==team);label=r['played'] if match else np.nan
                    for prefix,t in [('team_',team),('opp_',opp)]:f.update({prefix+k:v for k,v in tcache[t].items()})
                    f.update(schedules);f['home']=h;f['rest_difference']=f['team_days_rest']-f['opp_days_rest'];f['win_probability_elo']=1/(1+10**((state.elo[opp]-state.elo[team]-(60 if h else -60))/400))
                    past=list(s['h2h'].get(opp,[]));f['h2h_n']=len(past);f['h2h_residual_shrunk']=sum(past)/(len(past)+8)
                    f['calendar_month']=int(g['date'][5:7]);f['horizon_days']=lead
                    f.update(status_features(snapcache[skey],pid,issue,'inj_'));f.update(status_features(snapcache[nkey],pid,issue,'health_'));f['health_teammate_out_minutes']=total_out-burden[pid]
                    buffer.append(dict(pid=pid,game=g['game'],date=g['date'],issue_date=issue,season=g['season'],team=team,opp=opp,name=s['listed'][-1]['name'] if s['listed'] else '',exante_member=1,y_play=label,y_fp=r['fp'] if match else np.nan,y_minutes=r['minutes'] if match and label==1 else 0 if label==0 else np.nan,**f))
                    qa[f'lead_{lead}_opportunities']+=1;qa[f'lead_{lead}_'+('known' if np.isfinite(label) else 'UNKNOWN')]+=1
                if len(buffer)>=18000:flush()
    flush();print('Feature chunks',len(chunks),dict(qa),flush=True)
    # Categories differ across chunks: align inexpensive ID/date objects during concat.
    frames=[]
    for p in chunks:
        frame=pd.read_pickle(p)
        for c in ['pid','game','team','opp','name','date','issue_date']:frame[c]=frame[c].astype(str)
        frames.append(frame)
    d=pd.concat(frames,ignore_index=True);del frames;gc.collect()
    for c in ['pid','game','team','opp','name','date','issue_date']:d[c]=d[c].astype('category')
    return d,dict(source_qa=sourceqa,injury_qa=inj.qa,forecast_qa=dict(qa),history_qa=dict(state.qa))

def horizon_masks(d):
    issue=d.issue_date.astype(str);target=d.date.astype(str)
    return dict(train=(d.season==2024),select=(d.season==2025)&(issue>='2024-10-01')&(issue<='2024-11-30')&(target<='2024-12-28'),pcal=(d.season==2025)&(issue>='2024-12-29')&(issue<='2025-01-10')&(target<='2025-02-07'),ical=(d.season==2025)&(issue>='2025-02-08')&(issue<='2025-02-21')&(target<='2025-03-21'),confirm=(d.season==2025)&(issue>='2025-03-22'),audit=(d.season==2026)&(issue>='2025-07-01'))
