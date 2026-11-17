import unittest
import numpy as np
import pandas as pd
from calibration import (apply_status_offsets, calibration_masks, exact_order_quantile,
                         fit_status_offsets, nested_bands, status_groups, validate_quantiles)


def frame(n=1):
    return pd.DataFrame({k: np.zeros(n, dtype=int) for k in [
        "inj_report_present", "inj_team_submitted", "inj_unknown_identity", "inj_not_listed",
        "inj_out", "inj_doubtful", "inj_questionable", "inj_probable", "inj_available"]})


class Guards(unittest.TestCase):
    def test_status_missing_not_available(self):
        self.assertEqual(status_groups(frame()).tolist(), ["no_report"])

    def test_submitted_not_listed_is_separate(self):
        f = frame(2);f.inj_report_present = 1;f.inj_team_submitted = 1
        f.loc[0, "inj_not_listed"] = 1;f.loc[1, "inj_available"] = 1
        self.assertEqual(status_groups(f).tolist(), ["not_listed", "Available"])

    def test_status_conflict_rejected(self):
        f = frame();f.inj_out = 1;f.inj_available = 1
        with self.assertRaisesRegex(ValueError, "CONFLICTING"):
            status_groups(f)

    def test_nan_probability_rejected(self):
        with self.assertRaises(ValueError):
            validate_quantiles([[-2, 5]], [.1, .9], [np.nan])

    def test_bad_quantile_shapes_rejected(self):
        with self.assertRaises(ValueError):
            validate_quantiles([[-2, 5]], [.1, .9], [.5, .9])

    def test_negative_fp_valid(self):
        q, _, _ = validate_quantiles([[-5, 5]], [.1, .9], [.5])
        self.assertEqual(q[0, 0], -5)

    def test_exact_kth_rank(self):
        # n=10, k=ceil(11*.8)=9, so 9th sorted score is 8.
        self.assertEqual(exact_order_quantile(np.arange(10), .2), 8)

    def test_small_sample_infinite_bound(self):
        self.assertTrue(np.isinf(exact_order_quantile(np.arange(10), .05)))

    def test_unknown_labels_never_zero(self):
        with self.assertRaisesRegex(ValueError, "KNOWN_BINARY"):
            fit_status_offsets([.6], [np.nan], ["Questionable"])

    def test_sparse_group_shrunk(self):
        offsets = fit_status_offsets([.5], [0], ["Questionable"])
        self.assertGreater(offsets["Questionable"], -.03)
        self.assertLess(offsets["Questionable"], 0)

    def test_absent_group_fallback(self):
        np.testing.assert_allclose(apply_status_offsets([.7], ["unseen"], {}), [.7])

    def test_current_outcomes_rejected(self):
        with self.assertRaisesRegex(ValueError, "CURRENT_SEASON"):
            calibration_masks(pd.DataFrame({"date": ["2026-10-20"], "season": [2027]}))

    def test_calibration_disjoint(self):
        f = pd.DataFrame({"date": ["2026-01-23", "2026-01-24", "2026-02-15", "2026-02-16"], "season": [2026] * 4})
        m = calibration_masks(f)
        np.testing.assert_array_equal(sum(m.values()), np.ones(4))

    def test_nesting_only_expands(self):
        original = {50: (np.array([-2.]), np.array([5.])), 80: (np.array([-1.]), np.array([6.])), 95: (np.array([0.]), np.array([4.]))}
        b = nested_bands(original)
        self.assertEqual(b[95][0][0], -2);self.assertEqual(b[95][1][0], 6)
        for k in original:
            self.assertTrue((b[k][0] <= original[k][0]).all())
            self.assertTrue((b[k][1] >= original[k][1]).all())


if __name__ == "__main__":
    unittest.main()
