import unittest
from datetime import datetime, timezone
from copy import deepcopy
from src.conditional_minutes_fp_research import forecast,same_team_tail,prospective,MODEL,STATUS,verified_history_versions
from src.rolling_decision_research import canonical_hash
def sample(n=25,team="BOS"):
 return [{"min":30.0,"fp":25.0,"g":f"002250{i:05d}","d":"2026-01-01","team":team} for i in range(n)]
class Test(unittest.TestCase):
 def test_minutes_times_rate(self):
  x=forecast(sample())
  self.assertAlmostEqual(x["minutes_if_play"],30)
  self.assertAlmostEqual(x["fp_per_minute_if_play"],25/30,places=5)
  self.assertAlmostEqual(x["decomposed_fp_if_play"],25,places=3)
 def test_trade_requires_stable_tenure(self):
  self.assertIsNone(forecast(same_team_tail(sample(25,"BOS")+sample(15,"NYK"))))
 def test_unknown_never_dnp_and_real_lock(self):
  shadow={"schema_version":1,"status":STATUS,"adopt_on_site":False,"population_brier_enabled":False,"issued":[
  {"game_id":"g1","player_id":"n007","team":"BOS","tipoff_utc":"2026-10-28T23:00:00Z",
   "individual_lock_utc":"2026-10-28T22:30:00Z","issued_at_utc":"2026-10-27T18:00:00Z",
   "club_link_evidence":"same_club_independent_ESPN_ID_observed"}]}
  p={"n007":{"2025/26":sample()}}
  q={"minutes":8.0,"fp_per_minute":0.3,"decomposed_fp":10.0}
  out,qa=prospective(None,shadow,p,q,"immutable",datetime(2026,10,28,1,tzinfo=timezone.utc))
  self.assertEqual(len(out),1)
  self.assertEqual(out[0]["observed_game_outcome"],"UNKNOWN")
  self.assertFalse(out[0]["unconditional_FP_calculated"])
  self.assertFalse(out[0]["adopt_on_site"])
  old=deepcopy(shadow);old["issued"][0]["issued_at_utc"]="2026-10-28T22:31:00Z"
  with self.assertRaises(ValueError):
   prospective(None,old,p,q,"immutable",datetime(2026,10,28,23,tzinfo=timezone.utc))
  def test_history_index_rotation_keeps_old_issues_frozen(self):
   issued_time=datetime(2026,10,28,1,tzinfo=timezone.utc)
   next_time=datetime(2026,10,28,2,tzinfo=timezone.utc)
   first={"game_id":"g1","player_id":"n007","team":"BOS",
          "tipoff_utc":"2026-10-28T23:00:00Z",
          "individual_lock_utc":"2026-10-28T22:30:00Z",
          "issued_at_utc":"2026-10-27T18:00:00Z",
          "club_link_evidence":"same_club_independent_ESPN_ID_observed"}
   other={**first,"game_id":"g2","player_id":"n008",
          "tipoff_utc":"2026-10-29T00:00:00Z",
          "individual_lock_utc":"2026-10-28T23:30:00Z"}
   shadow={"schema_version":1,"status":STATUS,"adopt_on_site":False,
           "population_brier_enabled":False,"issued":[first]}
   people={"n007":{"2025/26":sample()},
           "n008":{"2025/26":sample()}}
   q={"minutes":8.0,"fp_per_minute":0.3,"decomposed_fp":10.0}
   original,_=prospective(None,shadow,people,q,"history-v1",issued_time)
   archive={"schema_version":1,"status":STATUS,"adopt_on_site":False,
            "historical_source_index_version":"history-v1",
            "frozen_rule_hash":canonical_hash(MODEL),"issued":deepcopy(original)}
   expanded=deepcopy(shadow)
   expanded["issued"].append(other)
   after,qa=prospective(archive,expanded,people,q,"history-v2",next_time)
   self.assertEqual(len(after),2)
   self.assertEqual(after[0],original[0])
   self.assertEqual(after[0]["historical_source_index_version"],"history-v1")
   self.assertEqual(after[1]["historical_source_index_version"],"history-v2")
   self.assertEqual(qa["new_minutes_rate_issues"],1)
   archive["historical_source_index_version"]="history-v2"
   archive["historical_source_index_versions"]=["history-v1","history-v2"]
   archive["issued"]=after
   self.assertEqual(verified_history_versions(archive),{"history-v1","history-v2"})
   third,again=prospective(archive,expanded,people,q,"history-v2",next_time)
   self.assertEqual(third,after)
   self.assertEqual(again.get("new_minutes_rate_issues",0),0)

  def test_history_rotation_rejects_unregistered_or_modified_lineage(self):
   one={"historical_source_index_version":"old",
        "issued":[{"historical_source_index_version":"old"}]}
   self.assertEqual(verified_history_versions(one),{"old"})
   failures=[
    {"historical_source_index_version":"new","issued":deepcopy(one["issued"])},
    {"historical_source_index_version":"new","historical_source_index_versions":["new"],"issued":deepcopy(one["issued"])},
    {"historical_source_index_version":"new","historical_source_index_versions":["old","new","invented"],"issued":deepcopy(one["issued"])},
    {"historical_source_index_version":"new","historical_source_index_versions":["new","old"],"issued":deepcopy(one["issued"])},
    {"historical_source_index_version":"new","historical_source_index_versions":["old","new","new"],"issued":deepcopy(one["issued"])},
   ]
   for archive in failures:
    with self.subTest(archive=archive), self.assertRaises(ValueError):
     verified_history_versions(archive)

if __name__=="__main__": unittest.main()
