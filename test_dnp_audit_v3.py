import unittest
from src.dnp_audit_v3 import box_min,predict,scoring
class TestDNP(unittest.TestCase):
 def test_missing_is_unknown(self):
  self.assertIsNone(box_min(None,""))
  self.assertEqual(box_min(None,"DNP - INJURY"),0)
 def test_minutes(self):
  self.assertAlmostEqual(box_min("12:30",""),12.5)
 def test_pit_only(self):
  r={"played20":3,"n20":5,"played5":2,"n5":3,"gap_days":4,"b2b":False,"played":1}
  p=predict(r,(10,.25,0.,0.),.9)
  self.assertGreater(p,0);self.assertLessEqual(p,1)
  self.assertEqual(scoring([r],(10,.25,0.,0.),.9)["n"],1)
if __name__=="__main__":unittest.main()
