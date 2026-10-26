import unittest
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from src.catalog_pit_research import capture,evaluate,STATUS,UNKNOWN
from src.rolling_decision_research import canonical_hash
UTC=timezone.utc
def dt(s): return datetime.fromisoformat(s.replace("Z","+00:00"))
def fixture():
 teams="ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split()
 people=[{"id":f"n{i:03d}","team":teams[i%30],"pos":"PG"} for i in range(450)]
 now=dt("2026-10-26T16:00:00Z")
 game={"id":"g1","utc":"2026-10-27T01:00:00Z","home":"ATL","away":"BOS","status":"scheduled"}
 live={"schema_version":4,"updated_at_utc":"2026-10-26T15:55:00Z",
       "schedule_quality":{"freshness":"fresh","validated_at_utc":"2026-10-26T15:55:00Z"},
       "schedule":[game],"games":[]}
 c={"players":people}
 snap=capture(c,live,now)
 finished=deepcopy(live)
 finished["games"]=[dict(game,status="final")]
 record={"game_id":"g1","player_id":"n000","team":"ATL","position":"PG",
         "game_utc":game["utc"],"participation_label":1,
         "evidence":"positive_minutes_verified_sportsru_fp",
         "source_first_observed_at_utc":"2026-10-27T03:00:00Z"}
 cohort={"schema_version":1,"status":STATUS,"adopt_on_site":False,
         "records":[record],"summary":{"verified_full_boxscores_checked":1,
                                        "listed_player_game_labels":1}}
 explicit={"schema_version":1,"adopt_on_site":False,"checked_final_game_ids":["g1"]}
 return c,live,snap,finished,cohort,explicit
class TestPIT(unittest.TestCase):
 def test_prospective_only_known_and_unknown(self):
  c,live,snap,final,co,ex=fixture()
  result=evaluate(final,co,ex,[snap],dt("2026-10-27T04:00:00Z"))
  self.assertEqual(result["summary"]["games_with_prelock_proxy_and_matching_fixture"],1)
  self.assertEqual(result["summary"]["played_verified"],1)
  self.assertGreater(result["summary"][UNKNOWN],0)
  self.assertFalse(result["calibrated_p_play_available"])
  self.assertFalse(result["adopt_on_site"])
 def test_no_prelock_snapshot_for_old_games(self):
  c,live,snap,final,co,ex=fixture()
  late=deepcopy(snap)
  late["captured_at_utc"]="2026-10-27T02:00:00Z"
  late["snapshot_date_msk"]="2026-10-27"
  late["future_fixtures_observed"]=[]
  late["future_fixtures_count"]=0
  result=evaluate(final,co,ex,[late],dt("2026-10-27T04:00:00Z"))
  self.assertEqual(result["summary"]["no_prelock_snapshot"],1)
  self.assertEqual(len(result["records"]),0)
 def test_fixture_reschedule_quarantine(self):
  c,live,snap,final,co,ex=fixture()
  final["games"][0]["utc"]="2026-10-27T01:30:00Z"
  co["records"][0]["game_utc"]="2026-10-27T01:30:00Z"
  result=evaluate(final,co,ex,[snap],dt("2026-10-27T04:00:00Z"))
  self.assertEqual(result["summary"]["fixture_changed_since_capture"],1)
 def test_tampering_rejected(self):
  c,live,snap,final,co,ex=fixture()
  snap["catalog_players_proxy"][0]["catalog_team"]="BOS"
  with self.assertRaises(ValueError):evaluate(final,co,ex,[snap],dt("2026-10-27T04:00:00Z"))
 def test_stale_or_future_feed_rejected(self):
  c,live,*_=fixture()
  live["updated_at_utc"]="2026-10-25T01:00:00Z"
  with self.assertRaises(ValueError):capture(c,live,dt("2026-10-26T16:00:00Z"))
 def test_not_pre_game_prediction(self):
  c,live,snap,final,co,ex=fixture()
  x=evaluate(final,co,ex,[snap],dt("2026-10-27T04:00:00Z"))
  self.assertTrue(x["outcome_evidence_available_after_game_only"])
  self.assertFalse(x["keep_transfer_advantage_claim_allowed"])
if __name__=="__main__":unittest.main()
