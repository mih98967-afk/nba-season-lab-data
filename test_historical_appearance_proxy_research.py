import unittest
from datetime import datetime,timezone,timedelta
from src.historical_appearance_proxy_research import player_samples,estimate,score,BASELINE,STATUS
def ts(x):return datetime.fromisoformat(x.replace("Z","+00:00"))
class HistoricalAppearanceProxyTests(unittest.TestCase):
 def fixture(self):
  games=[];played=[]
  for i in range(27):
   t=ts("2025-01-01T01:00:00Z")+timedelta(days=i)
   gid=f"002250{i:04d}"
   games.append({"id":gid,"utc":t,"home":"BOS","away":"NYK"})
   if i!=25:
    played.append({"id":gid,"utc":t,"club":"BOS"})
  return games,played
 def test_no_target_leak_and_unknown_not_dnp(self):
  f,active=self.fixture()
  sample,qa=player_samples(f,active,"n001","2025/26")
  d={r["game_id"]:r for r in sample}
  missing=d[f[25]["id"]]
  self.assertEqual(missing["appearance_logged_in_exact_game"],0)
  self.assertFalse(missing["negative_is_explicit_DNP"])
  self.assertTrue(missing["historical_team_membership_unverified"])
  self.assertEqual(missing["last5_appeared"],5)
  self.assertGreaterEqual(qa["no_logged_appearance_NOT_DNP"],1)
  self.assertGreaterEqual(len(sample),1)
 def test_illegal_lookahead_not_possible_for_target(self):
  f,active=self.fixture()
  out,_=player_samples(f,active,"n001","2025/26")
  early=next(r for r in out if r["game_id"]==f[25]["id"])
  altered=[r for r in active if r["id"]!=f[26]["id"]]
  later,_=player_samples(f,altered,"n001","2025/26")
  same=next(r for r in later if r["game_id"]==f[25]["id"])
  self.assertEqual(early["last20_appeared"],same["last20_appeared"])
  self.assertEqual(early["last5_appeared"],same["last5_appeared"])
 def test_scores_bounds_and_no_deployment(self):
  f,active=self.fixture()
  rows,_=player_samples(f,active,"n001","2025/26")
  self.assertTrue(0<estimate(rows[-1],BASELINE)<1)
  result=score(rows,BASELINE)
  self.assertGreaterEqual(result["brier"],0)
  self.assertGreaterEqual(result["logloss"],0)
  self.assertEqual(STATUS,"research_only_not_deployed")
if __name__=="__main__":unittest.main()
