"""Capture the existing project's licensed public sources, not private profiles."""
from __future__ import annotations
import argparse, hashlib, json, pathlib, urllib.request

BASE = 'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/'

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
    out=pathlib.Path(a.output); out.mkdir(parents=True,exist_ok=True)
    records=[]
    for year in (2024,2025,2026):
        for name in (f'nba_stats_player_boxscores/player_boxscores_{year}.csv', f'nba_stats_schedules/nba_schedule_{year}.csv.gz'):
            url=BASE+name; path=out/name.split('/')[-1]
            req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/research noncommercial'})
            with urllib.request.urlopen(req,timeout=90) as response:
                data=response.read(20000001)
            if len(data)>20000000: raise ValueError('SOURCE_TOO_LARGE')
            if len(data)<10000: raise ValueError('SOURCE_TOO_SMALL')
            path.write_bytes(data)
            records.append({'file':path.name,'source_url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            print(path.name,len(data),flush=True)
    (out/'manifest.json').write_text(json.dumps({'license':'CC BY 4.0 SportsDataverse; upstream NBA statistics','sources':records},indent=2)+'\n')
if __name__=='__main__': main()
