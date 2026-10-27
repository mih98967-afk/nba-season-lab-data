import unittest
from src.historical_appearance_calibration_research import _adjust,fit_dev,_score,paired_player_ci
class Tests(unittest.TestCase):
 def test_dev_only_shrink_prefers_less_overconfidence(self):
  dev=[("p"+str(i%12),int(i%3==0),0.99 if i%3==0 else 0.95) for i in range(1200)]
  fit=fit_dev(dev)
  self.assertGreater(fit["selected_shrink"],0)
  self.assertLessEqual(fit["selected_shrink"],0.5)
 def test_shrink_preserves_order_and_identity(self):
  self.assertEqual(_adjust(.7,0,.4),.7)
  self.assertLess(_adjust(.1,.2,.6),_adjust(.9,.2,.6))
 def test_pair_is_aligned_and_direction_preserved(self):
  a=[("p",1,.6),("q",0,.5)]
  c=[("p",1,.7),("q",0,.4)]
  x=paired_player_ci(a,a,c,draws=100)
  self.assertIn("brier_raw_to_calibrated",x["gain_intervals_95pct"])
  with self.assertRaises(ValueError):paired_player_ci(a,list(reversed(a)),c,draws=100)
 def test_invalid_probability_rejected(self):
  with self.assertRaises(ValueError):_score(0.,1,"logloss")
if __name__=="__main__":unittest.main()
