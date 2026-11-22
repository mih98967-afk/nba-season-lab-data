import copy,importlib.util,json,unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("future_minutes",root/"scripts/evaluate_minutes_prereg_v623.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
CONTRACT=json.loads((root/"docs/NBA_MINUTES_FUTURE_PREREG_20261120.json").read_text())
I={"game_id":"g1","player_id":"n1","team":"BOS","model_sha256":CONTRACT["model_sha256"],
 "game_utc":"2026-11-22T02:00:00Z","original_minutes_issued_at_utc":"2026-11-22T00:00:00Z",
 "challenger_issued_at_utc":"2026-11-22T00:02:00Z","individual_lock_utc":"2026-11-22T01:30:00Z",
 "source_all_current_minutes_first_seen_pre_issue":True,"current_same_team_played_n":4,
 "baseline_minutes":24,"challenger_minutes":26}
O={"game_id":"g1","player_id":"n1","team":"BOS","et_date":"2026-11-21",
   "postgame_first_seen_at_utc":"2026-11-22T04:00:00Z","actual_minutes":28}
def fixture():return {"status":"research_only_not_deployed","adopt_on_site":False,
"model_sha256":CONTRACT["model_sha256"],"issued":[copy.deepcopy(I)],"observed":[copy.deepcopy(O)]}
class FutureMinuteTests(unittest.TestCase):
 def test_future_no_automatic_promotion(self):
  x=mod.evaluate(fixture(),CONTRACT)
  self.assertEqual(x["conditional_played_only"]["paired_MAE_gain"],2)
  self.assertEqual(x["status"],"INSUFFICIENT_FUTURE_SAMPLE")
  self.assertFalse(x["site_adoption_allowed"])
 def test_old_predictions_excluded(self):
  r=fixture();r["issued"][0]["challenger_issued_at_utc"]="2026-11-20T12:00:00Z"
  x=mod.evaluate(r,CONTRACT)
  self.assertEqual(x["cohort"]["issued"],0)
 def test_unknown_not_dnp(self):
  r=fixture();r["observed"]=[]
  x=mod.evaluate(r,CONTRACT)
  self.assertEqual(x["cohort"]["not_scored_as_dnp_or_zero"],1)
 def test_future_predictions_are_locked(self):
  r=fixture();r["issued"][0]["challenger_issued_at_utc"]="2026-11-22T01:45:00Z"
  with self.assertRaisesRegex(ValueError,"T-30"):mod.evaluate(r,CONTRACT)
 def test_future_result_cannot_be_used_as_feature(self):
  r=fixture();r["observed"][0]["postgame_first_seen_at_utc"]="2026-11-22T01:00:00Z"
  with self.assertRaisesRegex(ValueError,"leaked"):mod.evaluate(r,CONTRACT)
 def test_model_hash_is_frozen(self):
  r=fixture();r["issued"][0]["model_sha256"]="b"*64
  with self.assertRaisesRegex(ValueError,"model drift"):mod.evaluate(r,CONTRACT)
 def test_duplicate_outcome_rejected(self):
  r=fixture();r["observed"].append(copy.deepcopy(r["observed"][0]))
  with self.assertRaisesRegex(ValueError,"duplicate"):mod.evaluate(r,CONTRACT)
 def test_unverified_source_first_seen_is_rejected(self):
  r=fixture();r["issued"][0]["source_all_current_minutes_first_seen_pre_issue"]=False
  with self.assertRaisesRegex(ValueError,"pre-issue source proof"):mod.evaluate(r,CONTRACT)
 def test_zero_minutes_outcome_not_scored_as_played(self):
  r=fixture();r["observed"][0]["actual_minutes"]=0
  with self.assertRaisesRegex(ValueError,"only positive-minute"):mod.evaluate(r,CONTRACT)
 def test_duplicate_prelock_issue_rejected(self):
  r=fixture();r["issued"].append(copy.deepcopy(r["issued"][0]))
  with self.assertRaisesRegex(ValueError,"duplicate issue"):mod.evaluate(r,CONTRACT)
 def test_observed_player_team_switch_cannot_match_issue(self):
  r=fixture();r["observed"][0]["team"]="DAL"
  with self.assertRaisesRegex(ValueError,"identity mismatch"):mod.evaluate(r,CONTRACT)
if __name__=="__main__":unittest.main()
