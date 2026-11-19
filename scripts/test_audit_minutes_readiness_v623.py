import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "minutes_gate_v623", Path(__file__).with_name("audit_minutes_readiness_v623.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    issue_time = "2026-11-18T10:00:00Z"
    issue = dict(game_id="g1",player_id="n1",team="BOS",game_utc="2026-11-19T01:00:00Z",
                 individual_lock_utc="2026-11-19T00:30:00Z",
                 original_minutes_issued_at_utc="2026-11-18T09:50:00Z",
                 challenger_issued_at_utc=issue_time,
                 source_all_current_minutes_first_seen_pre_issue=True,
                 baseline_minutes=24.0,challenger_minutes=28.0)
    obs = dict(game_id="g1",player_id="n1",team="BOS",
               game_utc="2026-11-19T01:00:00Z",et_date="2026-11-18",
               postgame_first_seen_at_utc="2026-11-19T03:00:00Z",
               actual_minutes=30.0)
    shadow = dict(status=module.EXPECTED_STATUS,adopt_on_site=False,
                  quality_gate={"adopt_on_site":False},
                  source_frozen_minutes_issue_sha256="a"*64,
                  issued=[issue],observed=[obs],
                  summary=dict(issued_total=1,played_verified=1,
                               literal_DNP_excluded=0,UNKNOWN_not_imputed=0,
                               awaiting_or_unchecked=0))
    prior = dict(status=module.EXPECTED_STATUS,adopt_on_site=False,
                 frozen_minutes_issue_sha256="a"*64)
    return shadow,prior


class ReadonlyMinutesEvidence(unittest.TestCase):
    def test_paired_better_model_still_cannot_be_promoted(self):
        shadow,base=fixture()
        result=module.audit(shadow,base)
        self.assertEqual(result["sample"]["verified_played"],1)
        self.assertEqual(result["conditional_minutes_on_verified_played_ONLY"]["MAE_gain_positive_favors_challenger"],4)
        self.assertFalse(result["release_gate"]["promote_as_expected_minutes_on_site"])
        self.assertIsNone(result["conditional_minutes_on_verified_played_ONLY"]["exploratory_95pct_ET_date_cluster_interval_gain"])

    def test_no_outcome_before_issue(self):
        shadow,base=fixture()
        shadow["observed"][0]["postgame_first_seen_at_utc"]="2026-11-18T09:30:00Z"
        with self.assertRaisesRegex(ValueError,"tipoff"):
            module.audit(shadow,base)

    def test_NO_unknown_as_dnp(self):
        shadow,base=fixture()
        shadow["summary"]["UNKNOWN_not_imputed"]=1
        with self.assertRaisesRegex(ValueError,"reconcile"):
            module.audit(shadow,base)

    def test_wrong_source_rejected(self):
        shadow,base=fixture()
        base["frozen_minutes_issue_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"mismatch"):
            module.audit(shadow,base)

    def test_individual_lock_required(self):
        shadow,base=fixture()
        shadow["issued"][0]["challenger_issued_at_utc"]="2026-11-19T00:35:00Z"
        with self.assertRaisesRegex(ValueError,"before lock"):
            module.audit(shadow,base)

    def test_promoted_research_cannot_be_consumed_as_valid(self):
        shadow,base=fixture()
        shadow["quality_gate"]["adopt_on_site"]=True
        with self.assertRaisesRegex(ValueError,"safety gate"):
            module.audit(shadow,base)

if __name__=="__main__":
    unittest.main()
