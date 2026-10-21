"""Offline regression checks: no NBA network or private accounts."""
import unittest
from src.sync import fantasy_fp, nba_box, norm, iso

class TestScoring(unittest.TestCase):
    def test_basic(self):
        st={"min":25,"pts":20,"fgm":8,"fga":16,"ftm":2,"fta":4,
            "reb":5,"ast":7,"stl":2,"blk":1,"tov":3,"pf":2}
        # Base 20+5+7+2+1+8+2-16-4-2-6 =17, minutes +2, away win +3
        self.assertEqual(fantasy_fp(st,False,True),22)
        self.assertEqual(fantasy_fp(st,True,False),16)
    def test_short_play(self):
        st={"min":5,"pts":0,"fgm":0,"fga":0,"ftm":0,"fta":0,
            "reb":0,"ast":0,"stl":0,"blk":0,"tov":0,"pf":0}
        self.assertEqual(fantasy_fp(st,True,True),3)
        self.assertEqual(fantasy_fp({**st,"min":0},True,True),0)
    def test_bad_stats(self):
        st={"min":15,"pts":8,"fgm":5,"fga":4,"ftm":0,"fta":0,
            "reb":0,"ast":0,"stl":0,"blk":0,"tov":0,"pf":0}
        with self.assertRaises(ValueError):fantasy_fp(st,True,True)
    def test_normalization(self):
        self.assertEqual(norm("Luka Dončić"),"luka doncic")
    def test_utc(self):
        self.assertTrue(iso("2026-10-20T19:00:00Z").endswith("Z"))

if __name__=="__main__":unittest.main()
