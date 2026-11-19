"""Additional 2026/27 replay using frozen models, never fitting on its outcomes."""
from __future__ import annotations
import argparse,bisect,collections,datetime as dt,gc,hashlib,json,pathlib,time
import numpy as np,pandas as pd
import run_phase1 as b
from availability import load_sources,merge_inactive,STATUSES
from horizon_data import HistoryState,status_features,compact_frame,LEADS
from infer import load_verified,predict_frame
ASOF_DATE='2026-11-16'

def load_current_combined(root):
    games,raw,qa=load_sources(root);folder=root/'current';sc=pd.read_csv(folder/'nba_schedule_2027.csv.gz',dtype=str,keep_default_na=False);sc=sc[sc.game_id.str.startswith('002')].copy()
    if sc.game_id.duplicated().any():raise ValueError('DUPLICATE_CURRENT_SCHEDULE')
    gm={r.game_id:r for r in sc.itertuples(index=False)};future=[];finished=[]
    for g in gm.values():
        h=pd.to_numeric(g.home_pts,errors='coerce');a=pd.to_numeric(g.away_pts,errors='coerce');v=dict(game=g.game_id,season=2027,date=g.game_date[:10],home=g.home_team_abbreviation,away=g.away_team_abbreviation,home_pts=h,away_pts=a)
        future.append(v)
        if np.isfinite(h) and np.isfinite(a) and h!=a and g.game_date[:10]<ASOF_DATE:finished.append(v)
    finalids={g['game'] for g in finished};rows=[];box=pd.read_csv(folder/'player_boxscores_2027.csv',dtype=str,keep_default_na=False);box=box[box.game_id.isin(finalids)]
    if box.duplicated(['game_id','person_id']).any():raise ValueError('DUPLICATE_CURRENT_PLAYER_GAME')
    for r in box.to_dict('records'):
        g=gm[r['game_id']];team=r['team_tricode']
        if team not in (g.home_team_abbreviation,g.away_team_abbreviation):raise ValueError('CURRENT_TEAM_MISMATCH')
        home=team==g.home_team_abbreviation;m=b.mins(r['minutes']);label=b.participation(m,r['comment']);stats={v:float(r[k] or 0) for k,v in b.STAT.items()};fp=np.nan
        if label==1:
            if any(r[k]=='' for k in b.STAT) or any(v<0 for v in stats.values()):raise ValueError('MISSING_CURRENT_PLAYED_STATS')
            won=(float(g.home_pts)>float(g.away_pts))==home;fp=stats['pts']+stats['reb']+stats['ast']+stats['stl']+stats['blk']+stats['fgm']+stats['ftm']-stats['fga']-stats['fta']-stats['pf']-2*stats['tov']+(2 if m>=10 else 1)+((2 if home else 3) if won else (-3 if home else -2))
        elif label==0:fp=0.
        rows.append(dict(pid=r['person_id'],game=r['game_id'],season=2027,date=g.game_date[:10],team=team,opp=g.away_team_abbreviation if home else g.home_team_abbreviation,home=int(home),minutes=m,played=label,fp=fp,comment=r['comment'],position=r['position'],name=(r['first_name']+' '+r['family_name']).strip(),**stats))
    current=pd.DataFrame(rows);fg=pd.DataFrame(finished);ina=pd.read_csv(folder/'game_rosters_2027.csv',dtype=str,keep_default_na=False);current,jq=merge_inactive(fg,current,ina[ina.game_id.isin(finalids)])
    schedule=pd.concat([games,pd.DataFrame(future)],ignore_index=True).sort_values(['date','game']);games=pd.concat([games,fg],ignore_index=True).sort_values(['date','game']);raw=pd.concat([raw,current],ignore_index=True)
    qa['2027']={'finished_games_before_asof':len(finalids),'schedule_rows':len(sc),'earliest_date':fg.date.min(),'latest_finished_date':fg.date.max(),'positive_minute_rows':int((current.played==1).sum()),'explicit_no_play_rows':int((current.played==0).sum()),'unknown_rows':int(current.played.isna().sum()),'inactive_join':jq}
    return games,raw,qa,schedule

class CurrentSnapshots:
    def __init__(self,root,games):
        self.data={};self.qa={};gmap={g['game']:g for g in games.to_dict('records')};sc=pd.read_csv(root/'current/nba_schedule_2027.csv.gz',dtype=str,keep_default_na=False);teams={}
        for side in ('home','away'):teams.update(zip(sc[side+'_team_id'],sc[side+'_team_abbreviation']))
        r=pd.read_csv(root/'current/injury_report_2027.csv.gz',dtype=str,keep_default_na=False);total=len(r);r=r[r.game_id.isin(gmap)].copy();r['team_code']=r.team_id.map(teams);r['actual_date']=r.game_id.map(lambda v:gmap[v]['date']);r=r[(r.game_date==r.actual_date)&(r.report_datetime.str[:10]<r.actual_date)&r.team_code.notna()];r=r[[t in (gmap[g]['home'],gmap[g]['away']) for g,t in zip(r.game_id,r.team_code)]]
        for (gid,team,stamp),part in r.groupby(['game_id','team_code','report_datetime'],sort=True):
            players={};bad=set();submitted=not part.reason.str.contains('NOT YET SUBMITTED',case=False,regex=False).any()
            for v in part[['person_id','current_status','match_method']].itertuples(index=False):
                if not v.person_id:continue
                if v.match_method not in ('exact','roster') or v.current_status not in STATUSES:bad.add(v.person_id);continue
                if v.person_id in players and players[v.person_id]!=v.current_status:bad.add(v.person_id)
                players[v.person_id]=v.current_status
            for pid in bad:players.pop(pid,None)
            self.data.setdefault((gid,team),[]).append(dict(stamp=stamp,submitted=bool(submitted),players=players,bad=bad))
        self.times={k:[x['stamp'] for x in values] for k,values in self.data.items()};self.qa={'raw_rows':total,'accepted_rows':len(r),'team_games':len(self.data)}
    def before(self,game,team,issue_date):
        key=(game,team);times=self.times.get(key,[]);i=bisect.bisect_left(times,issue_date+' 00:00:00')-1
        return self.data[key][i] if i>=0 else None

def build_current_frame(root,output,leads=LEADS):
    games,raw,sourceqa,schedule=load_current_combined(root);inj=CurrentSnapshots(root,schedule);state=HistoryState(games,raw)
    targets={g:rows.to_dict('records') for g,rows in raw.groupby('game',sort=False)}
    targetmap={g:{r['pid']:r for r in rows} for g,rows in targets.items()}
    club_games=collections.defaultdict(list);requests=collections.defaultdict(list)
    for g in schedule.to_dict('records'):
        day=dt.date.fromisoformat(g['date']).toordinal();g['day']=day
        for team in (g['home'],g['away']):club_games[team].append(g)
        if g['season']==2027:
            if g['game'] in targetmap:
                for lead in leads:requests[(dt.date.fromordinal(day)-dt.timedelta(days=int(lead))).isoformat()].append((g,lead))
            else:
                lead=day-dt.date.fromisoformat(ASOF_DATE).toordinal()
                if lead in leads:requests[ASOF_DATE].append((g,lead))
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
                    s=state.states[pid];f=pcache[pid].copy();r=targetmap.get(g['game'],{}).get(pid);match=bool(r and r['team']==team);label=r['played'] if match else np.nan
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


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,required=True);ap.add_argument('--models',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=True);start=time.time();bundle,model_report=load_verified(a.models)
    d,qa=build_current_frame(a.source,a.output/'chunks');d.to_pickle(a.output/'feature_frame.pkl');pred=predict_frame(bundle,d);finished=d.date.astype(str)<ASOF_DATE;known=d.y_play.notna();report={'status':'current_season_replay_not_prospective','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'model_sha256':model_report['model_sha256'],'asof_date_ET':ASOF_DATE,'no_current_outcomes_used_for_fit':True,'qa':qa,'per_lead':{}}
    for lead in LEADS:
        allrows=finished&(d.horizon_days==lead);mask=allrows&known;played=mask&(d.y_play==1)
        if not mask.any():report['per_lead'][str(lead)]={'known':0,'status':'INSUFFICIENT_OBSERVATIONS'};continue
        basep=d.obs_play_rate25.to_numpy();p=pred.p_play.to_numpy();unknown=allrows&~known;gain=(((d.loc[mask,'y_play']-basep[mask])**2-(d.loc[mask,'y_play']-p[mask])**2).sum());g0=basep[unknown]**2-p[unknown]**2;g1=(1-basep[unknown])**2-(1-p[unknown])**2
        entry=dict(opportunities=int(allrows.sum()),known=int(mask.sum()),unknown=int(unknown.sum()),played=int(played.sum()),fp_conditional={'baseline_last10':b.reg_metrics(d.loc[played,'y_fp'],d.loc[played,'fp10']),'selected':b.reg_metrics(d.loc[played,'y_fp'],pred.loc[played,'mean_if_play'])},p_play={'history_baseline':b.prob_metrics(d.loc[mask,'y_play'],basep[mask]),'selected':b.prob_metrics(d.loc[mask,'y_play'],p[mask])},unconditional_fp={'history_baseline':b.reg_metrics(d.loc[mask,'y_fp'],d.loc[mask,'fp10']*basep[mask]),'selected':b.reg_metrics(d.loc[mask,'y_fp'],pred.loc[mask,'expected_fp'])},missing_label_brier_gain_lower=float((gain+np.minimum(g0,g1).sum())/allrows.sum()),intervals={})
        for nominal in (50,80,95):
            alpha=1-nominal/100;entry['intervals'][str(nominal)]={'conditional':b.interval_metrics(d.loc[played,'y_fp'],pred.loc[played,f'conditional_lo{nominal}'],pred.loc[played,f'conditional_hi{nominal}'],alpha),'unconditional':b.interval_metrics(d.loc[mask,'y_fp'],pred.loc[mask,f'lo{nominal}'],pred.loc[mask,f'hi{nominal}'],alpha)}
        report['per_lead'][str(lead)]=entry
    pred.to_csv(a.output/'predictions.csv.gz',index=False);preview=pred[~finished].copy();preview.to_csv(a.output/'RESEARCH_ONLY_preview.csv',index=False)
    report['preview_rows']=len(preview);report['limitations']=['Retrospective day-level replay, not issued-before-lock proof','Historical and current source vintages may include revisions','Only players with five prior appearances and recent observed team membership','Incomplete target schedule, no prices, no official Sports.ru credit reconciliation','No 28-day current validation if not enough elapsed season','Per-game intervals, not aggregate-week intervals','No deployment or optimizer adoption'];report['runtime_seconds']=time.time()-start;b.write_json(a.output/'CURRENT_SEASON_REPORT.json',report);print('CURRENT COMPLETE',report['per_lead'],flush=True)
if __name__=='__main__':main()
