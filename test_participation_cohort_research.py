import unittest
from datetime import datetime,timezone
from copy import deepcopy
from src.participation_cohort_research import build
NOW=datetime(2026,10,26,tzinfo=timezone.utc)
def fixture():
 g={"id":"espn_42","espn_id":"42","status":"final","home":"BOS","away":"NYK","utc":"2026-10-25T20:00:00Z"}
 cat={"players":[{"id":"n001","english":"Test Player","team":"BOS","pos":"PG"},{"id":"n002","english":"Other Player","team":"NYK","pos":"C"}]+[{"id":"n%03d"%i,"english":"P%d"%i,"team":"BOS","pos":"SF"} for i in range(3,404)]}
 rows=[{"id":"n001","name":"Test Player","game_id":"espn_42","team":"BOS","played":True,"minutes":20,"fp":17,"source_url":"public"}]
 rows += [{"id":"n%03d"%i,"name":"P%d"%i,"game_id":"espn_42","team":"BOS" if i<8 else "NYK","played":True,"minutes":15,"fp":10} for i in range(3,13)]
 live={"games":[g],"rows":rows}
 dnp={"schema_version":1,"adopt_on_site":False,"checked_final_game_ids":["espn_42"],"events":[
 {"game_id":"espn_42","player_id":"n002","team":"NYK","home":"BOS","away":"NYK","game_utc":g["utc"],"observed_at_utc":"2026-10-26T02:00:00Z","evidence":"explicit_espn_didNotPlay_true","source_url":"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=42"}]}
 rolling={"schema_version":1,"adopt_on_site":False,"row_first_seen_at_utc":{"espn_42|n001":"2026-10-26T01:00:00Z"}}
 off={"status":"official_report_observed_pit_research_only","events":[]}
 telegram={"status":"observed_unconfirmed_research_archive","events":[]}
 return live,dnp,cat,{"players":{}},rolling,off,telegram
class TestCohort(unittest.TestCase):
 def test_unique_labels_and_unknown_not_inferred(self):
  x=build(*fixture(),NOW)
  self.assertEqual(x["summary"]["active_played"],11)
  self.assertEqual(x["summary"]["explicit_dnp"],1)
  self.assertEqual(x["summary"]["listed_player_game_labels"],12)
  self.assertFalse(x["representative_of_full_fantasy_population"])
  self.assertEqual(x["by_position"]["C"]["explicit_dnp"],1)
  self.assertEqual(x["summary"]["fantasy_population_cards"],403)
 def test_positive_vs_negative_conflict_fail(self):
  v=list(fixture());v[1]["events"][0]["player_id"]="n001";v[1]["events"][0]["team"]="BOS"
  with self.assertRaises(ValueError):build(*v,NOW)
 def test_wrong_dnp_team_fail(self):
  v=list(fixture());v[1]["events"][0]["team"]="LAL"
  with self.assertRaises(ValueError):build(*v,NOW)
 def test_future_observed_dnp_fail(self):
  v=list(fixture());v[1]["events"][0]["observed_at_utc"]="2026-10-27T02:00:00Z"
  with self.assertRaises(ValueError):build(*v,NOW)
if __name__=="__main__":unittest.main()
