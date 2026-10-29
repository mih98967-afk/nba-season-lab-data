"""Git committed values may be used only at/after their actual commit."""
import unittest
from copy import deepcopy
from datetime import datetime

from src.rolling_decision_research import canonical_hash
from src.git_preversion_boxscore_proof_research import (
    build, _at, audit_nearlock_issuance, FIRST_SHA, LAST_SHA
)


def fixture():
    r={"game_id":"g1","player_id":"p","team":"BOS",
       "fp":14,"minutes":23,"utc":"2026-10-25T00:00:00Z"}
    def snapshot(sha,at,rows):
        return {"commit_sha":sha,"blob_sha":"a"*40,
                "committed_at_utc":at,
                "live":{"schema_version":4,
                        "updated_at_utc":at,
                        "rows":[{"game_id":x["game_id"],"id":x["player_id"],
                                 "team":x["team"],"fp":x["fp"],
                                 "minutes":x["minutes"],"utc":x["utc"],
                                 "played":True} for x in rows]}}
    one=snapshot(FIRST_SHA,"2026-10-25T18:00:00Z",[r])
    new={**r,"fp":17}
    two=snapshot("b"*40,"2026-10-27T18:00:00Z",[new])
    three=snapshot(LAST_SHA,"2026-10-29T18:10:00Z",[new])
    archive={"schema_version":1,"status":"research_only_not_deployed",
             "adopt_on_site":False,
             "first_version_archive_at_utc":"2026-10-29T18:09:35Z",
             "versions":{"g1|p":[{"row_sha256":canonical_hash(new)}]}}
    issue={
        "game_id":"g4","player_id":"p","team":"BOS",
        "original_frozen_issued_at_utc":"2026-10-26T00:00:00Z",
        "refresh_issued_at_utc":"2026-10-28T18:00:00Z",
        "individual_lock_utc":"2026-10-29T23:30:00Z",
        "source_current_played_rows_first_seen_before_refresh":[{
            "game_id":"g1","team":"BOS","game_utc":r["utc"],
            "row_first_seen_at_utc":"2026-10-25T18:00:00Z",
            "minutes":23,"fp_reconstructed":17,
            "rolling_row_sha256":canonical_hash(new),
        }],
    }
    issued={"status":"research_only_not_deployed","adopt_on_site":False,
            "issued":[issue]}
    return [one,two,three],archive,issued


class GitBeforeVersion(unittest.TestCase):
    def test_restores_exact_old_value_and_later_corrected_value(self):
        snapshots,anchor,issues=fixture()
        result=build(snapshots,anchor,issues)
        chain=result["versions"]["g1|p"]
        self.assertEqual([v["row"]["fp"] for v in chain],[14,17])
        self.assertIsNone(_at(chain,datetime.fromisoformat("2026-10-25T17:00:00+00:00")))
        self.assertEqual(_at(chain,datetime.fromisoformat("2026-10-26T18:00:00+00:00"))["row"]["fp"],14)
        self.assertEqual(_at(chain,datetime.fromisoformat("2026-10-28T18:00:00+00:00"))["row"]["fp"],17)
        self.assertEqual(result["summary"]["value_corrections_after_first_git_proof"],1)
        self.assertEqual(result["summary"]["first_row_version_archive_keys_exactly_reconciled"],1)
        self.assertEqual(result["previously_issued_refresh_evidence_audit"]["counts"]
                         ["all_sources_verified_by_preissue_git_commit"],1)

    def test_prospective_issue_before_correction_cannot_use_future_value(self):
        snapshots,anchor,issues=fixture()
        issue=issues["issued"][0]
        issue["refresh_issued_at_utc"]="2026-10-26T18:00:00Z"
        report=build(snapshots,anchor,issues)
        self.assertEqual(report["previously_issued_refresh_evidence_audit"]["counts"]
                         ["historical_git_value_conflict_require_manual_review"],1)

    def test_missing_precommit_snapshot_is_not_imputed_as_dnp(self):
        snapshots,anchor,issues=fixture()
        issue=issues["issued"][0]
        issue["refresh_issued_at_utc"]="2026-10-25T12:00:00Z"
        issue["original_frozen_issued_at_utc"]="2026-10-25T10:00:00Z"
        report=build(snapshots,anchor,issues)
        self.assertEqual(report["previously_issued_refresh_evidence_audit"]["counts"]
                         ["incomplete_preissue_git_proof"],1)
        self.assertEqual(report["previously_issued_refresh_evidence_audit"]["counts"]
                         ["input_not_proven_from_git_before_issue"],1)

    def test_invalid_anchor_and_nonmonotonic_evidence_block(self):
        snapshots,anchor,issues=fixture()
        anchor["versions"]["g1|p"][0]["row_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"reconcile"):
            build(snapshots,anchor,issues)
        snapshots,anchor,issues=fixture()
        snapshots[1]["committed_at_utc"]="2026-10-25T10:00:00Z"
        with self.assertRaisesRegex(ValueError,"strictly increasing"):
            build(snapshots,anchor,issues)

    def test_future_correction_tombstone_does_not_imply_dnp(self):
        snapshots,anchor,issues=fixture()
        report=build(snapshots,anchor,issues)
        chain=report["versions"]["g1|p"]
        removed=chain+[{"kind":"absent","observed_at_utc":"2026-10-29T19:00:00Z"}]
        self.assertIsNone(_at(removed,datetime.fromisoformat("2026-10-29T20:00:00+00:00")))

    def test_git_history_recovery_is_one_time_single_main_writer(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent
        yml=(root/".github/workflows/nba-sync.yml").read_text()
        self.assertIn("python -m src.git_preversion_boxscore_proof_research",yml)
        self.assertIn("data/git_preversion_boxscore_proof_research.json",yml)
        self.assertIn("test_git_preversion_boxscore_proof_research",yml)
        self.assertIn("git fetch --no-tags --shallow-since=",yml)
        self.assertNotIn("git push",Path(__file__).resolve().with_name(
            "src").joinpath("git_preversion_boxscore_proof_research.py").read_text())


if __name__=="__main__":
    unittest.main()
