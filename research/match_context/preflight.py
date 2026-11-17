"""Fail-closed audit of raw played-game stat lines and frozen source hashes."""
import argparse,hashlib,json,pathlib
import pandas as pd
import run_phase1 as b

def audit(root):
    manifest=json.loads((root/'upstream_manifest.json').read_text());out={'sources':[],'seasons':{},'status':'PASS'}
    for entry in manifest:
        if entry.get('status')!='retrieved':raise ValueError('MISSING_SOURCE: '+entry['url'])
        p=root/'upstream'/entry['file'];actual=hashlib.sha256(p.read_bytes()).hexdigest()
        if actual!=entry['sha256']:raise ValueError('SOURCE_HASH_MISMATCH: '+p.name)
        out['sources'].append({'file':p.name,'sha256':actual})
    for year in (2024,2025,2026):
        d=pd.read_csv(root/'upstream'/f'player_boxscores_{year}.csv',dtype=str,keep_default_na=False);d=d[d.game_id.str.startswith('002')].copy();d['minutes_value']=d.minutes.map(b.mins)
        p=d[d.minutes_value>0];n=p[list(b.STAT)].apply(pd.to_numeric,errors='coerce')
        if n.isna().any().any() or (n<0).any().any():raise ValueError('INVALID_PLAYED_STATS')
        if ((n.field_goals_made>n.field_goals_attempted)|(n.free_throws_made>n.free_throws_attempted)).any():raise ValueError('INVALID_SHOOTING_LINE')
        if d.duplicated(['game_id','person_id']).any():raise ValueError('DUPLICATE_PLAYER_GAME')
        out['seasons'][str(year)]={'positive_minute_rows':len(p),'missing_or_negative_required_values':0,'duplicate_player_games':0}
    return out
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();b.write_json(a.output,audit(a.source))
