import unittest
from copy import deepcopy
from datetime import datetime,timezone
from src.prelock_roster_opportunities import build,validate_espn_snapshots
from src.catalog_pit_research import capture,STATUS,UNKNOWN
from src.rolling_decision_research import canonical_hash

def d(x):return datetime.fromisoformat(x.replace("Z","+00:00"))
def inputs():
 teams="ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split()
 catalog={"players":[{"id":f"n{i:03d}","team":teams[i%30],"pos":"PG"} for i in range(450)]}
 now=d("2026-10-26T18:00:00Z")
 g={"id":"g","utc":"2026-10-27T01:00:00Z","home":"ATL","away":"BOS","status":"scheduled"}
 live={"schema_version":4,"updated_at_utc":"2026-10-26T17:55:00Z","schedule_quality":{"freshness":"fresh","validated_at_utc":"2026-10-26T17:55:00Z"},"schedule":[g],"games":[]}
 c=capture(catalog,live,now)
 es=[]
 from src.espn_roster_pit import ESPN_TEAMS
 for t in sorted(teams):
  es.append({"club":t,"url":f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{ESPN_TEAMS[t]}/roster","source_status":"parsed_not_game_day_eligibility","source_first_seen_at_utc":"2026-10-26T18:01:00Z","athletes":[{"espn_person_id":str(100000+teams.index(t)*100+i),"display_name":f"P{i}","sportsru_player_id":None,"identity_method":None,"catalog_team_at_capture":None} for i in range(12)]})
 es[0]["athletes"][0].update(sportsru_player_id="n000",identity_method="previously_named_played_ESPN_person_ID",catalog_team_at_capture="ATL")
 e={"schema_version":1,"status":STATUS,"adopt_on_site":False,"publication_time_unknown":True,"game_day_eligibility_verified":False,"source":"ESPN public team roster current snapshot","captured_at_utc":"2026-10-26T18:01:00Z","teams":es,"all_teams_available":True}
 e["snapshot_hash_sha256"]=canonical_hash({"teams":es,"captured":e["captured_at_utc"]})
 co={"schema_version":1,"status":STATUS,"adopt_on_site":False,"records":[],"summary":{"verified_full_boxscores_checked":0,"listed_player_game_labels":0}}
 ex={"schema_version":1,"adopt_on_site":False,"checked_final_game_ids":[]}
 return live,co,ex,[c],[e]
class Tests(unittest.TestCase):
 def test_future_is_unknown_never_dnp(self):
  a=inputs();v=build(*a,d("2026-10-26T18:03:00Z"))
  self.assertEqual(v["summary"]["games_with_both_prelock_sources"],1)
  self.assertGreater(v["summary"][UNKNOWN],0)
  self.assertEqual(v["summary"].get("explicit_dnp_verified_after_game",0),0)
  self.assertFalse(v["p_play_training_permitted"])
  self.assertFalse(v["adopt_on_site"])
 def test_espn_after_lock_is_excluded(self):
  a=inputs();snap=a[4][0];snap["captured_at_utc"]="2026-10-27T00:31:00Z"
  for t in snap["teams"]:t["source_first_seen_at_utc"]=snap["captured_at_utc"]
  snap["snapshot_hash_sha256"]=canonical_hash({"teams":snap["teams"],"captured":snap["captured_at_utc"]})
  v=build(*a,d("2026-10-27T00:40:00Z"))
  self.assertEqual(v["summary"]["without_recent_prelock_espn_snapshot"],1)
 def test_two_espn_captures_and_spacing(self):
  a=inputs()
  first=a[4][0]
  second=deepcopy(first)
  second["captured_at_utc"]="2026-10-26T22:02:00Z"
  for t in second["teams"]:t["source_first_seen_at_utc"]=second["captured_at_utc"]
  second["snapshot_hash_sha256"]=canonical_hash({"teams":second["teams"],"captured":second["captured_at_utc"]})
  self.assertEqual(len(validate_espn_snapshots([first,second],d("2026-10-26T22:10:00Z"))),2)
  second["captured_at_utc"]="2026-10-26T21:00:00Z"
  for t in second["teams"]:t["source_first_seen_at_utc"]=second["captured_at_utc"]
  second["snapshot_hash_sha256"]=canonical_hash({"teams":second["teams"],"captured":second["captured_at_utc"]})
  with self.assertRaises(ValueError):validate_espn_snapshots([first,second],d("2026-10-26T22:10:00Z"))
 def test_tampered_hash_is_rejected(self):
  a=inputs();a[4][0]["teams"][0]["athletes"][0]["display_name"]="Tampered"
  with self.assertRaises(ValueError):build(*a,d("2026-10-26T18:03:00Z"))
 def test_outcomes_only_after_final(self):
  a=inputs();live,co,ex=a[:3];live["games"]=[dict(live["schedule"][0],status="final")]
  co["records"]=[{"game_id":"g","player_id":"n000","team":"ATL","position":"PG","game_utc":"2026-10-27T01:00:00Z","participation_label":1,"evidence":"positive_minutes_verified_sportsru_fp","source_first_observed_at_utc":"2026-10-27T03:00:00Z"}]
  co["summary"]={"verified_full_boxscores_checked":1,"listed_player_game_labels":1}
  ex["checked_final_game_ids"]=["g"]
  out=build(*a,d("2026-10-27T04:00:00Z"))
  self.assertEqual(out["summary"]["played_verified_after_game"],1)
  self.assertEqual(out["summary"].get("explicit_dnp_verified_after_game",0),0)
 def test_reject_postgame_timestamp_from_future(self):
  a=inputs();live,co,ex=a[:3]
  live["games"]=[dict(live["schedule"][0],status="final")]
  co["records"]=[{"game_id":"g","player_id":"n000","team":"ATL","position":"PG","game_utc":"2026-10-27T01:00:00Z","participation_label":1,"evidence":"positive_minutes_verified_sportsru_fp","source_first_observed_at_utc":"2026-10-27T08:00:00Z"}]
  co["summary"]={"verified_full_boxscores_checked":1,"listed_player_game_labels":1}
  ex["checked_final_game_ids"]=["g"]
  with self.assertRaises(ValueError):build(*a,d("2026-10-27T04:00:00Z"))
 def test_reject_postgame_timestamp_before_tip(self):
  a=inputs();live,co,ex=a[:3]
  live["games"]=[dict(live["schedule"][0],status="final")]
  co["records"]=[{"game_id":"g","player_id":"n000","team":"ATL","position":"PG","game_utc":"2026-10-27T01:00:00Z","participation_label":1,"evidence":"positive_minutes_verified_sportsru_fp","source_first_observed_at_utc":"2026-10-26T23:00:00Z"}]
  co["summary"]={"verified_full_boxscores_checked":1,"listed_player_game_labels":1}
  ex["checked_final_game_ids"]=["g"]
  with self.assertRaises(ValueError):build(*a,d("2026-10-27T04:00:00Z"))
 def test_empty_pregame_cohort_remains_unknown(self):
  a=inputs()
  result=build(*a,d("2026-10-26T18:03:00Z"))
  self.assertTrue(all(z["context_known_asof_utc"]=="2026-10-26T18:03:00Z" for z in result["records"]))
  self.assertTrue(all(z["postgame_outcome"]==UNKNOWN for z in result["records"]))

if __name__=="__main__":unittest.main()
