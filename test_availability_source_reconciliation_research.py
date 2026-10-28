import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone

from src.sync import DATA
from src.availability_source_reconciliation_research import build
from src.official_nba_nonout_unknown_research import build as nonout_build

FILES=("participation_evidence_ledger_research.json",
       "official_nba_nonout_unknown_research.json",
       "official_nba_gameday_status_research.json",
       "official_nba_inactive_summary_research.json",
       "p_play_selection_bias_audit.json",
       "p_play_shadow_research.json")

class AvailabilityProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=[json.loads((DATA/name).read_text(encoding="utf8")) for name in FILES]
        cls.now=datetime.now(timezone.utc)
        # Exact current UNKNOWN snapshot; retain historical resolved independent
        # source cases, never promote them to a p_play/DNP label.
        old=cls.sources[1]
        cls.sources[1]=nonout_build(
            cls.sources[0],cls.sources[5],cls.sources[4],cls.sources[2],
            json.loads((DATA/"identity.json").read_text()),
            json.loads((DATA/"live.json").read_text()),
            json.loads((DATA/"explicit_dnp_research.json").read_text()),
            None,lambda _: (_ for _ in ()).throw(AssertionError("Network during test")),
            cls.now,old)

    def evaluate(self,data=None):
        return build(*(self.sources if data is None else data),self.now)
    def test_all_missing_labels_have_disjoint_evidence(self):
        report=self.evaluate()
        s=report["summary"]
        self.assertEqual(s["UNKNOWN_checked"],self.sources[4]["unknown_postgame_results"])
        self.assertEqual(s["OUT_branch"]+s["non_OUT_branch"],s["UNKNOWN_checked"])
        self.assertEqual(s["game_specific_NBA_boxscore_observed"],s["UNKNOWN_checked"])
        self.assertEqual(len(report["case_records"]),s["UNKNOWN_checked"])
        self.assertEqual(s["new_pplay_DNP_labels"],0)
        self.assertTrue(all(r["p_play_result_still_UNKNOWN"] is True and
                            r["training_negative_created"] is False
                            for r in report["case_records"]))
        self.assertFalse(report["quality_gate"]["adopt_on_site"])
        self.assertFalse(report["quality_gate"]["game_day_roster_denominator_validated"])
    def test_unlisted_not_DNP_or_membership(self):
        report=self.evaluate()
        grouped=report["summary"]["source_class_counts"]
        self.assertEqual(sum(grouped.values()),report["summary"]["UNKNOWN_checked"])
        for row in report["case_records"]:
            if row["evidence_class_NOT_training_label"] == "athlete_unlisted_in_NBA_game_box_NOT_DNP":
                self.assertFalse(row["game_day_same_club_membership_verified"])
                self.assertTrue(row["p_play_result_still_UNKNOWN"])
    def test_remove_source_case_fails_closed(self):
        data=deepcopy(self.sources)
        data[1]["records"].pop()
        with self.assertRaises(ValueError):self.evaluate(data)
    def test_fake_game_day_team_tenure_and_training_negative_rejected(self):
        data=deepcopy(self.sources)
        data[1]["records"][0]["team"]="INVALID"
        with self.assertRaises(ValueError):self.evaluate(data)
        data=deepcopy(self.sources)
        data[2]["records"][0]["model_training_negative"]=True
        with self.assertRaises(ValueError):self.evaluate(data)
    def test_source_future_clock_fails(self):
        data=deepcopy(self.sources)
        data[1]["records"][0]["source_first_observed_at_utc"]="2030-01-01T00:00:00Z"
        with self.assertRaises(ValueError):self.evaluate(data)
    def test_forged_negative_and_inactive_same_team_checks(self):
        data=deepcopy(self.sources)
        data[3]["records"][0]["outcome"]="VERIFIED_OFFICIAL_NBA_INACTIVE_LIST"
        with self.assertRaises(ValueError):self.evaluate(data)
        data=deepcopy(self.sources)
        data[1]["records"][0]["independent_NBA_verdict"]="VERIFIED_ACTIVE_NONPLAY"
        with self.assertRaises(ValueError):self.evaluate(data)
    def test_stale_selection_denominator_abstains(self):
        data=deepcopy(self.sources)
        data[4]["unknown_postgame_results"]+=1
        with self.assertRaises(ValueError):self.evaluate(data)

if __name__=="__main__":unittest.main()
