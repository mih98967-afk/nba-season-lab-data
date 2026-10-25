import unittest
from datetime import datetime, timezone, timedelta
from copy import deepcopy
from src.rolling_decision_research import (
    week_key, transfer_clock, official_asof, telegram_asof, advance)
UTC=timezone.utc
def d(x):return datetime.fromisoformat(x.replace("Z","+00:00"))
class TestRolling(unittest.TestCase):
 def fixtures(self):
  game={"id":"g1","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"NYK","status":"scheduled"}
  live={"schema_version":4,"updated_at_utc":"2026-10-26T18:00:00Z",
        "schedule_quality":{"freshness":"fresh"},"schedule":[game],"games":[],"rows":[]}
  e={"event_id":"a","game_id":"g1","player_id":"n1","team":"BOS","home":"BOS","away":"NYK",
     "status":"questionable","tipoff_utc":game["utc"],"report_at_utc":"2026-10-26T19:00:00Z",
     "first_seen_at_utc":"2026-10-26T19:10:00Z"}
  return live,{"events":[e]},{"events":[]}
 def test_week_moves_independent_monday_deadline(self):
  self.assertEqual(week_key(d("2026-10-26T09:00:00Z")),"2026-10-26")
  self.assertEqual(week_key(d("2026-11-01T20:00:00Z")),"2026-10-26")
  self.assertEqual(week_key(d("2026-11-01T22:00:00Z")),"2026-11-02")
 def test_lock_is_not_monday_gate(self):
  live,_,_=self.fixtures()
  self.assertEqual(transfer_clock("BOS",live["schedule"],d("2026-10-26T17:00:00Z"))["status"],
                   "no_scheduled_lock_detected_manual_sportsru_check")
  self.assertEqual(transfer_clock("BOS",live["schedule"],d("2026-10-26T23:35:00Z"))["status"],
                   "blocked_30_minutes_before_game")
  self.assertEqual(transfer_clock("BOS",live["schedule"],d("2026-10-27T00:30:00Z"))["status"],
                   "postgame_unlock_unverified")
 def test_knowledge_really_first_seen(self):
  _,a,_=self.fixtures()
  self.assertIsNone(official_asof(a,"g1","n1","BOS",d("2026-10-26T19:05:00Z")))
  self.assertEqual(official_asof(a,"g1","n1","BOS",d("2026-10-26T19:15:00Z"))["status"],"questionable")
 def test_telegram_not_backdated(self):
  tg={"events":[{"id":"a","player_ids":["n1"],"status":"out","verification":"unconfirmed_telegram",
  "match_quality":"full_name","url":"https://t.me/nba_injurynews/1",
  "published_at":"2026-10-26T15:00:00Z","first_seen_at":"2026-10-26T19:15:00Z"}]}
  self.assertIsNone(telegram_asof(tg,"n1",d("2026-10-26T18:00:00Z")))
  self.assertFalse(telegram_asof(tg,"n1",d("2026-10-26T20:00:00Z"))["fixture_verified"])
 def test_bootstrap_not_historical_forecast(self):
  live,off,tg=self.fixtures()
  live["updated_at_utc"]="2026-10-26T20:00:00Z"
  x,res=advance({},live,off,tg,d("2026-10-26T20:01:00Z"))
  self.assertEqual(x["status"],"research_only_not_deployed")
  self.assertEqual(len(x["snapshots"]),1)
  self.assertTrue(x["snapshots"][0]["bootstrap_prior_matches_not_retroactively_available"])
  self.assertFalse(x["adopt_on_site"])
  y,out=advance(x,live,off,tg,d("2026-10-26T20:05:00Z"))
  self.assertEqual(out["result"],"no_new_observation")
  self.assertEqual(len(y["snapshots"]),1)
 def test_new_completed_match_is_captured_when_seen(self):
  live,off,tg=self.fixtures()
  live["updated_at_utc"]="2026-10-27T03:00:00Z"
  x,_=advance({},live,off,tg,d("2026-10-27T03:05:00Z"))
  live["games"]=[dict(live["schedule"][0],status="final")]
  for i in range(10):
   live["rows"].append({"game_id":"g1","id":"n"+str(i),"team":"BOS","played":True,
                       "minutes":25,"fp":10+i,"utc":"2026-10-27T00:00:00Z"})
  y,res=advance(x,live,off,tg,d("2026-10-27T04:05:00Z"))
  self.assertEqual(res["newly_observed_final_games"],1)
  self.assertEqual(res["rows_changed"],10)
  self.assertEqual(y["row_first_seen_at_utc"]["g1|n0"],"2026-10-27T04:05:00Z")
  self.assertEqual(y["snapshots"][-1]["rolling_played_fp_form_features"]["n0"]["last_5_played_game_fp_mean"],10)
 def test_disappearing_history_fails(self):
  live,off,tg=self.fixtures()
  live["updated_at_utc"]="2026-10-27T03:00:00Z"
  live["rows"]=[{"game_id":"g1","id":"n1","team":"BOS","played":True,
                "minutes":22,"fp":17,"utc":"2026-10-27T00:00:00Z"}]
  x,_=advance({},live,off,tg,d("2026-10-27T03:05:00Z"))
  live["rows"]=[]
  with self.assertRaises(ValueError):advance(x,live,off,tg,d("2026-10-27T04:05:00Z"))
if __name__=="__main__":unittest.main()
