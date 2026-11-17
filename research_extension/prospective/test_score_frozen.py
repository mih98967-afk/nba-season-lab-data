import unittest
from copy import deepcopy
from datetime import datetime, timezone
from score_frozen import outcome_for, unique_index, identity_crosswalk, evaluate
NOW=datetime(2026,11,17,19,30,tzinfo=timezone.utc)
F={'nba_player_id':'123','nba_game_id':'0022600245','calendar_game_id':'espn_1','tipoff_utc':'2026-11-17T00:00:00Z','team':'BOS','opponent':'ORL'}
def fixture():
    game={'id':'espn_1','utc':F['tipoff_utc'],'home':'BOS','away':'ORL','status':'final'}
    return {'game_index':{('espn_1',):game},'row_index':{}},{'event_index':{},'checked_game_evidence':{}},{},{'123':'n1'}
class OutcomeTests(unittest.TestCase):
    def test_absence_is_unknown(self):
        l,d,o,i=fixture();r=outcome_for(F,l,d,o,i,NOW)
        self.assertEqual(r['outcome_espn'],'UNKNOWN');self.assertIsNone(r['y_fp'])
    def test_positive_exact_game(self):
        l,d,o,i=fixture();l['row_index'][('espn_1','n1')]={'team':'BOS','utc':F['tipoff_utc'],'played':True,'minutes':1.,'fp':-3.,'source_url':'url'}
        r=outcome_for(F,l,d,o,i,NOW);self.assertEqual(r['outcome_espn'],'PLAYED');self.assertEqual(r['y_fp'],-3.)
    def test_future_not_dnp(self):
        l,d,o,i=fixture();f={**F,'tipoff_utc':'2026-11-18T00:00:00Z'}
        self.assertEqual(outcome_for(f,l,d,o,i,NOW)['outcome_espn'],'FUTURE')
    def test_wrong_team_quarantined(self):
        l,d,o,i=fixture();l['row_index'][('espn_1','n1')]={'team':'ORL','utc':F['tipoff_utc'],'played':True,'minutes':1.,'fp':3.}
        self.assertEqual(outcome_for(F,l,d,o,i,NOW)['outcome_espn'],'UNKNOWN')
    def test_explicit_dnp_requires_checked_game(self):
        l,d,o,i=fixture();d['event_index'][('espn_1','n1')]={'team':'BOS','game_utc':F['tipoff_utc'],'evidence':'explicit_espn_didNotPlay_true','observed_at_utc':'2026-11-17T10:00:00Z'}
        self.assertEqual(outcome_for(F,l,d,o,i,NOW)['outcome_espn'],'UNKNOWN')
        d['checked_game_evidence']['espn_1']={'game_utc':F['tipoff_utc'],'home':'BOS','away':'ORL','verified_at_utc':'2026-11-17T10:00:00Z'}
        self.assertEqual(outcome_for(F,l,d,o,i,NOW)['outcome_espn'],'EXPLICIT_DNP')
    def test_duplicate_identity_is_rejected(self):
        v={'confidence':'high','nba_id':'123'}
        self.assertEqual(identity_crosswalk({'players':{'n1':v,'n2':v}}),{})
        with self.assertRaises(ValueError):unique_index([{'x':1},{'x':1}],['x'])
    def test_official_negative_stays_separate(self):
        l,d,o,i=fixture();o[('espn_1','n1')]={'independent_NBA_verdict':'VERIFIED_GAME_DAY_INACTIVE','historical_identity_strength':'high','historical_nba_id_if_high':'123','team':'BOS','game_utc':F['tipoff_utc'],'source_game_id':F['nba_game_id'],'source_url':'https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022600245.json','source_canonical_sha256':'a'*64,'official_game_day_team_membership_verified':True,'conflict_requires_review':False,'source_first_observed_at_utc':'2026-11-17T10:00:00Z'}
        r=outcome_for(F,l,d,o,i,NOW);self.assertEqual(r['outcome_espn'],'UNKNOWN');self.assertEqual(r['outcome_augmented'],'OFFICIAL_INACTIVE')
        o[('espn_1','n1')]['source_game_id']='0022600246'
        self.assertEqual(outcome_for(F,l,d,o,i,NOW)['outcome_augmented'],'UNKNOWN')
    def test_unknown_does_not_enter_metrics(self):
        r={'outcome_espn':'UNKNOWN','p_play':.9,'baseline_p_play':.5}
        v=evaluate([r],'outcome_espn');self.assertEqual(v['participation']['frozen_candidate']['n'],0);self.assertEqual(v['counts']['UNKNOWN'],1)
if __name__=='__main__':unittest.main()
