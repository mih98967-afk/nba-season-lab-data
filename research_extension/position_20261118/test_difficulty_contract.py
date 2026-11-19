import json
import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd

from build_difficulty import HERE,load_reference,general_deltas,residual_statistics,historical_position_digest
from packed_assets import materialize_assets
from position_effects import POSITIONS,build_position_features


class DifficultyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory()
        if (HERE/"PUBLIC_ASSETS_MANIFEST.json").exists():
            materialize_assets(HERE,Path(cls.temporary.name),["results/"+n for n in ("GENERAL_REFERENCE.json","general_ridge_reference.pkl","general_reference_covariance.npz","historical_residual_anchor.csv.gz")])
            assets=Path(cls.temporary.name)/"results"
        else:assets=HERE/"results"
        cls.reference,cls.metadata,cls.covariance=load_reference(assets)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def fixture(self):
        fields=self.reference["features"]
        values=self.reference["model"][0].statistics_
        rows=[]
        for i in range(30):
            row=dict(zip(fields,values))
            row.update(pid=f"p{i}",game=f"g{i}",date="2026-11-19",issue_date="2026-11-18",team=f"T{i:02}",opp=f"T{(i+1)%30:02}",team_elo=1470.+2*i,opp_elo=1450.+3*i)
            row["opp_poss10"]=95.+i/4
            rows.append(row)
        return pd.DataFrame(rows)

    def test_calendar_fixture_count_does_not_reweight_reference(self):
        frame=self.fixture()
        a,meta=general_deltas(frame,self.reference,self.covariance)
        repeated=pd.concat([frame,frame.iloc[:15],frame.iloc[:4]],ignore_index=True)
        b,other=general_deltas(repeated,self.reference,self.covariance)
        self.assertEqual(meta["players"],other["players"])
        for team in a:
            self.assertAlmostEqual(a[team]["delta"],b[team]["delta"],places=12)

    def test_incoherent_opponent_information_fails_closed(self):
        frame=self.fixture();dup=frame.iloc[[0]].copy();dup["opp_poss10"]+=1
        with self.assertRaisesRegex(ValueError,"INCOHERENT_OPPONENT"):
            general_deltas(pd.concat([frame,dup]),self.reference,self.covariance)

    def test_missing_team_is_not_silently_average_neutral(self):
        with self.assertRaisesRegex(ValueError,"COMPLETE_30_OPPONENT"):
            general_deltas(self.fixture().iloc[:-1],self.reference,self.covariance)

    def test_future_residuals_are_forbidden(self):
        d=pd.DataFrame([dict(date="2026-11-18",season=2027,game="g",pid="p",opp="DAL",fantasy_position="PG",residual=1.)])
        with self.assertRaisesRegex(ValueError,"PRECEDE_ASOF"):
            residual_statistics(d,"2026-11-18")

    def test_daily_effect_matches_asof_feature_engine(self):
        data=[]
        for day in ("2026-11-16","2026-11-17"):
            for j,opp in enumerate(("DAL","BOS")):
                for i,pos in enumerate(POSITIONS):
                    data.append(dict(date=day,season=2027,game=f"{day}{opp}",pid=f"p{i}",opp=opp,fantasy_position=pos,residual=(i+1.)*(j+1),y_play=1.,y_fp=(i+1.)*(j+1)))
        d=pd.DataFrame(data)
        _,engine=build_position_features(d,np.zeros(len(d)))
        current=residual_statistics(d,"2026-11-18")
        for team in ("DAL","BOS"):
            for pos in POSITIONS:
                expected=engine.feature(team,pos,"2026-11-18")["adj_position_residual_k100"]
                self.assertAlmostEqual(expected,current[team][pos]["effect"],places=12)

    def test_effect_uncertainty_is_finite_and_separate_from_game_prediction(self):
        values,_=general_deltas(self.fixture(),self.reference,self.covariance)
        for row in values.values():
            self.assertTrue(np.isfinite(row["interval95"]).all())
            self.assertLessEqual(row["interval95"][0],row["delta"])
            self.assertGreaterEqual(row["interval95"][1],row["delta"])
        self.assertIn("not prediction intervals",self.metadata["limits"])

    def test_proven_history_overlay_has_only_different_exact_ids(self):
        data=json.loads((HERE/"results/catalog_history_corrections.json").read_text())
        self.assertEqual(data["correction_count"],5)
        for item in data["corrections"]:
            self.assertNotEqual(item["current_nba_person_id"],item["wrong_history_nba_person_id"])
            self.assertFalse(item["legacy_seed_use_allowed"])
            self.assertFalse(item["nba_id_boxscore_model_features_affected"])

    def test_historical_digest_ignores_current_changes_but_detects_history_changes(self):
        mapping={"records":[{"season":2024,"nba_person_id":"1","fantasy_position":"PG"},{"season":2027,"nba_person_id":"1","fantasy_position":"SG"}]}
        original=historical_position_digest(mapping)
        mapping["records"][1]["fantasy_position"]="C"
        self.assertEqual(original,historical_position_digest(mapping))
        mapping["records"][0]["fantasy_position"]="C"
        self.assertNotEqual(original,historical_position_digest(mapping))

    def test_changed_encoded_chunk_is_rejected_before_decoding(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            package=Path(folder)/"package";package.mkdir();(package/"chunk.b64").write_bytes(b"changed")
            manifest={"schema":"nba-position-public-assets-v1","files":{"x":{"encoding":"base64","size_bytes":1,"sha256":"expected","storage":[{"path":"chunk.b64","sha256":hashlib.sha256(b"original").hexdigest()}]}}}
            (package/"PUBLIC_ASSETS_MANIFEST.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"CHUNK_HASH"):
                materialize_assets(package,Path(folder)/"output")


if __name__=="__main__":unittest.main()
