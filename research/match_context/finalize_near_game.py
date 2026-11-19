"""Refit/calibrate the development-selected near-game participation challenger."""
import argparse,copy,hashlib,json,pathlib,pickle,time
import numpy as np,pandas as pd
from scipy.special import logit
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
import run_phase1 as b
from availability import mixture_quantiles

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase2',type=pathlib.Path,required=True);ap.add_argument('--challenge',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();a.output.mkdir(exist_ok=True);start=time.time()
    with (a.phase2/'research_models.pkl').open('rb') as f:bundle=pickle.load(f)
    with (a.challenge/'development_models.pkl').open('rb') as f:challengers=pickle.load(f)
    challenge=json.loads((a.challenge/'CHALLENGE_REPORT.json').read_text());d=pd.read_pickle(a.phase2/'feature_frame.pkl');d=d[(d.exante_member==1)&(d.history_n>=5)].reset_index(drop=True);m=b.masks(d);known=d.y_play.notna();cols=challengers['p_features'];winner=challenge['p_winner'];model=clone(challengers['p_models'][winner]);tr=(m['train']|m['select'])&known;model.fit(d.loc[tr,cols],d.loc[tr,'y_play']);raw=model.predict_proba(d[cols])[:,1];pc=m['pcal']&known;cal=LogisticRegression(C=100.,max_iter=500).fit(logit(np.clip(raw[pc],.001,.999)).reshape(-1,1),d.loc[pc,'y_play']);p=cal.predict_proba(logit(np.clip(raw,.001,.999)).reshape(-1,1))[:,1]
    mean=d.fp10.to_numpy()+np.mean([model.predict(d[bundle['feature_sets'][bundle['specs'][name][0]]]) for name,model in bundle['mean_models'].items()],axis=0)+bundle['mean_bias_correction'];efp=mean*p;levels=bundle['quantile_levels'];q=np.sort(np.column_stack([d.fp10.to_numpy()+bundle['quantile_models'][v].predict(d[bundle['quantile_features']]) for v in levels]),axis=1);mix=mixture_quantiles(q,levels,p,levels)
    report={'status':'research_only_not_deployed','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'fp_winner':challenge['fp_winner'],'participation_winner':winner,'selection_protocol_sha256':challenge['protocol_sha256'],'participation_metrics':{},'unconditional_fp':{},'intervals':{},'frozen_fp_module_unchanged':True}
    for split in ['confirm','audit']:
        mask=m[split]&known;report['participation_metrics'][split]=b.prob_metrics(d.loc[mask,'y_play'],p[mask]);report['unconditional_fp'][split]=b.reg_metrics(d.loc[mask,'y_fp'],efp[mask])
    offsets={}
    for alpha in [.5,.2,.05]:
        li=int(np.argmin(np.abs(np.array(levels)-alpha/2)));hi=int(np.argmin(np.abs(np.array(levels)-(1-alpha/2))));ci=m['ical']&known;o=b.conformal_offset(d.loc[ci,'y_fp'],mix[ci,li],mix[ci,hi],alpha);offsets[alpha]=o;key=str(1-alpha);report['intervals'][key]={}
        for split in ['confirm','audit']:
            mask=m[split]&known;report['intervals'][key][split]=b.interval_metrics(d.loc[mask,'y_fp'],mix[mask,li]-o,mix[mask,hi]+o,alpha)
    bundle.update(participation_model=model,participation_features=cols,participation_calibrator=cal,participation_winner=winner,mixture_offsets=offsets)
    with (a.output/'research_models.pkl').open('wb') as f:pickle.dump(bundle,f)
    report['model_sha256']=hashlib.sha256((a.output/'research_models.pkl').read_bytes()).hexdigest();report['runtime_seconds']=time.time()-start;report['limitations']=['Development selection reused historical audit; not pristine holdout','Conditional FP and quantile modules unchanged from phase2','Near-game day-level model only; not validated for 7-28 day issuance','No official Sports.ru credits or independent economic gain proof'];b.write_json(a.output/'MODEL_RESEARCH_REPORT.json',report);print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
