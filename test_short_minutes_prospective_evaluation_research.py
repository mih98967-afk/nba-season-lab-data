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
  gates=v["precommitted_exploratory_date_cluster_gates"]
  eligible=(s["distinct_ET_dates_scored"]>=MIN_ET_DATES and
            s["played_verified"]>=MIN_PLAYED and
            s["distinct_NBA_games_scored"]>=MIN_GAMES)
  self.assertEqual(gates["interval_eligible"],eligible)
  self.assertEqual(gates["date_gate"],s["distinct_ET_dates_scored"]>=MIN_ET_DATES)
  self.assertEqual(gates["played_gate"],s["played_verified"]>=MIN_PLAYED)
  self.assertEqual(gates["games_gate"],s["distinct_NBA_games_scored"]>=MIN_GAMES)
  interval=v["paired_global_minus_group_uncertainty_if_eligible"]
  if not eligible:
   self.assertIsNone(interval)
  else:
   self.assertIsNotNone(interval)
   self.assertEqual(interval["independent_ET_dates"],s["distinct_ET_dates_scored"])
   self.assertEqual(interval["distinct_NBA_games"],s["distinct_NBA_games_scored"])
   self.assertEqual(interval["scored_played_player_games"],s["played_verified"])
   self.assertEqual(interval["resampling_unit"],"NBA_ET_date_with_all_verified_played_player_games")
   self.assertEqual(interval["resamples"],2000)
   for field in ("paired_global_minus_group_Brier_gain_95pct_exploratory",
                 "paired_global_minus_group_logloss_gain_95pct_exploratory"):
    self.assertEqual(len(interval[field]),2)
    self.assertLessEqual(interval[field][0],interval[field][1])
   self.assertTrue(interval["descriptive_bootstrap_not_confirmatory_inference"])
   self.assertTrue(interval["not_population_or_transfer_value_evidence"])
  self.assertFalse(v["quality_gate"]["full_population_calibration_proven"])
  self.assertFalse(v["quality_gate"]["unconditional_FP_allowed"])
  self.assertFalse(v["quality_gate"]["KEEP_TRANSFER_gain_proven"])
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
