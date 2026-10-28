"""Public research-only regression for append-only OUT evidence catch-up."""
import json
import unittest
from datetime import datetime, timezone
from src.sync import DATA
from src.official_out_boxscore_evidence_research import audit


class CompletedOutCatchup(unittest.TestCase):
    def test_existing_case_immutable_when_new_ESPN_source_unavailable(self):
        load = lambda path: json.loads((DATA / path).read_text(encoding="utf8"))
        previous = load("official_out_boxscore_evidence_research.json")
        selection = load("p_play_selection_bias_audit.json")
        before = {(x["game_id"], x["player_id"]): x
                  for x in previous["records"]}
        self.assertEqual(len(before), len(previous["records"]))
        roster = [json.loads(p.read_text(encoding="utf8"))
                  for p in sorted((DATA / "espn_roster_pit").glob("*.json"))]
        def offline_source(_):
            raise TimeoutError("simulated source outage")
        report, qa = audit(selection["out_status_missing_review_queue"],
                           load("p_play_shadow_research.json"), load("live.json"),
                           load("explicit_dnp_research.json"),
                           load("official_injury_status_archive.json"), roster,
                           previous, offline_source, datetime.now(timezone.utc))
        after = {(x["game_id"], x["player_id"]): x for x in report["records"]}
        for key, frozen in before.items():
            self.assertIn(key, after)
            self.assertEqual(frozen, after[key])
            self.assertFalse(after[key]["model_training_negative"])
        self.assertTrue(report["no_inferred_DNP_from_unlisted_athletes"])
        self.assertFalse(report["adopt_on_site"])
        self.assertFalse(report["model_training_negative_allowed"])
        self.assertEqual(qa["new"], 0)
        self.assertEqual(len(after), len(before))
        self.assertEqual(qa["total"], len(before))


if __name__ == "__main__":
    unittest.main()
