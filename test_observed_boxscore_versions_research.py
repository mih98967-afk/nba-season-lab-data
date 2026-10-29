"""Regression for genuine row-level as-of reconstruction, no backdating."""
import unittest
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path

from src.observed_boxscore_versions_research import build,replay_asof
from src.rolling_decision_research import canonical_hash


def when(s): return datetime.fromisoformat(s.replace("Z","+00:00"))


class RowVersionResearch(unittest.TestCase):
    def data(self):
        row={"game_id":"g1","player_id":"p1","team":"BOS","fp":14,
             "minutes":23,"utc":"2026-10-28T00:00:00Z"}
        live={"schema_version":4,
              "updated_at_utc":"2026-10-29T14:00:00Z",
              "rows":[{"game_id":row["game_id"],"id":row["player_id"],
                       "team":row["team"],"fp":row["fp"],"minutes":row["minutes"],
                       "utc":row["utc"],"played":True}]}
        rolling={"schema_version":1,"status":"research_only_not_deployed",
                 "adopt_on_site":False,
                 "row_first_seen_at_utc":{"g1|p1":"2026-10-28T08:00:00Z"},
                 "row_hashes":{"g1|p1":canonical_hash(row)},
                 "snapshots":[{"corrected_rows":2}]}
        return live,rolling

    def test_legacy_first_seen_is_NOT_a_version_clock(self):
        live,rolling=self.data()
        record=build({},live,rolling,when("2026-10-29T15:00:00Z"))
        self.assertEqual(record["summary"]["unique_player_games"],1)
        self.assertEqual(record["summary"]["rolling_observed_corrections_total_no_row_values"],2)
        self.assertEqual(record["summary"]["observed_corrections_since_version_archive_started"],0)
        self.assertTrue(record["versions"]["g1|p1"][0]["legacy_value_before_version_not_proven"])
        self.assertEqual(replay_asof(record,when("2026-10-29T14:59:00Z")),{})
        self.assertEqual(replay_asof(record,when("2026-10-29T15:00:00Z"))["g1|p1"]["fp"],14)

    def test_correction_versions_are_asof_not_latest_value(self):
        live,rolling=self.data()
        first=build({},live,rolling,when("2026-10-29T15:00:00Z"))
        live["rows"][0]["fp"]=17
        rolling["row_hashes"]["g1|p1"]=canonical_hash({
            "game_id":"g1","player_id":"p1","team":"BOS",
            "fp":17,"minutes":23,"utc":"2026-10-28T00:00:00Z"})
        changed=build(first,live,rolling,when("2026-10-29T16:00:00Z"))
        self.assertEqual(changed["summary"]["captured_row_versions"],2)
        self.assertEqual(changed["summary"]["observed_corrections_since_version_archive_started"],1)
        self.assertEqual(replay_asof(changed,when("2026-10-29T15:30:00Z"))["g1|p1"]["fp"],14)
        self.assertEqual(replay_asof(changed,when("2026-10-29T16:30:00Z"))["g1|p1"]["fp"],17)
        self.assertEqual(changed["versions"]["g1|p1"][0],
                         first["versions"]["g1|p1"][0])
        self.assertEqual(build(changed,live,rolling,when("2026-10-29T17:00:00Z")),changed)

    def test_rolling_hash_mismatch_is_fatal(self):
        live,rolling=self.data()
        rolling["row_hashes"]["g1|p1"]="0"*64
        with self.assertRaisesRegex(ValueError,"authoritative rolling hash"):
            build({},live,rolling,when("2026-10-29T15:00:00Z"))

    def test_old_value_tamper_cannot_launder_asof(self):
        live,rolling=self.data()
        first=build({},live,rolling,when("2026-10-29T15:00:00Z"))
        changed=deepcopy(first)
        changed["versions"]["g1|p1"][0]["row"]["fp"]=99
        with self.assertRaisesRegex(ValueError,"Existing observed row versions"):
            build(changed,live,rolling,when("2026-10-29T16:00:00Z"))
        with self.assertRaisesRegex(ValueError,"Corrupted earlier source"):
            replay_asof(changed,when("2026-10-29T15:30:00Z"))

    def test_missing_firstseen_future_and_disappeared_guard(self):
        live,rolling=self.data()
        rolling["row_first_seen_at_utc"]["g1|p1"]="2026-10-29T18:00:00Z"
        with self.assertRaises(ValueError):
            build({},live,rolling,when("2026-10-29T15:00:00Z"))
        live,rolling=self.data()
        first=build({},live,rolling,when("2026-10-29T15:00:00Z"))
        live["rows"].clear()
        rolling["row_first_seen_at_utc"].clear()
        rolling["row_hashes"].clear()
        with self.assertRaises(ValueError):
            build(first,live,rolling,when("2026-10-29T16:00:00Z"))

    def test_no_double_writer_or_historical_retroactive_issues(self):
        root=Path(__file__).resolve().parent
        workflow=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(workflow.count("python -m src.observed_boxscore_versions_research"),2)
        self.assertIn("data/observed_boxscore_versions_research.json",workflow)
        self.assertIn("test_observed_boxscore_versions_research",workflow)
        parts=workflow.split("python -m src.rolling_decision_research")
        self.assertEqual(len(parts),3)
        for part in parts[1:]:
            self.assertLess(part.index("python -m src.observed_boxscore_versions_research"),
                            part.index("python -m src.participation_cohort_research"))


if __name__=="__main__":
    unittest.main()
