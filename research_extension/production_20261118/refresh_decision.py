"""Cheap stdlib cadence gate before installing scientific packages or fetching data."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def fingerprint(root,now=None):
    root=Path(root);now=now or dt.datetime.now(dt.timezone.utc)
    live=json.loads((root/'data/live.json').read_text());inv=json.loads((root/'data/official_injury_snapshots.json').read_text())
    rows=[{k:r.get(k) for k in ('id','game_id','utc','team','minutes','played','fp','box')} for r in live.get('rows',[])]
    rows.sort(key=lambda r:(r.get('game_id') or '',r.get('id') or ''))
    games=[{k:r.get(k) for k in ('id','utc','home','away','status','et_date')} for r in live.get('schedule',[])]
    games.sort(key=lambda r:r.get('id') or '')
    schedule=json.loads((root/'data/schedule.json').read_text())
    schedule_content={'status':schedule.get('status'),'completeness':schedule.get('completeness'),
                      'games':sorted([{k:r.get(k) for k in ('id','utc','home','away','status','et_date')} for r in schedule.get('games',[])],key=lambda r:r.get('id') or '')}
    reports=[{k:r.get(k) for k in ('url','sha256','report_at_utc')} for r in inv.get('snapshots',[])]
    reports.sort(key=lambda r:r.get('report_at_utc') or '')
    fixed=['data/identity.json','data/catalog.json','data/schedule.json','site/hosting_v620/data/base.json',
           'research_extension/production_20261118/models/MANIFEST.json','research_extension/production_20261118/SITE_DEFAULT_GATE.json',
           'research_extension/prospective_20261118/derive_current_supplement.py','research_extension/prospective_20261118/validate_current_sources.py',
           'research_extension/prospective_20261118/injury_fix/export_fresh_status.py','research_extension/recency/features.py',
           'src/official_injury_rows.py','src/official_nba_gameday_status_research.py',
           'research_extension/position_20261118/results/CURRENT_CATALOG_IDENTITY_OVERLAY.json',
           'research_extension/position_20261118/PUBLIC_ASSETS_MANIFEST.json']
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in fixed if (root/name).is_file() and name!='data/schedule.json'}
    for pattern in ('research_extension/production_20261118/*.py','research_extension/position_20261118/*.py','research/match_context/*.py'):
        for p in sorted(root.glob(pattern)):hashes[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return digest({'asof_date_et':now.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                   'completed_player_content':rows,'calendar_content':games,'verified_calendar':schedule_content,'latest_official_report':reports[-1:] or [],'fixed_inputs':hashes})


def decision(root,force=False,now=None):
    now=now or dt.datetime.now(dt.timezone.utc);fp=fingerprint(root,now);path=Path(root)/'data/model_forecasts_v1.json'
    result={'refresh':True,'fingerprint':fp,'reason':'new_inputs_or_no_prior_feed'}
    if force:result['reason']='explicit_force';return result
    if path.is_file():
        feed=json.loads(path.read_text());issued=dt.datetime.fromisoformat(feed['issued_at_utc'].replace('Z','+00:00'))
        expires=dt.datetime.fromisoformat(feed.get('valid_until_utc',feed['issued_at_utc']).replace('Z','+00:00'))
        if feed.get('refresh_fingerprint')==fp and feed.get('status')=='ready' and now<expires and dt.timedelta(0)<=now-issued<dt.timedelta(hours=12):
            result.update(refresh=False,reason='same_date_meaningful_data_models_and_injury_hash_within12h')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));p.add_argument('--force',action='store_true');p.add_argument('--github-output',type=Path)
    a=p.parse_args();r=decision(a.root,a.force)
    if a.github_output:
        with a.github_output.open('a') as f:f.write('refresh='+str(r['refresh']).lower()+'\n')
    print(json.dumps(r,indent=2))
