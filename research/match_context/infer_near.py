"""Read-only near-game inference; accepts the shared frozen feature contract."""
import numpy as np
from scipy.special import logit
from availability import mixture_quantiles

def near_features(frame,*,complete_team_groups=False):
    d=frame.copy()
    if 'horizon_days' in d and (d.horizon_days!=0).any():raise ValueError('NEAR_GAME_ONLY')
    for source,target in [('inj_present','inj_report_present'),('inj_submitted','inj_team_submitted'),('inj_age_hours','inj_report_age_hours')]:
        if target not in d and source in d:d[target]=d[source]
    if 'inj_teammate_out_fp' not in d:
        if not complete_team_groups:raise ValueError('COMPLETE_TEAM_CONTEXT_REQUIRED')
        groups=['issue_date','game','team'];d['_out_fp']=d.fp10*d.inj_out;d['_out_min']=d.min10*d.inj_out;d['inj_teammate_out_fp']=d.groupby(groups,observed=True)._out_fp.transform('sum')-d._out_fp;d['inj_teammate_out_minutes']=d.groupby(groups,observed=True)._out_min.transform('sum')-d._out_min;d=d.drop(columns=['_out_fp','_out_min'])
    return d

def conditional_offsets(bundle, frame, alpha):
    """Optional predeclared status calibration can widen, never narrow, a band."""
    baseline = float(bundle['conditional_offsets'][alpha])
    offsets = np.full(len(frame), baseline)
    for status, value in bundle.get('conditional_status_offsets', {}).get(alpha, {}).items():
        field = 'inj_' + status.lower()
        if field in frame:
            mask = frame[field].to_numpy() == 1
            offsets[mask] = np.maximum(offsets[mask], float(value))
    return offsets

def predict_near(bundle,frame,*,complete_team_groups=False):
    d=near_features(frame,complete_team_groups=complete_team_groups);base=d.fp10.to_numpy();mean=base+np.mean([model.predict(d[bundle['feature_sets'][bundle['specs'][name][0]]]) for name,model in bundle['mean_models'].items()],axis=0)+bundle['mean_bias_correction'];raw=bundle['participation_model'].predict_proba(d[bundle['participation_features']])[:,1];p=bundle['participation_calibrator'].predict_proba(logit(np.clip(raw,.001,.999)).reshape(-1,1))[:,1];levels=np.array(bundle['quantile_levels']);q=np.sort(np.column_stack([base+bundle['quantile_models'][v].predict(d[bundle['quantile_features']]) for v in levels]),axis=1);mix=mixture_quantiles(q,levels,p,levels)
    out=d[[c for c in ['pid','game','date','issue_date','season','team','opp','name','horizon_days','y_play','y_fp','min10','fp10','obs_play_rate25'] if c in d]].copy();out['p_play']=p;out['mean_if_play']=mean;out['expected_fp']=p*mean
    for alpha in [.5,.2,.05]:
        lo=int(np.argmin(abs(levels-alpha/2)));hi=int(np.argmin(abs(levels-(1-alpha/2))));n=int((1-alpha)*100);co=conditional_offsets(bundle,d,alpha);mo=bundle['mixture_offsets'][alpha];out[f'conditional_lo{n}']=q[:,lo]-co;out[f'conditional_hi{n}']=q[:,hi]+co;out[f'lo{n}']=mix[:,lo]-mo;out[f'hi{n}']=mix[:,hi]+mo
    return out
