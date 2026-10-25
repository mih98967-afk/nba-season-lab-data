"""Offline test with real committed, verified NBA calendar. No paid APIs."""
import copy
import datetime as dt
import json
import unittest
from src.live_calendar_fallback import verified_fallback
from src.sync import DATA

class TestCalendarFallback(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=json.loads((DATA/'schedule.json').read_text())
  cls.now=dt.datetime(2026,10,25,13,tzinfo=dt.timezone.utc)
 def test_real_verified_calendar(self):
  games,q=verified_fallback(self.original,self.now)
  self.assertEqual(len(games),1200)
  self.assertEqual(q['unassigned_games'],30)
  self.assertEqual(q['teams'],30)
  self.assertEqual(q['freshness'],'stale_requires_review')
  self.assertIsNot(games[0],self.original['games'][0])
 def test_duplicate_fails(self):
  x=copy.deepcopy(self.original)
  x['games'][1]['id']=x['games'][0]['id']
  with self.assertRaises(ValueError):verified_fallback(x,self.now)
 def test_wrong_moscow_boundary_fails(self):
  x=copy.deepcopy(self.original);x['games'][0]['msk_week']='2026-10-26'
  with self.assertRaises(ValueError):verified_fallback(x,self.now)
 def test_wrong_team_fails(self):
  x=copy.deepcopy(self.original);x['games'][0]['home']='XYZ'
  with self.assertRaises(ValueError):verified_fallback(x,self.now)
 def test_incomplete_fails(self):
  x=copy.deepcopy(self.original);x['games']=[]
  with self.assertRaises(ValueError):verified_fallback(x,self.now)
if __name__=='__main__':unittest.main()
