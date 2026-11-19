"""Timestamp regression for NBA v6.21 real-data browser acceptance."""
import unittest
from datetime import datetime, timedelta, timezone

from test_hosting_v621_browser import difficulty_snapshot_is_fresh

UTC = timezone.utc


class DifficultyFreshnessClockTests(unittest.TestCase):
    def setUp(self):
        self.replay = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
        self.now = self.replay + timedelta(minutes=8)

    def test_generated_after_forecast_replay_is_valid_on_wall_clock(self):
        later = (self.replay + timedelta(minutes=6)).isoformat()
        self.assertTrue(difficulty_snapshot_is_fresh(later, self.replay, True, self.now))
        self.assertFalse(difficulty_snapshot_is_fresh(later, self.replay, False, self.now))

    def test_stale_more_than_72_hours_rejected(self):
        stale = (self.now - timedelta(hours=72, seconds=1)).isoformat()
        self.assertFalse(difficulty_snapshot_is_fresh(stale, self.replay, True, self.now))

    def test_future_generated_time_rejected(self):
        future = (self.now + timedelta(seconds=1)).isoformat()
        self.assertFalse(difficulty_snapshot_is_fresh(future, self.replay, True, self.now))

    def test_exact_72_hour_boundary_is_allowed(self):
        boundary = (self.now - timedelta(hours=72)).isoformat()
        self.assertTrue(difficulty_snapshot_is_fresh(boundary, self.replay, True, self.now))

    def test_fixture_clock_is_deterministic(self):
        self.assertTrue(difficulty_snapshot_is_fresh(self.replay.isoformat(), self.replay, False, self.now))


if __name__ == "__main__":
    unittest.main()
