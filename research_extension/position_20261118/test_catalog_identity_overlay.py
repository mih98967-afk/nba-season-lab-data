import copy
import unittest

from build_catalog_identity_overlay import build


class CatalogIdentityOverlayTests(unittest.TestCase):
    def setUp(self):
        self.player = {"id": "n900", "name": "Тестовый игрок", "english": None, "team": "BOS", "pos": "PG", "history": []}
        self.people = {"123": {"name": "Test Player", "names": ["Test Player"]},
                       "456": {"name": "Other Player", "names": ["Other Player"]}}

    def run_case(self, players=None, identities=None, rows=None, mapping=None):
        return build({"players": players or [self.player]}, {"players": identities or {}}, {"rows": rows or []},
                     self.people, {"records": mapping or []})

    def test_medium_statistical_identity_alone_is_not_promoted(self):
        out = self.run_case(identities={"n900": {"nba_id": "123", "confidence": "medium"}})
        self.assertEqual(out["players"], {})
        self.assertTrue(out["unresolved"][0]["unknown_not_DNP"])

    def test_exact_observed_full_name_can_upgrade_matching_medium_identity(self):
        out = self.run_case(identities={"n900": {"nba_id": "123", "confidence": "medium"}},
                            rows=[{"id": "n900", "name": "Test Player", "team": "BOS", "utc": "2026-11-17T00:00:00Z"}])
        self.assertEqual(out["players"]["n900"]["nba_id"], "123")
        self.assertEqual(out["players"]["n900"]["confidence"], "high")
        self.assertFalse(out["historical_vintage_verified"])

    def test_conflicting_full_names_remain_unresolved(self):
        out = self.run_case(rows=[{"id": "n900", "name": name, "team": "BOS", "utc": "2026-11-17T00:00:00Z"}
                                  for name in ["Test Player", "Other Player"]])
        self.assertEqual(out["players"], {})
        self.assertEqual(out["unresolved"][0]["reason"], "conflicting_observed_full_names")

    def test_unreviewed_existing_id_contradiction_fails(self):
        self.player["english"] = "Test Player"
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_IDENTITY_CONFLICT"):
            self.run_case(identities={"n900": {"nba_id": "456", "confidence": "medium"}})

    def test_two_catalog_cards_for_one_nba_id_fail(self):
        self.player["english"] = "Test Player"
        other = copy.deepcopy(self.player); other["id"] = "n901"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_CATALOG_NBA_IDS"):
            self.run_case(players=[self.player, other])

    def test_history_requires_complete_fingerprint(self):
        self.player["english"] = "Test Player"
        self.player["history"] = [{"season": "2023/24", "row": 44, "team": "Бостон", "games": 7, "total": 20}]
        history = {"season": 2024, "source_row": 44, "nba_person_id": "456", "english_name": "Other Player",
                   "source_file": "synthetic.xlsx", "sheet": "fixture", "russian_name": "Тестовый игрок",
                   "fantasy_team_ru": "Бостон", "games": 7, "total_fp": 21}
        self.assertEqual(self.run_case(mapping=[history])["history_corrections"], [])
        history["total_fp"] = 20
        correction = self.run_case(mapping=[history])["history_corrections"][0]
        self.assertFalse(correction["legacy_seed_use_allowed"])
        self.assertFalse(correction["nba_id_boxscore_model_features_affected"])


if __name__ == "__main__":
    unittest.main()
