import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.p_play_precommitted_paired_evaluation import evaluate,_sharp_bounds

class PairedProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=[json.loads((DATA/n).read_text(encoding="utf8")) for n in
            ("p_play_shadow_research.json",
             "historical_prior_prospective_shadow_research.json",
             "explicit_dnp_research.json","live.json")]
        cls.now=datetime.now(timezone.utc)
    def test_live_data_advances_without_retroactive_predictions(self):
        x=evaluate(*self.inputs,self.now)
        self.assertEqual(x["p_play_first_issued_total"],len(self.inputs[0]["issued"]))
        self.assertEqual(x["historical_prelock_overlapping_issued_total"],len(self.inputs[1]["issued"]))
        self.assertEqual(x["paired_cohort"]["verified_pairs"],len(self.inputs[1]["observed"]))
        self.assertEqual(
            x["paired_cohort"]["issued"],
            x["paired_cohort"]["verified_pairs"]
            + x["paired_cohort"]["outcome_UNKNOWN"]
            + x["paired_cohort"]["waiting_historical_reconciliation"]
            + x["paired_cohort"]["awaiting_finished_checked_game"]
            + x["paired_cohort"]["final_game_not_independently_DNP_checked"])
        if len(self.inputs[1]["observed"]) == 0:
            self.assertIsNone(x["verified_only_matched_proper_scores"])
        else:
            self.assertEqual(
                x["verified_only_matched_proper_scores"]["verified_player_games"],
                len(self.inputs[1]["observed"]))
        if (x["paired_cohort"]["verified_pairs"] < 100
            or x["verified_only_matched_proper_scores"] is None
            or x["verified_only_matched_proper_scores"]["verified_ET_dates"] < 8):
            self.assertIsNone(x["ET_date_cluster_bootstrap_if_sufficient"])
        self.assertFalse(x["fixed_protocol_gates"]["adopt_on_site"])
        self.assertTrue(x["by_NBA_ET_date"])
    def test_changed_historical_prediction_is_quarantined(self):
        x=deepcopy(self.inputs)
        x[1]["issued"][0]["current_pplay_candidate_frozen"]=0.42
        with self.assertRaises(ValueError):evaluate(*x,self.now)
    def test_future_dated_historical_issue_is_rejected(self):
        x=deepcopy(self.inputs)
        x[1]["issued"][0]["historical_proxy_issued_at_utc"]="2030-01-01T00:00:00Z"
        with self.assertRaises(ValueError):evaluate(*x,self.now)
    def test_full_unknown_bounds_are_not_assumed_negatives(self):
        x=[{"classification":"UNKNOWN","probabilities":{
              "current_candidate":0.9,"current_baseline":0.5,
              "frozen_historical_appearance_proxy":0.1},"actual_played":None}]
        result=_sharp_bounds(x)
        d=result["sharp_missing_label_gain_range"]["Brier"]["current_candidate_over_current_baseline"]
        self.assertAlmostEqual(d["lower_gain"],-0.56,places=5)
        self.assertAlmostEqual(d["upper_gain"],0.24,places=5)
        self.assertTrue(result["not_a_confidence_interval"])
    def test_no_false_dnp_from_implicit_missing(self):
        x=evaluate(*self.inputs,self.now)
        self.assertTrue(x["unknown_never_mapped_to_DNP"])
        self.assertFalse(x["fixed_protocol_gates"]["representative_population_p_play_validated"])

if __name__=="__main__":
    unittest.main()
