"""Real-data regression: preserve 23 old cases on 27-case NBA inactive catch-up."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from src.sync import DATA
from src.official_nba_inactive_summary_research import (
    plan_requests, reconcile, UNKNOWN,
)
NOW = datetime(2026, 10, 28, 10, tzinfo=timezone.utc)
def get(filename):
    return json.loads((DATA / filename).read_text(encoding="utf8"))

class Catchup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nba=get("official_nba_gameday_status_research.json")
        cls.espn=get("official_out_boxscore_evidence_research.json")
        cls.live=get("live.json")
        cls.old=get("official_nba_inactive_summary_research.json")
    def test_only_new_games_requested_and_failure_preserves_outcomes(self):
        req,defer=plan_requests(self.nba,self.old,NOW)
        old_games={x["nba_game_id"] for x in self.old["records"]}
        all_games={x["nba_game_id"] for x in self.nba["records"]}
        self.assertEqual(set(defer),old_games)
        self.assertEqual(set(req),all_games-old_games)
        result=reconcile(self.nba,self.espn,self.live,{}, {gid:"TimeoutError" for gid in req},
                         NOW,deepcopy(self.old),attempted_game_ids=req,deferred_game_ids=defer)
        self.assertEqual(result["original_queue_count"],len(self.nba["records"]))
        self.assertEqual(result["source_attempts_this_run"],len(req))
        self.assertEqual(result["source_retry_deferred_games"],len(defer))
        before={(r["game_id"],r["player_id"]):r for r in self.old["records"]}
        after={(r["game_id"],r["player_id"]):r for r in result["records"]}
        self.assertTrue(all(after[k]==v for k,v in before.items()))
        self.assertEqual(result["unresolved_unknown"],len(after))
        self.assertTrue(all(r["outcome"]==UNKNOWN and
                            r["model_training_negative"] is False for r in after.values()))
    def test_future_provenance_rejected(self):
        old=deepcopy(self.old)
        old["source_attempted_utc_by_game"]={
            self.old["records"][0]["nba_game_id"]:"2030-01-01T00:00:00Z"}
        with self.assertRaises(ValueError):plan_requests(self.nba,old,NOW)
    def test_retry_after_24_hours_without_backdating(self):
        req,defer=plan_requests(self.nba,self.old,NOW+timedelta(days=2))
        self.assertFalse(defer)
        self.assertEqual(len(req),len({r["nba_game_id"] for r in self.nba["records"]}))
    def test_new_game_cannot_be_deferred_without_prior(self):
        games={r["nba_game_id"] for r in self.nba["records"]}
        with self.assertRaises(ValueError):
            reconcile(self.nba,self.espn,self.live,{}, {},NOW,self.old,
                      attempted_game_ids=[],deferred_game_ids=list(games))
if __name__=="__main__":unittest.main()
