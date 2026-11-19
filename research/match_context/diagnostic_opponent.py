"""Post-selection diagnostic, never used to retune the selected research model."""
import argparse,pathlib,pickle
import pandas as pd
import run_phase1 as b
import run_phase2 as t

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--results',type=pathlib.Path,required=True);a=ap.parse_args();d=pd.read_pickle(a.results/'feature_frame.pkl');d=d[(d.exante_member==1)&(d.history_n>=5)&(d.y_play==1)].reset_index(drop=True)
    fs=t.feature_sets(d);mask=b.masks(d);y=d.y_fp.to_numpy();base=d.fp10.to_numpy();full=fs['context'];opp=[c for c in full if c.startswith(('opp_','h2h_')) or c in ('rest_difference','win_probability_elo')];noopp=[c for c in full if c not in opp];no_h2h=[c for c in full if not c.startswith('h2h_')]
    report={'status':'diagnostic_only_no_reselection','removed_opponent_related_features':opp,'models':{},'paired_gain':{}}
    pred={}
    for name,cols in [('no_opponent',noopp),('full_context',full),('no_head_to_head',no_h2h)]:
        m=t.regression('ridge');m.fit(d.loc[mask['train'],cols],y[mask['train']]-base[mask['train']]);pred[name]=base+m.predict(d[cols]);report['models'][name]={split:b.reg_metrics(y[mask[split]],pred[name][mask[split]]) for split in ('select','confirm','audit')}
    for first,second in [('no_opponent','full_context'),('no_head_to_head','full_context')]:
        k=first+'__'+second;report['paired_gain'][k]={}
        for split in ('select','confirm','audit'):
            ix=mask[split];report['paired_gain'][k][split]={'cluster_by_date':b.cluster_gain(y[ix],pred[first][ix],pred[second][ix],d.loc[ix,'date']),'cluster_by_player':b.cluster_gain(y[ix],pred[first][ix],pred[second][ix],d.loc[ix,'pid'])}
    b.write_json(a.results/'OPPONENT_DIAGNOSTIC.json',report);print(report['models']);print(report['paired_gain'])
if __name__=='__main__':main()
