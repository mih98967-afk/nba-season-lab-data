"""Free, bounded daily source intake with a strict official-NBA lag supplement.

Historical twelve files are hash pinned and cacheable. Four current archives are
fetched once. If a fresh public final is absent from the slow archive, at most18
recent official NBA boxscores are added with exact fixture and team-stat checks.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.request
from model_store import HERE,ROOT,add_research_path,sha256
from export_feed import utc,iso,schedule_key,finite
add_research_path()
from collect_sources import collect

HELPER=ROOT/'research_extension/prospective_20261118'
sys.path.insert(0,str(HELPER))
from derive_current_supplement import normalize,official_schedule,fixture_match,read_csv,write_csv


def fetch(url,path,limit=80_000_000):
    allowed=url.startswith('https://github.com/sportsdataverse/sportsdataverse-data/releases/download/') or url.startswith('https://cdn.nba.com/static/json/')
    if not allowed:raise ValueError('UNSUPPORTED_PUBLIC_SOURCE')
    req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/free-reproducible-inference','Referer':'https://www.nba.com/','Accept':'application/json,*/*'})
    started=iso(dt.datetime.now(dt.timezone.utc))
    with urllib.request.urlopen(req,timeout=45) as response:blob=response.read(limit+1)
    if len(blob)>limit:raise ValueError('SOURCE_SIZE_LIMIT')
    Path(path).write_bytes(blob)
    return {'url':url,'file':Path(path).name,'started_at_utc':started,'fetched_at_utc':iso(dt.datetime.now(dt.timezone.utc)),
            'status':'retrieved','sha256':sha256(blob),'bytes':len(blob)}


def historical_cache(cache):
    cache=Path(cache)
    preserved=Path(os.environ.get('NBA_RESEARCH_BASE',ROOT/'research_base'))/'source/upstream'
    if cache.resolve()==preserved.resolve():raise ValueError('PRESERVED_SOURCE_CACHE_CANNOT_BE_MUTATED')
    cache.mkdir(parents=True,exist_ok=True)
    pinned=json.loads((HERE/'HISTORICAL_SOURCE_MANIFEST.json').read_text())
    for item in pinned:
        path=cache/item['file']
        if not path.is_file() or sha256(path.read_bytes())!=item['sha256']:fetch(item['url'],path)
        if sha256(path.read_bytes())!=item['sha256']:raise ValueError('HISTORICAL_SOURCE_REVISION_REJECTED:'+item['file'])
        if path.suffix=='.parquet':
            import pyarrow.parquet as pq
            dest=path.with_suffix('.csv.gz')
            marker=cache/(dest.name+'.conversion.json')
            existing=json.loads(marker.read_text()) if marker.exists() else {}
            if not dest.exists() or existing.get('source_sha256')!=item['sha256'] or existing.get('derived_sha256')!=sha256(dest.read_bytes()):
                table=pq.read_table(path)
                with gzip.open(dest,'wt',newline='',encoding='utf8') as f:
                    w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader()
                    for batch in table.to_batches(max_chunksize=10000):w.writerows(batch.to_pylist())
                marker.write_text(json.dumps({'source_sha256':item['sha256'],'derived_sha256':sha256(dest.read_bytes())})+'\n')
    return cache


def supplemental_source(raw_current,out,snapshot,asof,fetcher=fetch):
    """Pure file derivation except injected bounded fetcher; originals unchanged."""
    raw_current,out,snapshot=map(Path,(raw_current,out,snapshot))
    current=out/'source/current'
    if current.exists():raise ValueError('DERIVED_SOURCE_DESTINATION_ALREADY_EXISTS')
    current.mkdir(parents=True)
    for path in raw_current.iterdir():
        if path.is_file():shutil.copyfile(path,current/path.name)
    live=json.loads((snapshot/'live.json').read_text())
    games=live.get('schedule',[])
    boxfields,box=read_csv(current/'player_boxscores_2027.csv')
    rosterfields,rosters=read_csv(current/'game_rosters_2027.csv')
    scfields,sc=read_csv(current/'nba_schedule_2027.csv.gz')
    scored={(r['game_date'][:10],r['home_team_abbreviation'],r['away_team_abbreviation']) for r in sc
            if finite(r['home_pts']) and finite(r['away_pts']) and float(r['home_pts'])!=float(r['away_pts'])}
    missing=[g for g in games if g.get('status') in ('final','Final','completed') and schedule_key(g)[0]<asof and schedule_key(g) not in scored]
    if len(missing)>18:raise ValueError('OFFICIAL_SUPPLEMENT_GAME_LIMIT')
    if any((dt.date.fromisoformat(asof)-dt.date.fromisoformat(schedule_key(g)[0])).days>3 for g in missing):
        raise ValueError('OFFICIAL_SUPPLEMENT_TOO_OLD')
    direct=out/'direct_nba';direct.mkdir()
    sources=[];added=[];newbox=[];newrosters=[]
    if missing:
        path=direct/'scheduleLeagueV2_1.json'
        sources.append(fetcher('https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json',path,14_000_000))
        official=official_schedule(json.loads(path.read_text()));scidx={r['game_id']:i for i,r in enumerate(sc)}
        for g in sorted(missing,key=lambda v:(v['utc'],v['id'])):
            match,error=fixture_match(g,official)
            if error or not match:raise ValueError('OFFICIAL_SUPPLEMENT_FIXTURE_MISMATCH')
            gid=match['id'];path=direct/(gid+'.json')
            sources.append(fetcher('https://cdn.nba.com/static/json/liveData/boxscore/boxscore_'+gid+'.json',path,5_000_000))
            br,ir,sr=normalize(json.loads(path.read_text()),match,g)
            if gid not in scidx:raise ValueError('SUPPLEMENT_NOT_IN_ARCHIVE_CALENDAR')
            old=sc[scidx[gid]]
            for key in ('game_date','home_team_id','away_team_id','home_team_abbreviation','away_team_abbreviation'):
                if old[key]!=sr[key]:raise ValueError('SUPPLEMENT_ARCHIVE_IDENTITY_CONFLICT')
            if any(r['game_id']==gid for r in box+rosters):raise ValueError('SUPPLEMENT_DUPLICATES_ARCHIVE_ROWS')
            newbox.extend(br);newrosters.extend(ir);sc[scidx[gid]]=sr
            added.append({'nba_game_id':gid,'calendar_game_id':g['id'],'game_utc':g['utc'],'box_rows':len(br),'explicit_inactive_rows':len(ir)})
    if added:
        write_csv(current/'player_boxscores_2027.csv',boxfields,box+newbox)
        write_csv(current/'game_rosters_2027.csv',rosterfields,rosters+newrosters)
        write_csv(current/'nba_schedule_2027.csv.gz',scfields,sc)
    raw_manifest=json.loads((raw_current/'manifest.json').read_text())
    availability=iso(max(utc(r['fetched_at_utc']) for r in raw_manifest+sources))
    manifest=[]
    for item in raw_manifest:
        path=current/item['file'];entry=dict(item,sha256=sha256(path.read_bytes()),bytes=path.stat().st_size)
        if entry['sha256']!=item['sha256']:
            entry.update(original_archive_sha256=item['sha256'],processing='Verified additive official NBA final supplement',
                         source_derivation='DERIVATION.json',fetched_at_utc=availability)
        manifest.append(entry)
    (current/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (direct/'MANIFEST.json').write_text(json.dumps({'sources':sources},indent=2)+'\n')
    provenance={'schema':'nba-current-source-additive-official-supplement-v1','source_availability_upper_bound_utc':availability,
                'built_at_utc':iso(dt.datetime.now(dt.timezone.utc)),'raw_archive_manifest_sha256':sha256((raw_current/'manifest.json').read_bytes()),
                'direct_sources':sources,'added_games':added,'original_sources_modified':False,'UNKNOWN_is_DNP':False,
                'injury_source_unchanged':True,'injury_source_freshness_not_upgraded':True,'fit_or_tuning_performed':False,
                'normalizer_sha256':sha256((HELPER/'derive_current_supplement.py').read_bytes())}
    (out/'DERIVATION.json').write_text(json.dumps(provenance,indent=2)+'\n')
    capture={'completed_at_utc':availability,'derivation_sha256':sha256((out/'DERIVATION.json').read_bytes()),
             'availability_bound_is_latest_captured_input':True}
    (out/'CAPTURE_SUMMARY.json').write_text(json.dumps(capture,indent=2)+'\n')
    return provenance


def validate(out):
    spec=importlib.util.spec_from_file_location('daily_source_qa',HELPER/'validate_current_sources.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.OUT=Path(out);module.CURRENT=Path(out)/'source/current';module.main()
    qa=json.loads((Path(out)/'SOURCE_QA.json').read_text())
    if qa['status']!='INTERNAL_COHERENCE_PASS':raise ValueError('DAILY_SOURCE_COHERENCE_FAILED')
    return qa


def main():
    p=argparse.ArgumentParser();p.add_argument('--work',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--snapshot-data',type=Path,required=True);p.add_argument('--asof-date',required=True)
    p.add_argument('--current-source',type=Path,help='Optional already captured immutable archive for a reproducible offline run')
    a=p.parse_args();a.work.mkdir(parents=True,exist_ok=True)
    historic=historical_cache(a.cache)
    raw=a.current_source or a.work/'raw_current'
    if a.current_source is None:
        manifest=collect((2027,),raw)
        # The preserved collector records the request start under fetched_at_utc.
        # Keep it as provenance, but use the actual completed batch as a
        # conservative availability bound for every newly downloaded archive.
        completed=iso(dt.datetime.now(dt.timezone.utc))
        for item in manifest:
            item['request_started_at_utc']=item.get('fetched_at_utc')
            item['fetched_at_utc']=completed
            item['availability_is_completed_batch_upper_bound']=True
        (raw/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        if len(manifest)!=4 or any(r['status']!='retrieved' for r in manifest):raise ValueError('CURRENT_SOURCE_FETCH_FAILED')
    supplemental_source(raw,a.work/'derived',a.snapshot_data,a.asof_date)
    source=a.work/'derived/source';(source/'upstream').symlink_to(historic.resolve(),target_is_directory=True)
    shutil.copyfile(HERE/'HISTORICAL_SOURCE_MANIFEST.json',source/'upstream_manifest.json')
    qa=validate(a.work/'derived')
    print(json.dumps({'source':str(source),'capture':str(a.work/'derived/CAPTURE_SUMMARY.json'),
                      'source_qa':str(a.work/'derived/SOURCE_QA.json'),'latest_completed':qa['schedule']['latest_completed_date']},indent=2))


if __name__=='__main__':main()
