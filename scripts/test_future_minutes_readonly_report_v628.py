"""Independent regressions for the future-only minutes progress report."""
import unittest
from scripts.future_minutes_readonly_report_v628 import report
from scripts.test_evaluate_minutes_prereg_v623 import fixture, CONTRACT


class ReadOnlyFutureMinutesTests(unittest.TestCase):
    def test_played_future_and_no_adoption(self):
        original = fixture()
        got = report(original, CONTRACT, "a"*64, "b"*64)
        self.assertEqual(got["cohort"]["issued"], 1)
        self.assertEqual(got["cohort"]["verified_played"], 1)
        self.assertEqual(got["preregistered_progress"]["positive_minute_pairs"]["actual"], 1)
        self.assertEqual(got["preregistered_progress"]["positive_minute_pairs"]["remaining"],
                         CONTRACT["thresholds"]["positive_minute_pairs"]-1)
        self.assertEqual(got["scored_ET_dates"], ["2026-11-21"])
        self.assertFalse(got["limits"]["adopt_on_site"])
        self.assertFalse(got["limits"]["change_FP_or_P_play"])
        self.assertEqual(got["source_blob_sha256"], "a"*64)
        self.assertEqual(got["contract_blob_sha256"], "b"*64)
        self.assertEqual(original, fixture(), "Research input must not be mutated")

    def test_unobserved_is_unknown_not_dnp(self):
        data=fixture()
        data["observed"]=[]
        got=report(data, CONTRACT)
        self.assertEqual(got["cohort"]["issued"],1)
        self.assertEqual(got["cohort"]["verified_played"],0)
        self.assertEqual(got["unscored_issued_cases_not_assumed_DNP"],1)
        self.assertEqual(got["paired_minutes"]["n"],0)
        self.assertIsNone(got["bootstrap95_only_after_predeclared_gates"])

    def test_pre_window_is_excluded(self):
        data=fixture()
        data["issued"][0]["challenger_issued_at_utc"]="2026-11-20T12:00:00Z"
        got=report(data,CONTRACT)
        self.assertEqual(got["cohort"]["issued"],0)
        self.assertEqual(got["cohort"]["verified_played"],0)

    def test_fake_date_cannot_inflate_ET_bootstrap_gate(self):
        data=fixture()
        data["observed"][0]["et_date"]="2026-11-22"
        with self.assertRaisesRegex(ValueError,"NBA ET date"):report(data,CONTRACT)

    def test_ET_date_is_new_york_not_UTC(self):
        self.assertEqual(report(fixture(),CONTRACT)["scored_ET_dates"],["2026-11-21"])

    def test_postgame_evidence_cannot_precede_snapshot(self):
        data=fixture()
        data["updated_at_utc"]="2026-11-22T03:00:00Z"
        with self.assertRaisesRegex(ValueError,"after source snapshot"):
            report(data,CONTRACT)

    def test_model_and_T30_still_frozen(self):
        data=fixture()
        data["issued"][0]["individual_lock_utc"]="2026-11-22T00:01:00Z"
        with self.assertRaisesRegex(ValueError,"T-30"):report(data,CONTRACT)
        data=fixture()
        data["issued"][0]["model_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"model drift"):report(data,CONTRACT)

    def test_unplayed_zero_not_accepted(self):
        data=fixture()
        data["observed"][0]["actual_minutes"]=0
        with self.assertRaisesRegex(ValueError,"only positive-minute"):
            report(data,CONTRACT)


if __name__ == "__main__":
    unittest.main()
