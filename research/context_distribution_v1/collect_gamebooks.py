"""Bounded public postgame source collection. No absence is converted to DNP."""
from __future__ import annotations
import argparse, concurrent.futures, csv, datetime as dt, gzip, hashlib, json, pathlib, time, urllib.request
import fitz

def collect(root,raw,output,limit=4000,seconds=540):
 root=pathlib.Path(root);raw=pathlib.Path(raw);out=pathlib.Path(output);out.mkdir(parents=True,exist_ok=True)
 targets=[]
 for year in (2024,2025,2026):
  with gzip.open(raw/f'nba_schedule_{year}.csv.gz','rt') as f:games=list(csv.DictReader(f))
  for g in games:
   gid=str(g['game_id']).zfill(10)
   if not gid.startswith('002'):continue
   day=g['game_date'][:10];home=g['home_team_abbreviation'];away=g['away_team_abbreviation']
   targets.append({'game_id':gid,'date':day,'year':year,'home':home,'away':away,'home_pts':float(g['home_pts']),'away_pts':float(g['away_pts'])})
 livepath=root/'data'/'live.json'
 if livepath.exists():
  live=json.load(open(livepath))
  for g in live.get('games',[]):
   if g.get('status')!='final' or not g.get('et_date'):continue
   targets.append({'game_id':g['id'],'date':g['et_date'],'year':2027,'home':g['home'],'away':g['away'],'home_pts':None,'away_pts':None})
 targets.sort(key=lambda x:(x['year']!=2027,x['date'],x['game_id']))
 targets=targets[:limit];start=time.monotonic()
 def fetch(g):
  record={**g,'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
  date=g['date'].replace('-','');url=f'https://statsdmz.nba.com/pdfs/{date}/{date}_{g["away"]}{g["home"]}.pdf';record['url']=url
  if time.monotonic()-start>seconds:return record,None,'TIME_BUDGET_NOT_FETCHED'
  time.sleep(.15)
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/Research noncommercial public statistics'})
   with urllib.request.urlopen(req,timeout=10) as r:data=r.read(1000001)
   if not data.startswith(b'%PDF') or len(data)>1000000:raise ValueError('INVALID_OR_OVERSIZED_PDF')
   record.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   return record,data,None
  except Exception as e:return record,None,str(e)[:200]
 counts={};success=0
 with gzip.open(out/'official_gamebooks.jsonl.gz','wt',encoding='utf8') as dest,concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for i,(record,data,error) in enumerate(pool.map(fetch,targets)):
   if data is not None:
    try:
     with fitz.open(stream=data,filetype='pdf') as doc:
      if len(doc)>3:raise ValueError('UNEXPECTED_PAGE_COUNT')
      text='\n'.join(p.get_text() for p in doc)
     if 'NATIONAL BASKETBALL ASSOCIATION' not in text or 'FINAL BOX' not in text:raise ValueError('NOT_OFFICIAL_FINAL_BOX')
     record.update(status='FETCHED_NOT_IDENTITY_VERIFIED',text=text,has_inactive_section='Inactive:' in text)
     success+=1
    except Exception as e:record.update(status='PARSE_UNKNOWN',error=str(e)[:200])
   else:record.update(status='UNKNOWN_SOURCE_UNAVAILABLE',error=error)
   counts[record['status']]=counts.get(record['status'],0)+1
   dest.write(json.dumps(record,ensure_ascii=False)+'\n')
   if i%250==0:print('GAMEBOOK',i,'of',len(targets),'success',success,'seconds',round(time.monotonic()-start,1),flush=True)
 manifest={'target_count':len(targets),'status_counts':counts,'seconds':time.monotonic()-start,'workers':2,'max_seconds':seconds,'observed_vintage':'postgame files retrieved now, not pregame publication evidence','absence_implies_DNP':False,'full_identity_validation':False}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print('GAMEBOOK_DONE',manifest,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--raw',required=True);p.add_argument('--output',required=True);a=p.parse_args();collect(a.root,a.raw,a.output)
