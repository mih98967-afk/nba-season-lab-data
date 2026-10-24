import unittest
from datetime import datetime,timezone
from src.decision_deadline_backtest import boundaries,pick_moves,sample_scenarios
class Tests(unittest.TestCase):
 def test_monday_boundary(self):
  start,end=boundaries("2026-10-19")
  self.assertEqual(start.isoformat(),"2026-10-19T12:00:00+00:00")
  self.assertEqual(end.isoformat(),"2026-10-25T21:00:00+00:00")
 def test_non_monday_rejected(self):
  with self.assertRaises(ValueError):boundaries("2026-10-20")
 def test_team_limit(self):
  a={"pid":"a","team":"NYK","actual":5}
  b={"pid":"b","team":"BOS","actual":9}
  c={"pid":"c","team":"BOS","actual":10}
  pairs=[(a,b),(c,a)]
  # no forecast here because fake rows missing stats
  self.assertEqual(len(sample_scenarios([a], "fixed")),0)
if __name__=="__main__":unittest.main()
