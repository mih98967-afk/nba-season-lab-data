import datetime as dt
import json
import unittest
from src.sync import DATA
from src.schedule_sync import refresh
class SelfHealTests(unittest.TestCase):
 def test_verified_recent_cache(self):
  src=json.loads((DATA/"schedule.json").read_text())
  t=dt.datetime.fromisoformat(src["updated_at_utc"].replace("Z","+00:00"))+dt.timedelta(hours=4)
  self.assertEqual(refresh(fetch=lambda url: (_ for _ in ()).throw(AssertionError("unexpected network")),now=t)["result"],"fresh_cache")
 def test_twelve_hour_ttl_requires_fetch(self):
  src=json.loads((DATA/"schedule.json").read_text())
  t=dt.datetime.fromisoformat(src["updated_at_utc"].replace("Z","+00:00"))+dt.timedelta(hours=13)
  with self.assertRaises(AssertionError):
   refresh(fetch=lambda url: (_ for _ in ()).throw(AssertionError("refresh needed")),now=t)
if __name__=="__main__":unittest.main()
