import datetime as dt
from pathlib import Path
import tempfile
import unittest
import numpy as np
from freeze_pair import validate_target, immutable_write

class PairedFreezeTests(unittest.TestCase):
    def setUp(self):
        self.row = {"y_play": np.nan, "y_fp": np.nan, "horizon_days": 0,
                    "issue_date": "2026-11-17", "date": "2026-11-17", "team": "BOS", "opp": "NYK"}
        self.game = {"utc": "2026-11-18T00:00:00Z", "home": "BOS", "away": "NYK", "status": "scheduled"}
        self.issued = dt.datetime(2026, 11, 17, 20, tzinfo=dt.timezone.utc)

    def test_future_pair_is_allowed(self):
        validate_target(self.row, self.game, self.issued)

    def test_known_target_result_is_rejected(self):
        for field in ("y_fp", "y_play"):
            with self.assertRaises(ValueError):
                validate_target(dict(self.row, **{field: 0}), self.game, self.issued)

    def test_original_lead_cannot_be_renamed_near(self):
        with self.assertRaises(ValueError):
            validate_target(dict(self.row, horizon_days=1), self.game, self.issued)

    def test_t_minus_30_and_started_are_excluded(self):
        with self.assertRaises(ValueError):
            validate_target(self.row, self.game, dt.datetime(2026, 11, 17, 23, 30, tzinfo=dt.timezone.utc))
        with self.assertRaises(ValueError):
            validate_target(self.row, dict(self.game, status="final"), self.issued)

    def test_commitment_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.json"
            immutable_write(path, {"value": 1})
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                immutable_write(path, {"value": 2})
            self.assertEqual(path.read_bytes(), original)

if __name__ == "__main__":
    unittest.main()
