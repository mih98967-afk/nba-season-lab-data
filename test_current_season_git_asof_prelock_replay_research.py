"""As-of 2026 retro replay is separated from actual genuine prelock issuance."""
import unittest
from copy import deepcopy
from pathlib import Path

from src.current_season_git_asof_prelock_replay_research import (
    provenance_index,values_at,candidate_prediction,build,LOCK,STATUS,
)
from src.rolling_decision_research import canonical_hash
from src.conditional_minutes_fp_research import forecast


class GitAsOfReplayTests(unittest.TestCase):
    def sources(self):
        first="2026-10-25T19:26:07Z"
        version_first="2026-10-29T18:09:35Z"
        key="g0|p"
        src={"game_id":"g0","player_id":"p","team":"BOS",
             "fp":11,"minutes":21,"utc":"2026-10-25T00:00:00Z"}
        corrected={**src,"fp":18}
        proof={
            "status":STATUS,"adopt_on_site":False,
            "first_row_version_archive_at_utc":version_first,
            "summary":{"first_row_version_archive_keys_exactly_reconciled":1},
            "fixed_last_git_sha":"d1225876",
            "quality_gate":{"historical_commit_blobs_anchored_to_original_immutable_git_SHA":True},
            "versions":{key:[
                {"observed_at_utc":first,"kind":"observed",
                 "row":src,"row_sha256":canonical_hash(src)},
                {"observed_at_utc":"2026-10-28T16:00:00Z","kind":"observed",
                 "row":corrected,"row_sha256":canonical_hash(corrected)},
            ]},
        }
        versions={
            "status":STATUS,"adopt_on_site":False,
            "first_version_archive_at_utc":version_first,
            "summary":{"unique_player_games":1},
            "versions":{key:[{"version_observed_at_utc":version_first,
                "row":corrected,"row_sha256":canonical_hash(corrected)}]},
        }
        return proof,versions

    def prior(self):
        return [{"g":"00225%06d"%i,"team":"BOS","d":"2026-03-%02d"%(i+1),
                 "min":30,"fp":24} for i in range(22)]

    def candidate(self):
        return {
            "game_id":"g4","player_id":"p","team_in_catalog_snapshot":"BOS",
            "fantasy_position":"PG","game_utc":"2026-10-29T23:00:00Z",
            "individual_lock_utc":"2026-10-29T22:30:00Z",
            "catalog_capture_utc":"2026-10-29T15:00:00Z",
            "espn_roster_capture_utc":"2026-10-29T14:00:00Z",
            "club_cross_source_evidence":"same_club_independent_ESPN_ID_observed",
            "postgame_outcome":"unknown_outcome_or_unverified_game_day_membership",
            "postgame_first_seen_at_utc":None,
            "postgame_first_seen_timestamp_verified":False,
            "postgame_evidence":None,
        }

    def test_post_anchor_new_player_game_keeps_original_git_bridge_valid(self):
        # New genuine game rows cannot make the frozen 1346-row origin count
        # look incorrect. They are only visible from their actual capture.
        from src.rolling_decision_research import instant
        proof, versions = self.sources()
        new_row = {"game_id":"g1","player_id":"q","team":"NYK",
                   "fp":7,"minutes":14,"utc":"2026-10-30T00:00:00Z"}
        versions["versions"]["g1|q"] = [{
            "version_observed_at_utc":"2026-10-30T07:00:00Z",
            "row":new_row,"row_sha256":canonical_hash(new_row),
        }]
        versions["summary"]["unique_player_games"] = 2
        timeline = provenance_index(proof, versions)
        self.assertNotIn("q", values_at(timeline, instant("2026-10-29T22:00:00Z")))
        self.assertEqual(values_at(timeline, instant("2026-10-30T08:00:00Z"))
                         ["q"][0]["fp"], 7)

    def test_original_git_bridge_still_fails_closed_if_tampered(self):
        proof, versions = self.sources()
        lost = deepcopy(versions)
        lost["versions"]["g0|p"][0]["version_observed_at_utc"] = (
            "2026-10-30T07:00:00Z")
        with self.assertRaisesRegex(ValueError, "bridge drift"):
            provenance_index(proof, lost)
        forged = deepcopy(versions)
        forged_row = forged["versions"]["g0|p"][0]["row"]
        forged_row["fp"] = 19
        forged["versions"]["g0|p"][0]["row_sha256"] = canonical_hash(forged_row)
        with self.assertRaisesRegex(ValueError, "differs from sealed Git proof"):
            provenance_index(proof, forged)
        backdated = deepcopy(versions)
        backdated["versions"]["g0|p"][0]["version_observed_at_utc"] = (
            "2026-10-29T18:09:34Z")
        with self.assertRaisesRegex(ValueError, "falsely predates"):
            provenance_index(proof, backdated)

    def test_git_values_are_timestamped_not_latest_revision(self):
        proof,versions=self.sources()
        tl=provenance_index(proof,versions)
        from src.rolling_decision_research import instant
        old=values_at(tl,instant("2026-10-27T00:00:00Z"))
        new=values_at(tl,instant("2026-10-29T00:00:00Z"))
        self.assertEqual(old["p"][0]["fp"],11)
        self.assertEqual(new["p"][0]["fp"],18)
        self.assertEqual(values_at(tl,instant("2026-10-25T19:00:00Z")),{})

    def test_no_latest_or_future_row_is_used_in_earlier_forecast(self):
        from src.rolling_decision_research import instant
        proof,versions=self.sources()
        tl=provenance_index(proof,versions)
        rows=values_at(tl,instant("2026-10-27T00:00:00Z"))
        row=rows["p"][0]
        self.assertEqual(row["fp"],11)
        for i in (1,2):
            rows["p"].append({
                **row,"game_id":f"g{i}",
                "game_utc":f"2026-10-2{5+i}T00:00:00Z",
            })
        rows["p"].sort(key=lambda x:x["game_utc"])
        c=self.candidate()
        p,reason=candidate_prediction(c,self.prior(),rows,
                                      instant(c["individual_lock_utc"]))
        self.assertIsNone(reason)
        self.assertEqual(p["source_form_n"],3)
        self.assertEqual(p["FP_variants"]["prior_previous_season_FP"],24)
        self.assertTrue(p["not_genuine_historical_issue"])

    def test_same_team_trade_and_no_prior_abstain(self):
        from src.rolling_decision_research import instant
        c=self.candidate()
        now=instant(c["individual_lock_utc"])
        recent={"game_id":"g0","team":"NYK","game_utc":"2026-10-27T00:00:00Z",
                "minutes":20,"fp":8}
        p,reason=candidate_prediction(c,self.prior(),{"p":[recent]},now)
        self.assertIsNone(p)
        self.assertEqual(reason,"last_proven_current_season_club_changed")
        p,reason=candidate_prediction(c,[],{"p":[recent]},now)
        self.assertIsNone(p)
        self.assertEqual(reason,"no_20_game_previous_season_same_club_prior")

    def test_no_outcome_selected_to_construct_candidate(self):
        from src.rolling_decision_research import instant
        c=self.candidate()
        now=instant(c["individual_lock_utc"])
        sample=[{"game_id":f"g{i}","team":"BOS",
                 "game_utc":f"2026-10-2{5+i}T00:00:00Z",
                 "fp":10+i,"minutes":20+i,"row_sha256":str(i),
                 "version_proven_at_utc":"2026-10-28T16:00:00Z"}
                 for i in range(3)]
        p,_=candidate_prediction(c,self.prior(),{"p":sample},now)
        cc=deepcopy(c)
        cc["postgame_outcome"]="played_verified_after_game"
        cc["postgame_evidence"]="positive_minutes_verified_sportsru_fp"
        updated,_=candidate_prediction(cc,self.prior(),{"p":sample},now)
        self.assertEqual(p,updated)

    def test_replay_never_embeds_future_asof_snapshot(self):
        proof,versions=self.sources()
        bad=deepcopy(proof)
        bad["versions"]["g0|p"][0]["row"]["fp"]=999
        with self.assertRaisesRegex(ValueError,"Corrupted"):
            provenance_index(bad,versions)
        from src.rolling_decision_research import instant
        tl=provenance_index(proof,versions)
        bad=deepcopy(tl)
        bad["g0|p"][0][1]["utc"]="2026-10-30T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"Target/future"):
            values_at(bad,instant("2026-10-27T00:00:00Z"))

    def test_replay_does_not_write_model_or_second_publisher(self):
        root=Path(__file__).resolve().parent
        workflow=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(workflow.count("python -m src.current_season_git_asof_prelock_replay_research"),2)
        self.assertIn("data/current_season_git_asof_prelock_replay_research.json",workflow)
        self.assertIn("test_current_season_git_asof_prelock_replay_research",workflow)
        code=(root/"src/current_season_git_asof_prelock_replay_research.py").read_text()
        self.assertIn('"adopt_on_site":False',code)
        self.assertNotIn("Firestore",code)


if __name__=="__main__":unittest.main()
