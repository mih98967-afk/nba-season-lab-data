"""Real-first-issue and no-backfill regression for prospective short minutes."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.short_minutes_prospective_research import build, validate_role

FIXED=datetime(2026,10,28,12,54,tzinfo=timezone.utc)

def load(name):
    return json.loads((DATA/name).read_text(encoding="utf8"))

class ShortMinuteIssues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minute=load("conditional_minutes_fp_research.json")
        # A historical replay must not load real forecasts issued AFTER FIXED.
        # Preserve every original field; restrict only the available first-issue set.
        cls.minute["issued"]=[x for x in cls.minute["issued"] if x["issued_at_utc"]<=FIXED.isoformat().replace("+00:00","Z")]
        cls.minute["issued_total"]=len(cls.minute["issued"])
        cls.shadow=load("p_play_shadow_research.json")
        cls.role=load("short_minutes_role_bands_research.json")
    def make(self,time=FIXED,old=None,minute=None,shadow=None,role=None):
        return build(minute or self.minute,shadow or self.shadow,
                     role or self.role,time,old)
    def test_real_prelock_issues_and_immutable_join(self):
        report=self.make()
        self.assertTrue(report["issued_total"]>0)
        self.assertEqual(report["issued_total"]+report["issue_QA"]["locked_cannot_backfill"],
                         self.minute["issued_total"])
        self.assertTrue(all(row["risk_first_issued_at_utc"]<
                            row["individual_lock_utc"] for row in report["issued"]))
        self.assertTrue(all(row["outcome_at_first_issue"]=="UNKNOWN" and
                            row["model_training_negative"] is False
                            and row["adopt_on_site"] is False
                            for row in report["issued"]))
        self.assertFalse(report["quality_gate"]["unconditional_FP_allowed"])
        self.assertFalse(report["quality_gate"]["p_play_population_calibrated"])
    def test_no_backfill_even_if_some_inputs_are_known_prelock(self):
        later=datetime(2026,11,1,tzinfo=timezone.utc)
        report=self.make(time=later)
        self.assertEqual(report["issued_total"],0)
        self.assertEqual(report["issue_QA"]["locked_cannot_backfill"],
                         self.minute["issued_total"])
    def test_second_run_preserves_first_prospective_timestamps(self):
        first=self.make()
        later=self.make(time=datetime(2026,11,1,tzinfo=timezone.utc),old=first)
        self.assertEqual(first["issued"],later["issued"])
        self.assertEqual(later["issue_QA"]["already_issued"],first["issued_total"])
        self.assertEqual(later["issue_QA"]["new_genuine_prelock_issues"],0)
    def test_changed_previous_minute_prediction_fails_closed(self):
        old=self.make()
        edited=deepcopy(self.minute)
        k=old["issued"][0]
        row=next(x for x in edited["issued"] if
                 (x["game_id"],x["player_id"])==(k["game_id"],k["player_id"]))
        row["min_if_play"]+=1
        with self.assertRaises(ValueError):
            self.make(time=datetime(2026,11,1,tzinfo=timezone.utc),old=old,minute=edited)
    def test_bad_pplay_identity_or_retrained_dev_fails(self):
        p=deepcopy(self.shadow)
        key=self.minute["issued"][0]
        row=next(x for x in p["issued"] if
                 (x["game_id"],x["player_id"])==(key["game_id"],key["player_id"]))
        row["team"]="INVALID"
        with self.assertRaises(ValueError): self.make(shadow=p)
        role=deepcopy(self.role)
        role["dev_only_fit"]["group_parameters_fitted_on_dev_only"]["under_15"][
            "dev_only_smoothed_conditional_short_probability"]=1.2
        with self.assertRaises(ValueError):self.make(role=role)
    def test_2025_holdout_is_never_an_issuance_feature(self):
        params,_=validate_role(self.role,self.minute)
        altered=deepcopy(self.role)
        altered["holdout_exploratory"]["group_short_minutes_Brier"]=0.99
        new,_=validate_role(altered,self.minute)
        self.assertEqual(params,new)
        self.assertEqual(self.make()["issued"],self.make(role=altered)["issued"])

if __name__=="__main__":
    unittest.main()
