import unittest
from datetime import datetime,timezone
from src.injury_status_backtest import name_key,record_2025,metrics,group_probabilities
class T(unittest.TestCase):
 def test_names(self):self.assertEqual(name_key("Jokić, Nikola"),"nikola jokic")
 def test_snapshot(self):
  row={"REPORT_TIMESTAMP":"2026-01-01 13:00:00-05:00","GAME_DATE":"2026-01-01","MATCHUP":"HOU@BKN","TEAM_ABBREVIATION":"HOU","PLAYER_NAME":"Adams, Steven","STATUS":"Questionable","REASON":"Injury/Illness - Ankle"}
  a=record_2025(row);self.assertEqual(a["name"],"steven adams");self.assertEqual(a["status"],"questionable")
 def test_no_naive_timestamp(self):
  row={"REPORT_TIMESTAMP":"2026-01-01 13:00:00","GAME_DATE":"2026-01-01","MATCHUP":"HOU@BKN","TEAM_ABBREVIATION":"HOU","PLAYER_NAME":"Adams, Steven","STATUS":"Questionable"}
  self.assertIsNone(record_2025(row))
 def test_metrics(self):
  self.assertEqual(metrics([{"actual":1},{"actual":0}],[.8,.2])["brier"],.04)
if __name__=="__main__":unittest.main()
