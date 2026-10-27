import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.participation_evidence_ledger_research import build

FILES=("p_play_shadow_research.json","p_play_selection_bias_audit.json",
       "explicit_dnp_research.json","live.json",
       "official_out_boxscore_evidence_research.json",
       "official_nba_gameday_status_research.json",
       "official_nba_inactive_summary_research.json")
def archive():
    return [json.loads((DATA / name).read_text(encoding="utf8")) for name in FILES]
class EvidenceLedger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=archive()
        cls.now=datetime.now(timezone.utc)
    def test_live_audit_has_exact_coverage_and_never_promotes_unknown(self):
        result=build(*self.inputs,self.now)
        self.assertEqual(result["issued_total_including_future"],
                         len(self.inputs[0]["issued"]))
        self.assertEqual(result["overall_selected_opportunity_coverage"]["finished_checked"],
                         self.inputs[1]["finished_checked"])
        self.assertEqual(result["overall_selected_opportunity_coverage"]["outcome_UNKNOWN"],
                         self.inputs[1]["unknown_postgame_results"])
        self.assertEqual(result["current_OUT_queue"],
                         self.inputs[1]["official_OUT_unknown_review_priority_count"])
        self.assertFalse(result["quality_gate"]["adopt_on_site"])
        self.assertFalse(result["quality_gate"]["training_from_UNKNOWN_allowed"])
        self.assertTrue(all(x["original_label_still_UNKNOWN"] for x in result["unknown_cases"]))
    def test_no_inference_from_unlisted_source(self):
        args=deepcopy(self.inputs)
        args[5]["records"][0]["model_training_negative"]=True
        with self.assertRaises(ValueError):
            build(*args,self.now)
    def test_stale_selection_is_rejected(self):
        args=deepcopy(self.inputs)
        args[1]["verified_postgame_results"]+=1
        with self.assertRaises(ValueError):
            build(*args,self.now)
    def test_fake_deployment_rejected(self):
        args=deepcopy(self.inputs)
        args[6]["adopt_on_site"]=True
        with self.assertRaises(ValueError):
            build(*args,self.now)
    def test_future_outcome_observation_rejected(self):
        args=deepcopy(self.inputs)
        args[0]["observations"][0]["source_first_observed_at_utc"]="2030-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            build(*args,self.now)
    def test_original_out_queue_mutation_rejected(self):
        args=deepcopy(self.inputs)
        args[4]["records"][0]["team"]="XX"
        with self.assertRaises(ValueError):
            build(*args,self.now)
if __name__=="__main__":
    unittest.main()
