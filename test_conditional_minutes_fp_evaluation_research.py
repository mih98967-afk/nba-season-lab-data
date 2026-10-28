import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from src.sync import DATA
from src.conditional_minutes_fp_evaluation_research import build

FILES = ("conditional_minutes_fp_research.json", "p_play_shadow_research.json",
         "participation_cohort_research.json", "explicit_dnp_research.json", "live.json")


class ConditionalMinutesProspectiveEvaluation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = [json.loads((DATA / name).read_text(encoding="utf8"))
                      for name in FILES]
        cls.now = datetime.now(timezone.utc)

    def make(self, args=None):
        return build(*(self.inputs if args is None else args), self.now)

    def test_real_immutable_issues_and_outcomes(self):
        report = self.make()
        issued = self.inputs[0]["issued"]
        n = report["summary"]
        self.assertEqual(n["issued_total"], len(issued))
        self.assertEqual(n["finished_checked"] + n["awaiting_or_unchecked"],
                         len(issued))
        self.assertEqual(n["played"] + n["explicit_DNP_not_scored"] +
                         n["UNKNOWN_not_imputed"], n["finished_checked"])
        self.assertEqual(len(report["scored_played"]), n["played"])
        self.assertEqual(len(report["UNKNOWN_unscored"]),
                         n["UNKNOWN_not_imputed"])
        self.assertTrue(report["frozen_minutes_issue_sha256"])
        self.assertFalse(report["quality_gate"]["unconditional_FP_allowed"])
        self.assertFalse(report["quality_gate"]["adopt_on_site"])

    def test_error_metrics_are_conditional_and_source_grounded(self):
        result = self.make()
        actual = result["scored_played"]
        self.assertTrue(actual, "Need current genuinely scored observations")
        gain = sum(abs(r["predicted_direct_fp"]-r["actual_fp_reconstructed"])
                   - abs(r["predicted_decomposed_fp"]-r["actual_fp_reconstructed"])
                   for r in actual) / len(actual)
        self.assertAlmostEqual(gain, result[
            "positive_minutes_selected_only_metrics"][
            "direct_minus_decomposed_FP_MAE"], delta=0.000051)
        self.assertTrue(all(r["actual_minutes"] > 0 for r in actual))
        self.assertTrue(all(r["outcome"] == "played" for r in actual))
        self.assertTrue(all(r["not_scored_as_zero_FP"] for r in
                            result["explicit_DNP_not_in_conditional_metrics"]))

    def test_missing_boxscore_keeps_unknown(self):
        result = self.make()
        for missing in result["UNKNOWN_unscored"]:
            self.assertEqual(missing["outcome"], "UNKNOWN")
            self.assertNotIn("actual_fp_reconstructed", missing)
        self.assertFalse(result["quality_gate"][
            "dev_q90_bands_are_valid_future_predictive_intervals"])

    def test_absent_et_metadata_uses_verified_tipoff_but_conflict_fails(self):
        args = deepcopy(self.inputs)
        existing = self.make()
        target = existing["scored_played"][0]["game_id"]
        game = next(g for g in args[4]["games"] if g["id"] == target)
        game.pop("et_date", None)
        self.assertEqual(self.make(args)["summary"], existing["summary"])
        game["et_date"] = "2030-01-01"
        with self.assertRaises(ValueError):
            self.make(args)

    def test_unarchived_first_seen_positive_stays_UNKNOWN(self):
        args = deepcopy(self.inputs)
        current = self.make()
        target = current["scored_played"][0]
        key = (target["game_id"], target["player_id"])
        cohort = next(r for r in args[2]["records"]
                      if (r["game_id"], r["player_id"]) == key)
        cohort["source_first_observed_at_utc"] = None
        args[1]["observations"] = [
            x for x in args[1]["observations"]
            if (x["game_id"], x["player_id"]) != key]
        updated = self.make(args)
        self.assertEqual(updated["summary"]["played"], current["summary"]["played"] - 1)
        self.assertEqual(updated["summary"]["UNKNOWN_not_imputed"],
                         current["summary"]["UNKNOWN_not_imputed"] + 1)
        self.assertTrue(any((r["game_id"], r["player_id"]) == key
                            for r in updated["UNKNOWN_unscored"]))

    def test_lock_time_tampering_rejected(self):
        args = deepcopy(self.inputs)
        issue = args[0]["issued"][0]
        issue["issued_at_utc"] = issue["individual_lock_utc"]
        with self.assertRaises(ValueError):
            self.make(args)

    def test_mismatched_club_rejected(self):
        args = deepcopy(self.inputs)
        row = args[2]["records"][0]
        match = next((i for i in args[0]["issued"]
                      if i["game_id"] == row["game_id"] and
                      i["player_id"] == row["player_id"]), None)
        if match is None:
            report = self.make()
            self.assertTrue(report["scored_played"])
            example = report["scored_played"][0]
            row = next(x for x in args[2]["records"] if
                       x["game_id"] == example["game_id"] and
                       x["player_id"] == example["player_id"])
        row["team"] = "INVALID"
        with self.assertRaises(ValueError):
            self.make(args)

    def test_postgame_source_before_tip_rejected(self):
        args = deepcopy(self.inputs)
        report = self.make()
        if not report["scored_played"]:
            self.skipTest("No positive-minute outcomes yet")
        x = report["scored_played"][0]
        row = next(x0 for x0 in args[2]["records"]
                   if (x0["game_id"], x0["player_id"]) ==
                   (x["game_id"], x["player_id"]))
        row["source_first_observed_at_utc"] = "2020-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            self.make(args)

    def test_fp_provenance_reconstruction_required(self):
        args = deepcopy(self.inputs)
        report = self.make()
        if not report["scored_played"]:
            self.skipTest("No positive-minute outcomes yet")
        x = report["scored_played"][0]
        row = next(x0 for x0 in args[4]["rows"]
                   if (x0["game_id"], x0["id"]) ==
                   (x["game_id"], x["player_id"]))
        row["fp"] += 1
        with self.assertRaises(ValueError):
            self.make(args)

    def test_deployment_and_fake_DNP_rejected(self):
        args = deepcopy(self.inputs)
        args[0]["adopt_on_site"] = True
        with self.assertRaises(ValueError):
            self.make(args)
        args = deepcopy(self.inputs)
        report = self.make()
        if not report["UNKNOWN_unscored"]:
            self.skipTest("No unknown example in this snapshot")
        unknown = report["UNKNOWN_unscored"][0]
        args[2]["records"].append({
            "game_id": unknown["game_id"], "player_id": unknown["player_id"],
            "team": unknown["team"], "game_utc": unknown["game_utc"],
            "played": False, "participation_label": 0,
            "source_first_observed_at_utc": self.now.isoformat(),
            "evidence": "official_OUT_not_a_DNP",
            "catalog_team_matches_game": True})
        with self.assertRaises(ValueError):
            self.make(args)


if __name__ == "__main__":
    unittest.main()
