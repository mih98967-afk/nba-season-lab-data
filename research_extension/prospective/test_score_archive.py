import unittest
from datetime import datetime,timezone
from score_archive import archive_outcome,quarantine_overlap
NOW=datetime(2026,11,17,20,tzinfo=timezone.utc)
F={'nba_player_id':'123','nba_game_id':'0022600245','tipoff_utc':'2026-11-17T00:00:00Z','date_ET':'2026-11-16','team':'BOS','opponent':'ORL'}
G={('0022600245',):{'game':'0022600245','date':'2026-11-16','home':'BOS','away':'ORL'}}
def row(**extra):return {'pid':'123','game':'0022600245','date':'2026-11-16','team':'BOS','opp':'ORL','played':1.,'minutes':20.,'fp':12.,'comment':'',**extra}
class ArchiveTests(unittest.TestCase):
    def test_absence_not_zero(self):
        x=archive_outcome(F,G,{},NOW);self.assertEqual(x['outcome_archive'],'UNKNOWN');self.assertIsNone(x['y_fp'])
    def test_positive_needs_exact_identity(self):
        x=archive_outcome(F,G,{('0022600245','124'):row(pid='124')},NOW);self.assertEqual(x['outcome_archive'],'UNKNOWN')
        x=archive_outcome(F,G,{('0022600245','123'):row()},NOW);self.assertEqual(x['outcome_archive'],'PLAYED')
    def test_wrong_team_quarantined(self):
        x=archive_outcome(F,G,{('0022600245','123'):row(team='ORL',opp='BOS')},NOW);self.assertEqual(x['outcome_archive'],'UNKNOWN')
    def test_zero_minutes_without_comment_stays_unknown(self):
        x=archive_outcome(F,G,{('0022600245','123'):row(minutes=0.,played=float('nan'),fp=float('nan'))},NOW);self.assertEqual(x['outcome_archive'],'UNKNOWN')
    def test_explicit_comment_and_inactive_are_distinct(self):
        x=archive_outcome(F,G,{('0022600245','123'):row(minutes=0.,played=0.,fp=0.,comment="DNP-Coach's Decision")},NOW);self.assertEqual(x['outcome_archive'],'EXPLICIT_DNP')
        x=archive_outcome(F,G,{('0022600245','123'):row(minutes=0.,played=0.,fp=0.,comment='EXPLICIT_INACTIVE_LIST')},NOW);self.assertEqual(x['outcome_archive'],'OFFICIAL_INACTIVE')
    def test_fp_disagreement_quarantined_regardless_model(self):
        x=quarantine_overlap({'outcome_archive':'PLAYED','y_fp':12.},{'outcome_espn':'PLAYED','y_fp':13.});self.assertEqual(x['outcome_archive'],'UNKNOWN');self.assertEqual(x['archive_fp_before_quarantine'],12.);self.assertEqual(x['participation_verified'],1)
    def test_participation_conflict_quarantined(self):
        x=quarantine_overlap({'outcome_archive':'PLAYED','y_fp':0.},{'outcome_espn':'EXPLICIT_DNP','y_fp':0.});self.assertEqual(x['outcome_archive'],'UNKNOWN');self.assertIsNone(x['participation_verified'])
    def test_exact_agreement_retained(self):
        x=quarantine_overlap({'outcome_archive':'PLAYED','y_fp':-3.},{'outcome_espn':'PLAYED','y_fp':-3.});self.assertEqual(x['outcome_archive'],'PLAYED');self.assertEqual(x['espn_archive_overlap'],'exact_agreement')
if __name__=='__main__':unittest.main()
