"""Actual saved-weight inference parity, independent of package hash validation."""
import json
import os
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from infer import load_verified
from infer_near import predict_near


HERE = Path(__file__).resolve().parent
BUNDLED_MODEL_DIR = HERE / 'models/20261116/results_near_latest'
MODEL_CANDIDATES = [BUNDLED_MODEL_DIR]
if os.environ.get('NBA_RESEARCH_BASE'):
    MODEL_CANDIDATES.append(Path(os.environ['NBA_RESEARCH_BASE']).resolve() / 'results_near_latest')
MODEL_CANDIDATES.append(HERE.parents[1] / 'research_base/results_near_latest')
MODEL_DIR = next((directory for directory in MODEL_CANDIDATES
                  if (directory / 'research_models.pkl').is_file()), BUNDLED_MODEL_DIR)


class FrozenModelParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((HERE / "fixtures/near_game_parity_20261116.json").read_text())
        cls.report = json.loads((MODEL_DIR / 'MODEL_RESEARCH_REPORT.json').read_text())

    def test_fixture_uses_original_model_and_pregame_inputs(self):
        self.assertEqual(self.report["model_sha256"], self.fixture["model_sha256"])
        self.assertEqual(self.fixture["row_count"], 20)
        frame = pd.DataFrame(self.fixture["features"])
        self.assertFalse({"y_play", "y_fp", "y_minutes"} & set(frame))
        self.assertTrue((frame.season <= 2026).all())
        self.assertTrue((frame.horizon_days == 0).all())
        self.assertTrue((frame.issue_date == frame.date).all())
        self.assertTrue({"Out", "Doubtful", "Questionable", "Probable", "Available",
                         "minutes_under15", "minutes28plus", "return7days"}
                        <= set(self.fixture["covered_conditions"]))

    @unittest.skipUnless((MODEL_DIR / 'research_models.pkl').exists(),
                         'Saved-weight parity is run locally with companion binary artifacts; CI is not a full model rerun')
    def test_frozen_weight_mean_probability_and_interval_parity(self):
        bundle, _ = load_verified(MODEL_DIR)
        frame = pd.DataFrame(self.fixture["features"])
        prediction = predict_near(bundle, frame)
        fields = self.fixture["expected_prediction_fields"]
        expected = pd.DataFrame(self.fixture["expected_predictions"])[fields].to_numpy(float)
        actual = prediction[fields].to_numpy(float)
        self.assertEqual(actual.shape, (20, 15))
        self.assertTrue(np.isfinite(actual).all())
        np.testing.assert_allclose(actual, expected, **self.fixture["tolerance"],
                                   err_msg="Saved-weight inference changed from the preserved historical fixture")


if __name__ == "__main__":
    unittest.main()
