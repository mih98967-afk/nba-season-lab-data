import json,unittest
from copy import deepcopy
from datetime import datetime,timezone
from src.sync import DATA
from src.short_minutes_prospective_evaluation_research import build
class Test(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=json.loads((DATA/"short_minutes_prospective_research.json").read_text())
  cls.m=json.loads((DATA/"conditional_minutes_fp_research.json").read_text())
  cls.e=json.loads((DATA/"conditional_minutes_fp_evaluation_research.json").read_text())
 def make(self,r=None,m=None,e=None):
  return build(r or self.r,m or self.m,e or self.e,datetime.now(timezone.utc))
 def test_real_pending_denominator(self):
  v=self.make();s=v["summary"]
  self.assertEqual(s["issued"],sum(s[k] for k in ("played_verified","explicit_DNP_excluded","UNKNOWN_not_imputed","awaiting_or_unchecked")))
  self.assertEqual(s["issued"],len(v["outcome_audit"]))
  self.assertFalse(v["quality_gate"]["adopt_on_site"])
  if not s["played_verified"]:self.assertIsNone(v["conditional_played_only_metrics"]["Brier_group"])
 def test_changed_first_issue_rejected(self):
  r=deepcopy(self.r);r["issued"][0]["risk_first_issued_at_utc"]=r["issued"][0]["individual_lock_utc"]
  with self.assertRaises(ValueError):self.make(r=r)
 def test_modified_original_prediction_rejected(self):
  m=deepcopy(self.m);m["issued"][-1]["min_if_play"]+=1
  with self.assertRaises(ValueError):self.make(m=m)
 def test_bad_probability_rejected_even_before_match(self):
  r=deepcopy(self.r);r["issued"][0]["group_dev_short_given_played_probability"]=-1
  with self.assertRaises(ValueError):self.make(r=r)
 def test_double_played_evidence_rejected(self):
  e=deepcopy(self.e);e["scored_played"].append(deepcopy(e["scored_played"][0]))
  with self.assertRaises(ValueError):self.make(e=e)
if __name__=="__main__":unittest.main()
