import unittest
from src.telegram_archive import update,asof
from datetime import datetime,timezone
def sample():
 return {"id":"nba_injurynews/123:n014:0","published_at":"2026-10-23T19:00:00Z",
         "player_ids":["n014"],"status":"out","match_quality":"full_name",
         "verification":"unconfirmed_telegram","source":"nba_injurynews",
         "text":"Tyrese Maxey ruled out","url":"https://t.me/nba_injurynews/123"}
class ArchiveTests(unittest.TestCase):
 def test_no_hindsight(self):
  now=datetime(2026,10,24,10,tzinfo=timezone.utc)
  d=update({"status":"public_preview_unverified","events":[sample()]},now=now)
  self.assertEqual(asof(d["events"],"2026-10-23T20:00:00Z"),[])
  self.assertEqual(len(asof(d["events"],"2026-10-24T10:00:00Z")),1)
 def test_append_dedupe(self):
  now=datetime(2026,10,24,10,tzinfo=timezone.utc)
  feed={"status":"public_preview_unverified","events":[sample()]}
  a=update(feed,now=now)
  b=update(feed,a,now=datetime(2026,10,25,10,tzinfo=timezone.utc))
  self.assertEqual(b["added"],0)
  self.assertEqual(a["events"][0]["first_seen_at"],b["events"][0]["first_seen_at"])
 def test_ambiguous_rejected(self):
  a=sample();a["match_quality"]="unique_surname"
  d=update({"status":"public_preview_unverified","events":[a]},now=datetime(2026,10,24,10,tzinfo=timezone.utc))
  self.assertEqual(len(d["events"]),0)
if __name__=="__main__":unittest.main()
