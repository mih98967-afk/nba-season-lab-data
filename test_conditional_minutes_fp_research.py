import unittest
from datetime import datetime, timezone
from copy import deepcopy
from src.conditional_minutes_fp_research import forecast,same_team_tail,prospective,MODEL,STATUS
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
if __name__=="__main__": unittest.main()
