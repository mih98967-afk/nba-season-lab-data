"""Research-only independent NBA review for 26 first-issued NON-OUT unknowns."""
import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from src.sync import DATA
from src.official_nba_nonout_unknown_research import build, eligible_cases
from src.official_nba_gameday_status_research import verdict

def archive():
    files = ("participation_evidence_ledger_research.json",
             "p_play_shadow_research.json",
             "p_play_selection_bias_audit.json",
             "official_nba_gameday_status_research.json",
             "identity.json","live.json","explicit_dnp_research.json")
    return [json.loads((DATA/f).read_text(encoding="utf8")) for f in files]

class NonOutEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=archive()
        cls.now=datetime.now(timezone.utc)
    def test_real_current_all_unknown_accounted_without_labels(self):
        result=build(*self.inputs,None,lambda u: self.fail("Network should not run"),
                     self.now)
        summary=result["summary"]
        self.assertEqual(summary["all_finished_p_play_UNKNOWN"],
                         self.inputs[2]["unknown_postgame_results"])
        self.assertEqual(summary["already_reviewed_official_OUT_excluded"],
                         len(self.inputs[3]["records"]))
        self.assertEqual(summary["new_non_OUT_review_cohort"] +
                         summary["already_reviewed_official_OUT_excluded"],
                         summary["all_finished_p_play_UNKNOWN"])
        self.assertEqual(len(result["records"]),
                         summary["new_non_OUT_review_cohort"])
        self.assertEqual(summary["p_play_negative_labels_created"],0)
        self.assertFalse(result["quality_gate"]["adopt_on_site"])
        self.assertTrue(all(row["p_play_outcome_still_UNKNOWN"] is True
                        and row["model_training_negative"] is False
                        and row["source_first_observed_at_utc"] is None
                        for row in result["records"]))
        self.assertTrue(all(row["independent_NBA_verdict"]=="UNKNOWN"
                        for row in result["records"]))
    def test_resolution_archives_only_genuine_verified_ESPN_labels(self):
        inputs=deepcopy(self.inputs)
        old=json.loads((DATA/"official_nba_nonout_unknown_research.json").read_text())
        report=build(*inputs,None,lambda _:self.fail("Network should not run"),
                     self.now,old)
        previous={(r["game_id"],r["player_id"]) for r in old["records"]}
        active={(r["game_id"],r["player_id"]) for r in report["records"]}
        historic={(r["source_case"]["game_id"],r["source_case"]["player_id"])
                  for r in report["resolved_verified_history"]}
        self.assertFalse(active&historic)
        self.assertEqual(report["summary"]["historical_verified_resolution_source_records_preserved"],len(historic))
        self.assertTrue(all(x["source_case_sha256"] and x["p_play_label_provenance"]
                            in ("positive_minutes_verified_sportsru_fp",
                                "explicit_espn_didNotPlay_true")
                            for x in report["resolved_verified_history"]))
        again=build(*inputs,None,lambda _:self.fail("Network should not run"),
                    self.now,report)
        self.assertEqual(again["resolved_verified_history"],report["resolved_verified_history"])
        corrupted=deepcopy(report)
        if corrupted["resolved_verified_history"]:
            corrupted["resolved_verified_history"][0]["p_play_verified_actual_played"]=0 if (
                corrupted["resolved_verified_history"][0]["p_play_verified_actual_played"]==1) else 1
            with self.assertRaises(ValueError):
                build(*inputs,None,lambda _:None,self.now,corrupted)
        missing=deepcopy(inputs)
        if report["resolved_verified_history"]:
            key=report["resolved_verified_history"][0]["source_case"]
            missing[1]["observations"]=[x for x in missing[1]["observations"] if
                (x["game_id"],x["player_id"])!=(key["game_id"],key["player_id"])]
            with self.assertRaises(ValueError):
                build(*missing,None,lambda _:None,self.now,old)

    def test_literal_NBA_only_and_wrong_team_conflict(self):
        obj={"111":{"team":"BOS","played":"0","status":"INACTIVE",
                    "not_playing_reason":"Injury"},
             "112":{"team":"BOS","played":"0","status":"ACTIVE",
                    "not_playing_reason":"DNP - Coach Decision"},
             "113":{"team":"NYK","played":"0","status":"INACTIVE",
                    "not_playing_reason":"Injury"},
             "114":{"team":"BOS","played":"1","status":"ACTIVE",
                    "not_playing_reason":None}}
        self.assertEqual(verdict(obj,"BOS","111",{})[0],
                         "VERIFIED_GAME_DAY_INACTIVE")
        self.assertEqual(verdict(obj,"BOS","112",{})[0],
                         "VERIFIED_ACTIVE_NONPLAY")
        self.assertTrue(verdict(obj,"BOS","113",{})[2])
        self.assertTrue(verdict(obj,"BOS","114",{})[2])
        self.assertEqual(verdict(obj,"BOS","999",{})[0],"UNKNOWN")
        self.assertEqual(verdict(obj,"BOS",None,{})[0],"UNKNOWN")
    def test_unsafe_prior_record_rejected(self):
        report=build(*self.inputs,None,lambda _:None,self.now)
        changed=deepcopy(report)
        changed["records"][0]["model_training_negative"]=True
        with self.assertRaises(ValueError):
            build(*self.inputs,None,lambda _:None,self.now,changed)
    def test_conflicting_club_and_out_review_queue_rejected(self):
        changes=deepcopy(self.inputs)
        changes[0]["unknown_cases"][-1]["team"]="XXX"
        with self.assertRaises(ValueError):
            build(*changes,None,lambda _:None,self.now)
        changes=deepcopy(self.inputs)
        changes[3]["records"].pop()
        with self.assertRaises(ValueError):
            build(*changes,None,lambda _:None,self.now)
    def test_fake_postgame_observation_rejected(self):
        changes=deepcopy(self.inputs)
        case=next(row for row in changes[0]["unknown_cases"]
                  if row["official_status_first_known_by_issue"]!="out")
        case["first_prediction_issued_at_utc"]="2026-10-30T00:00:00Z"
        with self.assertRaises(ValueError):
            build(*changes,None,lambda _:None,self.now)
    def test_reproducible_offline_repeat_preserves_old_source_times(self):
        first=build(*self.inputs,None,lambda _:None,self.now)
        second=build(*self.inputs,None,lambda _:None,self.now,first)
        self.assertEqual(first["records"],second["records"])
        self.assertEqual(second["summary"]["p_play_negative_labels_created"],0)

if __name__=="__main__": unittest.main()
