import unittest
from datetime import datetime,timezone
from src.participation_coverage_research import coverage
NOW=datetime(2026,10,26,tzinfo=timezone.utc)
def inputs():
 g={"id":"g","status":"final","home":"BOS","away":"NYK","utc":"2026-10-25T20:00:00Z"}
 people=[{"id":f"n{i:03d}","team":"BOS" if i<210 else "NYK","pos":"PG"} for i in range(420)]
 other="ATL BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split()
 people.extend({"id":f"n{i:03d}","team":team,"pos":"SG"} for i,team in enumerate(other,start=420))
 e={"game_id":"g","player_id":"n001","team":"BOS","position":"PG","game_utc":g["utc"],"participation_label":1,"evidence":"positive_minutes_verified_sportsru_fp","source_first_observed_at_utc":"2026-10-25T23:00:00Z"}
 c={"schema_version":1,"status":"research_only_not_deployed","adopt_on_site":False,"records":[e],"summary":{"verified_full_boxscores_checked":1,"listed_player_game_labels":1}}
 d={"schema_version":1,"adopt_on_site":False,"checked_final_game_ids":["g"]}
 o={"status":"official_report_observed_pit_research_only","events":[]}
 tg={"status":"observed_unconfirmed_research_archive","events":[]}
 return [{"games":[g]},c,d,{"players":people},o,tg]
class TestUnknown(unittest.TestCase):
 def test_unknown_not_dnp(self):
  x=coverage(*inputs(),NOW)
  self.assertEqual(x["summary"]["catalog_proxy_candidate_player_games"],420)
  self.assertEqual(x["summary"]["played_verified"],1)
  self.assertEqual(x["summary"]["unknown_roster_membership_or_unlisted"],419)
  self.assertFalse(x["full_population_brier_enabled"])
 def test_wrong_club_confirmed_is_excluded_but_preserved(self):
  a=inputs();a[1]["records"][0]["team"]="NYK"
  x=coverage(*a,NOW)
  self.assertEqual(x["summary"]["verified_labels_outside_catalog_proxy"],1)
  self.assertEqual(x["summary"].get("played_verified",0),0)
 def test_duplicate_source_rejected(self):
  a=inputs();a[1]["records"].append(a[1]["records"][0])
  with self.assertRaises(ValueError):coverage(*a,NOW)
 def test_not_final_rejected(self):
  a=inputs();a[0]["games"][0]["status"]="scheduled"
  with self.assertRaises(ValueError):coverage(*a,NOW)
if __name__=="__main__":unittest.main()
