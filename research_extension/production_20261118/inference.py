"""Read-only frozen inference and explicit, separately audited lead adapters."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.special import logit
from model_store import add_research_path
add_research_path()
from availability import mixture_quantiles
from infer_near import near_features, predict_near
from infer import predict_frame
import run_phase2 as phase2

SUPPORTED_LEADS = (0,1,3,7,14,21,28)
PREDICTION_COLUMNS = ['p_play','mean_if_play','expected_fp'] + [f'{prefix}{side}{n}'
    for prefix in ('conditional_','') for n in (50,80,95) for side in ('lo','hi')]


def calibration_bucket(lead):
    if not np.isfinite(lead) or int(lead)!=lead or not 0<=lead<=28:
        raise ValueError('UNSUPPORTED_ACTUAL_HORIZON')
    return next(v for v in SUPPORTED_LEADS if v>=int(lead))


def required_features(bundle, near):
    if near:
        cols = {c for name in bundle['mean_models'] for c in bundle['feature_sets'][bundle['specs'][name][0]]}
    else:
        cols = set(bundle['feature_sets'][bundle['specs'][bundle['winner']][0]]) if bundle['winner'] not in ('last10','fixed_v2') else {'fp10','fp25','min5','min10','fp_per_min10'}
    return sorted(cols | set(bundle['participation_features']) | set(bundle['quantile_features']) | {'fp10'})


def valid_feature_rows(bundle, frame, near):
    cols = required_features(bundle,near)
    if set(cols)-set(frame.columns):return np.zeros(len(frame),dtype=bool)
    return np.isfinite(frame[cols].to_numpy(dtype=float)).all(axis=1)


def predict_long_actual(bundle,frame):
    """Actual day enters every tree; only saved calibration parameters use a bucket.

    This is identical to original inference at exact saved leads. Intermediate
    leads are explicitly provisional until the frozen historical audit passes.
    """
    if frame.empty:return frame.copy()
    actual = frame.horizon_days.to_numpy(dtype=float)
    buckets = np.array([calibration_bucket(v) for v in actual])
    fs,winner,base = bundle['feature_sets'],bundle['winner'],frame.fp10.to_numpy()
    if winner=='last10':mu=base.copy()
    elif winner=='fixed_v2':mu=phase2.fixed_v2(frame)
    else:mu=base+bundle['mean_model'].predict(frame[fs[bundle['specs'][winner][0]]])
    mu = mu + np.array([bundle['mean_bias'][int(h)] for h in buckets])
    if bundle['participation_model'] is not None:
        raw = bundle['participation_model'].predict_proba(frame[bundle['participation_features']])[:,1]
    elif bundle['participation_winner']=='constant_087':raw=np.full(len(frame),.87)
    elif bundle['participation_winner']=='explicit_rate':raw=frame.obs_play_rate25.to_numpy()
    else:raise ValueError('UNKNOWN_PARTICIPATION_MODEL')
    p = np.zeros(len(frame))
    for lead in SUPPORTED_LEADS:
        mask = buckets==lead
        if mask.any():p[mask]=bundle['participation_calibrators'][lead].predict_proba(logit(np.clip(raw[mask],.001,.999)).reshape(-1,1))[:,1]
    levels=np.array(bundle['quantile_levels'])
    qs=np.sort(np.column_stack([base+bundle['quantile_models'][q].predict(frame[bundle['quantile_features']]) for q in levels]),axis=1)
    if not np.isfinite(p).all() or not np.isfinite(qs).all():raise ValueError('NONFINITE_DISTRIBUTION')
    mix=mixture_quantiles(qs,levels,p,levels)
    out=pd.DataFrame(index=frame.index)
    out['p_play']=p;out['mean_if_play']=mu;out['expected_fp']=p*mu
    for alpha in (.5,.2,.05):
        lo=int(np.argmin(abs(levels-alpha/2)));hi=int(np.argmin(abs(levels-(1-alpha/2))));n=int((1-alpha)*100)
        co=np.array([bundle['conditional_offsets'][alpha][int(h)] for h in buckets])
        mo=np.array([bundle['mixture_offsets'][alpha][int(h)] for h in buckets])
        out[f'conditional_lo{n}']=qs[:,lo]-co;out[f'conditional_hi{n}']=qs[:,hi]+co
        out[f'lo{n}']=mix[:,lo]-mo;out[f'hi{n}']=mix[:,hi]+mo
    return out


def check_predictions(pred):
    if not np.isfinite(pred[PREDICTION_COLUMNS].to_numpy(float)).all():raise ValueError('NONFINITE_PREDICTION')
    if not pred.p_play.between(0,1).all():raise ValueError('INVALID_PARTICIPATION_PROBABILITY')
    if not np.allclose(pred.expected_fp,pred.p_play*pred.mean_if_play,atol=1e-10,rtol=1e-10):raise ValueError('EXPECTED_VALUE_CONTRACT_FAILED')
    for prefix in ('conditional_',''):
        for n in (50,80,95):
            if (pred[f'{prefix}lo{n}']>pred[f'{prefix}hi{n}']).any():raise ValueError('CROSSED_INTERVAL')
        if ((pred[f'{prefix}lo95']>pred[f'{prefix}lo80']) | (pred[f'{prefix}lo80']>pred[f'{prefix}lo50']) | (pred[f'{prefix}hi50']>pred[f'{prefix}hi80']) | (pred[f'{prefix}hi80']>pred[f'{prefix}hi95'])).any():raise ValueError('NON_NESTED_INTERVALS')
    return True


def predict_current(frame,near_bundle,long_bundle):
    if set(frame.columns)&{'y_play','y_fp','y_minutes'}:raise ValueError('TARGET_LABEL_COLUMNS_FORBIDDEN')
    if frame.duplicated(['pid','game','issue_date']).any():raise ValueError('DUPLICATE_FORECAST_CASE')
    prepared=frame.copy()
    near_mask=prepared.horizon_days==0
    # Complete team groups are constructed before any missing-row fallback filter.
    if near_mask.any():
        enriched=near_features(prepared.loc[near_mask],complete_team_groups=True)
        for c in enriched:
            if c not in prepared:prepared[c]=np.nan
            prepared.loc[near_mask,c]=enriched[c]
    output=pd.DataFrame(index=prepared.index,columns=PREDICTION_COLUMNS,dtype=float)
    valid=np.zeros(len(prepared),dtype=bool)
    for is_near,bundle in ((True,near_bundle),(False,long_bundle)):
        idx=prepared.index[near_mask if is_near else ~near_mask]
        if not len(idx):continue
        supported=valid_feature_rows(bundle,prepared.loc[idx],is_near)
        good=idx[supported]
        if not len(good):continue
        prediction=predict_near(bundle,prepared.loc[good]) if is_near else predict_long_actual(bundle,prepared.loc[good])
        check_predictions(prediction)
        output.loc[good,PREDICTION_COLUMNS]=prediction[PREDICTION_COLUMNS].to_numpy()
        valid[prepared.index.get_indexer(good)]=True
    return output,valid,prepared
