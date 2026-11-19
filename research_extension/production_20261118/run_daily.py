"""Single free-Actions entry point: bounded intake, then frozen CPU inference."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo
from model_store import HERE,ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--snapshot-data',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--site-gate',type=Path)
    p.add_argument('--injury-snapshot',type=Path)
    a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
    asof=dt.datetime.now(dt.timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    subprocess.run([sys.executable,str(HERE/'refresh_sources.py'),'--work',str(a.work/'sources'),'--cache',str(a.cache),
                    '--snapshot-data',str(a.snapshot_data),'--asof-date',asof],check=True)
    derived=a.work/'sources/derived'
    cmd=[sys.executable,str(HERE/'export_feed.py'),'--source',str(derived/'source'),'--capture',str(derived/'CAPTURE_SUMMARY.json'),
         '--source-qa',str(derived/'SOURCE_QA.json'),'--snapshot-data',str(a.snapshot_data),'--base',str(a.base),
         '--asof-date',asof,'--out',str(a.out),'--work',str(a.work/'inference'),'--bucket-report',str(HERE/'BUCKET_ELIGIBILITY.json')]
    if a.site_gate:cmd+=['--site-gate',str(a.site_gate)]
    injury=a.injury_snapshot
    if injury is None:
        from capture_fresh_injury import capture
        try:
            injury=capture(a.snapshot_data,derived/'source/current',derived/'direct_nba',a.work/'official_injury',Path(os.environ.get('NBA_CODE_ROOT',ROOT)))
        except Exception as exc:
            # The unchanged base model does not depend on this optional intraday extension.
            (a.work/'OFFICIAL_EXTENSION_UNAVAILABLE.json').write_text(json.dumps({'status':'unavailable','reason':str(exc),'base_calibrated_model_unchanged':True},indent=2)+'\n')
    if injury:cmd+=['--injury-snapshot',str(injury)]
    subprocess.run(cmd,check=True)


if __name__=='__main__':main()
