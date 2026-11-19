import pathlib,tempfile,unittest
import numpy as np
import pandas as pd
import availability as a
import test_research as tests_base

class AvailabilityTests(unittest.TestCase):
    def test_exact_inactive_is_added(self):
        games,raw=tests_base.Safeguards().fixture();r=pd.DataFrame([dict(game_id='2',player_id='c',team_abbreviation='AAA',first_name='C',last_name='Player')])
        m,qa=a.merge_inactive(games,raw,r);v=m[m.pid=='c'].iloc[0]
        self.assertEqual(v.played,0.);self.assertEqual(v.fp,0.);self.assertEqual(v.comment,'EXPLICIT_INACTIVE_LIST');self.assertEqual(qa['new_explicit_inactive'],1)
    def test_inactive_positive_conflict_quarantined(self):
        games,raw=tests_base.Safeguards().fixture();r=pd.DataFrame([dict(game_id='2',player_id='a',team_abbreviation='AAA')])
        m,qa=a.merge_inactive(games,raw,r);v=m[(m.pid=='a')&(m.game=='2')].iloc[0]
        self.assertTrue(np.isnan(v.played));self.assertTrue(np.isnan(v.fp));self.assertEqual(qa['quarantined_conflict'],1)
    def test_wrong_team_rejected(self):
        games,raw=tests_base.Safeguards().fixture();r=pd.DataFrame([dict(game_id='2',player_id='c',team_abbreviation='CCC')])
        with self.assertRaisesRegex(ValueError,'TEAM_MISMATCH'):a.merge_inactive(games,raw,r)
    def test_duplicate_inactive_rejected(self):
        games,raw=tests_base.Safeguards().fixture();r=pd.DataFrame([dict(game_id='2',player_id='c',team_abbreviation='AAA')]*2)
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):a.merge_inactive(games,raw,r)
    def test_no_play_mixture_negative_not_lost(self):
        # Half uniform(-10,+10) and half zero: lower 10% quantile is -6, not 0.
        v=a.mixture_quantiles([[-10.,10.]],[0.,1.],[.5],[.1,.5,.9])
        np.testing.assert_allclose(v,[[-6.,0.,6.]])
    def test_certain_play_matches_conditional(self):
        v=a.mixture_quantiles([[-5.,15.]],[0.,1.],[1.],[.1,.5,.9])
        np.testing.assert_allclose(v,[[-3.,5.,13.]])
    def test_certain_dnp_is_zero(self):
        np.testing.assert_array_equal(a.mixture_quantiles([[-5.,15.]],[0.,1.],[0.],[.1,.5,.9]),[[0.,0.,0.]])
    def test_mixture_quantiles_monotone(self):
        rng=np.random.default_rng(1);q=rng.normal(10,10,(50,7));p=rng.random(50)
        x=a.mixture_quantiles(q,[.025,.1,.25,.5,.75,.9,.975],p,[.025,.1,.25,.5,.75,.9,.975])
        self.assertTrue((np.diff(x,axis=1)>=0).all())
    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):a.mixture_quantiles([[1.,3.]],[0.,1.],[1.2],[.5])
    def test_unknown_report_not_available(self):
        games,raw=tests_base.Safeguards().fixture();f,_=a.base.build_frame(games,raw);d=a.injury_features(f,{})
        self.assertTrue((d.inj_available==0).all());self.assertTrue((d.inj_not_listed==0).all());self.assertTrue((d.inj_team_submitted==0).all())
    def test_new_player_not_in_teammate_burden(self):
        f=pd.DataFrame([dict(game='g',pid='a',team='AAA',date='2024-01-02',exante_member=1,history_n=10,min10=30.,fp10=20.),dict(game='g',pid='b',team='AAA',date='2024-01-02',exante_member=0,history_n=10,min10=35.,fp10=30.)])
        ix={('g','AAA'):dict(issue='2024-01-01 22:00:00',submitted=True,players={'b':'Out'},uncertain=set())}
        v=a.injury_features(f,ix);self.assertEqual(v.iloc[0].inj_teammate_out_minutes,0.)
    def test_report_latest_snapshot_and_strict_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'upstream').mkdir();games=[]
            cols=['season','report_datetime','game_date','team_id','game_id','person_id','current_status','match_method','reason']
            for year in (2024,2025,2026):
                gid=str(year);date=f'{year}-01-02';prev=f'{year}-01-01'
                games.append(dict(game=gid,season=year,date=date,home='AAA',away='BBB'))
                pd.DataFrame([dict(game_id=gid,home_team_id='1',home_team_abbreviation='AAA',away_team_id='2',away_team_abbreviation='BBB')]).to_csv(root/'upstream'/f'nba_schedule_{year}.csv.gz',index=False)
                rr=[(year,prev+' 20:00:00',date,'1',gid,'a','Out','exact','Injury'),(year,prev+' 23:00:00',date,'1',gid,'b','Probable','exact','Injury'),(year,date+' 10:00:00',date,'1',gid,'a','Out','exact','Injury')]
                pd.DataFrame(rr,columns=cols).to_csv(root/'upstream'/f'injury_report_{year}.csv.gz',index=False)
            ix,qa=a.injury_index(root,pd.DataFrame(games));s=ix[('2024','AAA')]
            self.assertNotIn('a',s['players']);self.assertEqual(s['players']['b'],'Probable');self.assertEqual(s['issue'],'2024-01-01 23:00:00')

if __name__=='__main__':unittest.main()
