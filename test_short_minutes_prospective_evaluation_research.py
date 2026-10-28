import json,unittest
from copy import deepcopy
from datetime import datetime,timezone
from src.sync import DATA
from src.short_minutes_prospective_evaluation_research import build,date_cluster_paired_uncertainty,MIN_ET_DATES,MIN_GAMES,MIN_PLAYED
class Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads((DATA/"short_minutes_prospective_research.json").read_text())
  cls.m=json.loads((DATA/"conditional_minutes_fp_research.json").read_text())
  cls.e=json.loads((DATA/"conditional_minutes_fp_evaluation_research.json").read_text())
 def make(self,r=None,m=None,e=None):
  return build(r or self.r,m or self.m,e or self.e,datetime.now(timezone.utc))
 def test_real_pending_denominator(self):
  v=self.make();s=v["summary"]
  self.assertEqual(s["issued"],sum(s[k] for k in ("played_verified","explicit_DNP_excluded","UNKNOWN_not_imputed","awaiting_or_unchecked")))
  self.assertEqual(s["issued"],len(v["outcome_audit"]))
  self.assertFalse(v["quality_gate"]["adopt_on_site"])
  if not s["played_verified"]:self.assertIsNone(v["conditional_played_only_metrics"]["Brier_group"])
  self.assertIsNone(v["paired_global_minus_group_uncertainty_if_eligible"])
  self.assertFalse(v["precommitted_exploratory_date_cluster_gates"]["interval_eligible"])
 def test_changed_first_issue_rejected(self):
  r=deepcopy(self.r);r["issued"][0]["risk_first_issued_at_utc"]=r["issued"][0]["individual_lock_utc"]
  with self.assertRaises(ValueError):self.make(r=r)
 def test_modified_original_prediction_rejected(self):
  m=deepcopy(self.m);m["issued"][-1]["min_if_play"]+=1
  with self.assertRaises(ValueError):self.make(m=m)
 def test_bad_probability_rejected_even_before_match(self):
  r=deepcopy(self.r);r["issued"][0]["group_dev_short_given_played_probability"]=-1
  with self.assertRaises(ValueError):self.make(r=r)
 def test_double_played_evidence_rejected(self):
  e=deepcopy(self.e);e["scored_played"].append(deepcopy(e["scored_played"][0]))
  with self.assertRaises(ValueError):self.make(e=e)
 def test_preregistered_cluster_gate_and_determinism(self):
  rows=[{"game_id":f"g{day}_{j%3}","player_id":f"p{j}",
         "ET_date":f"2026-11-{day+1:02d}",
         "bg":0.25 if day%2 else 0.12,"bp":0.18,
         "lg":0.7 if day%2 else 0.3,"lp":0.5}
        for day in range(MIN_ET_DATES) for j in range(max(14,MIN_PLAYED//MIN_ET_DATES+1))]
  self.assertGreaterEqual(len({r["game_id"] for r in rows}),MIN_GAMES)
  self.assertIsNone(date_cluster_paired_uncertainty(rows[:MIN_PLAYED-1]))
  self.assertIsNone(date_cluster_paired_uncertainty([dict(r,ET_date="2026-11-01") for r in rows[:13]]))
  a=date_cluster_paired_uncertainty(rows)
  self.assertIsNotNone(a)
  self.assertEqual(a,date_cluster_paired_uncertainty(rows))
  self.assertEqual(a["resampling_unit"],"NBA_ET_date_with_all_verified_played_player_games")
  self.assertLess(a["paired_global_minus_group_Brier_gain_95pct_exploratory"][0],a["paired_global_minus_group_Brier_gain_95pct_exploratory"][1])
 def test_inferred_DNP_or_fake_predicted_threshold_rejected(self):
  r=deepcopy(self.r);r["issued"][0]["short_actual_minutes_threshold"]=9
  with self.assertRaises(ValueError):self.make(r=r)
  r=deepcopy(self.r);r["issued"][0]["observed_minutes_used_as_feature"]=True
  with self.assertRaises(ValueError):self.make(r=r)
if __name__=="__main__":unittest.main()
