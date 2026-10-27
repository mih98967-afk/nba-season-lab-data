import unittest
from datetime import datetime,timezone
from src.historical_prior_prospective_shadow import frozen,_new_issues,_observed,_metrics,advance,MODEL_STATUS
def d(s):return datetime.fromisoformat(s.replace("Z","+00:00"))
class TestFrozenHistoricalProspective(unittest.TestCase):
 def setup(self):
  h={"status":MODEL_STATUS,"adopt_on_site":False,"training_season":"2024/25","untouched_holdout_season":"2025/26","confirmed_DNP_observations":0,"selected_development_params":{"shrinkage":0,"recent_weight":.75}}
  c={"status":MODEL_STATUS,"adopt_on_site":False,"used_in_live_site_or_forecast":False,"actual_DNP_label_count":0,"scope":"retrospective_selected_logged_appearance_PROXY_NOT_DNP","frozen_raw_parameters":{"shrinkage":0,"recent_weight":.75},"calibration_training_only_2024_25":{"selected_shrink":.25,"smoothed_development_appearance_rate":.789164}}
  return frozen(c,h)
 def pplay(self,tip="2026-10-28T01:00:00Z",issued="2026-10-27T10:00:00Z"):
  return {"status":MODEL_STATUS,"adopt_on_site":False,"population_brier_enabled":False,"issued":[{"game_id":"g","player_id":"p","team":"BOS","position":"PG","tipoff_utc":tip,"individual_lock_utc":"2026-10-28T00:30:00Z","issued_at_utc":issued,"club_link_evidence":"same_club_independent_ESPN_ID_observed","catalog_capture_utc":"2026-10-27T09:00:00Z","espn_capture_utc":"2026-10-27T09:05:00Z","baseline_p_selected_listed_proxy":.85,"candidate_p_selected_listed_proxy":.88}],"observations":[]}
 def profile(self):
  return {"p":{"last_verified_played_club_2025_26":"BOS","history_row":{"last20_appeared":17,"last20_team_games":20,"last5_appeared":5,"last5_team_games":5}}}
 def test_prelock_issue_is_frozen_and_no_backfill(self):
  cfg,sha=self.setup();p=self.pplay()
  rows,qa=_new_issues([],self.profile(),p,cfg,sha,d("2026-10-27T12:00:00Z"))
  self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]["historical_proxy_issued_at_utc"],"2026-10-27T12:00:00Z")
  self.assertLess(rows[0]["historical_score_dev_calibrated"],1)
  skipped,why=_new_issues([],self.profile(),p,cfg,sha,d("2026-10-28T00:30:00Z"))
  self.assertEqual(skipped,[])
  self.assertEqual(why["already_locked_no_historical_backfill"],1)
 def test_team_conflict_and_weak_name_excluded(self):
  cfg,sha=self.setup()
  p=self.pplay();p["issued"][0]["team"]="NYK"
  out,_=_new_issues([],self.profile(),p,cfg,sha,d("2026-10-27T12:00:00Z"))
  self.assertEqual(out,[])
  p["issued"][0]["team"]="BOS"
  p["issued"][0]["club_link_evidence"]="same_club_unique_name_only_observed"
  out,_=_new_issues([],self.profile(),p,cfg,sha,d("2026-10-27T12:00:00Z"))
  self.assertEqual(out,[])
 def test_only_explicit_postgame_labels(self):
  cfg,sha=self.setup();p=self.pplay()
  issued,_=_new_issues([],self.profile(),p,cfg,sha,d("2026-10-27T12:00:00Z"))
  obs,qa=_observed(issued,[],p,d("2026-10-28T05:00:00Z"))
  self.assertEqual(obs,[])
  self.assertEqual(qa["no_explicit_verified_outcome_UNKNOWN"],1)
  p["observations"]=[{"game_id":"g","player_id":"p","tipoff_utc":"2026-10-28T01:00:00Z","actual_played":0,"label_provenance":"explicit_espn_didNotPlay_true","source_first_observed_at_utc":"2026-10-28T04:00:00Z","club_link_evidence_at_issue":"same_club_independent_ESPN_ID_observed"}]
  obs,_=_observed(issued,[],p,d("2026-10-28T05:00:00Z"))
  self.assertEqual(len(obs),1)
  self.assertEqual(obs[0]["actual_played"],0)
  self.assertFalse(_metrics(obs)["population_model_adoption_permitted"])
 def test_run_never_claims_deployment(self):
  cfg,sha=self.setup()
  output,qa=advance({},self.pplay(),self.profile(),cfg,sha,d("2026-10-27T12:00:00Z"))
  self.assertEqual(output["status"],MODEL_STATUS)
  self.assertFalse(output["adopt_on_site"])
  self.assertEqual(output["summary"]["matched_verified_labels"],0)
  self.assertFalse(output["population_p_play_calibrated"])
if __name__=="__main__":unittest.main()
