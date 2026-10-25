import unittest
from datetime import datetime,timezone
from src.injury_outcome_observations import evaluate
class TestOutcomes(unittest.TestCase):
 def base(self):
  event={"event_id":"1","game_id":"g1","player_id":"n01","team":"BOS","home":"NYK","away":"BOS",
   "report_at_utc":"2026-10-25T13:00:00Z","first_seen_at_utc":"2026-10-25T13:02:00Z",
   "tipoff_utc":"2026-10-25T22:00:00Z","status":"questionable"}
  live={"games":[{"id":"g1","status":"final","home":"NYK","away":"BOS"}],
        "rows":[{"game_id":"g1","id":"n0"+str(i),"team":"BOS","played":True} for i in range(1,8)]}
  return {"status":"official_report_observed_pit_research_only","events":[event]},live
 def test_verified_positive(self):
  a,b=self.base();x=evaluate(a,b,datetime(2026,10,26,tzinfo=timezone.utc))
  self.assertEqual(x["verified_played"],1);self.assertEqual(x["unlisted_unknown"],0)
 def test_missing_not_dnp(self):
  a,b=self.base();a["events"][0]["player_id"]="n99"
  x=evaluate(a,b,datetime(2026,10,26,tzinfo=timezone.utc))
  self.assertEqual(x["verified_played"],0);self.assertEqual(x["unlisted_unknown"],1)
  self.assertFalse(x["sample_sufficient_for_brier"])
 def test_no_hindsight(self):
  a,b=self.base();a["events"][0]["first_seen_at_utc"]="2026-10-25T21:31:00Z"
  x=evaluate(a,b,datetime(2026,10,26,tzinfo=timezone.utc))
  self.assertEqual(x["qa"]["not_known_before_lock"],1)
 def test_future_no_outcome(self):
  a,b=self.base();x=evaluate(a,b,datetime(2026,10,25,15,tzinfo=timezone.utc))
  self.assertEqual(x["qa"]["future_game"],1)
if __name__=="__main__":unittest.main()
