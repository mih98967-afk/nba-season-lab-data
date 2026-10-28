import copy
import unittest
from src.keep_transfer_public_readiness import public_report
from test_keep_transfer_public_bridge import fixture, NOW

class Tests(unittest.TestCase):
 def sample(self):
  live,p,c=fixture()
  return {"live":live,"p_play_first_issues":p,"conditional_first_issues":c}
 def test_true_coverage_no_economic_claims(self):
  source=self.sample();old=copy.deepcopy(source)
  result=public_report(source,{"live":"0"*64},NOW)
  self.assertEqual(result["phase"],"PUBLIC_FROZEN_COVERAGE_ONLY")
  self.assertEqual(result["selected_player_games"],1)
  self.assertEqual(result["conditional_if_play_player_games"],1)
  self.assertFalse(result["valid_KEEP_TRANSFER_backtest_possible"])
  self.assertFalse(result["historical_prices_inferred"])
  self.assertFalse(result["unconditional_FP_validated"])
  self.assertEqual(source,old)
 def test_missing_or_stale_source_refused(self):
  s=self.sample();s["live"]["updated_at_utc"]="2026-10-27T00:00:00Z"
  report=public_report(s,{},NOW)
  self.assertEqual(report["phase"],"BLOCKED_PUBLIC_SOURCE")
  self.assertIsNone(report["selected_player_games"])
 def test_later_conditional_not_used(self):
  s=self.sample()
  s["conditional_first_issues"]["issued"][0]["issued_at_utc"]="2026-10-28T23:00:00Z"
  r=public_report(s,{},NOW)
  self.assertEqual(r["conditional_if_play_player_games"],0)
 def test_incomplete_schedule_is_not_complete(self):
  r=public_report(self.sample(),{},NOW)
  self.assertFalse(r["source_schedule_complete"])
  self.assertTrue(any("Incomplete future" in s for s in r["blocking_reasons"]))
if __name__=="__main__":unittest.main()
