import unittest
from datetime import datetime,timezone
from copy import deepcopy
from src.played_fp_shadow import issue,audit
from src.rolling_decision_research import canonical_hash

def d(s):return datetime.fromisoformat(s.replace("Z","+00:00"))

class TestShadow(unittest.TestCase):
 def inputs(self):
  g={"id":"g1","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"NYK","status":"scheduled"}
  live={"schedule_quality":{"freshness":"fresh","validated_at_utc":"2026-10-26T12:00:00Z"},
        "updated_at_utc":"2026-10-26T16:55:00Z","schedule":[g],"games":[],"rows":[]}
  cat={"players":[{"id":"n01","team":"BOS"},{"id":"n02","team":"NYK"}]}
  history={"n01":20,"n02":15}
  rolling={"schema_version":1,"updated_at_utc":"2026-10-26T16:50:00Z",
    "snapshots":[{"captured_at_utc":"2026-10-26T16:50:00Z"}],
    "row_hashes":{},"row_first_seen_at_utc":{}}
  return live,cat,history,rolling

 def test_original_and_idempotence(self):
  live,cat,h,r=self.inputs();now=d("2026-10-26T17:00:00Z")
  a,c=issue(None,live,cat,h,r,now)
  self.assertEqual(c["new_player_game_forecasts"],2)
  self.assertEqual([x["revision_number"] for x in a["issued"]],[1,1])
  b,q=issue(a,live,cat,h,r,d("2026-10-26T17:05:00Z"))
  self.assertEqual(len(b["issued"]),2)
  self.assertEqual(q["no_feature_change"],2)
  self.assertFalse(b["adopt_on_site"])

 def test_new_confirmed_row_creates_append_only_version(self):
  live,cat,h,r=self.inputs()
  first,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  row={"game_id":"prior","id":"n01","team":"BOS","utc":"2026-10-25T00:00:00Z",
       "minutes":20,"fp":40,"played":True}
  from src.rolling_decision_research import player_games
  live["games"]=[{"id":"prior","utc":row["utc"],"home":"BOS","away":"NYK","status":"final"}]
  live["rows"]=[row]
  live["updated_at_utc"]="2026-10-26T17:15:00Z"
  r["updated_at_utc"]="2026-10-26T17:16:00Z"
  r["snapshots"][-1]["captured_at_utc"]=r["updated_at_utc"]
  canonical=list(player_games(live,d("2026-10-26T17:20:00Z"))[0].values())[0]
  r["row_hashes"]["prior|n01"]=canonical_hash(canonical)
  r["row_first_seen_at_utc"]["prior|n01"]="2026-10-26T17:16:00Z"
  second,q=issue(first,live,cat,h,r,d("2026-10-26T17:20:00Z"))
  self.assertEqual(len(second["issued"]),3)
  self.assertEqual(q["revisions"],1)
  self.assertEqual(second["issued"][0]["candidate_fp_if_play"],20)
  self.assertEqual(second["issued"][-1]["revision_number"],2)
  self.assertAlmostEqual(second["issued"][-1]["candidate_fp_if_play"],240/11,places=3)
  report=audit(second,live,d("2026-10-27T02:00:00Z"))
  self.assertEqual(report["unique_player_game_forecasts"],2)

 def test_uncaptured_correction_cannot_leak(self):
  live,cat,h,r=self.inputs()
  row={"game_id":"prior","id":"n01","team":"BOS","utc":"2026-10-25T00:00:00Z",
       "minutes":20,"fp":40,"played":True}
  live["games"]=[{"id":"prior","home":"BOS","away":"NYK","status":"final","utc":row["utc"]}]
  live["rows"]=[row]
  r["row_hashes"]["prior|n01"]="wrong_old_hash"
  r["row_first_seen_at_utc"]["prior|n01"]="2026-10-25T12:00:00Z"
  out,qa=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  self.assertEqual(len(out["issued"]),1)
  self.assertEqual(out["issued"][0]["player_id"],"n02")
  self.assertEqual(qa["abstain_uncaptured_changed_boxscore"],1)

 def test_pair_once_and_no_dnp_as_zero(self):
  live,cat,h,r=self.inputs()
  first,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  updated=deepcopy(first["issued"][0])
  updated["issued_at_utc"]="2026-10-26T18:00:00Z"
  updated["candidate_fp_if_play"]=24
  updated["revision_number"]=2
  first["issued"].append(updated)
  live["games"]=[dict(live["schedule"][0],status="final")]
  live["rows"]=[{"game_id":"g1","id":"n01","team":"BOS","minutes":21,
                 "fp":25,"played":True}]
  report=audit(first,live,d("2026-10-27T02:00:00Z"))
  self.assertEqual(report["paired_played_games"],1)
  self.assertEqual(report["player_games_with_revisions"],1)
  self.assertEqual(report["first_issue"]["candidate"]["mae"],5)
  self.assertEqual(report["latest_prelock_issue"]["candidate"]["mae"],1)
  self.assertEqual(report["qa"]["unknown_unmatched_or_dnp"],1)

 def test_stale_calendar_absolute_time_fails(self):
  live,cat,h,r=self.inputs()
  live["schedule_quality"]["validated_at_utc"]="2026-10-23T00:00:00Z"
  with self.assertRaises(ValueError):issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))

 def test_legacy_v1_no_spurious_change(self):
  live,cat,h,r=self.inputs()
  old,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  for p in old["issued"]:
   p.pop("feature_signature",None)
   p.pop("source_model_version",None)
  old["schema_version"]=1
  updated,qa=issue(old,live,cat,h,r,d("2026-10-26T17:10:00Z"))
  self.assertEqual(len(updated["issued"]),2)
  self.assertEqual(qa["legacy_unchanged"],2)
  self.assertEqual(updated["schema_version"],2)


 def test_game_cluster_interval_and_unevaluated_revisions(self):
  g1={"id":"a","utc":"2026-10-27T00:00:00Z","et_date":"2026-10-26","home":"BOS","away":"NYK","status":"final"}
  g2={"id":"b","utc":"2026-10-28T00:00:00Z","et_date":"2026-10-27","home":"ATL","away":"MIA","status":"final"}
  preds={"issued":[
   {"game_id":"a","player_id":"n1","team":"BOS","game_utc_at_issue":g1["utc"],
    "issued_at_utc":"2026-10-26T18:00:00Z","baseline_fp_if_play":20,"candidate_fp_if_play":22},
   {"game_id":"b","player_id":"n2","team":"ATL","game_utc_at_issue":g2["utc"],
    "issued_at_utc":"2026-10-27T18:00:00Z","baseline_fp_if_play":20,"candidate_fp_if_play":22}
  ]}
  live={"games":[g1,g2],"rows":[
   {"game_id":"a","id":"n1","team":"BOS","played":True,"minutes":22,"fp":24},
   {"game_id":"b","id":"n2","team":"ATL","played":True,"minutes":24,"fp":16},
  ]}
  report=audit(preds,live,d("2026-10-28T02:00:00Z"))
  s=report["paired_reliability"]
  self.assertEqual(report["paired_played_games"],2)
  self.assertEqual(s["distinct_completed_games"],2)
  self.assertEqual(s["distinct_ET_game_dates"],2)
  self.assertEqual(s["distinct_players"],2)
  self.assertEqual(s["candidate_vs_baseline_paired_mae_gain_fp"],0)
  self.assertEqual(s["game_cluster_95pct_gain_interval_fp"]["lower"],-2)
  self.assertEqual(s["game_cluster_95pct_gain_interval_fp"]["upper"],2)
  self.assertEqual(s["played_player_games_with_evaluable_prelock_revisions"],0)
  self.assertFalse(s["first_to_last_revision_quality_evaluable"])
  self.assertFalse(s["adoption_ready"])
  self.assertFalse(report["adopt_on_site"])

 def test_evidence_cannot_retroactively_appear_in_earlier_issue(self):
  g={"id":"a","utc":"2026-10-27T00:00:00Z","home":"BOS","away":"NYK","status":"final"}
  p={"game_id":"a","player_id":"n1","team":"BOS","game_utc_at_issue":g["utc"],
     "issued_at_utc":"2026-10-26T18:00:00Z","baseline_fp_if_play":20,
     "candidate_fp_if_play":22,
     "official_report_asof":{"first_seen_at_utc":"2026-10-26T19:00:00Z",
                              "report_at_utc":"2026-10-26T17:00:00Z"}}
  live={"games":[g],"rows":[{"game_id":"a","id":"n1","team":"BOS","played":True,
                              "minutes":20,"fp":24}]}
  rep=audit({"issued":[p]},live,d("2026-10-27T02:00:00Z"))
  self.assertEqual(rep["paired_played_games"],0)
  self.assertEqual(rep["qa"]["post_issue_source_leak_or_invalid_provenance"],1)

 def test_legacy_one_match_is_not_independent_cluster_evidence(self):
  live,cat,h,r=self.inputs()
  first,_=issue(None,live,cat,h,r,d("2026-10-26T17:00:00Z"))
  live["games"]=[dict(live["schedule"][0],status="final")]
  live["rows"]=[{"game_id":"g1","id":"n01","team":"BOS","minutes":20,
                 "fp":25,"played":True}]
  report=audit(first,live,d("2026-10-27T02:00:00Z"))
  s=report["paired_reliability"]
  self.assertEqual(s["distinct_completed_games"],1)
  self.assertEqual(s["distinct_ET_game_dates"],1)
  self.assertIsNone(s["game_cluster_95pct_gain_interval_fp"])
  self.assertFalse(s["adoption_ready"])

if __name__=="__main__":unittest.main()
