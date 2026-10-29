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
        self.assertEqual(s["game_specific_NBA_boxscore_observed"] +
                         s["pending_OUT_independent_review"],s["UNKNOWN_checked"])
        self.assertEqual(len(report["case_records"]),s["UNKNOWN_checked"])
        self.assertEqual(s["new_pplay_DNP_labels"],0)
        self.assertTrue(all(r["p_play_result_still_UNKNOWN"] is True and
                            r["training_negative_created"] is False
                            for r in report["case_records"]))
        self.assertFalse(report["quality_gate"]["adopt_on_site"])
        self.assertFalse(report["quality_gate"]["game_day_roster_denominator_validated"])
    def test_out_growth_pending_reconciles_without_negative_label(self):
        data=deepcopy(self.sources)
        ledger, nonout, nba_out, nba_inactive, selection, shadow = data
        seed=next(x for x in ledger["unknown_cases"]
                  if x["official_status_first_known_by_issue"]=="out")
        first=next(x for x in shadow["issued"]
                   if x["game_id"]==seed["game_id"] and x["player_id"]==seed["player_id"])
        for i in range(11):
            pid="pending_out_source_%02d"%i
            new_case, new_issue=deepcopy(seed),deepcopy(first)
            new_case["player_id"]=new_issue["player_id"]=pid
            ledger["unknown_cases"].append(new_case)
            shadow["issued"].append(new_issue)
        selection["unknown_postgame_results"]+=11
        selection["total_issued_predictions"]+=11
        ledger["overall_selected_opportunity_coverage"]["outcome_UNKNOWN"]+=11
        ledger["issued_total_including_future"]+=11
        ledger["current_OUT_queue"]+=11
        nonout["summary"]["all_finished_p_play_UNKNOWN"]+=11
        nonout["summary"]["total_official_OUT_UNKNOWN_excluded"]+=11
        nonout["summary"]["pending_official_OUT_independent_review_excluded"]+=11
        result=self.evaluate(data)
        previous_pending = len([r for r in self.sources[0]["unknown_cases"]
                                if r["official_status_first_known_by_issue"]=="out"]) - len(self.sources[2]["records"])
        self.assertEqual(result["summary"]["pending_OUT_independent_review"],previous_pending+11)
        self.assertEqual(result["summary"]["new_pplay_DNP_labels"],0)
        pending=[x for x in result["case_records"] if x["player_id"].startswith("pending_out_source_")]
        self.assertEqual(len(pending),11)
        self.assertTrue(all(x["official_NBA_game_specific_verdict"]=="UNKNOWN"
                            and x["official_NBA_game_source_observed_at_utc"] is None
                            and x["training_negative_created"] is False
                            for x in pending))
        corrupt=deepcopy(data)
        corrupt[2]["records"][0]["team"]="INVALID"
        with self.assertRaises(ValueError):
            self.evaluate(corrupt)

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
