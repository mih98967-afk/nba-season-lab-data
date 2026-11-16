"""Read-only source probe. Gamebook Inactive rows are outcomes, never pregame features."""
from __future__ import annotations
import csv, datetime as dt, gzip, hashlib, io, json, pathlib, urllib.request

def main(raw, output):
    raw=pathlib.Path(raw); out=pathlib.Path(output); out.mkdir(parents=True,exist_ok=True)
    urls=[f'https://statsdmz.nba.com/pdfs/{day}/{day}_{clubs}.pdf' for day,clubs in [('20261111','OKCPOR'),('20261112','CHAPHX'),('20261109','NOPGSW')]]
    for year in (2024,2025,2026):
        with gzip.open(raw/f'nba_schedule_{year}.csv.gz','rt') as f:
            games=list(csv.DictReader(f))
        games=[g for g in games if str(g['game_id']).zfill(10).startswith('002') and str(g['game_date']).startswith(str(year)+'-01')]
        for g in games[:2]:
            day=g['game_date'][:10].replace('-','')
            clubs=g['away_team_abbreviation']+g['home_team_abbreviation']
            urls.append(f'https://statsdmz.nba.com/pdfs/{day}/{day}_{clubs}.pdf')
    evidence=[]
    for url in urls:
        record={'source_url':url,'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'purpose':'postgame-label source feasibility, no label inferred'}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab noncommercial public-source research'})
            with urllib.request.urlopen(req,timeout=25) as r: data=r.read(5000001)
            if not data.startswith(b'%PDF') or len(data)>5000000: raise ValueError('NOT_BOUNDED_PDF')
            name=url.rsplit('/',1)[-1]; (out/name).write_bytes(data)
            record.update(status='DOWNLOADED_NOT_IDENTITY_VERIFIED',file=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        except Exception as e: record.update(status='UNAVAILABLE_NO_LABEL_INFERENCE',error=str(e)[:250])
        evidence.append(record); print(record['status'],url,flush=True)
    (out/'manifest.json').write_text(json.dumps({'records':evidence,'automatic_DNP_inference':False},indent=2)+'\n')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--raw',required=True);p.add_argument('--output',required=True);a=p.parse_args();main(a.raw,a.output)
