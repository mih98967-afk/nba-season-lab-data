"""Scientifically meaningful contract tests for new evidence and unchanged forecasts."""
from pathlib import Path
import copy,hashlib,json,tempfile,unittest
from unittest.mock import patch
import score_completed as score
from score_evidence_union import union_evidence
from derive_current_supplement import normalize,official_schedule,fixture_match
HERE=Path(__file__).resolve().parent
class TestProspective(unittest.TestCase):
 @unittest.skipUnless((score.BASE/'prospective_20261116/forecasts.json').exists() and (HERE.parent/'prospective_20261117/forecasts.json').exists(),'Scientific checkpoint forecast bytes required')
 def test_both_frozen_hash_locks_and_pairing(self):
  old=score.load_frozen(score.BASE/'prospective_20261116/forecasts.json');new=score.locked_new(HERE.parent/'prospective_20261117/forecasts.json')
  self.assertEqual(len(old['records']),1741);self.assertEqual(len(new['records']),334)
 @unittest.skipUnless((HERE.parent/'prospective_20261117/forecasts.json').exists(),'Scientific checkpoint forecast bytes required')
 def test_changed_forecast_bytes_rejected(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'forecasts.json';p.write_bytes((HERE.parent/'prospective_20261117/forecasts.json').read_bytes()+b' ')
   with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):score.locked_new(p)
 @unittest.skipUnless((HERE.parent/'prospective_20261117/forecasts.json').exists(),'Scientific checkpoint forecast bytes required')
 def test_mean_pair_with_changed_interval_rejected_even_after_integrity_fixture(self):
  j=json.loads((HERE.parent/'prospective_20261117/forecasts.json').read_text());j['records'][0]['lo50']-=.1
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'fixture.json';p.write_text(json.dumps(j))
   with patch.object(score,'NEW_SHA',score.sha(p)):
    with self.assertRaisesRegex(ValueError,'UNPAIRED_NONMEAN_COMPONENT'):score.locked_new(p)
 def test_FP_conflict_preserves_participation_and_separate_ESPN_value(self):
  r={'outcome_archive':'UNKNOWN','y_fp':None,'participation_verified':1,'outcome_espn':'PLAYED','espn_y_fp':21.,'p_play':.8,'baseline_p_play':.9,'baseline_fp10':20.,'mean_if_play':19.,'expected_fp':15.2,'archive_reason':'ESPN_archive_disagreement','reason':'positive_minutes_exact_game','espn_archive_overlap':'CONFLICT','nba_game_id':'g1','date_ET':'2026-11-17'}
  for n in [50,80,95]:
   for prefix in ['', 'conditional_']:r[prefix+'lo'+str(n)]=0.;r[prefix+'hi'+str(n)]=30.
  self.assertEqual(r['participation_verified'],1);self.assertIsNone(r['y_fp']);self.assertIsNotNone(r['espn_y_fp'])
  d=score.describe([r]);self.assertEqual(d['strict_ESPN']['conditional']['frozen_candidate']['n'],1);self.assertEqual(d['archive_reconciled']['conditional']['frozen_candidate']['n'],0)
 def test_union_never_overrides_conflict(self):
  r={'outcome_archive':'UNKNOWN','y_fp':None,'participation_verified':1,'espn_archive_overlap':'CONFLICT','outcome_espn':'PLAYED','espn_y_fp':42}
  u=union_evidence(r);self.assertEqual(u['outcome_evidence_union'],'UNKNOWN');self.assertIsNone(u['union_y_fp']);self.assertEqual(u['union_participation_verified'],1)
 def test_union_absence_not_DNP_and_all_explicit_labels_used(self):
  r={'outcome_archive':'UNKNOWN','y_fp':None,'participation_verified':None,'espn_archive_overlap':'not_both_known','outcome_espn':'UNKNOWN','espn_y_fp':None}
  self.assertEqual(union_evidence(r)['outcome_evidence_union'],'UNKNOWN')
  for state,y in [('EXPLICIT_DNP',0),('PLAYED',-3)]:
   u=union_evidence({**r,'outcome_espn':state,'espn_y_fp':y});self.assertEqual(u['outcome_evidence_union'],state);self.assertEqual(u['union_y_fp'],y)
 def test_cluster_count_and_direction(self):
  rows=[{'nba_game_id':'a','date_ET':'2026-11-17','y':0,'b':2,'c':1},{'nba_game_id':'a','date_ET':'2026-11-17','y':0,'b':2,'c':1},{'nba_game_id':'b','date_ET':'2026-11-17','y':0,'b':4,'c':1}]
  d=score.clustered_difference(rows,lambda r:r['b'],lambda r:r['c'],lambda r:r['y'])
  self.assertEqual(d['games'],2);self.assertEqual(d['n'],3);self.assertAlmostEqual(d['paired_gain'],5/3);self.assertIsNone(d['date_cluster_CI'])
 def test_direct_final_normalization_identity_and_zeros(self):
  def team(name,base,points):
   players=[]
   for i in range(7):
    positive=i<5;stats={key:0 for key in ['fieldGoalsMade','fieldGoalsAttempted','fieldGoalsPercentage','threePointersMade','threePointersAttempted','threePointersPercentage','freeThrowsMade','freeThrowsAttempted','freeThrowsPercentage','reboundsOffensive','reboundsDefensive','reboundsTotal','assists','steals','blocks','turnovers','foulsPersonal','points','plusMinusPoints']};stats['minutes']='PT48M00S'if positive else'PT00M00S';stats['points']=points if positive else 0
    players.append({'personId':base+i,'status':'ACTIVE'if i<6 else'INACTIVE','played':'1'if positive else'0','statistics':stats,'firstName':'Fixture','familyName':str(base+i)})
   return {'teamId':base,'teamTricode':name,'score':5*points,'players':players}
  p={'game':{'gameId':'0022600253','gameStatus':3,'gameTimeUTC':'2026-11-18T00:30:00Z','homeTeam':team('TOR',1000,11),'awayTeam':team('NYK',2000,10)}}
  g={'id':'espn_401910002','utc':'2026-11-18T00:30:00Z','home':'TOR','away':'NYK'};official={'id':'0022600253'}
  box,inactive,schedule=normalize(p,official,g);self.assertEqual(schedule['home_pts'],'55');self.assertEqual(schedule['away_pts'],'50')
  inactiveids={r['player_id']for r in inactive}
  raw={str(r['personId']):r for side in ['homeTeam','awayTeam']for r in p['game'][side]['players']}
  for r in box:
   if raw[r['person_id']]['status']=='ACTIVE'and raw[r['person_id']]['played']=='0'and not raw[r['person_id']].get('notPlayingReason'):
    self.assertEqual(r['comment'],'');self.assertNotIn(r['person_id'],inactiveids)
  broken=copy.deepcopy(p);broken['game']['homeTeam']['players'][0]['statistics']['points']+=1
  with self.assertRaisesRegex(ValueError,'team totals'):normalize(broken,official,g)
  with self.assertRaises(ValueError):normalize(p,{'id':'0022600254'},g)
 def test_preissue_runtime_and_frozen_predicates(self):
  meta=json.loads((HERE/'baseline_results_v2/REPLAY_METADATA.json').read_text())
  self.assertTrue(meta['pregame_team_update_applied']);self.assertTrue(meta['PR176_same_prediction_functions_verified']);self.assertTrue(meta['baseline_predictions_were_not_prospectively_frozen'])
  for r in meta['cohorts'].values():self.assertTrue(r['all_live_outcomes_predate_issue']);self.assertTrue(r['all_status_observations_predate_issue'])
 def test_fresh_status_full_cell_and_unresolved_team_gate(self):
  j=json.loads((HERE/'injury_fix/FRESH_OFFICIAL_NBA_STATUS.json').read_text());self.assertEqual(j['native_explicit_status_cells'],102);self.assertEqual(j['matched_rows'],101)
  atl=[t for t in j['team_report_states']if t['team']=='ATL'];self.assertEqual(len(atl),1);self.assertFalse(atl[0]['all_explicit_named_rows_resolved']);self.assertFalse(atl[0]['allow_missing_player_as_NOT_LISTED_feature'])
  for r in j['team_report_states']:
   if r['NOT_YET_SUBMITTED']:self.assertFalse(r['allow_missing_player_as_NOT_LISTED_feature'])
if __name__=='__main__':unittest.main()
