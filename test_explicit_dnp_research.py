import unittest
from datetime import datetime,timezone
from src.explicit_dnp_research import explicit_rows,gather
NOW=datetime(2026,10,26,tzinfo=timezone.utc)
GAME={"id":"espn_42","espn_id":"42","utc":"2026-10-25T20:00:00Z",
      "home":"BOS","away":"NYK","status":"final"}
IDENTITY={"players":{"n001":{"english":"Test Player"}}}
def payload(flag=True):
 return {"header":{"competitions":[{"competitors":[
 {"homeAway":"home","team":{"abbreviation":"BOS"}},
 {"homeAway":"away","team":{"abbreviation":"NYK"}}]}]},
 "boxscore":{"players":[
 {"team":{"abbreviation":"BOS"},"statistics":[{"athletes":[
 {"athlete":{"displayName":"Test Player"},"didNotPlay":flag}]}]},
 {"team":{"abbreviation":"NYK"},"statistics":[{"athletes":[]}]}]}}
class Tests(unittest.TestCase):
 def test_explicit_only(self):
  a,qa=explicit_rows(payload(),GAME,IDENTITY,NOW)
  self.assertEqual(len(a),1)
  self.assertEqual(a[0]["player_id"],"n001")
  self.assertEqual(explicit_rows(payload(False),GAME,IDENTITY,NOW)[0],[])
 def test_wrong_fixture_rejected(self):
  p=payload();p["header"]["competitions"][0]["competitors"][0]["team"]["abbreviation"]="LAL"
  with self.assertRaises(ValueError):explicit_rows(p,GAME,IDENTITY,NOW)
 def test_append_without_backdate(self):
  live={"games":[GAME],"rows":[]}
  x,s=gather(live,IDENTITY,{},lambda _:payload(),NOW)
  self.assertEqual(s["new_games_checked"],1)
  y,s2=gather(live,IDENTITY,x,lambda _: (_ for _ in ()).throw(ValueError("should not fetch")),NOW)
  self.assertEqual(s2["new_games_checked"],0)
  self.assertEqual(x["events"],y["events"])
 def test_active_conflict_fails(self):
  live={"games":[GAME],"rows":[{"game_id":"espn_42","id":"n001","played":True}]}
  with self.assertRaises(ValueError):gather(live,IDENTITY,{},lambda _:payload(),NOW)
 def test_missing_is_unknown(self):
  live={"games":[GAME],"rows":[]}
  x,_=gather(live,IDENTITY,{},lambda _:payload(False),NOW)
  self.assertEqual(x["events"],[])
  self.assertEqual(x["checked_final_game_ids"],["espn_42"])
if __name__=="__main__":unittest.main()
