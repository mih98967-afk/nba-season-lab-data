import unittest
from copy import deepcopy

import numpy as np
import pandas as pd

from general_opponent import opponent_residual_features
from position_contract import normalize_name, resolve_position
from run_general_opponent import prequential_mean


def record(**overrides):
    row = dict(person_id="1", season="2026/27", position="PG", identity_status="exact_unique_normalized_name", source_kind="fantasy_catalog_snapshot", source_ref="frozen.json", source_sha256="abc", observed_at="2026-11-17T12:00:00Z", effective_from="2026-10-20T00:00:00Z", effective_until=None)
    return dict(row, **overrides)


class PositionContractTests(unittest.TestCase):
    def test_future_observation_is_unavailable_even_with_early_effective_date(self):
        self.assertEqual(resolve_position([record()], "1", "2026/27", "2026-11-17T11:59:00Z")["position"], "UNKNOWN")

    def test_current_catalog_does_not_backfill_historical_season(self):
        self.assertEqual(resolve_position([record()], "1", "2025/26", "2026-11-18T00:00:00Z")["position"], "UNKNOWN")

    def test_coarse_guard_or_starter_position_rejected(self):
        self.assertEqual(resolve_position([record(position="G")], "1", "2026/27", "2026-11-18T00:00:00Z")["position"], "UNKNOWN")
        self.assertEqual(resolve_position([record(position="C", source_kind="nba_starter_label")], "1", "2026/27", "2026-11-18T00:00:00Z")["position"], "UNKNOWN")

    def test_conflict_is_not_hidden_by_latest_snapshot(self):
        result = resolve_position([record(), record(position="SG", observed_at="2026-11-18T00:00:00Z")], "1", "2026/27", "2026-11-19T00:00:00Z")
        self.assertEqual(result["status"], "conflict")

    def test_expired_record_can_be_replaced_explicitly(self):
        result = resolve_position([record(effective_until="2026-11-18T00:00:00Z"), record(position="SG", observed_at="2026-11-18T00:00:00Z", effective_from="2026-11-18T00:00:00Z")], "1", "2026/27", "2026-11-19T00:00:00Z")
        self.assertEqual(result["position"], "SG")
        self.assertEqual(result["status"], "resolved_catalog")

    def test_ambiguous_identity_missing_provenance_and_naive_timezone_rejected(self):
        for bad in [record(identity_status="fuzzy"), record(source_sha256=None)]:
            self.assertEqual(resolve_position([bad], "1", "2026/27", "2026-11-19T00:00:00Z")["position"], "UNKNOWN")
        with self.assertRaises(ValueError):
            resolve_position([record()], "1", "2026/27", "2026-11-19T00:00:00")

    def test_name_normalization_does_not_do_fuzzy_matching(self):
        self.assertEqual(normalize_name("Nikola Jokić"), normalize_name("Nikola Jokic"))
        self.assertNotEqual(normalize_name("Jalen Williams"), normalize_name("Jaylin Williams"))


class ResidualFeatureTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame([
            dict(date="2025-01-01", opp="DAL", game="g1", y_play=1, y_fp=12.0),
            dict(date="2025-01-01", opp="DAL", game="g1", y_play=1, y_fp=14.0),
            dict(date="2025-01-02", opp="DAL", game="g2", y_play=1, y_fp=20.0),
            dict(date="2025-01-03", opp="DAL", game="g3", y_play=1, y_fp=7.0),
        ])

    def test_cold_start_is_zero_and_same_day_is_excluded(self):
        f = opponent_residual_features(self.frame(), [10]*4)
        self.assertEqual(f.adj_opp_residual.iloc[0], 0)
        self.assertEqual(f.adj_opp_residual.iloc[1], 0)
        self.assertGreater(f.adj_opp_residual.iloc[2], 0)

    def test_future_outcome_mutation_does_not_change_prior_features(self):
        d = self.frame()
        a = opponent_residual_features(d, [10]*4)
        d.loc[2:, "y_fp"] = [-100000, 100000]
        b = opponent_residual_features(d, [10]*4)
        np.testing.assert_array_equal(a.iloc[:3].to_numpy(), b.iloc[:3].to_numpy())

    def test_shrinkage_and_decay_are_explicit(self):
        d = self.frame()
        d.loc[2, "date"] = "2025-03-02"
        d.loc[3, "date"] = "2025-03-03"
        f = opponent_residual_features(d, [10]*4, prior_strength=50, half_life=60)
        self.assertAlmostEqual(f.adj_opp_weighted_n.iloc[2], 1.0)
        self.assertAlmostEqual(f.adj_opp_residual.iloc[2], 3.0/51.0)
        self.assertAlmostEqual(f.adj_opp_effective_games.iloc[2], 1.0)

    def test_unknown_and_nonfinite_forecasts_never_create_residuals(self):
        d = self.frame()
        d.loc[0, "y_play"] = np.nan
        d.loc[1, "y_fp"] = np.nan
        f = opponent_residual_features(d, [np.nan, 10, 10, 10])
        self.assertEqual(f.adj_opp_weighted_n.iloc[2], 0)
        self.assertTrue(np.isfinite(f.to_numpy()).all())

    def test_alignment_and_hyperparameter_validation(self):
        with self.assertRaises(ValueError):
            opponent_residual_features(self.frame(), [10], prior_strength=50)
        with self.assertRaises(ValueError):
            opponent_residual_features(self.frame(), [10]*4, prior_strength=0)


class PrequentialFitTests(unittest.TestCase):
    def frame(self):
        rows = []
        for month in (1, 2, 3):
            for day in range(1, 21):
                rows.append(dict(date=f"2025-{month:02d}-{day:02d}", y_play=1., y_fp=10. + day / 5 + month, fp10=10., trend=float(day % 4)))
        return pd.DataFrame(rows)

    def test_each_nuisance_fit_precedes_its_prediction_month(self):
        d = self.frame()
        pred, fits = prequential_mean(d, ["fp10", "trend"], minimum_training=10)
        self.assertTrue(np.isnan(pred[:20]).all())
        for fit in fits:
            if fit["predicted_n"]:
                self.assertLess(fit["train_max_date"], fit["prediction_min_date"])

    def test_future_targets_never_change_earlier_nuisance_predictions(self):
        d = self.frame()
        a, _ = prequential_mean(d, ["fp10", "trend"], minimum_training=10)
        d.loc[d.date >= "2025-03-01", "y_fp"] = 100000
        b, _ = prequential_mean(d, ["fp10", "trend"], minimum_training=10)
        np.testing.assert_allclose(a, b, equal_nan=True)


if __name__ == "__main__":
    unittest.main()
