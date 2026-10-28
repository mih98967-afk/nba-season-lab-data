"""Tests for causal split, frozen source, short-minutes and player grouping."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.short_minutes_role_bands_research import (
    fit_development_only, scored_holdout, group_by_predicted_minutes,
    whole_player_uncertainty, build, MIN_DEV_GROUP,
)

def read(filename):
    return json.loads((DATA/filename).read_text(encoding="utf8"))

def historical_loader(filename):
    return read("history/"+filename)

class RoleBands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=read("history/index.json")
        cls.frozen=read("conditional_minutes_fp_research.json")
        cls.now=datetime.now(timezone.utc)
    def test_real_holdout_denominators_and_non_deployment(self):
        result=build(self.index,historical_loader,self.frozen,self.now)
        s=result["holdout_exploratory"]
        old=self.frozen["2025_26_untouched_early_season_played_holdout"]
        self.assertEqual(s["played_only_cases"],old["all"]["played_cases"])
        self.assertEqual(s["distinct_players"],old["distinct_players"])
        self.assertEqual(s["distinct_NBA_games"],old["distinct_NBA_games"])
        self.assertEqual(s["original_global_q90_coverage"] if "original_global_q90_coverage" in s else s["original_global_q90_coverage"],old["all"]["minutes_empirical_dev_q90_coverage"])
        self.assertEqual(result["dev_only_fit"]["development_cases"],3032)
        self.assertEqual(sum(x["played_only_cases"] for x in result[
            "holdout_by_predicted_minutes_before_2025_outcomes"].values()),
            s["played_only_cases"])
        self.assertFalse(result["quality_gate"]["adopt_on_site"])
        self.assertFalse(result["quality_gate"]["new_individual_minutes_interval_calibrated"])
    def test_no_holdout_used_to_fit_and_smooth_when_empty_group(self):
        dev=[{"split":"2024_25_dev","forecast_minutes":12.0 if i%2 else 32.0,
              "actual_minutes":4.0 if i%7==0 else 20.0,"player_id":str(i)}
             for i in range(250)]
        param=fit_development_only(dev,10.0)
        hold=[{"split":"2025_26_previously_inspected_holdout","forecast_minutes":12.0,
               "actual_minutes":0.1,"player_id":"x","game_id":"g"}]
        before=json.dumps(param,sort_keys=True)
        scored_holdout(hold,param)
        self.assertEqual(json.dumps(param,sort_keys=True),before)
        self.assertEqual(param["group_parameters_fitted_on_dev_only"]["15_to_under_25"][
            "dev_only_residual_q90_minutes"],10.0)
        self.assertGreaterEqual(param["group_parameters_fitted_on_dev_only"]["under_15"][
            "dev_cases"],MIN_DEV_GROUP)
        with self.assertRaises(ValueError):
            fit_development_only([dict(dev[0],split="2025_26_previously_inspected_holdout")],10.0)
    def test_prediction_role_bins_only_from_past_minutes(self):
        self.assertEqual(group_by_predicted_minutes(14.999),"under_15")
        self.assertEqual(group_by_predicted_minutes(15),"15_to_under_25")
        self.assertEqual(group_by_predicted_minutes(25),"25_to_under_35")
        self.assertEqual(group_by_predicted_minutes(35),"35_plus")
        with self.assertRaises(ValueError):group_by_predicted_minutes(-1)
    def test_player_bootstrap_repeatable(self):
        dev=[{"split":"2024_25_dev","forecast_minutes":20.0,
              "actual_minutes":7.0 if i%10==0 else 24.0} for i in range(250)]
        params=fit_development_only(dev,12.0)
        hold=[{"split":"2025_26_previously_inspected_holdout",
               "player_id":f"p{i}","game_id":f"g{i}_{j}",
               "forecast_minutes":20,"actual_minutes": 9.0 if (i+j)%10==0 else 20.0}
              for i in range(105) for j in range(3)]
        scored=scored_holdout(hold,params)
        a=whole_player_uncertainty(scored,draws=110,seed=17)
        self.assertEqual(a,whole_player_uncertainty(scored,draws=110,seed=17))
        self.assertLessEqual(a["paired_global_minus_group_Brier_gain"]["lower"],
                             a["paired_global_minus_group_Brier_gain"]["upper"])
    def test_tampering_with_frozen_2024_25_quantiles_rejected(self):
        x=deepcopy(self.frozen)
        x["2024_25_chronological_development_residuals"][
            "q90_absolute_residual_dev_only"]["minutes"] += 2
        with self.assertRaises(ValueError):
            build(self.index,historical_loader,x,self.now)
        x=deepcopy(self.frozen)
        x["adopt_on_site"]=True
        with self.assertRaises(ValueError):
            build(self.index,historical_loader,x,self.now)

if __name__=="__main__":unittest.main()
