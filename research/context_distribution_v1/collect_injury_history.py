"""Bounded dated NBA injury reports. Pregame statuses are FEATURES, never outcomes."""
from __future__ import annotations
import argparse,concurrent.futures,datetime as dt,gzip,hashlib,io,json,pathlib,re,sys,time,urllib.request
from zoneinfo import ZoneInfo
import pandas as pd
import fitz


def collect(root,raw,current_raw,output,seconds=480):
 root=pathlib.Path(root);out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(root))
 from src.official_injury_rows import parse_pages,validate_extracted_status_rows
 dates=set()
 for directory in [pathlib.Path(raw),pathlib.Path(current_raw)]:
  for path in directory.glob('nba_schedule_*.csv.gz'):
   s=pd.read_csv(path,dtype={'game_id':str});s=s[s.game_id.str.zfill(10).str.startswith('002')&(s.home_pts>0)&(s.away_pts>0)]
   dates.update(str(d)[:10] for d in s.game_date)
 start=time.monotonic();records=[];counts={}
 class NativePage:
  def __init__(self,page):self.page=page
  def extract_words(self,**kwargs):
   return [{'x0':w[0],'top':w[1],'text':w[4]} for w in self.page.get_text('words')]
 def fetch(day):
  suffix='11_00AM' if day>='2025-10-01' else '11AM'
  url=f'https://ak-static.cms.nba.com/referee/injury/Injury-Report_{day}_{suffix}.pdf'
  r={'requested_date':day,'url':url,'first_retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
  if time.monotonic()-start>seconds:return r,None,'TIME_BUDGET'
  time.sleep(.15)
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab noncommercial public-source research'})
   with urllib.request.urlopen(req,timeout=12) as response:data=response.read(3000001)
   if not data.startswith(b'%PDF') or len(data)>3000000:raise ValueError('INVALID_BOUNDED_PDF')
   r.update(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data));return r,data,None
  except Exception as e:return r,None,str(e)[:200]
 with gzip.open(out/'dated_injury_reports.jsonl.gz','wt',encoding='utf8') as dest,concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for i,(r,data,error) in enumerate(pool.map(fetch,sorted(dates))):
   if error:r.update(status='UNAVAILABLE_NO_HEALTH_INFERENCE',error=error)
   else:
    try:
     with fitz.open(stream=data,filetype='pdf') as doc:
      if not 1<=len(doc)<=30:raise ValueError('INVALID_PAGE_COUNT')
      text=doc[0].get_text();m=re.search(r'Injury\s*Report:\s*(\d{2}/\d{2}/\d{2})\s+(\d{1,2}:\d{2})\s*(AM|PM)',text)
      if not m:raise ValueError('REPORT_TIME_NOT_IN_HEADER')
      report=dt.datetime.strptime(' '.join(m.groups()),'%m/%d/%y %I:%M %p').replace(tzinfo=ZoneInfo('America/New_York'))
      if report.date().isoformat()!=r['requested_date']:raise ValueError('REPORT_HEADER_DATE_MISMATCH')
      pages=[NativePage(p) for p in doc];events,qa=parse_pages(pages);validation=validate_extracted_status_rows(pages,events)
      r.update(status='DATED_OFFICIAL_REPORT_NOT_HISTORICALLY_FIRST_SEEN',claimed_report_at_utc=report.astimezone(dt.timezone.utc).isoformat(),events=events,parser_qa=qa,validation=validation)
     if i<3 or r['requested_date'] in ('2025-01-01','2026-01-01','2026-10-25'):(out/(r['requested_date']+'_sample.pdf')).write_bytes(data)
    except Exception as e:r.update(status='UNKNOWN_PARSE_REJECTED',error=str(e)[:200])
   counts[r['status']]=counts.get(r['status'],0)+1;dest.write(json.dumps(r,ensure_ascii=False)+'\n')
   if i%100==0:print('INJURY_HISTORY',i,'of',len(dates),counts,flush=True)
 manifest={'target_dates':len(dates),'counts':counts,'seconds':time.monotonic()-start,'workers':2,'max_seconds':seconds,
  'dated_report_reconstructed_asof_only':True,'actual_historical_first_seen_not_verified':True,'absence_implies_healthy':False,'Out_status_implies_outcome_DNP':False}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2));print('INJURY_HISTORY_DONE',manifest,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--raw',required=True);p.add_argument('--current-raw',required=True);p.add_argument('--output',required=True);a=p.parse_args();collect(a.root,a.raw,a.current_raw,a.output)
