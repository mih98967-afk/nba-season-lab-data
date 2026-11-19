"""Guardrails for multi-lead forecasts; all fixtures are synthetic."""
import copy, datetime as dt, pathlib, tempfile, unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import horizon_data as h
from train_horizons import boundary_checks,sets
import test_research as base_tests

class HorizonSafeguards(unittest.TestCase):
    def fixture(self):
        return base_tests.Safeguards().fixture()
    def test_state_excludes_issue_date_outcomes(self):
        games,raw=self.fixture();s=h.HistoryState(games,raw);s.advance_before('2023-11-03')
        self.assertEqual(len(s.states['a']['played']),2)
        self.assertEqual(s.states['a']['last_day'],dt.date(2023,11,2).toordinal())
    def test_future_mutation_cannot_change_frozen_features(self):
        games,raw=self.fixture();changed=raw.copy();changed.loc[changed.date>='2023-11-03',['fp','minutes','pts']]=[200.,20.,200.]
        a=h.HistoryState(games,raw);b=h.HistoryState(games,changed)
        for s in (a,b):s.advance_before('2023-11-03')
        day=dt.date(2023,11,3).toordinal()
        self.assertEqual(h.b.player_features(a.states['a'],day,'AAA'),h.b.player_features(b.states['a'],day,'AAA'))
        self.assertEqual(a.team_features('AAA',day),b.team_features('AAA',day))
    def test_state_does_not_advance_twice(self):
        games,raw=self.fixture();s=h.HistoryState(games,raw);s.advance_before('2023-11-03');s.advance_before('2023-11-03')
        self.assertEqual(len(s.states['a']['played']),2)
    def test_injury_snapshot_strict_issuance_cutoff(self):
        x=h.InjurySnapshots.__new__(h.InjurySnapshots);key=('g','AAA');x.data={key:[{'stamp':'2025-01-01 23:30:00','players':{'a':'Out'}},{'stamp':'2025-01-02 00:00:00','players':{'a':'Available'}}]};x.times={key:[r['stamp'] for r in x.data[key]]}
        self.assertEqual(x.before('g','AAA','2025-01-02')['players']['a'],'Out')
        self.assertIsNone(x.before('g','AAA','2025-01-01'))
    def test_unobserved_report_is_not_healthy(self):
        f=h.status_features(None,'a','2025-01-01','health_')
        self.assertEqual(f['health_available'],0);self.assertEqual(f['health_not_listed'],0);self.assertEqual(f['health_present'],0)
    def test_horizon_split_boundaries_are_purged(self):
        d=pd.DataFrame({'season':[2024,2025,2025,2025,2025,2026],'issue_date':['2024-03-01','2024-11-30','2025-01-10','2025-02-21','2025-03-22','2025-10-01'],'date':['2024-03-29','2024-12-28','2025-02-07','2025-03-21','2025-04-19','2025-10-29']})
        masks=h.horizon_masks(d);self.assertTrue((sum(m.astype(int) for m in masks.values())==1).all());self.assertEqual(len(boundary_checks(d,masks)),5)
    def test_bad_boundary_raises(self):
        d=pd.DataFrame({'date':['2025-01-05','2025-01-10'],'issue_date':['2024-12-01','2025-01-01']})
        a=np.array([True,False]);b=~a;m={k:b for k in ['select','pcal','ical','confirm','audit']};m['train']=a
        with self.assertRaises(AssertionError):boundary_checks(d,m)
    def test_targets_metadata_are_not_features(self):
        d=pd.DataFrame(columns=list(h.META)+['fp10','home','team_pts10','opp_drtg10','inj_out','health_out','horizon_days'])
        f=sets(d)
        self.assertFalse(set(f['all'])&h.META);self.assertNotIn('health_out',f['context']);self.assertIn('horizon_days',f['form'])
    def test_final_schedule_does_not_import_future_rating(self):
        games,raw=self.fixture();s=h.HistoryState(games,raw);s.advance_before('2023-11-03')
        before=s.team_features('AAA',dt.date(2023,11,3).toordinal());rating=before['elo']
        self.assertEqual(rating,s.team_features('AAA',dt.date(2023,11,3).toordinal())['elo'])
        self.assertEqual(before['pts10'],(200.+5*112.)/7)

if __name__=='__main__':unittest.main()
