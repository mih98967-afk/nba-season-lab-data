"""Offline P0 coverage: current verified calendar wins over previous nonempty cache."""
import datetime as dt
import json
import unittest
from copy import deepcopy
from src.sync import DATA, NBA_SCHEDULE, select_live_schedule

class TestLiveScheduleProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calendar=json.loads((DATA/"schedule.json").read_text())
        cls.now=dt.datetime.fromisoformat(cls.calendar["updated_at_utc"].replace("Z","+00:00"))+dt.timedelta(hours=2)

    @staticmethod
    def cdn_403(url):
        raise PermissionError("NBA CDN HTTP 403")

    def test_current_calendar_supersedes_nonempty_old(self):
        old={"schedule":[{"id":"outdated","utc":"2020-01-01T00:00:00Z"}],
             "games":[{"id":"kept_final","status":"final"}],
             "rows":[{"game_id":"kept_final","id":"player","fp":24}]}
        games,source,quality,provider,warnings=select_live_schedule(self.cdn_403,self.now,old,self.calendar)
        self.assertEqual(source,"data/schedule.json")
        self.assertIn("verified ESPN",provider)
        self.assertEqual(len(games),1200)
        self.assertNotEqual(games[0]["id"],"outdated")
        self.assertEqual(quality["games"],1200)
        self.assertEqual(quality["unassigned_games"],30)
        self.assertEqual(quality["age_hours"],2)
        self.assertEqual(quality["freshness"],"fresh")
        self.assertEqual(len(old["rows"]),1)  # selection cannot mutate prior FP
        self.assertEqual(old["games"][0]["id"],"kept_final")
        self.assertEqual(old["schedule"][0]["id"],"outdated")

    def test_invalid_calendar_keeps_last_known_with_honest_quality(self):
        for invalid in ({}, {"games":[]}, {"status":"verified_public_calendar_with_known_gaps","games":[]}):
            with self.subTest(invalid=invalid):
                games,source,quality,provider,warnings=select_live_schedule(
                    self.cdn_403,self.now,{"schedule":[{"id":"cached"}]},invalid)
                self.assertEqual(games,[{"id":"cached"}])
                self.assertEqual(source,"last known")
                self.assertEqual(quality["freshness"],"stale_unverified")
                self.assertIsNone(quality["age_hours"])
                self.assertFalse(quality["complete"])
                self.assertTrue(any("rejected" in w for w in warnings))

    def test_wrong_moscow_week_fail_closed(self):
        bad=deepcopy(self.calendar)
        bad["games"][0]["msk_week"]="2026-10-26"
        _,source,quality,_,_=select_live_schedule(self.cdn_403,self.now,{"schedule":[]},bad)
        self.assertEqual(source,"last known")
        self.assertEqual(quality["games"],0)

    def test_stale_verified_calendar_is_not_pretended_fresh(self):
        _,source,quality,_,_=select_live_schedule(
            self.cdn_403,self.now+dt.timedelta(hours=48),{},self.calendar)
        self.assertEqual(source,"data/schedule.json")
        self.assertEqual(quality["freshness"],"stale_requires_review")
        self.assertEqual(quality["age_hours"],50)

if __name__=="__main__":
    unittest.main()
