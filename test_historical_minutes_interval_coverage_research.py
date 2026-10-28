import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.historical_minutes_interval_coverage_research import build, cluster_by_player
from src.conditional_minutes_fp_research import MODEL

class HistoricalHoldoutChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=json.loads((DATA/"history/index.json").read_text(encoding="utf8"))
        cls.frozen=json.loads((DATA/"conditional_minutes_fp_research.json").read_text(encoding="utf8"))
        cls.now=datetime.now(timezone.utc)
        cls.loads=staticmethod(lambda name:json.loads((DATA/"history"/name).read_text(encoding="utf8")))
    def make(self,index=None,frozen=None):
        return build(index or self.index,self.loads,frozen or self.frozen,self.now)
    def test_replay_matches_current_untouched_holdout(self):
        r=self.make()
        saved=self.frozen["2025_26_untouched_early_season_played_holdout"]
        self.assertEqual(r["summary"]["played_cases"],saved["all"]["played_cases"])
        self.assertEqual(r["summary"]["distinct_players"],saved["distinct_players"])
        self.assertEqual(r["summary"]["distinct_NBA_games"],saved["distinct_NBA_games"])
        self.assertEqual(r["summary"]["minutes_dev_q90_coverage"],
                         saved["all"]["minutes_empirical_dev_q90_coverage"])
        self.assertEqual(r["summary"]["decomposed_FP_dev_q90_coverage"],
                         saved["all"]["decomposed_fp_empirical_dev_q90_coverage"])
        self.assertAlmostEqual(r["summary"]["paired_direct_minus_decomposed_FP_MAE_gain"],
                               0.0186,delta=0.0001)
        self.assertFalse(r["quality_gate"]["adopt_on_site"])
        self.assertFalse(r["quality_gate"]["can_train_from_absent_or_unknown_player"])
    def test_stratification_is_exact_partition_and_not_a_feature(self):
        r=self.make()
        count=r["summary"]["played_cases"]
        self.assertEqual(sum(x["played_cases"] for x in
             r["by_predicted_minutes_PREOUTCOME"].values()), count)
        self.assertEqual(sum(x["played_cases"] for x in
             r["by_actual_minutes_POSTGAME_DIAGNOSTIC_ONLY"].values()), count)
        self.assertEqual(sum(x["played_cases"] for x in
             r["by_first_2025_played_club_POSTGAME_ONLY"].values()), count)
        self.assertEqual(sum(x["played_cases"] for x in
             r["by_first_five_played_game_slot_POSTGAME_ONLY"].values()), count)
    def test_frozen_historical_rule_and_quantiles_cannot_be_changed(self):
        bad=deepcopy(self.frozen)
        bad["2024_25_chronological_development_residuals"]["q90_absolute_residual_dev_only"]["minutes"] += 1
        with self.assertRaises(ValueError):self.make(frozen=bad)
        bad=deepcopy(self.frozen)
        bad["frozen_rule_hash"]="not-original"
        with self.assertRaises(ValueError):self.make(frozen=bad)
        bad=deepcopy(self.frozen)
        bad["2025_26_untouched_early_season_played_holdout"]["all"]["minutes_MAE"]+=1
        with self.assertRaises(ValueError):self.make(frozen=bad)
    def test_incompatible_history_version_fails_closed(self):
        bad=deepcopy(self.index)
        bad["version"]="another"
        with self.assertRaises(ValueError):self.make(index=bad)
    def test_player_cluster_bootstrap_deterministic_under_repetition(self):
        rows=[]
        for i in range(120):
            for day in range(5):
                rows.append({"player_id":str(i),"paired_direct_minus_decomposed_FP_gain":
                             (0.5 if i%2 else -0.4),
                             "minutes_dev_q90_covered":int(day!=0),
                             "decomposed_FP_dev_q90_covered":int(day!=1)})
        a=cluster_by_player(rows,draws=120,seed=23)
        self.assertEqual(a,cluster_by_player(rows,draws=120,seed=23))
        self.assertTrue(a["paired_direct_minus_decomposed_FP_gain"]["lower"]<
                        a["paired_direct_minus_decomposed_FP_gain"]["upper"])
        self.assertTrue(0<=a["minutes_dev_q90_covered"]["lower"]<=1)

if __name__=="__main__":unittest.main()
