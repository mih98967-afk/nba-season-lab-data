import unittest
from datetime import datetime,timezone
from src.played_fp_shadow import issue,audit
def d(s):return datetime.fromisoformat(s.replace("Z","+00:00"))
class TestShadow(unittest.TestCase):
 def inputs(self):
  g={"id":"g1","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"NYK","status":"scheduled"}
  live={"schedule_quality":{"freshness":"fresh"},"schedule":[g],"games":[],"rows":[]}
  cat={"players":[{"id":"n01","team":"BOS"},{"id":"n02","team":"NYK"}]}
  history={"n01":20,"n02":15}
  rolling={"schema_version":1,"updated_at_utc":"2026-10-26T15:00:00Z",
    "snapshots":[{"captured_at_utc":"2026-10-26T15:00:00Z"}],
    "row_first_seen_at_utc":{"previous|n01":"2026-10-26T14:59:00Z"}}
  return live,cat,history,rolling
 def test_issue_and_dedupe(self):
  live,cat,h,r=self.inputs()
  now=d("2026-10-26T17:00:00Z")
  out,count=issue(None,live,cat,h,r,now)
  self.assertEqual(count["new_predictions"],2)
  self.assertEqual(out["issued"][0]["baseline_fp_if_play"],20)
  self.assertEqual(out["issued"][0]["candidate_fp_if_play"],20)
  self.assertFalse(out["adopt_on_site"])
  again,c=issue(out,live,cat,h,r,now)
  self.assertEqual(len(again["issued"]),2)
  self.assertEqual(c.get("new_predictions",0),0)
 def test_candidate_only_uses_pre_observed_fp(self):
  live,cat,h,r=self.inputs()
  live["rows"]=[{"id":"n01","game_id":"previous","utc":"2026-10-26T10:00:00Z","fp":40,"played":True}]
  a,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  self.assertAlmostEqual(a["issued"][0]["candidate_fp_if_play"],(200+40)/11,places=3)
  r["row_first_seen_at_utc"]["previous|n01"]="2026-10-26T18:00:00Z"
  b,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  self.assertEqual(b["issued"][0]["candidate_fp_if_play"],20)
 def test_exact_played_only(self):
  live,cat,h,r=self.inputs();now=d("2026-10-26T17:00:00Z")
  out,_=issue(None,live,cat,h,r,now)
  live["games"]=[dict(live["schedule"][0],status="final")]
  live["rows"]=[{"id":"n01","game_id":"g1","team":"BOS","minutes":20,"played":True,"fp":25}]
  scored=audit(out,live,d("2026-10-27T03:00:00Z"))
  self.assertEqual(scored["paired_played_games"],1)
  self.assertEqual(scored["baseline_mae"],5)
  self.assertEqual(scored["qa"]["unknown_unmatched_or_dnp"],1)
 def test_bad_calendar_fails(self):
  live,cat,h,r=self.inputs();live["schedule_quality"]["freshness"]="stale_requires_review"
  with self.assertRaises(ValueError):issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
 def test_no_history_abstains(self):
  live,cat,h,r=self.inputs();h.pop("n02")
  a,c=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  self.assertEqual(len(a["issued"]),1)
  self.assertEqual(c["without_verified_prior_season"],1)
if __name__=="__main__":unittest.main()
