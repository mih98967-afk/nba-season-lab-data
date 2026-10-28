import unittest
from datetime import datetime, timezone, timedelta
from copy import deepcopy
from unittest.mock import patch
from src.official_nba_prelock_roster_pit_research import capture, extract_pregame, STATUS

T = datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc)
FIX = {"id": "0022600010", "home": "ATL", "away": "BOS",
       "utc": "2026-10-29T02:00:00Z"}
GAME = {"id": "espn_a", "utc": FIX["utc"], "home": "ATL", "away": "BOS",
        "status": "scheduled"}
LIVE = {"schema_version": 4, "schedule": [GAME]}

def box():
    return {"game": {"gameId": FIX["id"], "gameStatus": 1,
                     "gameTimeUTC": FIX["utc"],
                     "homeTeam": {"teamTricode": "ATL", "players":
                                  [{"personId": str(100 + i)} for i in range(10)]},
                     "awayTeam": {"teamTricode": "BOS", "players":
                                  [{"personId": str(200 + i)} for i in range(10)]}}}

class Tests(unittest.TestCase):
    def get(self, now=T, payload=None, old=None):
        with patch("src.official_nba_prelock_roster_pit_research.official_schedule", return_value=[FIX]):
            return capture(LIVE, {}, lambda url: payload if payload is not None else box(), now, old, clock=lambda: now + timedelta(seconds=2))

    def test_real_prelock_clock_only_and_append_only(self):
        r = self.get()
        self.assertEqual(r["qa"]["new"], 1)
        row = r["snapshots"][0]
        self.assertEqual(row["source_first_observed_at_utc"], "2026-10-29T00:00:00Z")
        self.assertEqual(row["individual_lock_utc"], "2026-10-29T01:30:00Z")
        self.assertFalse(row["game_day_active_eligibility_verified"])
        self.assertFalse(row["missing_player_implies_DNP"])
        self.assertFalse(r["model_training_permitted"])
        r2 = self.get(now=T + timedelta(minutes=20), old=r)
        self.assertEqual(r2["qa"]["new"], 0)
        self.assertEqual(r2["snapshots"], r["snapshots"])

    def test_after_lock_does_not_backfill(self):
        r = self.get(now=T + timedelta(minutes=91))
        self.assertEqual(r["qa"]["new"], 0)
        self.assertFalse(r["snapshots"])

    def test_missing_source_or_incomplete_roster_stays_unknown(self):
        payload = box()
        payload["game"]["homeTeam"]["players"] = []
        r = self.get(payload=payload)
        self.assertEqual(r["qa"]["unknown_or_unavailable"], 1)
        self.assertFalse(r["snapshots"])
        r = self.get(payload={"game": {"gameStatus": 3}})
        self.assertEqual(r["qa"]["unknown_or_unavailable"], 1)

    def test_network_response_after_lock_never_backdated(self):
        start = T + timedelta(minutes=89)
        r = self.get(now=start)
        self.assertEqual(r["qa"]["new"], 1)
        with patch("src.official_nba_prelock_roster_pit_research.official_schedule", return_value=[FIX]):
            late = capture(LIVE, {}, lambda _: box(), start,
                           clock=lambda: T + timedelta(minutes=91))
        self.assertEqual(late["qa"]["new"], 0)
        self.assertEqual(late["qa"]["source_finished_at_or_after_lock"], 1)
        self.assertEqual(late["snapshots"], [])

    def test_diagnostics_distinguish_partial_from_unavailable(self):
        partial = box()
        partial["game"]["homeTeam"]["players"] = []
        report = self.get(payload=partial)
        self.assertEqual(report["qa"]["nba_box_incomplete_pregame_listing"], 1)
        with patch("src.official_nba_prelock_roster_pit_research.official_schedule", return_value=[FIX]):
            def missing(_):
                from urllib.error import HTTPError
                raise HTTPError("https://example.com",404,"not found",None,None)
            report = capture(LIVE,{},missing,T,clock=lambda:T)
        self.assertEqual(report["qa"]["nba_box_http_404"],1)

    def test_wrong_game_and_cross_team_rejected(self):
        p = box()
        p["game"]["homeTeam"]["teamTricode"] = "NYK"
        with self.assertRaises(ValueError):
            extract_pregame(p, FIX)
        p = box()
        p["game"]["gameId"] = "0022600001"
        with self.assertRaises(ValueError):
            extract_pregame(p, FIX)

    def test_immutable_archive_and_no_future_source(self):
        r = self.get()
        corrupt = deepcopy(r)
        corrupt["snapshots"][0]["teams"][0]["club"] = "NYK"
        with self.assertRaises(ValueError):
            self.get(now=T + timedelta(minutes=10), old=corrupt)
        with self.assertRaises(ValueError):
            self.get(now=T-timedelta(minutes=1), old=r)

if __name__ == "__main__":
    unittest.main()
