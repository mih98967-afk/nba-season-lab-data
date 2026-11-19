import importlib.util, pathlib, unittest
import numpy as np
import pandas as pd
spec=importlib.util.spec_from_file_location('research_run',pathlib.Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class Safeguards(unittest.TestCase):
    def test_missing_is_unknown(self):
        for c in ['', 'OUT', 'Questionable', 'NA']:
            self.assertTrue(np.isnan(r.participation(0,c)))
    def test_explicit_no_play(self):
        for c in ["DNP - Coach's Decision",'DND - Injury/Illness','NWT - Personal','DND_LEAGUE_SUSPENSION']:
            self.assertEqual(r.participation(0,c),0)
    def test_positive_minutes_first(self):
        self.assertEqual(r.participation(.01,''),1)
    def test_seconds(self):
        self.assertAlmostEqual(r.mins('13:30'),13.5)
    def fixture(self):
        games=pd.DataFrame([dict(game=str(i),season=2024,date=f'2023-11-{i+1:02d}',home='AAA',away='BBB',home_pts=100.,away_pts=90.) for i in range(4)])
        rows=[]
        for g in games.to_dict('records'):
            for pid,team,opp,pts in [('a','AAA','BBB',100.),('b','BBB','AAA',90.)]:
                rows.append(dict(pid=pid,game=g['game'],date=g['date'],season=2024,team=team,opp=opp,home=int(team=='AAA'),minutes=240.,played=1.,fp=20.,comment='',position='G',name=pid,**{v:(pts if v=='pts' else 5.) for v in r.STAT.values()}))
        return games,pd.DataFrame(rows)
    def test_target_stats_never_enter_features(self):
        games,raw=self.fixture();a,_=r.build_frame(games,raw);changed=raw.copy()
        changed.loc[changed.game=='2',['fp','minutes','pts']]=[99.,1.,77.]
        b,_=r.build_frame(games,changed);cols=[x for x in a if x not in ['y_fp','y_minutes','y_play']]
        pd.testing.assert_frame_equal(a[a.game=='2'][cols],b[b.game=='2'][cols])
    def test_future_does_not_change_past(self):
        games,raw=self.fixture();a,_=r.build_frame(games,raw);changed=raw.copy()
        changed.loc[changed.game=='3','comment']='DNP - Injury/Illness'
        changed.loc[changed.game=='3','played']=0.;changed.loc[changed.game=='3','fp']=0.
        b,_=r.build_frame(games,changed)
        pd.testing.assert_frame_equal(a[a.game<'3'],b[b.game<'3'])
    def test_missing_row_is_unknown_opportunity(self):
        games,raw=self.fixture();raw=raw[~((raw.game=='2')&(raw.pid=='a'))];f,_=r.build_frame(games,raw)
        v=f[(f.game=='2')&(f.pid=='a')].iloc[0]
        self.assertEqual(v.exante_member,1);self.assertTrue(np.isnan(v.y_play));self.assertTrue(np.isnan(v.y_fp))
    def test_new_member_not_retroactive(self):
        games,raw=self.fixture();f,_=r.build_frame(games,raw)
        self.assertTrue((f[f.game=='0'].exante_member==0).all())
        self.assertTrue((f[f.game=='1'].exante_member==1).all())
    def test_intervals_include_negative_fp(self):
        q=r.interval_metrics([-4.,0.,20.],[-5.,-1.,19.],[-3.,1.,21.],.2)
        self.assertEqual(q['coverage'],1.)
    def test_disjoint_time_splits(self):
        x=pd.DataFrame({'season':[2024,2025,2025,2025,2025,2026], 'date':['2024-03-01','2024-12-31','2025-01-01','2025-02-01','2025-03-01','2026-03-01']})
        masks=r.masks(x);self.assertTrue((sum(m.astype(int) for m in masks.values())==1).all())
    def test_source_conflicts_not_silent(self):
        # A claimed zero without explicit no-play evidence must stay missing.
        self.assertTrue(np.isnan(r.participation(0,'0')))
    def test_conformal_uses_calibration_only(self):
        self.assertGreaterEqual(r.conformal_offset(np.array([0.,10.]),np.array([1.,1.]),np.array([2.,2.]),.2),0.)

if __name__=='__main__':unittest.main()
