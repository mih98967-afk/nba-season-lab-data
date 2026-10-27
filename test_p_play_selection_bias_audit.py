import unittest
from datetime import datetime,timezone
from src.p_play_selection_bias_audit import _interval,_loss,audit,STATUS
def t(s):return datetime.fromisoformat(s.replace("Z","+00:00"))
def fixture():
 issue={"game_id":"g","player_id":"p","team":"BOS","tipoff_utc":"2026-10-27T01:00:00Z","individual_lock_utc":"2026-10-27T00:30:00Z","issued_at_utc":"2026-10-26T18:00:00Z","adopt_on_site":False,"club_link_evidence":"same_club_independent_ESPN_ID_observed","baseline_p_selected_listed_proxy":.85,"candidate_p_selected_listed_proxy":.8,"official_status_first_known_asof_issue":"out"}
 shadow={"status":STATUS,"adopt_on_site":False,"population_brier_enabled":False,"issued":[issue],"observations":[]}
 game={"id":"g","status":"final","home":"BOS","away":"NYK","utc":issue["tipoff_utc"]}
 live={"games":[game]}
 explicit={"status":STATUS,"adopt_on_site":False,"checked_final_game_ids":["g"]}
 official={"status":"official_report_observed_pit_research_only","adopt_on_site":False,"events":[{"game_id":"g","player_id":"p","team":"BOS","home":"BOS","away":"NYK","status":"out","tipoff_utc":issue["tipoff_utc"],"first_seen_at_utc":"2026-10-26T16:00:00Z","report_at_utc":"2026-10-26T15:55:00Z","event_id":"e","source_url":"https://example.org/report"}]}
 return shadow,live,explicit,official
class Tests(unittest.TestCase):
 def test_out_is_unknown_not_imputed_negative(self):
  result=audit(*fixture(),t("2026-10-27T04:00:00Z"))
  self.assertEqual(result["official_OUT_unknown_review_priority_count"],1)
  self.assertEqual(result["verified_postgame_results"],0)
  self.assertEqual(result["unknown_postgame_results"],1)
  self.assertFalse(result["quality_gate"]["prospective_model_adoption_allowed"])
  self.assertTrue(result["out_status_missing_review_queue"][0]["needs_independent_full_boxscore_athlete_ID_review"])
 def test_bound_is_paired_not_cross_model_extremes(self):
  issue=fixture()[0]["issued"][0]
  z=_interval([], [issue])
  self.assertLessEqual(z["bounds"]["brier"]["paired_baseline_minus_candidate_gain_range"][0],0)
  self.assertGreater(z["bounds"]["brier"]["paired_baseline_minus_candidate_gain_range"][1],0)
  self.assertEqual(z["n"],1)
 def test_verified_explicit_negative(self):
  args=list(fixture())
  args[0]["observations"]=[{"game_id":"g","player_id":"p","actual_played":0,"label_provenance":"explicit_espn_didNotPlay_true","tipoff_utc":"2026-10-27T01:00:00Z","source_first_observed_at_utc":"2026-10-27T03:00:00Z"}]
  report=audit(*args,t("2026-10-27T04:00:00Z"))
  self.assertEqual(report["unknown_postgame_results"],0)
  self.assertEqual(report["by_first_observed_official_status"]["out"]["explicit_DNP"],1)
 def test_status_after_issuance_not_leaked(self):
  args=list(fixture());args[3]["events"][0]["first_seen_at_utc"]="2026-10-26T20:00:00Z"
  with self.assertRaises(ValueError):audit(*args,t("2026-10-27T04:00:00Z"))
 def test_unknown_cannot_be_directly_scored(self):
  with self.assertRaises(ValueError):_loss(.9,None,"brier")
if __name__=="__main__":unittest.main()
