import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd

from position_effects import POSITIONS, PositionalResidualEngine, build_position_features
from ingest_positions import read_roster, norm, HERE, ROOT


def rows():
    return pd.DataFrame([
        dict(date="2024-01-01", opp="DAL", game="a", pid="1", y_play=1, y_fp=12., fantasy_position="PG"),
        dict(date="2024-01-01", opp="DAL", game="a", pid="2", y_play=1, y_fp=7., fantasy_position="C"),
        dict(date="2024-01-01", opp="BOS", game="b", pid="3", y_play=1, y_fp=9., fantasy_position="PG"),
        dict(date="2024-01-02", opp="DAL", game="c", pid="1", y_play=1, y_fp=15., fantasy_position="PG"),
        dict(date="2024-01-03", opp="DAL", game="d", pid="1", y_play=1, y_fp=20., fantasy_position="PG"),
    ])


class PositionResidualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory()
        cls.data_dir=HERE/"results"
        if (HERE/"PUBLIC_ASSETS_MANIFEST.json").exists():
            from packed_assets import materialize_assets
            materialize_assets(HERE,Path(cls.temporary.name),["results/SEASON_POSITION_MAPPING.json"])
            cls.data_dir=Path(cls.temporary.name)/"results"

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
    def test_same_date_outcomes_never_enter_features(self):
        d=rows(); a,_=build_position_features(d,np.zeros(len(d)))
        changed=d.copy(); changed.loc[0,"y_fp"]=1e9
        b,_=build_position_features(changed,np.zeros(len(d)))
        np.testing.assert_array_equal(a.iloc[:3].values,b.iloc[:3].values)
        self.assertNotEqual(a.loc[3,"adj_general_residual"],b.loc[3,"adj_general_residual"])

    def test_future_outcome_cannot_change_earlier_features(self):
        d=rows(); a,_=build_position_features(d,np.zeros(len(d)))
        d.loc[4,"y_fp"]=-1e9; b,_=build_position_features(d,np.zeros(len(d)))
        np.testing.assert_array_equal(a.values,b.values)

    def test_day_order_is_batch_invariant(self):
        d=rows(); a,_=build_position_features(d,np.zeros(len(d)))
        order=[2,1,0,4,3]; perm=d.iloc[order].reset_index(drop=True)
        b,_=build_position_features(perm,np.zeros(len(perm)))
        np.testing.assert_allclose(a.values,b.iloc[np.argsort(order)].values)

    def test_unknown_is_not_assigned_a_five_position_signal(self):
        d=rows(); d.loc[4,"fantasy_position"]="UNKNOWN"
        a,_=build_position_features(d,np.zeros(len(d)))
        self.assertEqual(a.loc[4,"adj_position_residual_k30"],0)
        self.assertEqual(a.loc[4,"adj_position_residual_k100"],0)
        self.assertEqual(a.loc[4,"position_known"],0)
        self.assertGreater(a.loc[4,"adj_general_residual"],0)

    def test_unknown_outcomes_do_not_update(self):
        d=rows(); d.loc[0,"y_play"]=np.nan
        a,_=build_position_features(d,np.zeros(len(d)))
        d.loc[0,"y_fp"]=1e9; b,_=build_position_features(d,np.zeros(len(d)))
        np.testing.assert_array_equal(a.values,b.values)

    def test_missing_nuisance_does_not_enter_state(self):
        d=rows(); pre=np.zeros(len(d));pre[0]=np.nan
        a,_=build_position_features(d,pre)
        d.loc[0,"y_fp"]=1e9;b,_=build_position_features(d,pre)
        np.testing.assert_array_equal(a.values,b.values)

    def test_stronger_prior_reduces_interaction(self):
        a,_=build_position_features(rows(),np.zeros(5))
        self.assertTrue((a.adj_position_residual_k100.abs()<=a.adj_position_residual_k30.abs()+1e-12).all())

    def test_generic_effect_is_not_a_positional_interaction(self):
        data=[]
        for opp,general in [("DAL",5.),("BOS",-5.)]:
            for i,pos in enumerate(POSITIONS):
                data.append(dict(date="2024-01-01",opp=opp,game=opp,pid=f"{opp}{i}",fantasy_position=pos,residual=general+i*2.))
        engine=PositionalResidualEngine();engine.update_day(pd.DataFrame(data))
        for opp in ("DAL","BOS"):
            for pos in POSITIONS:
                got=engine.feature(opp,pos,"2024-01-02")
                self.assertAlmostEqual(got["adj_position_residual_k30"],0.,places=12)
                self.assertAlmostEqual(got["adj_position_residual_k100"],0.,places=12)

    def test_time_travel_fails_closed(self):
        engine=PositionalResidualEngine();engine.feature("DAL","PG","2024-02-01")
        with self.assertRaisesRegex(ValueError,"TIME_TRAVEL"):
            engine.feature("DAL","PG","2024-01-01")

    def test_wrong_alignment_fails(self):
        with self.assertRaisesRegex(ValueError,"ALIGNMENT"):
            build_position_features(rows(),np.zeros(2))

    def test_same_game_multiple_players_not_independent_game_count(self):
        data=rows().iloc[:2].copy();data["residual"]=data.y_fp
        engine=PositionalResidualEngine();engine.update_day(data)
        s=engine.opponents["DAL"].support()
        self.assertEqual(s["n_games"],1);self.assertEqual(s["effective_games"],1)
        self.assertEqual(s["n_players"],2)

    def test_position_source_is_season_specific(self):
        import json
        mapping=json.loads((self.data_dir/"SEASON_POSITION_MAPPING.json").read_text())
        self.assertFalse(mapping["historical_point_in_time_verified"])
        keys=[(r["season"],r["nba_person_id"]) for r in mapping["records"] if r["nba_person_id"]]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(all(r["nba_person_id"] for r in mapping["records"] if (r["games"] or 0)>0))

    def test_namesake_explicit_overrides(self):
        import json
        records=json.loads((self.data_dir/"SEASON_POSITION_MAPPING.json").read_text())["records"]
        lookup={(r["season"],r["source_row"]):r for r in records}
        self.assertEqual(lookup[(2024,422)]["english_name"],"Leaky Black")
        self.assertEqual(lookup[(2027,371)]["english_name"],"Karim López")
        self.assertEqual(lookup[(2027,528)]["english_name"],"Emanuel Sharp")
        self.assertEqual(lookup[(2027,224)]["english_name"],"Cameron Johnson")


if __name__=="__main__":
    unittest.main()
