"""Strict genuinely issued 2026/27 near-lock refresh versus OLD original."""
import unittest
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path

from src.current_season_prelock_refresh_research import (
    build,MODEL_HASH,FIELDS,verified_form,make_issue
)
from src.rolling_decision_research import player_games,canonical_hash


def when(x):return datetime.fromisoformat(x.replace("Z","+00:00"))


class Refresh(unittest.TestCase):
    def setup(self):
        # The previous-season baseline really existed 26h before refresh.
        orig="2026-10-28T12:00:00Z"
        base={
            "game_id":"g4","player_id":"p","team":"BOS",
            "game_utc":"2026-10-30T00:00:00Z",
            "individual_lock_utc":"2026-10-29T23:30:00Z",
            "issued_at_utc":orig,
            "min_if_play":30,"fp_per_minute_if_play":0.5,
            "decomposed_fp_if_play":15,
        }
        frozen={
            "schema_version":1,"status":"research_only_not_deployed",
            "adopt_on_site":False,"unconditional_FP_enabled":False,
            "issued":[base],
        }
        live={"schema_version":4,"games":[],"rows":[]}
        first={}
        for i in range(3):
            gid="g"+str(i)
            tip="2026-10-%02dT00:00:00Z"%(26+i)
            live["games"].append({"id":gid,"utc":tip,
                                  "home":"BOS","away":"NYK","status":"final"})
            live["rows"].append({
                "id":"p","game_id":gid,"utc":tip,
                "team":"BOS","played":True,"minutes":20+i,"fp":11+i,
            })
            first[gid+"|p"]=("2026-10-28T14:00:00Z" if i==2 else "2026-10-%02dT08:00:00Z"%(26+i))
        current,_=player_games(live,when("2026-10-29T20:00:00Z"))
        rolling={
            "schema_version":1,"status":"research_only_not_deployed",
            "adopt_on_site":False,"row_first_seen_at_utc":first,
            "row_hashes":{f"{gid}|{pid}":canonical_hash(v)
                          for (gid,pid),v in current.items()},
        }
        evaluation={
            "status":"research_only_not_deployed","adopt_on_site":False,
            "quality_gate":{"adopt_on_site":False},
            "frozen_minutes_issue_sha256":canonical_hash([base]),
            "summary":{"played":0},
            "scored_played":[],"explicit_DNP_not_in_conditional_metrics":[],
            "UNKNOWN_unscored":[],
        }
        return [{},frozen,evaluation,rolling,live]

    def test_issues_at_actual_new_time_not_original(self):
        args=self.setup()
        out=build(*args,when("2026-10-29T18:00:00Z"))
        self.assertEqual(out["summary"]["issued_total"],1)
        self.assertEqual(out["issued"][0]["refresh_issued_at_utc"],
                         "2026-10-29T18:00:00Z")
        self.assertEqual(out["issued"][0]["original_frozen_issued_at_utc"],
                         "2026-10-28T12:00:00Z")
        self.assertEqual(out["summary"]["issued_with_additional_source_after_original"],1)
        self.assertEqual(len(out["issued"][0]["FP_variants_frozen"]),len(FIELDS))
        self.assertFalse(out["quality_gate"]["adopt_on_site"])
        again=build(out,*args[1:],when("2026-10-29T19:00:00Z"))
        self.assertEqual(out["issued"],again["issued"])
        self.assertEqual(again["summary"]["new_issued_this_run"],0)

    def test_before_nearlock_window_no_false_issuance(self):
        args=self.setup()
        x=build(*args,when("2026-10-29T10:00:00Z"))
        self.assertEqual(x["summary"]["issued_total"],0)
        self.assertEqual(x["issuance_QA"]["await_near_lock_window"],1)

    def test_after_lock_no_backdating(self):
        args=self.setup()
        x=build(*args,when("2026-10-29T23:30:00Z"))
        self.assertEqual(x["summary"]["issued_total"],0)
        self.assertEqual(x["issuance_QA"]["original_opportunity_already_locked_no_backfill"],1)

    def test_firstseen_after_refresh_not_used(self):
        args=self.setup()
        args[3]["row_first_seen_at_utc"]["g2|p"]="2026-10-29T20:00:00Z"
        x=build(*args,when("2026-10-29T18:00:00Z"))
        self.assertEqual(x["summary"]["issued_total"],0)
        self.assertEqual(x["issuance_QA"]["insufficient_verified_same_club_prelock_form"],1)

    def test_source_fp_hash_changed_fails_closed(self):
        args=self.setup()
        args[3]["row_hashes"]["g1|p"]="0"*64
        with self.assertRaisesRegex(ValueError,"rolling hash"):
            build(*args,when("2026-10-29T18:00:00Z"))

    def test_cross_club_newer_seen_stops_issue(self):
        args=self.setup()
        new={"id":"p","game_id":"g3","utc":"2026-10-29T00:00:00Z",
             "team":"NYK","played":True,"minutes":12,"fp":1}
        args[4]["games"].append({"id":"g3","utc":new["utc"],
                                  "home":"BOS","away":"NYK","status":"final"})
        args[4]["rows"].append(new)
        args[3]["row_first_seen_at_utc"]["g3|p"]="2026-10-29T08:00:00Z"
        current,_=player_games(args[4],when("2026-10-29T20:00:00Z"))
        args[3]["row_hashes"]={f"{gid}|{pid}":canonical_hash(v)
                              for (gid,pid),v in current.items()}
        out=build(*args,when("2026-10-29T18:00:00Z"))
        self.assertEqual(out["summary"]["issued_total"],0)
        self.assertEqual(out["issuance_QA"]["latest_observed_club_differs_from_original_prior"],1)

    def test_postgame_played_then_unknown_label_never_zero(self):
        args=self.setup()
        out=build(*args,when("2026-10-29T18:00:00Z"))
        args[2]["UNKNOWN_unscored"]=[{"game_id":"g4","player_id":"p"}]
        other=build(out,*args[1:],when("2026-10-30T06:00:00Z"))
        self.assertEqual(other["summary"]["UNKNOWN_not_imputed"],1)
        self.assertEqual(other["played_only_paired_metrics"]["scored_positive_played"],0)
        args[2]["UNKNOWN_unscored"]=[]
        args[2]["scored_played"]=[{
            "game_id":"g4","player_id":"p",
            "team":"BOS","position":"PG","game_utc":"2026-10-30T00:00:00Z",
            "et_date":"2026-10-29",
            "postgame_first_seen_at_utc":"2026-10-30T05:00:00Z",
            "actual_minutes":26,"actual_fp_reconstructed":16,
        }]
        args[2]["summary"]["played"]=1
        args[2]["frozen_minutes_issue_sha256"]=canonical_hash(args[1]["issued"])
        next=build(out,*args[1:],when("2026-10-30T06:00:00Z"))
        self.assertEqual(next["summary"]["played_verified"],1)
        self.assertEqual(next["played_only_paired_metrics"]["scored_positive_played"],1)

    def test_source_original_immutable(self):
        args=self.setup()
        before=build(*args,when("2026-10-29T18:00:00Z"))
        args[1]["issued"][0]["min_if_play"]=44
        with self.assertRaises(ValueError):
            build(before,*args[1:],when("2026-10-29T19:00:00Z"))

    def test_sync_single_writer(self):
        main=(Path(__file__).resolve().parent/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(main.count("python -m src.current_season_prelock_refresh_research"),2)
        self.assertIn("data/current_season_prelock_refresh_research.json",main)
        self.assertIn("test_current_season_prelock_refresh_research",main)
        self.assertEqual(MODEL_HASH,canonical_hash({
            "name":"new_issued_nearlock_minutes_rate_refresh_v1",
            "issue_window_before_individual_Tminus30_hours":12,
            "min_verified_current_same_club_played":3,
            "max_verified_current_same_club_played":5,
            "frozen_previous_season_minutes_prior_strength_games":5,
            "frozen_previous_season_rate_prior_strength_games":10,
            "model_chosen_after_2026_27_season_started":True,
            "baseline_and_refresh_info_times_differ":True,
            "no_backdated_refresh_issuance":True,
            "unknown_is_not_DNP_or_FP_zero":True,
            "adopt_on_site":False,
        }))


if __name__=="__main__":unittest.main()
