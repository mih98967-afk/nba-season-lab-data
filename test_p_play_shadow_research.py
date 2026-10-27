import unittest
from copy import deepcopy
from datetime import datetime,timezone
from src.p_play_shadow_research import _verified_past,_issues,_observations,_metrics,_prospective_metrics,_fresh,STATUS
from src.catalog_pit_research import UNKNOWN
def d(x):return datetime.fromisoformat(x.replace("Z","+00:00"))
class Tests(unittest.TestCase):
 def test_never_use_future_history(self):
  rows=[{"game_id":"g0","player_id":"p","game_utc":"2026-10-26T15:00:00Z","source_first_observed_at_utc":"2026-10-26T20:00:00Z","team":"ATL","participation_label":0,"evidence":"explicit_espn_didNotPlay_true"}]
  valid,q=_verified_past({"records":rows},d("2026-10-26T19:00:00Z"))
  self.assertEqual(valid,[])
  self.assertEqual(q["future_or_not_yet_observed_label_excluded"],1)
 def test_only_before_lock_and_strong_or_weak_eligible(self):
  x={"game_id":"g","player_id":"p","team_in_catalog_snapshot":"ATL","fantasy_position":"PG","game_utc":"2026-10-27T01:00:00Z","individual_lock_utc":"2026-10-27T00:30:00Z","catalog_capture_utc":"2026-10-26T17:00:00Z","espn_roster_capture_utc":"2026-10-26T17:05:00Z","club_cross_source_evidence":"same_club_independent_ESPN_ID_observed"}
  cohort={"records":[]}
  a,q=_issues({"records":[x]},cohort,{"events":[]},{"events":[]},d("2026-10-26T20:00:00Z"),[])
  self.assertEqual(len(a),1)
  self.assertEqual(a[0]["baseline_p_selected_listed_proxy"],0.5)
  self.assertEqual(a[0]["candidate_p_selected_listed_proxy"],0.5)
  b,_=_issues({"records":[x]},cohort,{"events":[]},{"events":[]},d("2026-10-27T00:30:00Z"),[])
  self.assertEqual(len(b),0)
  c,_=_issues({"records":[dict(x,club_cross_source_evidence="club_conflict_between_observed_sources")]},cohort,{"events":[]},{"events":[]},d("2026-10-26T20:00:00Z"),[])
  self.assertEqual(len(c),0)
 def test_no_implicit_dnp_and_observation_requires_postgame_clock(self):
  issue={"game_id":"g","player_id":"p","team":"ATL","position":"PG","tipoff_utc":"2026-10-27T01:00:00Z","issued_at_utc":"2026-10-26T20:00:00Z","club_link_evidence":"same_club_independent_ESPN_ID_observed","baseline_p_selected_listed_proxy":0.5,"candidate_p_selected_listed_proxy":0.5}
  game={"id":"g","status":"final","utc":issue["tipoff_utc"],"home":"ATL","away":"BOS"}
  live={"games":[game]}
  exp={"checked_final_game_ids":["g"]}
  cohort={"summary":{"verified_full_boxscores_checked":1},"records":[]}
  out,qa=_observations([issue],[],live,cohort,exp,d("2026-10-27T04:00:00Z"))
  self.assertEqual(out,[])
  self.assertEqual(qa["no_explicit_outcome_UNKNOWN"],1)
  cohort["records"]=[{"game_id":"g","player_id":"p","team":"ATL","position":"PG","game_utc":issue["tipoff_utc"],"participation_label":0,"evidence":"explicit_espn_didNotPlay_true","source_first_observed_at_utc":"2026-10-27T03:00:00Z"}]
  out,qa=_observations([issue],[],live,cohort,exp,d("2026-10-27T04:00:00Z"))
  self.assertEqual(len(out),1)
  self.assertEqual(out[0]["actual_played"],0)
 def test_separate_calendar_and_live_freshness_bounds(self):
  now=d("2026-10-27T12:00:00Z")
  good={"schema_version":4,"updated_at_utc":"2026-10-27T11:00:00Z",
        "schedule_quality":{"freshness":"fresh",
        "validated_at_utc":"2026-10-26T20:00:00Z"}}
  self.assertTrue(_fresh(good,now))
  bad=deepcopy(good);bad["updated_at_utc"]="2026-10-27T03:59:59Z"
  self.assertFalse(_fresh(bad,now))
  bad=deepcopy(good);bad["schedule_quality"]["validated_at_utc"]="2026-10-26T00:00:00Z"
  self.assertFalse(_fresh(bad,now))
  bad=deepcopy(good);bad["schedule_quality"]["validated_at_utc"]="2026-10-27T12:01:00Z"
  self.assertFalse(_fresh(bad,now))
  bad=deepcopy(good);bad["schedule_quality"]["validated_at_utc"]="2026-10-27T11:30:00Z"
  self.assertFalse(_fresh(bad,now))
 def test_single_game_does_not_open_calibration(self):
  obs=[{"game_id":"g","player_id":"p","tipoff_utc":"2026-10-27T01:00:00Z","actual_played":1,"club_link_evidence_at_issue":"same_club_independent_ESPN_ID_observed","baseline_p_selected_listed_proxy":0.5,"candidate_p_selected_listed_proxy":0.6}]
  summary,metric=_metrics(obs)
  self.assertEqual(summary["verified_selected_distinct_games"],1)
  self.assertIsNone(metric)
 def test_prospective_one_date_is_not_adoption(self):
  rows=[]
  for gid in ("g1","g2"):
   for i in range(5):
    rows.append({"game_id":gid,"player_id":"n"+str(i),"tipoff_utc":"2026-10-27T01:00:00Z","actual_played":int(i!=0),"baseline_p_selected_listed_proxy":0.8,"candidate_p_selected_listed_proxy":0.7})
  metric=_prospective_metrics(rows)
  self.assertEqual(metric["NBA_games"],2)
  self.assertEqual(metric["ET_dates"],1)
  self.assertFalse(metric["sufficient_for_longitudinal_adoption"])
  self.assertTrue(metric["NBA_game_cluster_bootstrap_95pct_gain"]["few_independent_game_dates_caution"])
  self.assertIsNone(_prospective_metrics([]))

if __name__=="__main__":unittest.main()
