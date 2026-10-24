import unittest
from src.historical_calendar import games_espn,reconcile,week_msk,iso_parse
from datetime import datetime,timezone

class HistoricalCalendarTests(unittest.TestCase):
 def test_msk_boundary(self):
  self.assertEqual(week_msk(iso_parse("2025-10-26T20:59:00Z")),"2025-10-20")
  self.assertEqual(week_msk(iso_parse("2025-10-26T21:00:00Z")),"2025-10-27")
  self.assertEqual(week_msk(iso_parse("2026-03-08T21:30:00Z")),"2026-03-09")
 def test_reject_naive(self):
  with self.assertRaises(ValueError):iso_parse("2025-10-25T20:00:00")
 def test_espn_mapping(self):
  v={"events":[{"id":"401999999","season":{"type":2},"date":"2025-10-26T21:30:00Z",
      "status":{"type":{"completed":True}},
      "competitions":[{"competitors":[
          {"homeAway":"home","team":{"abbreviation":"NY"}},
          {"homeAway":"away","team":{"abbreviation":"PHI"}}]}]}]}
  out=games_espn(v)
  self.assertEqual(len(out),1)
  self.assertEqual(out[0]["home"],"NYK")
  self.assertEqual(out[0]["msk_week"],"2025-10-27")
 def test_no_fabricated_tipoff(self):
  with self.assertRaises(ValueError):games_espn({"data":[]})

if __name__=="__main__":unittest.main()
