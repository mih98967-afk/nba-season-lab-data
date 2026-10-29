import unittest
from pathlib import Path
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from src.current_season_minutes_shadow_research import build,MODEL_HASH,metrics
from src.rolling_decision_research import canonical_hash
def when(x):return datetime.fromisoformat(x.replace("Z","+00:00"))
class ShadowTests(unittest.TestCase):
 def fixture(self):
  base="2026-10-29T15:00:00Z";tip="2026-10-30T00:00:00Z"
  issue={"game_id":"g4","player_id":"p","team":"BOS","game_utc":tip,
   "individual_lock_utc":"2026-10-29T23:30:00Z","issued_at_utc":base,
   "min_if_play":30,"fp_per_minute_if_play":.5,"decomposed_fp_if_play":15}
  frozen={"schema_version":1,"status":"research_only_not_deployed","adopt_on_site":False,
    "unconditional_FP_enabled":False,"issued":[issue]}
  records=[];first={}
  for i in range(3):
   gid="g"+str(i)
   utc="2026-10-%02dT00:00:00Z"%(25+i)
   records.append({"id":"p","game_id":gid,"team":"BOS","played":True,
                   "minutes":20+i,"utc":utc})
   first[gid+"|p"]="2026-10-%02dT06:00:00Z"%(25+i)
  live={"schema_version":4,"games":[{"id":"g"+str(i),"status":"final","utc":"2026-10-%02dT00:00:00Z"%(25+i),"home":"BOS","away":"NYK"} for i in range(3)],"rows":records}
  rolling={"schema_version":1,"adopt_on_site":False,"row_first_seen_at_utc":first}
  eval={"status":"research_only_not_deployed","adopt_on_site":False,
        "frozen_minutes_issue_sha256":canonical_hash([issue]),
        "quality_gate":{"adopt_on_site":False},
        "summary":{"played":0},"scored_played":[],"explicit_DNP_not_in_conditional_metrics":[],"UNKNOWN_unscored":[]}
  return [{},frozen,rolling,live,eval]
 def test_valid_genuine_prelock_issue(self):
  a=self.fixture()
  result=build(*a,when("2026-10-29T15:05:00Z"))
  self.assertEqual(result["summary"]["issued_total"],1)
  row=result["issued"][0]
  self.assertEqual(row["current_same_team_played_n"],3)
  self.assertLess(row["challenger_minutes"],30)
  self.assertFalse(result["quality_gate"]["adopt_on_site"])
  next_run=build(result,*a[1:],when("2026-10-29T15:10:00Z"))
  self.assertEqual(next_run["issued"],result["issued"])
 def test_no_retroactive_issuance(self):
  a=self.fixture()
  out=build(*a,when("2026-10-29T16:00:00Z"))
  self.assertEqual(out["summary"]["issued_total"],0)
 def test_future_known_minutes_never_used(self):
  a=self.fixture()
  a[2]["row_first_seen_at_utc"]["g2|p"]="2026-10-29T16:00:00Z"
  self.assertEqual(build(*a,when("2026-10-29T15:05:00Z"))["summary"]["issued_total"],0)
 def test_post_baseline_source_cannot_be_leaked_into_challenger(self):
  a=self.fixture()
  a[2]["row_first_seen_at_utc"]["g2|p"]="2026-10-29T15:02:00Z"
  result=build(*a,when("2026-10-29T15:05:00Z"))
  self.assertEqual(result["summary"]["issued_total"],0)
  self.assertEqual(result["issue_QA"]["insufficient_current_same_team_verified_played_form"],1)
 def test_clock_qa_separates_stale_from_lock(self):
  a=self.fixture()
  stale=build(*a,when("2026-10-29T16:00:00Z"))
  self.assertEqual(stale["issue_QA"]["original_issue_stale_over_20_minutes_no_backfill"],1)
  self.assertEqual(stale["source_clock_QA"]["latest_original_frozen_issue_at_utc"],
                   "2026-10-29T15:00:00Z")
  locked=build(*a,when("2026-10-30T00:00:00Z"))
  self.assertEqual(locked["issue_QA"]["original_issue_no_longer_prelock"],1)
 def test_no_dnp_zero_and_immutable_source(self):
  a=self.fixture()
  v=build(*a,when("2026-10-29T15:05:00Z"))
  a[3]["rows"][0]["played"]=False
  self.assertEqual(build(*a,when("2026-10-29T15:06:00Z"))["summary"]["issued_total"],0)
  a=self.fixture();a[1]["issued"][0]["min_if_play"]=40
  with self.assertRaises(ValueError):
   build(v,*a[1:],when("2026-10-29T15:06:00Z"))
 def test_scored_result_only_postgame(self):
  a=self.fixture();v=build(*a,when("2026-10-29T15:05:00Z"))
  obs={"game_id":"g4","player_id":"p","game_utc":"2026-10-30T00:00:00Z",
       "team":"BOS","et_date":"2026-10-29","position":"PG",
       "actual_minutes":24,"actual_fp_reconstructed":12,
       "postgame_first_seen_at_utc":"2026-10-30T05:00:00Z"}
  a[4]["scored_played"]=[obs];a[4]["summary"]["played"]=1
  with self.assertRaises(ValueError):build(v,*a[1:],when("2026-10-29T15:06:00Z"))
  after=build(v,*a[1:],when("2026-10-30T06:00:00Z"))
  self.assertEqual(after["summary"]["played_verified"],1)
  self.assertEqual(after["played_only_paired_metrics"]["played_scored"],1)
class PipelineOwnership(unittest.TestCase):
 def test_current_minutes_challenger_has_one_publisher(self):
  root=Path(__file__).resolve().parent
  main=(root/".github/workflows/nba-sync.yml").read_text()
  self.assertEqual(main.count("python -m src.current_season_minutes_shadow_research"),2)
  parts=main.split("python -m src.participation_cohort_research")
  self.assertEqual(len(parts),3)
  for tail in parts[1:]:
   commands=["python -m src.conditional_minutes_fp_research",
             "python -m src.conditional_minutes_fp_evaluation_research",
             "python -m src.current_season_minutes_shadow_research"]
   offsets=[tail.index(c) for c in commands]
   self.assertEqual(offsets,sorted(offsets))
  self.assertIn("data/current_season_minutes_shadow_research.json",main)
  isolated=(root/".github/workflows/current-season-minutes-shadow.yml").read_text()
  self.assertIn("contents: read",isolated)
  for forbidden in ("contents: write","git add data/","git push origin",
                    "  schedule:","  workflow_run:","  workflow_dispatch:"):
   self.assertNotIn(forbidden,isolated)
if __name__=="__main__":unittest.main()
