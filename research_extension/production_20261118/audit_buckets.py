"""Run the declared frozen-model intermediate-day audit; no training."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from feature_build import build_bucket_audit
from inference import SUPPORTED_LEADS,predict_long_actual,check_predictions
from model_store import load_model
import run_phase1 as metrics
from infer import predict_frame


def run(source,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    d,qa=build_bucket_audit(source)
    d.to_pickle(out/'bucket_audit_features.pkl')
    bundle=load_model('long_latest')
    p=predict_long_actual(bundle,d);check_predictions(p)
    anchor=d.horizon_days.isin(SUPPORTED_LEADS)
    exact=predict_frame(bundle,d.loc[anchor])
    numeric=['p_play','mean_if_play','expected_fp']+[f'{pr}{side}{n}' for pr in ('conditional_','') for n in (50,80,95) for side in ('lo','hi')]
    delta=float(np.max(np.abs(exact[numeric].to_numpy()-p.loc[anchor,numeric].to_numpy()))) if anchor.any() else None
    if delta is not None and delta>1e-10:raise ValueError('ANCHOR_INFERENCE_PARITY_FAILED')
    report={'protocol_sha256':hashlib.sha256(Path(__file__).with_name('BUCKET_PROTOCOL.md').read_bytes()).hexdigest(),
            'status':'EXPOSED_HISTORICAL_AUDIT_NO_FIT','current_season_targets_used':False,'anchor_max_absolute_delta':delta,
            'feature_frame_sha256':hashlib.sha256((out/'bucket_audit_features.pkl').read_bytes()).hexdigest(),
            'actual_horizons':{},'source_qa':qa}
    for lead in range(29):
        rows=d.horizon_days==lead;known=rows&d.y_play.notna();played=known&(d.y_play==1)
        n,k=int(known.sum()),int(played.sum())
        entry={'rows':int(rows.sum()),'known':n,'unknown':int((rows&d.y_play.isna()).sum()),'played':k,'eligible':False,
               'calibration_lead_days':next(v for v in SUPPORTED_LEADS if v>=lead),'exact_saved_lead':lead in SUPPORTED_LEADS}
        if n and k:
            entry['p_play']={'selected':metrics.prob_metrics(d.loc[known,'y_play'],p.loc[known,'p_play']),
                             'baseline':metrics.prob_metrics(d.loc[known,'y_play'],d.loc[known,'obs_play_rate25'])}
            entry['conditional_fp']={'selected':metrics.reg_metrics(d.loc[played,'y_fp'],p.loc[played,'mean_if_play']),
                                     'baseline':metrics.reg_metrics(d.loc[played,'y_fp'],d.loc[played,'fp10'])}
            entry['unconditional_fp']={'selected':metrics.reg_metrics(d.loc[known,'y_fp'],p.loc[known,'expected_fp']),
                                       'baseline':metrics.reg_metrics(d.loc[known,'y_fp'],d.loc[known,'fp10']*d.loc[known,'obs_play_rate25'])}
            checks=[n>=300,k>=150,entry['p_play']['selected']['brier']<=entry['p_play']['baseline']['brier']*1.01,
                    entry['unconditional_fp']['selected']['mae']<=entry['unconditional_fp']['baseline']['mae']*1.01]
            entry['intervals']={}
            for nominal in (50,80,95):
                entry['intervals'][str(nominal)]={}
                for kind,mask,prefix in [('conditional',played,'conditional_'),('unconditional',known,'')]:
                    v=metrics.interval_metrics(d.loc[mask,'y_fp'],p.loc[mask,f'{prefix}lo{nominal}'],p.loc[mask,f'{prefix}hi{nominal}'],1-nominal/100)
                    entry['intervals'][str(nominal)][kind]=v
                    checks.append(v['coverage']>=nominal/100-.05)
            entry['eligible']=bool(all(checks))
        report['actual_horizons'][str(lead)]=entry
    (out/'BUCKET_AUDIT_REPORT.json').write_text(json.dumps(metrics.clean(report),indent=2)+'\n')
    print(json.dumps({k:{q:v.get(q) for q in ('known','played','eligible','exact_saved_lead')} for k,v in report['actual_horizons'].items()},indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.source,a.out)
