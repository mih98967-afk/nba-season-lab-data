"""Offline regression checks: no NBA network or private accounts."""
import unittest
from src.sync import fantasy_fp, nba_box, norm, iso
from src.espn_adapter import parse_summary, parse_scoreboard

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

class TestESPNFallback(unittest.TestCase):
    def payload(self):
        names=["MIN","FG","3PT","FT","OREB","DREB","REB","AST","STL","BLK","TO","PF","PTS"]
        def player(name):
            return {"athlete":{"displayName":name,"id":"1"},"stats":["30","8-16","2-5","2-4","1","4","5","7","2","1","3","2","20"]}
        sides=[]
        for club,prefix in [("PHI","A"),("NYK","B")]:
            sides.append({"team":{"abbreviation":club},"statistics":[{"labels":names,"athletes":[player(prefix+str(i)) for i in range(7)]}]})
        return {"header":{"competitions":[{"competitors":[
                    {"homeAway":"home","team":{"abbreviation":"NYK"},"score":"100"},
                    {"homeAway":"away","team":{"abbreviation":"PHI"},"score":"110"}]}]},
                "boxscore":{"players":sides}}
    def test_full_espn_box(self):
        rows=parse_summary(self.payload(),{"home":"NYK","away":"PHI"})
        self.assertEqual(len(rows),14)
        self.assertEqual(rows[0]["fp"],22)
    def test_reject_missing_stats(self):
        p=self.payload()
        p["boxscore"]["players"][0]["statistics"][0]["labels"][2]="wrong"
        with self.assertRaises(ValueError):
            parse_summary(p,{"home":"NYK","away":"PHI"})
    def test_reject_wrong_teams(self):
        with self.assertRaises(ValueError):
            parse_summary(self.payload(),{"home":"BOS","away":"PHI"})
    def test_scoreboard_espn_id(self):
        p={"events":[{"id":"401909089","date":"2026-10-20T23:00Z",
               "season":{"type":2},"status":{"type":{"completed":True}},
               "competitions":[{"competitors":[
                   {"homeAway":"home","team":{"abbreviation":"NY"}},
                   {"homeAway":"away","team":{"abbreviation":"PHI"}}]}]}]}
        x=parse_scoreboard(p)
        self.assertEqual(x[0]["home"],"NYK")
        self.assertEqual(x[0]["espn_id"],"401909089")

if __name__=="__main__":unittest.main()
