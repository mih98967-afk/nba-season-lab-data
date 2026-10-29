"""Growing real-data regression: preserve frozen OUT evidence across inactive retries."""
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
        # Use a time AFTER the latest finished game in the current upstream cohort.
        # The archive grows independently of the older inactive research snapshot.
        latest_game=max(datetime.fromisoformat(row["game_utc"].replace("Z","+00:00"))
                        for row in cls.nba["records"])
        old_update=datetime.fromisoformat(cls.old["updated_at_utc"].replace("Z","+00:00"))
        cls.test_now=max(NOW,latest_game+timedelta(minutes=1),
                         old_update+timedelta(minutes=1))
    def test_only_new_games_requested_and_failure_preserves_outcomes(self):
        # Simulate a recent retry for the historical subset. Otherwise a
        # real archive older than 24 hours rightly becomes due for retry.
        recent_old=deepcopy(self.old)
        fresh_attempt=(self.test_now-timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_old["source_attempted_utc_by_game"]={
            x["nba_game_id"]:fresh_attempt for x in recent_old["records"]}
        req,defer,pending=plan_requests(self.nba,recent_old,self.test_now)
        old_games={x["nba_game_id"] for x in recent_old["records"]}
        all_games={x["nba_game_id"] for x in self.nba["records"]}
        self.assertEqual(set(defer),old_games)
        self.assertEqual(set(req),all_games-old_games)
        self.assertEqual(pending,[])
        result=reconcile(self.nba,self.espn,self.live,{}, {gid:"TimeoutError" for gid in req},
                         self.test_now,recent_old,attempted_game_ids=req,deferred_game_ids=defer,pending_game_ids=pending)
        self.assertEqual(result["original_queue_count"],len(self.nba["records"]))
        self.assertEqual(result["source_attempts_this_run"],len(req))
        self.assertEqual(result["source_retry_deferred_games"],len(defer))
        before={(r["game_id"],r["player_id"]):r for r in self.old["records"]}
        after={(r["game_id"],r["player_id"]):r for r in result["records"]}
        self.assertTrue(all(after[k]==v for k,v in before.items()))
        self.assertEqual(result["unresolved_unknown"],
                         sum(r["outcome"]==UNKNOWN for r in after.values()))
        self.assertTrue(all(r["model_training_negative"] is False
                            for r in after.values()))
    def test_future_finished_game_cannot_be_backdated(self):
        last=max(self.nba["records"],key=lambda x:x["game_utc"])
        premature=datetime.fromisoformat(last["game_utc"].replace("Z","+00:00"))-timedelta(seconds=1)
        games={r["nba_game_id"] for r in self.nba["records"]}
        with self.assertRaisesRegex(ValueError,"Unsafe or mismatched game/OUT evidence"):
            reconcile(self.nba,self.espn,self.live,{},
                      {gid:"TimeoutError" for gid in games},premature,
                      deepcopy(self.old),attempted_game_ids=games,
                      deferred_game_ids=[])

    def test_source_backlog_exceeds_18_without_invented_labels(self):
        data=deepcopy(self.nba)
        base=data["records"][0]
        for i in range(20):
            row=deepcopy(base)
            row["nba_game_id"]="00226%05d"%(3000+i)
            row["player_id"]="synthetic_%02d"%i
            row["game_id"]="synthetic_game_%02d"%i
            data["records"].append(row)
        req,defer,pending=plan_requests(data,{},self.test_now)
        self.assertEqual(len(req),18)
        self.assertEqual(len(defer),0)
        self.assertEqual(len(req)+len(pending),
                         len({r["nba_game_id"] for r in data["records"]}))
        self.assertGreater(len(pending),0)
        self.assertEqual(len(set(req)&set(pending)),0)
        # Pending games may not masquerade as fetched sources.
        with self.assertRaisesRegex(ValueError,"partition"):
            reconcile(self.nba,self.espn,self.live,{}, {},self.test_now,
                      deepcopy(self.old),attempted_game_ids=[],
                      deferred_game_ids=[],pending_game_ids=[])
    def test_invalid_batch_limit_fails_closed(self):
        for cap in (0,19,-1,True):
            with self.assertRaises(ValueError):
                plan_requests(self.nba,self.old,self.test_now,max_requests=cap)

    def test_future_provenance_rejected(self):
        old=deepcopy(self.old)
        old["source_attempted_utc_by_game"]={
            self.old["records"][0]["nba_game_id"]:"2030-01-01T00:00:00Z"}
        with self.assertRaises(ValueError):plan_requests(self.nba,old,NOW)
    def test_retry_after_24_hours_without_backdating(self):
        req,defer,pending=plan_requests(self.nba,self.old,self.test_now+timedelta(days=2))
        self.assertFalse(defer)
        self.assertEqual(len(req)+len(pending),len({r["nba_game_id"] for r in self.nba["records"]}))
    def test_new_game_cannot_be_deferred_without_prior(self):
        # Use a synthetic *older* saved snapshot. The real research archive
        # eventually catches up to all games; no test may require it to stay
        # perpetually at 23/27 cases.
        games={r["nba_game_id"] for r in self.nba["records"]}
        self.assertTrue(games)
        unseen=sorted(games)[-1]
        earlier=deepcopy(self.old)
        earlier["records"]=[
            r for r in earlier["records"] if r["nba_game_id"]!=unseen]
        earlier["source_attempted_utc_by_game"]={
            k:v for k,v in earlier.get("source_attempted_utc_by_game",{}).items()
            if k!=unseen}
        self.assertNotIn(unseen,{r["nba_game_id"] for r in earlier["records"]})
        with self.assertRaisesRegex(ValueError,"Invalid source attempted/deferred/pending partition"):
            reconcile(self.nba,self.espn,self.live,{}, {},self.test_now,earlier,
                      attempted_game_ids=[],deferred_game_ids=list(games))
if __name__=="__main__":unittest.main()
