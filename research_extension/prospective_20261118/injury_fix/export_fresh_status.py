"""Read-only current official PDF exact-ID export; no historical row rewrite."""
from pathlib import Path
from collections import defaultdict,Counter
import argparse, datetime as dt, hashlib, importlib.util, json, os, re, sys
from zoneinfo import ZoneInfo
import pandas as pd
HERE=Path(__file__).resolve().parent;PARENT=HERE.parent;ROOT=HERE.parents[2]
CODE=Path(os.environ.get('NBA_CODE_ROOT',ROOT/'nba-release-20261118'))
if not (CODE/'src/official_nba_gameday_status_research.py').exists():CODE=ROOT
sys.path.insert(0,str(CODE))
from src.official_nba_gameday_status_research import official_schedule
pdf=None
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
ET=ZoneInfo('America/New_York')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pdf',type=Path,default=HERE/'official_20261118_0245.pdf');ap.add_argument('--source-meta',type=Path,default=HERE/'SOURCE.json');ap.add_argument('--current',type=Path,default=PARENT/'derived_current/source/current');ap.add_argument('--live',type=Path,default=PARENT/'current_snapshot/data/live.json');ap.add_argument('--identity',type=Path,default=PARENT/'current_snapshot/data/identity.json');ap.add_argument('--official-schedule',type=Path,default=PARENT/'direct_nba/scheduleLeagueV2_1.json');ap.add_argument('--output',type=Path,default=HERE/'FRESH_OFFICIAL_NBA_STATUS.json');ap.add_argument('--parser-module',type=Path,default=CODE/'src/official_injury_rows.py');args=ap.parse_args()
 global pdf
 parser_spec=importlib.util.spec_from_file_location('selected_official_parser',args.parser_module);pdf=importlib.util.module_from_spec(parser_spec);parser_spec.loader.exec_module(pdf)
 source=json.loads(args.source_meta.read_text());now=dt.datetime.now(dt.timezone.utc)
 if sha(args.pdf)!=source['sha256']:raise ValueError('PDF hash mismatch')
 if 'retrieved_at_utc'not in source:raise ValueError('Actual PDF retrieval timestamp required; no inventory backdating')
 if dt.datetime.fromisoformat(source['retrieved_at_utc'].replace('Z','+00:00'))>now:raise ValueError('PDF capture is in future')
 import pdfplumber
 with pdfplumber.open(args.pdf)as doc:
  events,parserqa=pdf.parse_pages(doc.pages);extraction=pdf.validate_extracted_status_rows(doc.pages,events);fixture={'pages':[[{k:w[k]for k in('x0','top','text')}for w in p.extract_words(x_tolerance=2,y_tolerance=2)]for p in doc.pages]}
 native_cells=extraction['explicit_status_cells']
 current=args.current;box=pd.read_csv(current/'player_boxscores_2027.csv',dtype=str,keep_default_na=False);inactive=pd.read_csv(current/'game_rosters_2027.csv',dtype=str,keep_default_na=False)
 names=defaultdict(set);membership=set()
 for r in box.itertuples(index=False):
  names[pdf.norm(r.first_name+' '+r.family_name)].add(str(r.person_id));membership.add((str(r.person_id),r.team_tricode))
 for r in inactive.itertuples(index=False):
  names[pdf.norm(r.first_name+' '+r.last_name)].add(str(r.player_id));membership.add((str(r.player_id),r.team_abbreviation))
 identity=json.loads(args.identity.read_text())
 for r in identity['players'].values():
  if r.get('confidence')=='high' and str(r.get('nba_id','')).isdigit() and r.get('english'):names[pdf.norm(r['english'])].add(str(r['nba_id']))
 official=official_schedule(json.loads(args.official_schedule.read_text()))
 games=defaultdict(list)
 for g in official:
  date=dt.datetime.fromisoformat(g['utc'].replace('Z','+00:00')).astimezone(ET).date().isoformat();games[(date,g['away'],g['home'])].append(g)
 live=json.loads(args.live.read_text());calendar=defaultdict(list)
 for g in live['schedule']:calendar[(g.get('utc'),g.get('away'),g.get('home'))].append(g)
 mapped=[];unmatched=[];counts=Counter()
 for e in events:
  reason=None;ids=names[e['player_name']];gs=games[(e['et_date'],e['away'],e['home'])]
  if len(ids)!=1:reason='missing_or_ambiguous_exact_full_name_to_NBA_ID'
  elif (next(iter(ids)),e['team'])not in membership:reason='no_exact_current_season_team_membership'
  elif len(gs)!=1:reason='missing_or_ambiguous_official_fixture'
  elif dt.datetime.fromisoformat(gs[0]['utc'].replace('Z','+00:00'))<=now+dt.timedelta(minutes=30):reason='not_before_current_T_minus_30'
  if not reason:
   g=gs[0];cs=calendar[(g['utc'],g['away'],g['home'])]
   if len(cs)!=1:reason='missing_or_ambiguous_exact_UTC_calendar_fixture'
  if reason:unmatched.append({**e,'reason':reason});counts[reason]+=1;continue
  mapped.append({'nba_player_id':next(iter(ids)),'nba_game_id':g['id'],'calendar_game_id':cs[0]['id'],'date_ET':e['et_date'],'team':e['team'],'home':e['home'],'away':e['away'],'player_name_normalized':e['player_name'],'status':e['official_status'],'tipoff_utc':g['utc'],'report_at_utc':source['report_at_utc'],'first_observed_in_inventory_utc':source['first_seen_at_utc'],'available_at_utc':source['retrieved_at_utc'],'source_url':source['url'],'source_sha256':source['sha256'],'identity_method':'unique_exact_normalized_full_name_plus_current_season_NBA_team_membership','fixture_method':'exact_NBA_ID_ET_date_home_away_and_independent_UTC_calendar_match','intraday_current_feature_extension':True})
 # Identify explicitly unsubmitted teams from native text, without treating absence as healthy.
 teams={};current_date=None;current_match=None;current_team=None
 for words in fixture['pages']:
  for line in pdf.group_lines(words):
   date=pdf.col(line,19,109)
   if re.fullmatch(r'\d{1,2}/\d{1,2}/20\d{2}',date):current_date=dt.datetime.strptime(date,'%m/%d/%Y').date().isoformat()
   match=pdf.col(line,192,258).upper().replace(' ','')
   if re.fullmatch(r'[A-Z]{2,4}@[A-Z]{2,4}',match):current_match=tuple(pdf.ALIASES.get(t,t)for t in match.split('@'));current_team=None
   club=pdf.CLUBS.get(pdf.norm(pdf.col(line,263,418)))
   if club:current_team=club
   if not current_date or not current_match or current_team not in current_match:continue
   key=(current_date,*current_match,current_team);record=teams.setdefault(key,{'date_ET':current_date,'away':current_match[0],'home':current_match[1],'team':current_team,'explicit_status_rows':0,'NOT_YET_SUBMITTED':False})
   text=' '.join(w['text']for w in line).upper()
   if 'NOT YET SUBMITTED'in text:record['NOT_YET_SUBMITTED']=True
   if pdf.col(line,580,663).title()in pdf.STATUS:record['explicit_status_rows']+=1
 for r in teams.values():
  if r['NOT_YET_SUBMITTED']and r['explicit_status_rows']:raise ValueError('Conflicting submitted team evidence')
  r['report_state']='NOT_YET_SUBMITTED'if r['NOT_YET_SUBMITTED']else('HAS_EXPLICIT_ROWS'if r['explicit_status_rows']else'UNKNOWN')
  r['absence_implies_healthy']=False;r['full_player_roster_coverage_proven']=False
  same=lambda e:(e.get('date_ET',e.get('et_date')),e['away'],e['home'],e['team'])==(r['date_ET'],r['away'],r['home'],r['team'])
  r['mapped_status_rows']=sum(same(e)for e in mapped)
  r['unresolved_named_status_rows']=sum(same(e)for e in unmatched)
  r['all_explicit_named_rows_resolved']=r['explicit_status_rows']>0 and r['unresolved_named_status_rows']==0 and r['mapped_status_rows']==r['explicit_status_rows']
  r['native_status_cell_coverage_complete']=True
  r['allow_missing_player_as_NOT_LISTED_feature']=r['report_state']=='HAS_EXPLICIT_ROWS'and r['all_explicit_named_rows_resolved']
  gs=games[(r['date_ET'],r['away'],r['home'])]
  if len(gs)==1:
   r['nba_game_id']=gs[0]['id'];r['tipoff_utc']=gs[0]['utc']
   cs=calendar[(gs[0]['utc'],r['away'],r['home'])]
   r['calendar_game_id']=cs[0]['id']if len(cs)==1 else None
  r['report_at_utc']=source['report_at_utc'];r['available_at_utc']=source['retrieved_at_utc']
 if sum(r['explicit_status_rows']for r in teams.values())!=native_cells:raise ValueError('Per-team full-cell denominator mismatch')
 out={'schema':'nba-fresh-official-pdf-exact-ID-status-v1','generated_at_utc':now.isoformat(),'native_cells_complete':True,'native_explicit_status_cells':native_cells,'matched_rows':len(mapped),'unknown_identity_or_fixture_rows':len(unmatched),'source':source,'source_available_at_utc':source['retrieved_at_utc'],'minimum_inference_issue_after_utc':now.isoformat(),'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size}for p in [args.pdf,args.source_meta,args.parser_module,current/'player_boxscores_2027.csv',current/'game_rosters_2027.csv',args.identity,args.official_schedule,args.live]},'events':mapped,'unresolved':unmatched,'unresolved_reasons':dict(counts),'team_report_states':list(teams.values()),'historical_or_frozen_predictions_modified':False,'training_or_calibration_performed':False,'absent_players_healthy_inference':False,'intraday_current_status_extension_not_identical_to_original_midnight_feature_cutoff':True,'NOT_YET_SUBMITTED_is_negative_participation':False}
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n');print(json.dumps({'mapped':len(mapped),'unresolved':dict(counts),'team_states':Counter(r['report_state']for r in teams.values()),'source_available_at_utc':source['retrieved_at_utc'],'inference_after_utc':now.isoformat()},indent=2))
if __name__=='__main__':main()
