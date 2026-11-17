"""Recover report finalization after an empty far-horizon cohort; no model fitting."""
import argparse,hashlib,json,pathlib,pickle
import pandas as pd
import run_phase1 as b
from infer import predict_frame
from horizon_data import LEADS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--historical',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();old=json.loads((a.historical/'MODEL_RESEARCH_REPORT.json').read_text());path=a.output/'research_models.pkl'
    with path.open('rb') as f:bundle=pickle.load(f)
    d=pd.read_pickle(a.historical/'feature_frame.pkl');day=d.date.astype(str);issue=d.issue_date.astype(str);tr=day<'2025-12-29';pc=(issue>='2025-12-29')&(issue<='2026-01-10')&(day<='2026-02-07');ic=(issue>='2026-02-08')&(issue<='2026-02-21')&(day<='2026-03-21');cf=issue>='2026-03-22';m={'train':tr,'pcal':pc,'ical':ic,'confirm':cf};bounds={}
    for l,r in [('train','pcal'),('pcal','ical'),('ical','confirm')]:
        last=day[m[l]].max();first=issue[m[r]].min();assert last<first;bounds[l+'__'+r]={'last_target':last,'next_first_issue':first}
    report={'status':'refitted_current_candidate_not_deployed','adopt_on_site':False,'real_KEEP_TRANSFER_gain_proven':False,'family_source_model_sha256':old['model_sha256'],'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'no_2026_27_fit_or_calibration':True,'purged_boundaries':bounds,'training_rows':int(tr.sum()),'training_unique_player_games':int(d.loc[tr,['pid','game']].drop_duplicates().shape[0]),'protocol_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('PROTOCOL_FINAL_REFIT.md').read_bytes()).hexdigest(),'report_finalization_fix':'Skip empty 28-day post-calibration cohort. Saved weights unchanged; no refitting or tuning.','confirmation':{}}
    c=d[cf].copy();pred=predict_frame(bundle,c)
    for h in LEADS:
        ix=c.horizon_days==h;kn=ix&c.y_play.notna();pl=ix&(c.y_play==1)
        if not kn.any() or not pl.any():report['confirmation'][str(h)]={'status':'NO_POSTCALIBRATION_COHORT','known':int(kn.sum()),'played':int(pl.sum())};continue
        report['confirmation'][str(h)]={'fp':b.reg_metrics(c.loc[pl,'y_fp'],pred.loc[pl,'mean_if_play']),'baseline_fp':b.reg_metrics(c.loc[pl,'y_fp'],c.loc[pl,'fp10']),'p_play':b.prob_metrics(c.loc[kn,'y_play'],pred.loc[kn,'p_play']),'unconditional_fp':b.reg_metrics(c.loc[kn,'y_fp'],pred.loc[kn,'expected_fp']),'conditional80':b.interval_metrics(c.loc[pl,'y_fp'],pred.loc[pl,'conditional_lo80'],pred.loc[pl,'conditional_hi80'],.2),'unconditional80':b.interval_metrics(c.loc[kn,'y_fp'],pred.loc[kn,'lo80'],pred.loc[kn,'hi80'],.2)}
    b.write_json(a.output/'MODEL_RESEARCH_REPORT.json',report);print('REPORT RESTORED',report['model_sha256'],report['confirmation']['28'])
if __name__=='__main__':main()
