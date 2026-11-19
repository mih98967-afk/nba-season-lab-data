"""Bounded current official PDF capture and exact-ID mapper for daily Actions."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
from model_store import HERE,ROOT
from export_feed import utc,iso
from refresh_sources import fetch


def capture(snapshot_data,current,direct,out,code_root):
    snapshot_data,current,direct,out,code_root=map(Path,(snapshot_data,current,direct,out,code_root))
    out.mkdir(parents=True,exist_ok=True)
    inventory=json.loads((snapshot_data/'official_injury_snapshots.json').read_text())
    now=dt.datetime.now(dt.timezone.utc)
    candidates=[s for s in inventory.get('snapshots',[]) if s.get('report_at_utc') and utc(s['report_at_utc'])<=now]
    if not candidates:raise ValueError('NO_CURRENT_OFFICIAL_REPORT_INVENTORY')
    chosen=max(candidates,key=lambda s:utc(s['report_at_utc']))
    if now-utc(chosen['report_at_utc'])>dt.timedelta(hours=36):raise ValueError('OFFICIAL_REPORT_INVENTORY_STALE')
    url=chosen['url']
    if not re.fullmatch(r'https://ak-static\.cms\.nba\.com/referee/injury/Injury-Report_\d{4}-\d{2}-\d{2}_\d{2}_\d{2}(?:AM|PM)\.pdf',url):
        raise ValueError('OFFICIAL_PDF_URL_REJECTED')
    req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/free-reproducible-inference','Referer':'https://www.nba.com/'})
    with urllib.request.urlopen(req,timeout=35) as response:blob=response.read(8_000_001)
    if len(blob)>8_000_000 or not blob.startswith(b'%PDF'):raise ValueError('OFFICIAL_PDF_PAYLOAD_REJECTED')
    digest=hashlib.sha256(blob).hexdigest()
    if chosen.get('sha256') and chosen['sha256']!=digest:raise ValueError('OFFICIAL_PDF_INVENTORY_HASH_CHANGED')
    pdf=out/'latest_official.pdf';pdf.write_bytes(blob)
    meta={'url':url,'report_at_utc':chosen['report_at_utc'],'first_seen_at_utc':chosen.get('first_seen_at_utc') or iso(now),
          'retrieved_at_utc':iso(dt.datetime.now(dt.timezone.utc)),'sha256':digest,'bytes':len(blob)}
    metadata=out/'SOURCE.json';metadata.write_text(json.dumps(meta,indent=2)+'\n')
    official=direct/'scheduleLeagueV2_1.json'
    if not official.exists():
        direct.mkdir(parents=True,exist_ok=True)
        record=fetch('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json',official,14_000_000)
        (out/'OFFICIAL_CALENDAR_CAPTURE.json').write_text(json.dumps(record,indent=2)+'\n')
    output=out/'FRESH_OFFICIAL_NBA_STATUS.json'
    mapper=ROOT/'research_extension/prospective_20261118/injury_fix/export_fresh_status.py'
    env=dict(os.environ,NBA_CODE_ROOT=str(code_root.resolve()))
    subprocess.run([sys.executable,str(mapper),'--pdf',str(pdf),'--source-meta',str(metadata),'--current',str(current),
                    '--live',str(snapshot_data/'live.json'),'--identity',str(snapshot_data/'identity.json'),
                    '--official-schedule',str(official),'--output',str(output),'--parser-module',str(code_root/'src/official_injury_rows.py')],
                   check=True,env=env)
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot-data',type=Path,required=True);p.add_argument('--current',type=Path,required=True)
    p.add_argument('--direct',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--code-root',type=Path,default=ROOT)
    a=p.parse_args();print(capture(a.snapshot_data,a.current,a.direct,a.out,a.code_root))
