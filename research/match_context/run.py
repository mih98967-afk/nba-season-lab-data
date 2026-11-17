#!/usr/bin/env python3
"""Isolated, date-as-of NBA mean/participation/distribution research. No live writes."""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, json, math, pathlib, pickle, re, time
import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, brier_score_loss, log_loss
from lightgbm import LGBMRegressor, LGBMClassifier
SEED=20261116
STAT={'points':'pts','field_goals_made':'fgm','field_goals_attempted':'fga','free_throws_made':'ftm','free_throws_attempted':'fta','rebounds_total':'reb','rebounds_offensive':'orb','assists':'ast','steals':'stl','blocks':'blk','turnovers':'tov','fouls_personal':'pf','three_pointers_attempted':'three_a'}
BASE_PARAMS=dict(n_estimators=240,learning_rate=.035,num_leaves=15,max_depth=-1,min_child_samples=100,reg_lambda=10.,colsample_bytree=1.,subsample=1.,n_jobs=2,verbosity=-1,random_state=SEED,deterministic=True,force_col_wise=True)
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,np.integer):return int(v)
    if isinstance(v,(np.floating,float)):return float(v) if math.isfinite(float(v)) else None
    if isinstance(v,np.bool_):return bool(v)
    if isinstance(v,np.ndarray):return clean(v.tolist())
    return v

def write_json(path,value):
    pathlib.Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def mins(value):
    if value is None or str(value).strip()=='':return 0.
    text=str(value)
    if ':' in text:
        m,s=text.split(':');return float(m)+float(s)/60
    return float(text)

def participation(minutes,comment):
    if minutes>0:return 1.
    if re.match(r'^(DNP|DND|NWT)(?:\b|_|-)',str(comment).upper()):return 0.
    return np.nan

def load_sources(root):
    games=[];rows=[];qa={}
    for year in (2024,2025,2026):
        sc=pd.read_csv(root/'upstream'/f'nba_schedule_{year}.csv.gz',dtype={'game_id':str})
        sc=sc[sc.game_id.str.startswith('002')].copy()
        assert sc.game_id.is_unique and len(sc)==1230,(year,len(sc))
        game_map={r.game_id:r for r in sc.itertuples(index=False)}
        box=pd.read_csv(root/'upstream'/f'player_boxscores_{year}.csv',dtype={'game_id':str,'person_id':str},keep_default_na=False)
        box=box[box.game_id.isin(game_map)].copy()
        assert not box.duplicated(['game_id','person_id']).any()
        counts=collections.Counter()
        for r in box.to_dict('records'):
            g=game_map[r['game_id']];team=r['team_tricode']
            assert team in (g.home_team_abbreviation,g.away_team_abbreviation)
            h=team==g.home_team_abbreviation;opp=g.away_team_abbreviation if h else g.home_team_abbreviation
            m=mins(r['minutes']);label=participation(m,r['comment'])
            stats={v:float(r[k] or 0) for k,v in STAT.items()};fp=np.nan
            if label==1:
                fp=(stats['pts']+stats['reb']+stats['ast']+stats['stl']+stats['blk']+stats['fgm']+stats['ftm']-stats['fga']-stats['fta']-stats['pf']-2*stats['tov'])
                won=(g.home_pts>g.away_pts)==h
                fp+=(2 if m>=10 else 1)+((2 if h else 3) if won else (-3 if h else -2))
            elif label==0:fp=0.
            counts['played' if label==1 else 'explicit_no_play' if label==0 else 'UNKNOWN']+=1
            rows.append(dict(pid=r['person_id'],game=r['game_id'],season=year,date=str(g.game_date)[:10],team=team,opp=opp,home=int(h),minutes=m,played=label,fp=fp,comment=r['comment'],position=r['position'],name=(r['first_name']+' '+r['family_name']).strip(),**stats))
        for g in sc.itertuples(index=False):
            games.append(dict(game=g.game_id,season=year,date=str(g.game_date)[:10],home=g.home_team_abbreviation,away=g.away_team_abbreviation,home_pts=float(g.home_pts),away_pts=float(g.away_pts)))
        qa[str(year)]=dict(counts,rows=len(box),games=len(sc),players=box.person_id.nunique())
    return pd.DataFrame(games).sort_values(['date','game']),pd.DataFrame(rows),qa

def state_new():
    return dict(played=collections.deque(maxlen=100),listed=collections.deque(maxlen=100),opportunities=collections.deque(maxlen=30),last_team=None,last_day=-10000,h2h=collections.defaultdict(lambda:collections.deque(maxlen=8)))

def mean(v,default=0.):return float(np.mean(v)) if len(v) else default

def player_features(s,day,team):
    h=list(s['played']);listed=list(s['listed']);out={}
    out['history_n']=len(h);out['days_since_play']=min(180,day-h[-1]['day']) if h else 180
    out['days_since_listed']=min(180,day-s['last_day']);out['same_club_history_n']=sum(r['team']==team for r in h)
    for w in (3,5,10,25):
        q=h[-w:];out[f'fp{w}']=mean([r['fp'] for r in q],12.);out[f'min{w}']=mean([r['minutes'] for r in q],20.)
    q=h[-10:]
    out['fp_sd10']=float(np.std([r['fp'] for r in q])) if len(q)>1 else 8.
    out['min_sd10']=float(np.std([r['minutes'] for r in q])) if len(q)>1 else 6.
    out['fp_med10']=float(np.median([r['fp'] for r in q])) if q else 12.
    for k in ['pts','reb','ast','stl','blk','tov','pf','fga','fta','three_a','fgm','ftm']:out[f'{k}10']=mean([r[k] for r in q])
    out['fp_per_min10']=sum(r['fp'] for r in q)/max(25.,sum(r['minutes'] for r in q))
    out['minutes_trend']=out['min5']-out['min25'];out['fp_trend']=out['fp5']-out['fp25']
    out['prior_start_rate']=mean([float(bool(r['position'])) for r in q])
    out['prior_position_C']=float(bool(q) and 'C' in str(q[-1]['position']))
    out['prior_position_G']=float(bool(q) and 'G' in str(q[-1]['position']))
    for w in (5,10,25):
        obs=listed[-w:];out[f'obs_play_rate{w}']=(sum(r['played'] for r in obs)+3*.87)/(len(obs)+3)
    out['last_observed_played']=listed[-1]['played'] if listed else .87
    out['last_prior_injury']=float(bool(listed) and ('injury' in listed[-1]['comment'].lower() or 'illness' in listed[-1]['comment'].lower()))
    out['recent_missed_explicit']=sum(r['played']==0 for r in listed[-5:])
    out['recent_label_coverage']=mean([float(np.isfinite(v)) for v in s['opportunities']],1.)
    return out

def build_frame(games,raw):
    states=collections.defaultdict(state_new);teams=collections.defaultdict(list);elo=collections.defaultdict(lambda:1500.)
    records=[];qa=collections.Counter();grouped={k:v.to_dict('records') for k,v in raw.groupby('game',sort=False)}
    defaults=dict(pts=112.,opp_pts=112.,poss=100.,opp_fp=145.,net=0.,ortg=112.,drtg=112.)
    def team_context(team,day):
        hist=teams[team];out={}
        for w in (10,25):
            q=hist[-w:]
            for key,prior in defaults.items():out[f'{key}{w}']=(sum(r[key] for r in q)+5*prior)/(len(q)+5)
        out['days_rest']=min(14,day-hist[-1]['day']-1) if hist else 7
        out['b2b']=int(out['days_rest']==0);out['games_last4']=sum(0<day-r['day']<=4 for r in hist[-5:]);out['elo']=elo[team]
        return out
    for datestr,day_games in games.groupby('date',sort=True):
        day=dt.date.fromisoformat(datestr).toordinal();p_cache={};t_cache={};pending=[]
        for g in day_games.to_dict('records'):
            rs=grouped.get(g['game'],[]);actual={r['pid']:r for r in rs}
            candidates={pid for pid,s in states.items() if s['last_team'] in (g['home'],g['away']) and day-s['last_day']<=45}
            for pid in sorted(candidates|set(actual)):
                s=states[pid];r=actual.get(pid);team=s['last_team'] if pid in candidates else (r['team'] if r else None)
                if team not in (g['home'],g['away']):continue
                h=int(team==g['home']);opp=g['away'] if h else g['home'];matched=bool(r and r['team']==team)
                label=r['played'] if matched else np.nan;key=(pid,team)
                if key not in p_cache:p_cache[key]=player_features(s,day,team)
                f=p_cache[key].copy()
                for t in (team,opp):
                    if t not in t_cache:t_cache[t]=team_context(t,day)
                for prefix,t in [('team_',team),('opp_',opp)]:f.update({prefix+k:v for k,v in t_cache[t].items()})
                f['home']=h;f['rest_difference']=f['team_days_rest']-f['opp_days_rest']
                f['win_probability_elo']=1/(1+10**((elo[opp]-elo[team]-(60 if h else -60))/400))
                past=list(s['h2h'].get(opp,[]));f['h2h_n']=len(past);f['h2h_residual_shrunk']=sum(past)/(len(past)+8)
                f['calendar_month']=int(datestr[5:7])
                records.append(dict(pid=pid,game=g['game'],date=datestr,season=g['season'],team=team,opp=opp,name=r['name'] if matched else '',exante_member=int(pid in candidates),y_play=label,y_fp=r['fp'] if matched else np.nan,y_minutes=r['minutes'] if matched and label==1 else 0 if label==0 else np.nan,**f))
                if pid in candidates:
                    qa['exante_opportunities']+=1;qa['known_labels' if np.isfinite(label) else 'UNKNOWN']+=1;pending.append(('op',pid,label))
            for r in rs:pending.append(('player',r,day))
            by={t:[r for r in rs if r['team']==t and r['played']==1] for t in (g['home'],g['away'])};valid=True
            for t,rr in by.items():
                expected=g['home_pts'] if t==g['home'] else g['away_pts']
                if abs(sum(r['pts'] for r in rr)-expected)>.01 or sum(r['minutes'] for r in rr)<235:valid=False
            if valid:
                for t,other in ((g['home'],g['away']),(g['away'],g['home'])):
                    rr=by[t];opp_rows=by[other]
                    ownposs=sum(r['fga']+.44*r['fta']-r['orb']+r['tov'] for r in rr);oppos=sum(r['fga']+.44*r['fta']-r['orb']+r['tov'] for r in opp_rows);poss=max(50.,(ownposs+oppos)/2)
                    pts=g['home_pts'] if t==g['home'] else g['away_pts'];opppts=g['away_pts'] if t==g['home'] else g['home_pts']
                    pending.append(('team',t,dict(day=day,pts=pts,opp_pts=opppts,poss=poss,opp_fp=sum(r['fp'] for r in opp_rows),net=pts-opppts,ortg=100*pts/poss,drtg=100*opppts/poss)))
            else:qa['incomplete_team_aggregates_skipped']+=1
            expected=1/(1+10**((elo[g['away']]-elo[g['home']]-60)/400));change=20*(int(g['home_pts']>g['away_pts'])-expected)
            pending.append(('elo',g['home'],change));pending.append(('elo',g['away'],-change))
        for typ,a,b in pending:
            if typ=='op':states[a]['opportunities'].append(b)
            elif typ=='elo':elo[a]+=b
            elif typ=='team':teams[a].append(b)
            else:
                r=a;s=states[r['pid']]
                if r['played']==1:
                    prior=player_features(s,day,r['team'])['fp10'];s['h2h'][r['opp']].append(r['fp']-prior);s['played'].append(dict(r,day=day))
                if np.isfinite(r['played']):s['listed'].append(dict(r,day=day))
                s['last_team']=r['team'];s['last_day']=day
    return pd.DataFrame(records),dict(qa)

def masks(d):
    return dict(train=d.season==2024,select=(d.season==2025)&(d.date<='2024-12-31'),pcal=(d.season==2025)&(d.date>='2025-01-01')&(d.date<='2025-01-23'),ical=(d.season==2025)&(d.date>='2025-01-24')&(d.date<='2025-02-15'),confirm=(d.season==2025)&(d.date>'2025-02-15'),audit=d.season==2026)

def reg_metrics(y,p):
    y=np.asarray(y);p=np.asarray(p)
    return dict(n=len(y),mae=mean_absolute_error(y,p),rmse=mean_squared_error(y,p)**.5,bias=float(np.mean(p-y)))

def prob_metrics(y,p):
    y=np.asarray(y);p=np.clip(np.asarray(p),.001,.999);bins=[]
    for l in np.linspace(0,.9,10):
        ix=(p>=l)&(p<l+.100001)
        if ix.sum():bins.append(dict(n=int(ix.sum()),prediction=float(p[ix].mean()),actual=float(y[ix].mean())))
    return dict(n=len(y),brier=brier_score_loss(y,p),logloss=log_loss(y,p,labels=[0,1]),observed_play_rate=float(y.mean()),mean_prediction=float(p.mean()),ece=sum(b['n']*abs(b['prediction']-b['actual']) for b in bins)/len(y),reliability=bins)

def cluster_gain(y,a,b,groups,loss='absolute'):
    delta=np.abs(y-a)-np.abs(y-b) if loss=='absolute' else (y-a)**2-(y-b)**2
    g=pd.DataFrame({'group':np.asarray(groups),'delta':np.asarray(delta)}).groupby('group').delta.agg(['sum','count']);rng=np.random.default_rng(SEED);v=g.to_numpy();out=[]
    for i in range(1000):
        z=v[rng.integers(0,len(v),len(v))];out.append(z[:,0].sum()/z[:,1].sum())
    return dict(point=float(np.mean(delta)),low=float(np.quantile(out,.025)),high=float(np.quantile(out,.975)),clusters=len(g))

def interval_metrics(y,lo,hi,alpha):
    y=np.asarray(y);lo=np.asarray(lo);hi=np.asarray(hi);score=hi-lo+2/alpha*np.maximum(lo-y,0)+2/alpha*np.maximum(y-hi,0)
    return dict(n=len(y),coverage=float(np.mean((y>=lo)&(y<=hi))),width=float(np.mean(hi-lo)),interval_score=float(score.mean()),below=float(np.mean(y<lo)),above=float(np.mean(y>hi)))

def conformal_offset(y,lo,hi,alpha):
    scores=np.maximum(np.asarray(lo)-np.asarray(y),np.asarray(y)-np.asarray(hi));q=min(1.,math.ceil((len(scores)+1)*(1-alpha))/len(scores))
    return max(0.,float(np.quantile(scores,q,method='higher')))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=pathlib.Path,required=True);parser.add_argument('--output',type=pathlib.Path,required=True);args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True);beg=time.time();cache=out/'feature_frame.pkl'
    games,raw,sourceqa=load_sources(args.source)
    if cache.exists():d=pd.read_pickle(cache);featureqa=json.loads((out/'feature_qa.json').read_text())
    else:d,featureqa=build_frame(games,raw);d.to_pickle(cache);write_json(out/'feature_qa.json',featureqa)
    meta={'pid','game','date','season','team','opp','name','exante_member','y_play','y_fp','y_minutes'};features=[c for c in d if c not in meta]
    context=[c for c in features if c.startswith(('team_','opp_','h2h_')) or c in ['home','rest_difference','win_probability_elo','calendar_month']];form=[c for c in features if c not in context]
    rest=form+['home','team_days_rest','team_b2b','team_games_last4','opp_days_rest','opp_b2b','rest_difference']
    fp=d[(d.y_play==1)&(d.exante_member==1)&(d.history_n>=5)].copy().reset_index(drop=True);m=masks(fp);y=fp.y_fp.to_numpy();preds={};models={};used={}
    preds['last10']=fp.fp10.to_numpy();preds['fixed_v2']=(.6*fp.fp10+.4*fp.fp25+np.clip(.25*(fp.min5-fp.min10)*fp.fp_per_min10.clip(0,1.5),-8,8)).clip(-5,80).to_numpy()
    print('FP cohort',len(fp),'features',len(features),'splits',{k:int(v.sum()) for k,v in m.items()},flush=True)
    specs=[('ridge_form',form,'ridge'),('ridge_context',features,'ridge'),('lgb_form',form,15),('lgb_rest',rest,15),('lgb_context',features,15),('lgb_context31',features,31)]
    for name,cols,typ in specs:
        model=make_pipeline(SimpleImputer(),StandardScaler(),Ridge(alpha=500.)) if typ=='ridge' else LGBMRegressor(**dict(BASE_PARAMS,num_leaves=typ))
        model.fit(fp.loc[m['train'],cols],y[m['train']]-preds['last10'][m['train']]);preds[name]=model.predict(fp[cols])+preds['last10'];models[name]=model;used[name]=cols
        print(name,reg_metrics(y[m['select']],preds[name][m['select']]),flush=True)
    preds['blend_form_context']=(preds['lgb_form']+preds['lgb_context'])/2
    metrics={k:{name:reg_metrics(y[mask],v[mask]) for name,v in preds.items()} for k,mask in m.items() if k!='train'};winner=min(preds,key=lambda n:metrics['select'][n]['rmse']);print('WINNER FROZEN',winner,flush=True)
    report=dict(status='research_only_not_deployed',adopt_on_site=False,source_qa=sourceqa,feature_qa=featureqa,fp_cohort=len(fp),features=features,form_features=form,fp_metrics=metrics,selected_by_development_rmse=winner,limitations=['Reused 2025/26 audit; not an untouched holdout','Date-as-of replay from final archives; not historical publication-time proof','NBA reconstructed FP, not official Sports.ru credits','Observed prior-club cohort, missing player-game labels stay UNKNOWN','No production promotion or economic transfer utility demonstrated'])
    for split in ['confirm','audit']:
        mask=m[split];ys=y[mask];a=preds['last10'][mask];b=preds[winner][mask]
        report[split+'_paired_gain']={key:cluster_gain(ys,a,b,fp.loc[mask,key]) for key in ['date','pid']}
        report[split+'_context_ablation']={key:cluster_gain(ys,preds['lgb_form'][mask],preds['lgb_context'][mask],fp.loc[mask,key]) for key in ['date','pid']}
    report['role_subgroups']={}
    for name,sub in {'under15':fp.min10<15,'15to28':(fp.min10>=15)&(fp.min10<28),'28plus':fp.min10>=28,'b2b':fp.team_b2b==1,'recent_return':fp.days_since_play>=7,'new_role':np.abs(fp.minutes_trend)>=5}.items():
        ix=m['audit']&sub
        if ix.sum():report['role_subgroups'][name]={k:reg_metrics(y[ix],preds[k][ix]) for k in ['last10',winner]}
    rankings={}
    for name,p in preds.items():
        a=fp.loc[m['audit'],['date','y_fp']].copy();a['pred']=p[m['audit']];g=a.groupby('date').apply(lambda x:x.nlargest(10,'pred').y_fp.sum(),include_groups=False);rankings[name]=dict(days=len(g),top10_actual_fp_per_day=float(g.mean()))
    report['ranking_descriptive_not_fantasy_backtest']=rankings
    pp=d[(d.exante_member==1)&(d.history_n>=5)].copy().reset_index(drop=True);pm=masks(pp);known=pp.y_play.notna();py=pp.y_play.to_numpy();pr={};pmodels={};pcols=form+['home','team_days_rest','team_b2b','team_games_last4','opp_b2b']
    pr['constant_087']=np.repeat(.87,len(pp));pr['explicit_rate']=pp.obs_play_rate25.to_numpy();train=pm['train']&known
    for name,model in [('logistic',make_pipeline(SimpleImputer(),StandardScaler(),LogisticRegression(C=.05,max_iter=1000))),('lgb',LGBMClassifier(**BASE_PARAMS))]:
        model.fit(pp.loc[train,pcols],py[train]);pr[name]=model.predict_proba(pp[pcols])[:,1];pmodels[name]=model
    raw_winner=min(pr,key=lambda n:brier_score_loss(py[pm['select']&known],pr[n][pm['select']&known]));pc=pm['pcal']&known
    calibrator=LogisticRegression(C=100.,max_iter=500).fit(logit(np.clip(pr[raw_winner][pc],.001,.999)).reshape(-1,1),py[pc]);pr['selected_sigmoid_calibrated']=calibrator.predict_proba(logit(np.clip(pr[raw_winner],.001,.999)).reshape(-1,1))[:,1]
    report['participation_selected_by_development_brier']=raw_winner;report['participation_metrics']={k:{n:prob_metrics(py[mask&known],v[mask&known]) for n,v in pr.items()} for k,mask in pm.items() if k not in ['train','pcal']}
    report['participation_coverage']={k:dict(opportunities=int(mask.sum()),known=int((mask&known).sum()),unknown=int((mask&~known).sum()),explicit_no_play=int((mask&known&(pp.y_play==0)).sum())) for k,mask in pm.items()}
    mask=pm['audit'];unk=mask&~known;kn=mask&known;bestp=pr['selected_sigmoid_calibrated'];bp=pr['constant_087'];known_diff=((py[kn]-bp[kn])**2-(py[kn]-bestp[kn])**2).sum();e0=bp[unk]**2-bestp[unk]**2;e1=(1-bp[unk])**2-(1-bestp[unk])**2
    report['participation_unknown_bounds']=dict(brier_gain_lower=float((known_diff+np.minimum(e0,e1).sum())/mask.sum()),brier_gain_upper=float((known_diff+np.maximum(e0,e1).sum())/mask.sum()),full_population_calibration_proven=False)
    qlevels=[.025,.1,.25,.5,.75,.9,.975];qp={};qmodels={};qcols=used.get(winner,features)
    if winner=='blend_form_context':qcols=features
    for q in qlevels:
        model=LGBMRegressor(**dict(BASE_PARAMS,objective='quantile',alpha=q));model.fit(fp.loc[m['train'],qcols],y[m['train']]-preds['last10'][m['train']]);qp[q]=model.predict(fp[qcols])+preds['last10'];qmodels[q]=model
    matrix=np.sort(np.column_stack([qp[q] for q in qlevels]),axis=1);qp={q:matrix[:,i] for i,q in enumerate(qlevels)};report['conditional_intervals']={};offsets={}
    for alpha in (.5,.2,.05):
        loq=alpha/2;hiq=1-alpha/2;lo=qp[min(qlevels,key=lambda q:abs(q-loq))];hi=qp[min(qlevels,key=lambda q:abs(q-hiq))];cal=m['pcal']|m['ical'];offset=conformal_offset(y[cal],lo[cal],hi[cal],alpha);offsets[alpha]=offset;baseline_width=float(np.quantile(np.abs(y[cal]-preds['last10'][cal]),1-alpha,method='higher'))
        report['conditional_intervals'][str(1-alpha)]=dict(calibration_n=int(cal.sum()),offset=offset,evaluations={split:{'quantile_raw':interval_metrics(y[mask],lo[mask],hi[mask],alpha),'quantile_calibrated':interval_metrics(y[mask],lo[mask]-offset,hi[mask]+offset,alpha),'baseline_symmetric':interval_metrics(y[mask],preds['last10'][mask]-baseline_width,preds['last10'][mask]+baseline_width,alpha)} for split,mask in m.items() if split in ['confirm','audit']})
        fp[f'lo{int((1-alpha)*100)}']=lo-offset;fp[f'hi{int((1-alpha)*100)}']=hi+offset
    if winner in ['last10','fixed_v2']:
        ppmean=pp.fp10.to_numpy() if winner=='last10' else (.6*pp.fp10+.4*pp.fp25+np.clip(.25*(pp.min5-pp.min10)*pp.fp_per_min10.clip(0,1.5),-8,8)).clip(-5,80).to_numpy()
    elif winner=='blend_form_context':ppmean=pp.fp10.to_numpy()+.5*(models['lgb_form'].predict(pp[form])+models['lgb_context'].predict(pp[features]))
    else:ppmean=pp.fp10.to_numpy()+models[winner].predict(pp[used[winner]])
    fullpred=bestp*ppmean;report['unconditional_verified_cohort']={k:dict(model=reg_metrics(pp.loc[mask&known,'y_fp'],fullpred[mask&known]),naive_all_play=reg_metrics(pp.loc[mask&known,'y_fp'],pp.loc[mask&known,'fp10']),availability_baseline=reg_metrics(pp.loc[mask&known,'y_fp'],pp.loc[mask&known,'fp10']*.87)) for k,mask in pm.items() if k in ['confirm','audit']}
    for name,p in preds.items():fp[name]=p
    fp[['pid','game','date','season','team','opp','home','y_fp','min10','team_b2b']+list(preds)+['lo50','hi50','lo80','hi80','lo95','hi95']].to_csv(out/'fp_audit_predictions.csv.gz',index=False)
    pp['p_play_selected']=bestp;pp['mean_fp_if_play']=ppmean;pp['expected_fp']=fullpred;pp[['pid','game','date','season','team','opp','y_play','y_fp','p_play_selected','mean_fp_if_play','expected_fp']].to_csv(out/'participation_predictions.csv.gz',index=False)
    report['runtime_seconds']=time.time()-beg;report['feature_frame_sha256']=hashlib.sha256(cache.read_bytes()).hexdigest();report['protocol_sha256']=hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL.md').read_bytes()).hexdigest();report['source_hashes']=json.loads((args.source/'upstream_manifest.json').read_text());write_json(out/'MODEL_RESEARCH_REPORT.json',report)
    with (out/'research_models.pkl').open('wb') as f:pickle.dump(dict(regression_models=models,features=used,winner=winner,quantile_models=qmodels,quantile_features=qcols,offsets=offsets,participation_models=pmodels,pfeatures=pcols,participation_raw_winner=raw_winner,participation_calibrator=calibrator),f)
    print('DONE',json.dumps(clean(dict(winner=winner,audit=metrics['audit'][winner],baseline=metrics['audit']['last10'],pplay=raw_winner,runtime=report['runtime_seconds']))),flush=True)
if __name__=='__main__':main()
