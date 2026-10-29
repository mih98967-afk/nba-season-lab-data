"""Test genuinely prelock FP-rate variants and single writer ownership."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from src.current_season_fp_rate_shadow_research import (
    build, RATE_FIELDS, CONTROL, MODEL_HASH, source_fp_rows,
)
from src.current_season_minutes_shadow_research import build as minutes_build
from src.rolling_decision_research import canonical_hash, player_games


def when(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))


class RateProspective(unittest.TestCase):
    def sample(self):
        original="2026-10-29T15:00:00Z"
        tip="2026-10-30T00:00:00Z"
        frozen_issue={
            "game_id":"g4","player_id":"p","team":"BOS",
            "game_utc":tip,"individual_lock_utc":"2026-10-29T23:30:00Z",
            "issued_at_utc":original,
            "min_if_play":30,"fp_per_minute_if_play":.5,
            "decomposed_fp_if_play":15,
        }
        frozen={
            "schema_version":1, "status":"research_only_not_deployed",
            "adopt_on_site":False,"unconditional_FP_enabled":False,
            "issued":[frozen_issue],
        }
        rows=[];final=[];first={}
        for i in range(3):
            gid="g"+str(i)
            utc="2026-10-%02dT00:00:00Z"%(25+i)
            rows.append({
                "id":"p","game_id":gid,"team":"BOS","played":True,
                "minutes":20+i,"fp":10+i,"utc":utc,
            })
            final.append({"id":gid,"utc":utc,"status":"final","home":"BOS","away":"NYK"})
            first[f"{gid}|p"]="2026-10-%02dT06:00:00Z"%(25+i)
        live={"schema_version":4,"rows":rows,"games":final}
        indexed,_=player_games(live,when("2026-10-29T15:04:00Z"))
        rolling={
            "schema_version":1,"status":"research_only_not_deployed",
            "adopt_on_site":False,
            "row_first_seen_at_utc":first,
            "row_hashes":{
                f"{gid}|{pid}":canonical_hash(row)
                for (gid,pid),row in indexed.items()},
        }
        evaluation={
            "status":"research_only_not_deployed",
            "adopt_on_site":False,
            "quality_gate":{"adopt_on_site":False},
            "frozen_minutes_issue_sha256":canonical_hash([frozen_issue]),
            "summary":{"played":0},
            "scored_played":[],
            "explicit_DNP_not_in_conditional_metrics":[],
            "UNKNOWN_unscored":[],
        }
        minutes=minutes_build(
            {},frozen,rolling,live,evaluation,when("2026-10-29T15:05:00Z"))
        self.assertEqual(minutes["summary"]["issued_total"],1)
        return [{},minutes,frozen,evaluation,live,rolling]

    def test_genuine_issued_variants_and_immutability(self):
        args=self.sample()
        issued=build(*args,when("2026-10-29T15:06:00Z"))
        self.assertEqual(issued["summary"]["issued_total"],1)
        self.assertFalse(issued["quality_gate"]["adopt_on_site"])
        row=issued["issued"][0]
        self.assertEqual(set(row["FP_variants_frozen_prelock"]),set(RATE_FIELDS))
        self.assertEqual(row["source_sample_n"],3)
        self.assertLess(row["current_fp_per_minute"],row["old_fp_per_minute"])
        self.assertEqual(row["FP_variants_frozen_prelock"][CONTROL],
                         args[1]["issued"][0]["challenger_decomposed_fp"])
        again=build(issued,*args[1:],when("2026-10-29T16:20:00Z"))
        self.assertEqual(issued["issued"],again["issued"])
        self.assertEqual(again["summary"]["new_issued_this_run"],0)

    def test_no_late_first_issue_backfill(self):
        args=self.sample()
        output=build(*args,when("2026-10-29T16:20:00Z"))
        self.assertEqual(output["summary"]["issued_total"],0)
        self.assertEqual(output["issue_QA"]["stale_original_issuance_no_retrospective_backfill"],1)

    def test_bad_row_hash_and_missing_preissue_fp_fail_closed(self):
        args=self.sample()
        args[5]["row_hashes"]["g1|p"]="f"*64
        with self.assertRaises(ValueError):
            build(*args,when("2026-10-29T15:06:00Z"))
        args=self.sample()
        args[4]["rows"][1]["fp"]=None
        with self.assertRaises(ValueError):
            build(*args,when("2026-10-29T15:06:00Z"))

    def test_no_post_original_firstseen_leak(self):
        args=self.sample()
        sample=args[1]["issued"][0]["source_played_rows_known_at_issue"]
        args[5]["row_first_seen_at_utc"]["g2|p"]="2026-10-29T15:02:00Z"
        with self.assertRaises(ValueError):
            source_fp_rows(args[1]["issued"][0],args[4],args[5],
                           when("2026-10-29T15:00:00Z"))
        self.assertEqual(sample[0]["game_id"],"g0")

    def test_immutable_source_and_postgame_scored_only(self):
        args=self.sample()
        first=build(*args,when("2026-10-29T15:06:00Z"))
        changed=deepcopy(args)
        changed[1]["issued"][0]["challenger_minutes"]=40
        with self.assertRaises(ValueError):
            build(first,*changed[1:],when("2026-10-29T15:10:00Z"))
        args[1]["observed"]=[{
            "game_id":"g4","player_id":"p","team":"BOS","position":"PG",
            "et_date":"2026-10-29","game_utc":"2026-10-30T00:00:00Z",
            "postgame_first_seen_at_utc":"2026-10-30T05:00:00Z",
            "actual_minutes":24,"actual_fp_reconstructed":12,
        }]
        with self.assertRaises(ValueError):
            build(first,*args[1:],when("2026-10-29T15:10:00Z"))
        outcome=build(first,*args[1:],when("2026-10-30T06:00:00Z"))
        self.assertEqual(outcome["summary"]["played_verified"],1)
        self.assertEqual(outcome["played_only_paired_metrics"]["played_scored"],1)
        self.assertFalse(outcome["quality_gate"]["adopt_on_site"])

    def test_unknown_and_literal_dnp_never_score_zero(self):
        args=self.sample()
        original=build(*args,when("2026-10-29T15:06:00Z"))
        args[3]["UNKNOWN_unscored"]=[{"game_id":"g4","player_id":"p"}]
        result=build(original,*args[1:],when("2026-10-30T06:00:00Z"))
        self.assertEqual(result["summary"]["UNKNOWN_not_imputed"],1)
        self.assertEqual(result["summary"]["played_verified"],0)
        self.assertEqual(result["played_only_paired_metrics"]["played_scored"],0)

    def test_one_publisher_and_read_only_science(self):
        root=Path(__file__).resolve().parent
        sync=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertEqual(sync.count("python -m src.current_season_fp_rate_shadow_research"),2)
        self.assertIn("data/current_season_fp_rate_shadow_research.json",sync)
        self.assertIn("test_current_season_fp_rate_shadow_research",sync)
        chunks=sync.split("python -m src.participation_cohort_research")
        self.assertEqual(len(chunks),3)
        for tail in chunks[1:]:
            a=tail.index("python -m src.current_season_minutes_shadow_research")
            b=tail.index("python -m src.current_season_fp_rate_shadow_research")
            self.assertLess(a,b)
        self.assertIsInstance(MODEL_HASH,str)


if __name__=="__main__":
    unittest.main()
