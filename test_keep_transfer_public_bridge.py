import unittest
from copy import deepcopy
from src.keep_transfer_public_bridge import build
NOW="2026-10-28T22:00:00Z"
def fixture():
 live={"schema_version":4,"updated_at_utc":"2026-10-28T21:00:00Z",
       "schedule_quality":{"validated_at_utc":"2026-10-28T21:00:00Z","freshness":"fresh","complete":False},
       "schedule":[{"id":"g1","utc":"2026-10-29T01:00:00Z","status":"scheduled","home":"BOS","away":"NYK"}]}
 p={"schema_version":1,"status":"research_only_not_deployed","adopt_on_site":False,
    "population_brier_enabled":False,"full_game_day_roster_denominator_verified":False,
    "issued":[{"game_id":"g1","player_id":"p1","issued_at_utc":"2026-10-28T20:00:00Z",
               "individual_lock_utc":"2026-10-29T00:30:00Z","tipoff_utc":"2026-10-29T01:00:00Z",
               "team":"BOS","position":"PG","club_link_evidence":"same_club_independent_ESPN_ID_observed"}]}
 c={"schema_version":1,"status":"research_only_not_deployed","adopt_on_site":False,
    "unconditional_FP_enabled":False,
    "issued":[{"game_id":"g1","player_id":"p1","issued_at_utc":"2026-10-28T21:00:00Z",
               "game_utc":"2026-10-29T01:00:00Z","team":"BOS","direct_fp_if_play":14.5}]}
 return live,p,c
class BridgeTests(unittest.TestCase):
 def test_join_is_not_unconditional_or_economic(self):
  a=fixture();before=deepcopy(a);r=build(*a,NOW)
  self.assertEqual(r["frozen_coverage"]["matched_conditional_if_play"],1)
  self.assertEqual(r["observed_player_games"][0]["fp_if_play_first_issued"],14.5)
  self.assertFalse(r["valid_KEEP_TRANSFER_backtest_possible"])
  self.assertFalse(r["model_population_pplay_calibrated"])
  self.assertEqual(a,before)
 def test_no_postdecision_prediction(self):
  a=fixture();a[2]["issued"][0]["issued_at_utc"]="2026-10-28T22:30:00Z"
  r=build(*a,NOW);self.assertEqual(r["frozen_coverage"]["conditional_issue_after_decision_excluded"],1)
  self.assertIsNone(r["observed_player_games"][0]["fp_if_play_first_issued"])
 def test_reject_after_lock_issue(self):
  a=fixture();a[2]["issued"][0]["issued_at_utc"]="2026-10-29T00:30:00Z"
  with self.assertRaises(ValueError):build(*a,"2026-10-29T00:40:00Z")
 def test_reject_team_conflict(self):
  a=fixture();a[2]["issued"][0]["team"]="DEN"
  with self.assertRaises(ValueError):build(*a,NOW)
 def test_stale_calendar(self):
  a=fixture();a[0]["updated_at_utc"]="2026-10-27T00:00:00Z"
  with self.assertRaises(ValueError):build(*a,NOW)
if __name__=="__main__":unittest.main()
