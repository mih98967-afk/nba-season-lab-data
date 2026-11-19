"""Bounded, read-only current NBA final boxscores for the locked five-game cohort."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen
import datetime as dt, hashlib, json, re

HERE=Path(__file__).resolve().parent
OUT=HERE/'direct_nba'
OUT.mkdir(exist_ok=True)
NEW=json.loads((HERE.parent/'prospective_20261117/forecasts.json').read_text())
IDS=sorted({r['nba_game_id'] for r in NEW['records']})
if len(IDS)!=5 or any(not re.fullmatch(r'00226\d{5}',g) for g in IDS):raise ValueError('Unexpected bounded cohort')
URLS=[('scheduleLeagueV2_1.json','https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json')]+[(g+'.json','https://cdn.nba.com/static/json/liveData/boxscore/boxscore_'+g+'.json') for g in IDS]
if (OUT/'MANIFEST.json').exists():raise ValueError('Immutable direct source capture already exists')
def capture(item):
 name,url=item;start=dt.datetime.now(dt.timezone.utc).isoformat();limit=14_000_000 if name.startswith('schedule') else 5_000_000
 try:
  req=Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0','Referer':'https://www.nba.com/','Accept':'application/json'})
  with urlopen(req,timeout=23) as response:
   data=response.read(limit+1);headers=dict(response.headers.items())
  if len(data)>limit:raise ValueError('Source exceeds bounded limit')
  json.loads(data)
  path=OUT/name
  if path.exists():raise ValueError('Source path already exists')
  path.write_bytes(data)
  return {'file':name,'url':url,'started_at_utc':start,'fetched_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'retrieved','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'response_last_modified':headers.get('Last-Modified'),'response_etag':headers.get('ETag')}
 except Exception as e:return {'file':name,'url':url,'started_at_utc':start,'completed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'unavailable','error':type(e).__name__+': '+str(e)}
with ThreadPoolExecutor(max_workers=3) as pool:manifest=list(pool.map(capture,URLS))
(OUT/'MANIFEST.json').write_text(json.dumps({'captured_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':manifest,'fit_or_tuning_performed':False},indent=2)+'\n')
print(json.dumps(manifest,indent=2))
