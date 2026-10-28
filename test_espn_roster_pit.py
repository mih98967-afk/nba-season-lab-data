import unittest
from datetime import datetime,timezone,timedelta
from src.espn_roster_pit import athletes,capture,ESPN_TEAMS,seal_capture_after_final_fetch
from src.live_calendar_fallback import TEAMS

class Tests(unittest.TestCase):
 def test_all_30_teams_mapped(self):
  self.assertEqual(set(ESPN_TEAMS),TEAMS)
  self.assertEqual(len(set(ESPN_TEAMS.values())),30)
 def test_flat_and_grouped(self):
  data=[{"id":str(i),"displayName":f"Player {i}"} for i in range(12)]
  self.assertEqual(len(athletes({"athletes":data})),12)
  self.assertEqual(len(athletes({"athletes":[{"position":"G","items":data}]})),12)
  with self.assertRaises(ValueError):athletes({"athletes":data[:2]})
 def test_fail_closed_unknown_and_cross_team_disagreement(self):
  now=datetime(2026,10,26,18,0,tzinfo=timezone.utc)
  teams=list(sorted(TEAMS))
  catalog={"players":[{"id":f"n{i:03d}","team":teams[i%30],"pos":"PG","english":f"Player {i}"} for i in range(450)]}
  identity={"players":{}}
  live={"schema_version":4,"updated_at_utc":"2026-10-26T17:55:00Z",
        "schedule_quality":{"freshness":"fresh"},"games":[{"id":"game","status":"final"}],
        "rows":[{"id":"n000","played":True,"minutes":20,"team":"ATL",
                 "game_id":"game","name":"Player 0","espn_person_id":"101"}]}
  person=[{"id":str(101+i),"displayName":f"Player {i}"} for i in range(12)]
  def provider(url):
   if url.endswith("/2/roster"):raise OSError("unavailable")
   return {"athletes":person}
  out=capture(catalog,identity,live,provider,now)
  self.assertFalse(out["all_teams_available"])
  self.assertEqual(out["qa"]["unavailable_or_invalid_team"],1)
  self.assertFalse(out["adopt_on_site"])
  self.assertFalse(out["game_day_eligibility_verified"])
  self.assertEqual(next(t for t in out["teams"] if t["club"]=="BOS")["source_status"],"invalid_or_unavailable")
  self.assertTrue(out["publication_time_unknown"])
  sealed=seal_capture_after_final_fetch(out,now+timedelta(minutes=3))
  self.assertEqual(sealed["captured_at_utc"],"2026-10-26T18:03:00Z")
  self.assertEqual(out["captured_at_utc"],"2026-10-26T18:00:00Z")
  self.assertTrue(all(t["source_first_seen_at_utc"]==sealed["captured_at_utc"]
                      for t in sealed["teams"]))
  from src.prelock_roster_opportunities import validate_espn_snapshots
  self.assertEqual(len(validate_espn_snapshots([sealed],now+timedelta(minutes=4))),1)
  with self.assertRaises(ValueError):
   seal_capture_after_final_fetch(out,now+timedelta(minutes=16))
  with self.assertRaises(ValueError):
   seal_capture_after_final_fetch(out,now-timedelta(seconds=1))
if __name__=="__main__":unittest.main()
