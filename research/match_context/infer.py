"""Read-only inference for the frozen multi-lead research bundle.

Load only a trusted locally generated bundle whose SHA256 matches its report.
Pickle files from arbitrary third parties must never be passed here.
"""
import hashlib,json,pathlib,pickle
import numpy as np
from scipy.special import logit
from availability import mixture_quantiles
import run_phase2 as t

def load_verified(directory):
    directory=pathlib.Path(directory);report=json.loads((directory/'MODEL_RESEARCH_REPORT.json').read_text());path=directory/'research_models.pkl'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=report['model_sha256']:raise ValueError('MODEL_HASH_MISMATCH')
    with path.open('rb') as f:bundle=pickle.load(f)
    return bundle,report

def predict_frame(bundle,frame):
    if frame.empty:return frame[['pid','game']].copy()
    leads=frame.horizon_days.to_numpy(dtype=int)
    if not set(leads)<=set(bundle['leads']):raise ValueError('UNVALIDATED_LEAD_TIME')
    fs=bundle['feature_sets'];winner=bundle['winner'];base=frame.fp10.to_numpy()
    if winner=='last10':mu=base.copy()
    elif winner=='fixed_v2':mu=t.fixed_v2(frame)
    else:mu=base+bundle['mean_model'].predict(frame[fs[bundle['specs'][winner][0]]])
    mu=mu+np.array([bundle['mean_bias'][int(h)] for h in leads])
    pw=bundle['participation_winner']
    if bundle['participation_model'] is not None:raw=bundle['participation_model'].predict_proba(frame[bundle['participation_features']])[:,1]
    elif pw=='constant_087':raw=np.full(len(frame),.87)
    elif pw=='explicit_rate':raw=frame.obs_play_rate25.to_numpy()
    else:raise ValueError('UNKNOWN_PPLAY_MODEL')
    p=np.zeros(len(frame))
    for lead in bundle['leads']:
        mask=leads==lead
        if mask.any():p[mask]=bundle['participation_calibrators'][lead].predict_proba(logit(np.clip(raw[mask],.001,.999)).reshape(-1,1))[:,1]
    qlevels=np.array(bundle['quantile_levels']);qs=np.sort(np.column_stack([base+bundle['quantile_models'][q].predict(frame[bundle['quantile_features']]) for q in qlevels]),axis=1);mix=mixture_quantiles(qs,qlevels,p,qlevels)
    out=frame[[c for c in ['pid','game','date','issue_date','season','team','opp','name','horizon_days','y_play','y_fp','min10','fp10','obs_play_rate25'] if c in frame]].copy()
    out['p_play']=p;out['mean_if_play']=mu;out['expected_fp']=p*mu
    for alpha in (.5,.2,.05):
        li=int(np.argmin(abs(qlevels-alpha/2)));hi=int(np.argmin(abs(qlevels-(1-alpha/2))));nominal=int((1-alpha)*100)
        conditional=np.array([bundle['conditional_offsets'][alpha][int(h)] for h in leads]);mixed=np.array([bundle['mixture_offsets'][alpha][int(h)] for h in leads])
        out[f'conditional_lo{nominal}']=qs[:,li]-conditional;out[f'conditional_hi{nominal}']=qs[:,hi]+conditional;out[f'lo{nominal}']=mix[:,li]-mixed;out[f'hi{nominal}']=mix[:,hi]+mixed
    return out
