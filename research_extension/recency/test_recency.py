import unittest
import numpy as np
import pandas as pd
from features import weighted_history, build_recency_features, training_weights

def history():
    return pd.DataFrame([
        {"pid": "1", "game": "g1", "date": "2024-01-01", "played": 1, "fp": 10., "minutes": 20.},
        {"pid": "1", "game": "g2", "date": "2024-01-03", "played": 1, "fp": 30., "minutes": 30.},
        {"pid": "1", "game": "g3", "date": "2024-01-05", "played": 0, "fp": 0., "minutes": 0.},
        {"pid": "1", "game": "g4", "date": "2024-01-07", "played": np.nan, "fp": np.nan, "minutes": 0.},
        {"pid": "1", "game": "g5", "date": "2024-01-09", "played": 1, "fp": -5., "minutes": 10.},
    ])

class RecencyTests(unittest.TestCase):
    def test_same_day_and_future_outcomes_cannot_change_features(self):
        h = history()
        a = weighted_history(h, "2024-01-09", kind="games", half_life=3)
        h.loc[h.date >= "2024-01-09", ["fp", "minutes"]] = 99999
        self.assertEqual(a, weighted_history(h, "2024-01-09", kind="games", half_life=3))

    def test_unknown_and_dnp_are_not_zero_played_performance(self):
        h = history()
        a = weighted_history(h, "2024-01-09", kind="days", half_life=7)
        b = weighted_history(h.loc[h.played == 1], "2024-01-09", kind="days", half_life=7)
        self.assertEqual(a, b)

    def test_calendar_gap_does_not_artificially_change_normalized_mean(self):
        h = history().iloc[:2]
        a = weighted_history(h, "2024-01-04", kind="days", half_life=7)
        b = weighted_history(h, "2024-10-04", kind="days", half_life=7)
        for k in a:
            self.assertAlmostEqual(a[k], b[k])

    def test_negative_fp_retained_and_recent_weight_has_expected_direction(self):
        h = history()
        a = weighted_history(h, "2024-01-10", kind="games", half_life=1)
        self.assertAlmostEqual(a["fp"], (10*.25+30*.5-5)/1.75)
        self.assertGreater(a["effective_n"], 1)
        self.assertLess(a["effective_n"], 3)

    def test_optimized_builder_matches_reference_with_unknown_player(self):
        t = pd.DataFrame({"pid": ["1", "1", "2"], "date": ["2024-01-09", "2024-01-10", "2024-01-10"]})
        f = build_recency_features(t, history())
        for i in (0, 1):
            for prefix, kind, half in (("g3", "games", 3), ("d21", "days", 21)):
                expected = weighted_history(history(), t.iloc[i].date, kind=kind, half_life=half)
                for key, value in expected.items():
                    self.assertAlmostEqual(f.iloc[i][f"ew_{prefix}_{key}"], value)
        self.assertTrue(np.isnan(f.iloc[2].ew_g3_fp))
        self.assertEqual(f.iloc[2].ew_g3_effective_n, 0)

    def test_training_weights_are_fit_window_only_and_normalized(self):
        d = pd.Series(["2024-01-01", "2024-01-11"])
        w = training_weights(d, 10)
        self.assertAlmostEqual(w.mean(), 1.)
        self.assertAlmostEqual(w[1] / w[0], 2.)

    def test_input_order_does_not_change_weighted_summary(self):
        h = history()
        self.assertEqual(weighted_history(h, "2024-01-10", kind="games", half_life=3),
                         weighted_history(h.sample(frac=1, random_state=5), "2024-01-10", kind="games", half_life=3))

if __name__ == "__main__":
    unittest.main()
