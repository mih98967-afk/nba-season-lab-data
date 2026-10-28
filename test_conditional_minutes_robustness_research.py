"""Live-fixture provenance and synthetic 8-date date-cluster tests."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from src.sync import DATA
from src.conditional_minutes_robustness_research import (
    build, validate, cluster_bootstrap_by_ET_date, MIN_ET_DATES, MIN_PLAYED, MIN_GAMES,
)

class Robustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evaluation=json.loads((DATA/"conditional_minutes_fp_evaluation_research.json").read_text(encoding="utf8"))
        cls.frozen=json.loads((DATA/"conditional_minutes_fp_research.json").read_text(encoding="utf8"))
        cls.now=datetime.now(timezone.utc)
    def test_real_issued_44_scored_and_no_unsound_interval(self):
        report=build(self.evaluation,self.frozen,self.now)
        counts=self.evaluation["summary"]
        self.assertEqual(report["summary"]["played_scored_conditional"],counts["played"])
        self.assertEqual(report["summary"]["finished_checked"],counts["finished_checked"])
        self.assertEqual(report["summary"]["explicit_DNP_not_scored_as_zero"],
                         counts["explicit_DNP_not_scored"])
        self.assertEqual(report["summary"]["UNKNOWN_not_imputed"],
                         counts["UNKNOWN_not_imputed"])
        self.assertEqual(report["summary"]["independent_ET_date_clusters"],
                         counts["played_distinct_ET_dates"])
        self.assertEqual(report["ET_date_cluster_paired_MAE_gain_95pct_interval_if_eligible"],None)
        self.assertFalse(report["quality_gate"]["adopt_on_site"])
        self.assertFalse(report["quality_gate"]["unconditional_FP_allowed"])
    def test_tampered_source_issue_hash_or_prediction_rejected(self):
        bad=deepcopy(self.frozen)
        bad["issued"][0]["min_if_play"]+=1
        with self.assertRaises(ValueError):build(self.evaluation,bad,self.now)
        e=deepcopy(self.evaluation)
        e["scored_played"][0]["predicted_minutes"]+=1
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)
    def test_unknown_never_zero_and_wrong_team_rejected(self):
        e=deepcopy(self.evaluation)
        self.assertTrue(e["UNKNOWN_unscored"])
        e["UNKNOWN_unscored"][0]["actual_fp_reconstructed"]=0
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)
        e=deepcopy(self.evaluation)
        e["scored_played"][0]["team"]="INVALID"
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)
        e=deepcopy(self.evaluation)
        e["explicit_DNP_not_in_conditional_metrics"][0]["not_scored_as_zero_FP"]=False
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)
    def test_future_postgame_clock_rejected(self):
        e=deepcopy(self.evaluation)
        e["scored_played"][0]["postgame_first_seen_at_utc"]="2030-01-01T00:00:00Z"
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)
    def test_prospective_day_bootstrap_fixed_seed_with_sufficient_days(self):
        rows=[]
        for day in range(MIN_ET_DATES):
            for case in range(max(14,MIN_PLAYED//MIN_ET_DATES+1)):
                rows.append({"ET_date":f"2026-11-{day+1:02d}",
                             "game_id":f"espn_test_{day}_{case%3}",
                             "paired_absolute_FP_gain": 1.5 if day%2==0 else -0.5})
        self.assertGreaterEqual(len(rows),MIN_PLAYED)
        self.assertGreaterEqual(len({r["game_id"] for r in rows}),MIN_GAMES)
        result=cluster_bootstrap_by_ET_date(rows)
        self.assertIsNotNone(result)
        self.assertEqual(result,cluster_bootstrap_by_ET_date(rows))
        self.assertLess(result["lower"],result["upper"])
        self.assertEqual(result["resampling_unit"],
                         "NBA_ET_date_with_all_verified_played_player_games")
        self.assertFalse(result["can_establish_full_population_effect"])
    def test_game_cluster_gate_never_substitutes_for_ET_dates(self):
        rows=[{"ET_date":"2026-11-01","game_id":f"g{i}",
               "paired_absolute_FP_gain":0.2} for i in range(150)]
        self.assertIsNone(cluster_bootstrap_by_ET_date(rows))
        self.assertIsNone(cluster_bootstrap_by_ET_date(rows[:12]))
    def test_no_predicted_2026_27_outcomes_backdated(self):
        e=deepcopy(self.evaluation)
        e["scored_played"][0]["minutes_issued_at_utc"]= "2026-10-28T08:00:00Z"
        with self.assertRaises(ValueError):build(e,self.frozen,self.now)

if __name__=="__main__":
    unittest.main()
