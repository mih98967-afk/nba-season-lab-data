import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.p_play_issuance_readiness_research import diagnose

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read=lambda p:json.loads((DATA/p).read_text(encoding="utf8"))
        cls.live=read("live.json")
        cls.shadow=read("p_play_shadow_research.json")
        cls.catalog=[read(p.relative_to(DATA)) for p in sorted((DATA/"catalog_pit").glob("*.json"))]
        cls.espn=[read(p.relative_to(DATA)) for p in sorted((DATA/"espn_roster_pit").glob("*.json"))]
        cls.now=datetime(2026,10,27,14,0,tzinfo=timezone.utc)
    def test_real_archived_snapshots_diagnose_without_inferred_outcome(self):
        r=diagnose(self.live,self.shadow,self.catalog,self.espn,self.now)
        self.assertGreater(r["future_scheduled_games_next_72h"],0)
        self.assertEqual(r["existing_frozen_issues_total"],len(self.shadow["issued"]))
        self.assertEqual(r["existing_verified_outcomes_unchanged"],len(self.shadow["observations"]))
        self.assertFalse(r["adopt_on_site"])
        self.assertFalse(r["training_negative_from_unknown_permitted"])
        self.assertEqual(len(r["per_game"]),r["future_scheduled_games_next_72h"])
        self.assertTrue(all(row["readiness"] for row in r["per_game"]))
    def test_does_not_backdate_future_screenshot(self):
        c=deepcopy(self.catalog)
        c[0]["captured_at_utc"]="2026-11-01T00:00:00Z"
        with self.assertRaises(ValueError):
            diagnose(self.live,self.shadow,c,self.espn,self.now)
    def test_does_not_rewrite_frozen_issue(self):
        s=deepcopy(self.shadow)
        s["issued"][0]["issued_at_utc"]="2030-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            diagnose(self.live,s,self.catalog,self.espn,self.now)
    def test_deploy_flag_is_rejected(self):
        s=deepcopy(self.shadow);s["adopt_on_site"]=True
        with self.assertRaises(ValueError):
            diagnose(self.live,s,self.catalog,self.espn,self.now)

if __name__=="__main__":
    unittest.main()
