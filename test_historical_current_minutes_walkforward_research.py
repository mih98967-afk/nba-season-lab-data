"""Fail-closed tests for retrospective date-only, positive-played NBA comparisons."""
import unittest
from pathlib import Path

from src.historical_current_minutes_walkforward_research import (
    _row, evaluate_player, paired_metrics, build, STATUS,
)


def game(day, minutes, fp, team="BOS", gid="0022400001"):
    return {"d": day, "min": float(minutes), "fp": float(fp),
            "team": team, "g": gid}


def previous():
    return [game("2024-03-%02d" % (i + 1), 30, 25, gid="002230%04d" % i)
            for i in range(25)]


def current():
    return [game("2024-11-%02d" % (i + 1), 18 + i, 20,
                 gid="002240%04d" % i) for i in range(7)]


class HistoricalAnalogue(unittest.TestCase):
    def test_challenger_uses_only_prior_current_season_played(self):
        records, qa = evaluate_player("n007", previous(), current(), "2024/25")
        self.assertEqual(qa["paired_played_only"], 4)
        self.assertEqual(records[0]["player_season_played_game_number"], 4)
        self.assertEqual(records[0]["prior_current_same_team_n"], 3)
        self.assertLess(records[0]["challenger_minutes"], records[0]["baseline_minutes"])
        self.assertEqual(records[0]["prior_current_last_date"], "2024-11-03")

    def test_later_game_cannot_change_earlier_forecast(self):
        base = evaluate_player("n007", previous(), current()[:4], "2024/25")[0][0]
        added = current()[:4] + [game("2024-12-01", 60, 100, gid="0022400199")]
        after = evaluate_player("n007", previous(), added, "2024/25")[0][0]
        self.assertEqual(base, after)

    def test_same_day_final_unknown_time_not_used(self):
        rows = current()[:3]
        rows[2]["d"] = "2024-11-04"
        rows.append(game("2024-11-04", 14, 10, gid="0022400099"))
        selected, qa = evaluate_player("n007", previous(), rows, "2024/25")
        self.assertEqual(selected, [])
        self.assertEqual(qa["fewer_than_three_prior_played_games_same_club"], 4)

    def test_no_previous_prior_or_changed_club(self):
        rows, qa = evaluate_player("n007", [], current(), "2024/25")
        self.assertEqual(rows, [])
        self.assertEqual(qa["no_previous_season_same_club_20_game_prior"], 7)
        rows, qa = evaluate_player("n007", previous(), [
            game("2024-11-%02d" % (i + 1), 30, 25, "NYK", "002240%04d" % i)
            for i in range(7)], "2024/25")
        self.assertEqual(rows, [])
        self.assertEqual(qa["observed_club_differs_from_previous_year_prior"], 7)

    def test_early_and_late_history_not_retrofit(self):
        current_rows = current() + [
            game("2024-11-%02d" % (i + 1), 20, 22,
                 gid="002240%04d" % i) for i in range(7, 13)]
        selected, _ = evaluate_player("n007", previous(), current_rows, "2024/25")
        self.assertEqual(len([x for x in selected
                              if x["player_season_played_game_number"] <= 10]), 7)
        self.assertEqual(len([x for x in selected
                              if x["player_season_played_game_number"] > 10]), 3)

    def test_no_zero_minutes_or_wrong_year(self):
        with self.assertRaises(ValueError):
            _row(game("2024-11-04", 0, 0), "2024/25")
        with self.assertRaises(ValueError):
            _row(game("2024-11-04", 20, 15, gid="0022301000"), "2024/25")
        with self.assertRaises(ValueError):
            _row(game("2026-11-04", 20, 15), "2024/25")

    def test_metrics_pair_on_same_rows(self):
        rows = [{
            "player_id": "n007", "game_id": "g", "date": "2024-11-01",
            "actual_minutes": 24.0, "actual_fp": 20.0,
            "baseline_minutes": 30.0, "challenger_minutes": 25.0,
            "baseline_fp": 26.0, "challenger_fp": 21.0,
        }]
        report = paired_metrics(rows)
        self.assertEqual(report["minutes_if_play"]["paired_MAE_gain_positive_favors_challenger"], 5)
        self.assertEqual(report["FP_given_played"]["paired_MAE_gain_positive_favors_challenger"], 5)

    def test_reject_incomplete_history_index(self):
        with self.assertRaisesRegex(ValueError, "Incomplete public"):
            build({"status": "complete", "version": "fake", "player_shards": {}},
                  lambda filename: {})

    def test_one_public_writer_and_research_not_deployed(self):
        root = Path(__file__).resolve().parent
        workflow = (root / ".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(workflow.count("python -m src.historical_current_minutes_walkforward_research"), 2)
        self.assertIn("data/historical_current_minutes_walkforward_research.json", workflow)
        self.assertIn("test_historical_current_minutes_walkforward_research", workflow)
        source = (root / "src/historical_current_minutes_walkforward_research.py").read_text()
        self.assertIn('STATUS = "research_only_not_deployed"', source)
        self.assertNotIn("Firestore", workflow)
        self.assertEqual(STATUS, "research_only_not_deployed")


if __name__ == "__main__":
    unittest.main()
