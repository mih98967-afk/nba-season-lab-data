"""Normalize exact official NBA finals into a separate, provenance-tracked source root.
The original downloaded archives remain untouched. No predictions are fitted.
"""
from __future__ import annotations
import csv, datetime as dt, gzip, hashlib, importlib.util, io, json, math, os, re, shutil, sys
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
CODE_ROOT=Path(os.environ.get('NBA_CODE_ROOT',ROOT/'nba-release-20261118'))
if not (CODE_ROOT/'src/official_nba_gameday_status_research.py').exists():CODE_ROOT=ROOT
sys.path.insert(0,str(CODE_ROOT))
from src.official_nba_gameday_status_research import official_box, official_schedule, fixture_match, parse_minutes
ET=ZoneInfo('America/New_York')
STAT={'field_goals_made':'fieldGoalsMade','field_goals_attempted':'fieldGoalsAttempted','field_goals_percentage':'fieldGoalsPercentage','three_pointers_made':'threePointersMade','three_pointers_attempted':'threePointersAttempted','three_pointers_percentage':'threePointersPercentage','free_throws_made':'freeThrowsMade','free_throws_attempted':'freeThrowsAttempted','free_throws_percentage':'freeThrowsPercentage','rebounds_offensive':'reboundsOffensive','rebounds_defensive':'reboundsDefensive','rebounds_total':'reboundsTotal','assists':'assists','steals':'steals','blocks':'blocks','turnovers':'turnovers','fouls_personal':'foulsPersonal','points':'points','plus_minus_points':'plusMinusPoints'}
NONNEGATIVE=set(STAT)-{'plus_minus_points'}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def normalize(payload, official, espn_game):
 validated=official_box(payload,official,espn_game)
 game=payload['game'];gid=str(game['gameId'])
 if game['gameTimeUTC']!=espn_game['utc']:raise ValueError('Exact UTC fixture timestamp mismatch')
 date=dt.datetime.fromisoformat(game['gameTimeUTC'].replace('Z','+00:00')).astimezone(ET).date().isoformat()
 scores={x:int(game[x]['score']) for x in ('homeTeam','awayTeam')}
 if scores['homeTeam']==scores['awayTeam']:raise ValueError('Final tied game invalid')
 box=[];inactive=[]
 for side,field in [('home','homeTeam'),('away','awayTeam')]:
  team=game[field];totalpoints=0;totalminutes=0
  for p in team['players']:
   v=validated['players'][str(p['personId'])];s=p.get('statistics') or {};seconds=parse_minutes(s.get('minutes'));mins=(seconds or 0)/60
   row={'team_id':str(team['teamId']),'team_city':team.get('teamCity',''),'team_name':team.get('teamName',''),'team_tricode':team['teamTricode'],'team_slug':'','side':side,'person_id':str(p['personId']),'first_name':p.get('firstName',''),'family_name':p.get('familyName',''),'name_i':p.get('nameI',''),'player_slug':'','position':p.get('position',''),'comment':p.get('notPlayingReason') or '', 'jersey_num':p.get('jerseyNum',''),'minutes':str(mins),'game_id':gid,'season':'2027','season_type_id':'2'}
   for target,source in STAT.items():
    value=s.get(source)
    if v['played']=='1' and (not isinstance(value,(int,float)) or not math.isfinite(value) or (target in NONNEGATIVE and value<0)):raise ValueError('Invalid played stat component '+target)
    row[target]=str(value) if value is not None else ''
   box.append(row)
   if v['played']=='1':totalpoints+=float(s['points']);totalminutes+=mins
   if v['status']=='INACTIVE' and v['played']=='0':
    inactive.append({'player_id':str(p['personId']),'first_name':p.get('firstName',''),'last_name':p.get('familyName',''),'jersey_num':p.get('jerseyNum',''),'team_id':str(team['teamId']),'team_city':team.get('teamCity',''),'team_name':team.get('teamName',''),'team_abbreviation':team['teamTricode'],'season':'2027','game_id':gid,'season_type_id':'2'})
  if totalpoints!=scores[field] or totalminutes<235:raise ValueError('Incomplete official team totals')
 schedule={'game_id':gid,'season':'2027','season_type':'regular','game_date':date,'matchup':game['homeTeam']['teamTricode']+' vs. '+game['awayTeam']['teamTricode']}
 for side,field,other in [('home','homeTeam','awayTeam'),('away','awayTeam','homeTeam')]:
  t=game[field];schedule.update({side+'_team_id':str(t['teamId']),side+'_team_abbreviation':t['teamTricode'],side+'_team_name':t.get('teamCity','')+' '+t.get('teamName',''),side+'_pts':str(scores[field]),side+'_wl':'W' if scores[field]>scores[other] else 'L'})
 return box,inactive,schedule

def write_csv(path,fieldnames,rows):
 raw=io.StringIO(newline='');w=csv.DictWriter(raw,fieldnames=fieldnames,lineterminator='\n');w.writeheader();w.writerows(rows);data=raw.getvalue().encode()
 path.write_bytes(gzip.compress(data,mtime=0) if path.suffix=='.gz' else data)

def read_csv(path):
 raw=gzip.decompress(path.read_bytes()).decode() if path.suffix=='.gz' else path.read_text();r=csv.DictReader(io.StringIO(raw));return r.fieldnames,list(r)

def main():
 out=HERE/'derived_current';current=out/'source/current'
 if current.exists():raise ValueError('Immutable derived source already exists')
 direct=json.loads((HERE/'direct_nba/MANIFEST.json').read_text());snap=json.loads((HERE/'source/current/manifest.json').read_text());captured=json.loads((HERE/'CAPTURE_SUMMARY.json').read_text())
 for r in direct['sources']:
  if r['status']!='retrieved' or sha(HERE/'direct_nba'/r['file'])!=r['sha256']:raise ValueError('Direct source hash mismatch')
 schedule_payload=json.loads((HERE/'direct_nba/scheduleLeagueV2_1.json').read_text());schedule=official_schedule(schedule_payload)
 live=json.loads((HERE/'current_snapshot/data/live.json').read_text());live_games={g['id']:g for g in live['games']}
 new=json.loads((HERE.parent/'prospective_20261117/forecasts.json').read_text());fixtures={r['nba_game_id']:r for r in new['records']}
 addition_box=[];addition_inactive=[];addition_games=[];qa=[]
 for gid,f in sorted(fixtures.items()):
  g=live_games[f['calendar_game_id']]
  official,error=fixture_match(g,schedule)
  if error or official['id']!=gid or f['tipoff_utc']!=g['utc']:raise ValueError('Frozen NBA/calendar fixture identity mismatch')
  rows,inactive,sc=normalize(json.loads((HERE/'direct_nba'/(gid+'.json')).read_text()),official,g)
  if sc['game_date']!=f['date_ET'] or {sc['home_team_abbreviation'],sc['away_team_abbreviation']}!={f['team'],f['opponent']}:raise ValueError('Frozen NBA date/team mismatch')
  addition_box+=rows;addition_inactive+=inactive;addition_games.append(sc);qa.append({'NBA_game_id':gid,'calendar_game_id':g['id'],'tipoff_utc':g['utc'],'exact_fixture_match':True,'box_rows':len(rows),'explicit_inactive_rows':len(inactive)})
 current.mkdir(parents=True)
 for p in (HERE/'source/current').iterdir():
  if p.is_file() and p.name!='manifest.json':shutil.copyfile(p,current/p.name)
 boxfields,box=read_csv(current/'player_boxscores_2027.csv');rosterfields,roster=read_csv(current/'game_rosters_2027.csv');scfields,sc=read_csv(current/'nba_schedule_2027.csv.gz')
 ids=set(fixtures)
 if any(r['game_id'] in ids for r in box+roster):raise ValueError('Supplement duplicates existing player games')
 scidx={r['game_id']:i for i,r in enumerate(sc)}
 for r in addition_games:
  old=sc[scidx[r['game_id']]]
  for key in ['game_date','home_team_id','away_team_id','home_team_abbreviation','away_team_abbreviation']:
   if old[key]!=r[key]:raise ValueError('Source schedule identity disagreement '+key)
  if any(old[k] not in ('','0','0.0') for k in ['home_pts','away_pts']):raise ValueError('Refuse replace already scored archive game')
  sc[scidx[r['game_id']]]=r
 write_csv(current/'player_boxscores_2027.csv',boxfields,box+addition_box);write_csv(current/'game_rosters_2027.csv',rosterfields,roster+addition_inactive);write_csv(current/'nba_schedule_2027.csv.gz',scfields,sc)
 availability=max([captured['completed_at_utc']]+[r['fetched_at_utc'] for r in direct['sources']])
 manifest=[]
 for r in snap:
  path=current/r['file'];entry={**r,'sha256':sha(path),'bytes':path.stat().st_size}
  if r['file']!='injury_report_2027.parquet':entry.update(status='retrieved',processing='verified additive normalization of direct official NBA JSON; original archive preserved separately',fetched_at_utc=availability,original_archive_sha256=r['sha256'],source_derivation='DERIVATION.json')
  manifest.append(entry)
 (current/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 upstream=HERE/'source/upstream';(out/'source/upstream').symlink_to(os.path.relpath(upstream.resolve(),out/'source'),target_is_directory=True)
 shutil.copyfile(HERE/'source/upstream_manifest.json',out/'source/upstream_manifest.json')
 derivative={'schema':'nba-current-source-additive-official-supplement-v1','built_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_availability_upper_bound_utc':availability,'original_sources_modified':False,'fit_or_tuning_performed':False,'raw_archive_manifest_sha256':sha(HERE/'source/current/manifest.json'),'direct_NBA_manifest_sha256':sha(HERE/'direct_nba/MANIFEST.json'),'direct_sources':direct['sources'],'normalizer_sha256':sha(Path(__file__)),'official_validation_code_sha256':sha(CODE_ROOT/'src/official_nba_gameday_status_research.py'),'added_games':qa,'added_box_rows':len(addition_box),'added_explicit_inactive_rows':len(addition_inactive),'UNKNOWN_is_DNP':False,'injury_source_unchanged':True,'injury_source_freshness_not_upgraded':True,'not_Sports_ru_credited_FP':True,'current_files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in current.iterdir() if p.is_file()}}
 (out/'DERIVATION.json').write_text(json.dumps(derivative,indent=2)+'\n')
 spec=importlib.util.spec_from_file_location('qa_derived',HERE/'validate_current_sources.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.OUT=out;mod.CURRENT=current;mod.main()
 sourceqa=json.loads((out/'SOURCE_QA.json').read_text())
 if not sourceqa['coherent_current_snapshot_verified']:raise ValueError('Derived source QA failure')
 print(json.dumps({'source':str(out/'source'),'available_at_utc':availability,'schedule':sourceqa['schedule'],'added_games':qa},indent=2))

if __name__=='__main__':main()
