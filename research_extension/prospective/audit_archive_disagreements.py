"""Explain quarantined FP disagreements from raw observed boxscore components."""
import argparse,json
from pathlib import Path
import pandas as pd

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--research',type=Path,default=Path('research_extension/prospective'));ap.add_argument('--archive',type=Path,default=Path('research_extension/fresh_20261117/source/current/player_boxscores_2027.csv'));a=ap.parse_args();r=a.research
    report=json.loads((r/'results/ARCHIVE_AUGMENTED_REPORT.json').read_text());scored=json.loads((r/'results/scored_records.json').read_text());old={(v['nba_player_id'],v['nba_game_id']):v for v in scored if v['model_role']=='near_primary'}
    live=json.loads((r/'current_snapshot/data/live.json').read_text());li={(v['game_id'],v['id']):v for v in live['rows']};box=pd.read_csv(a.archive,dtype=str,keep_default_na=False)
    fields={'points':'pts','field_goals_made':'fgm','field_goals_attempted':'fga','free_throws_made':'ftm','free_throws_attempted':'fta','rebounds_total':'reb','assists':'ast','steals':'stl','blocks':'blk','turnovers':'tov','fouls_personal':'pf'};outputs=[]
    for x in report['conflicts_primary']:
        o=old[(x['nba_player_id'],x['nba_game_id'])];espn=li[(o['calendar_game_id'],o['catalog_id'])];matches=box[(box.person_id==x['nba_player_id'])&(box.game_id==x['nba_game_id'])]
        if len(matches)!=1:raise ValueError('AMBIGUOUS_SOURCE_ROW')
        nba=matches.iloc[0].to_dict();diff=[]
        for field,stat in fields.items():
            av=float(nba[field]);ev=float(espn['box'][stat]);weight=-2 if stat=='tov' else -1 if stat in ('fga','fta','pf') else 1
            if av!=ev:diff.append({'stat':stat,'ESPN':ev,'archive':av,'FP_component_delta':(av-ev)*weight})
        outputs.append({'player':x['player_name'],'nba_player_id':x['nba_player_id'],'nba_game_id':x['nba_game_id'],'ESPN_fp':x['espn_fp'],'archive_fp':x['archive_fp_before_quarantine'],'ESPN_minutes':espn['minutes'],'archive_minutes':nba['minutes'],'component_differences':diff,'summed_component_delta':sum(d['FP_component_delta'] for d in diff),'quarantined_for_FP_evaluation':True,'participation_agrees':True})
    (r/'results/FP_SOURCE_DISAGREEMENTS.json').write_text(json.dumps({'status':'source_disagreement_not_arbitrated','records':outputs},indent=2)+'\n')
if __name__=='__main__':main()
