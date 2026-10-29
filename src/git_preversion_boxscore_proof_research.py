"""Bounded, independently committed Git snapshots BEFORE the 29 Oct row-version archive.

Purpose: salvage provable earlier public NBA FP/min value versions from the
existing repository's immutable DATA commits. A Git commit's timestamp proves
the value was in THIS repository at commit time, NOT original ESPN availability.
Never backdate a prospective forecast or overwrite the post-PR119 archive.

Fixed public inputs:
  first rolling capture live-data commit: 9806309...
  first row-version archive data commit: d122587...
One-time main writer research artifact; no network API, no account data.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import subprocess

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, player_games, stamp

STATUS = "research_only_not_deployed"
FIRST_SHA = "9806309b9eaf6192a1550749a52e8f05b24fdd03"
LAST_SHA = "d1225876a20c176a15985e481d156c8e6a5754d6"
MAX_COMMITS = 160
FILE = "data/live.json"


def _git(*args):
    run = subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, cwd=Path(__file__).resolve().parents[1])
    return run.stdout.decode("utf8").strip()


def git_snapshots():
    """Only use Git ancestry, SHA objects and committer time; no invented clocks."""
    shas = _git("log", "--reverse", "--format=%H", LAST_SHA, "--", FILE).splitlines()
    if FIRST_SHA not in shas or not shas or shas[-1] != LAST_SHA:
        raise ValueError("Git history incomplete: first or fixed last snapshot absent")
    shas = shas[shas.index(FIRST_SHA):]
    if not 2 <= len(shas) <= MAX_COMMITS or len(set(shas)) != len(shas):
        raise ValueError("Unexpected or unbounded historical source commits")
    for sha in shas:
        date = _git("show", "-s", "--format=%cI", sha)
        blob = _git("rev-parse", sha+":"+FILE)
        raw = _git("show", sha+":"+FILE)
        yield {"commit_sha":sha,"committed_at_utc":stamp(instant(date)),
               "blob_sha":blob,"live":json.loads(raw)}


def _rows(snapshot):
    live = snapshot["live"]
    time = instant(snapshot["committed_at_utc"])
    if (not isinstance(snapshot["commit_sha"],str) or
            len(snapshot["commit_sha"]) != 40 or
            not isinstance(snapshot["blob_sha"],str) or
            len(snapshot["blob_sha"]) != 40 or
            live.get("schema_version") != 4 or
            instant(live["updated_at_utc"]) > time):
        raise ValueError("Historical Git snapshot invalid, unknown or future-dated")
    pairs, _ = player_games(live,time)
    if not pairs:
        raise ValueError("Empty or unavailable historical snapshot")
    rows={}
    for (gid,pid), row in pairs.items():
        if "|" in gid or "|" in pid:
            raise ValueError("Malformed player-game identity")
        rows[gid+"|"+pid]=row
    return rows


def _at(chain, cutoff):
    """Last immutable snapshot state: future corrections and removals never leak."""
    if cutoff.utcoffset() is None:
        raise ValueError("As-of lookup requires timezone")
    last=None
    for e in chain:
        observed=instant(e["observed_at_utc"])
        if observed > cutoff:
            break
        last=e
    if last is None or last["kind"] == "absent":
        return None
    if last["kind"] != "observed" or last["row_sha256"] != canonical_hash(last["row"]):
        raise ValueError("Git observed-value content or SHA was tampered with")
    return last


def audit_nearlock_issuance(report, issued):
    """Audit previously ISSUED data only. Does not issue or change forecasts."""
    counts=Counter()
    rows=[]
    for issue in issued:
        captured=instant(issue["refresh_issued_at_utc"])
        if (captured >= instant(issue["individual_lock_utc"]) or
                captured < instant(issue["original_frozen_issued_at_utc"])):
            raise ValueError("Invalid archived research-issue clock")
        evidence=[]
        for sample in issue["source_current_played_rows_first_seen_before_refresh"]:
            key=sample["game_id"]+"|"+issue["player_id"]
            event=_at(report["versions"].get(key,[]),captured)
            if event is None:
                evidence.append("not_proven_from_git_before_issue")
                counts["input_not_proven_from_git_before_issue"]+=1
                continue
            row=event["row"]
            if (row["game_id"] != sample["game_id"] or
                    row["player_id"] != issue["player_id"] or
                    row["team"] != sample["team"] or
                    row["utc"] != sample["game_utc"] or
                    row["fp"] != sample["fp_reconstructed"] or
                    row["minutes"] != sample["minutes"] or
                    event["row_sha256"] != sample["rolling_row_sha256"]):
                evidence.append("git_value_conflicts_with_frozen_issue")
                counts["input_conflicts_with_frozen_issue"]+=1
            else:
                evidence.append("matched_public_git_value_at_or_before_issue")
                counts["input_git_proved_asof_issuance"]+=1
        if not evidence:
            raise ValueError("Empty played features in archived prelock forecast")
        matched=sum(x == "matched_public_git_value_at_or_before_issue" for x in evidence)
        if matched==len(evidence):
            klass="all_sources_verified_by_preissue_git_commit"
        elif "git_value_conflicts_with_frozen_issue" in evidence:
            klass="historical_git_value_conflict_require_manual_review"
        else:
            klass="incomplete_preissue_git_proof"
        counts[klass]+=1
        rows.append({
            "game_id":issue["game_id"],"player_id":issue["player_id"],
            "refresh_issued_at_utc":issue["refresh_issued_at_utc"],
            "total_sources":len(evidence),"matched_git_sources":matched,
            "evidence_status":klass,
            "not_provider_publication_proof":True,
        })
    return {
        "issued_original_refreshes":len(rows),
        "counts":dict(counts),
        "per_issued_forecast":rows,
        "semantic":"Compare already frozen forecasts against public Git values committed BEFORE their genuine issue. No new/backdated forecasts.",
    }


def build(snapshots, first_archive, issued):
    if (first_archive.get("schema_version") != 1
            or first_archive.get("status") != STATUS
            or first_archive.get("adopt_on_site") is not False
            or not isinstance(first_archive.get("versions"),dict)
            or not isinstance(issued,dict)
            or issued.get("status") != STATUS
            or issued.get("adopt_on_site") is not False):
        raise ValueError("Untrusted public research sources")
    entries=list(snapshots)
    if not 2 <= len(entries) <= MAX_COMMITS:
        raise ValueError("Inadequate Git snapshot history")
    snapshots_out=[]
    prior={}
    versions={}
    prev_time=None
    total=Counter()
    for snapshot in entries:
        at=instant(snapshot["committed_at_utc"])
        if prev_time is not None and at <= prev_time:
            raise ValueError("Historical Git commit timestamps not strictly increasing")
        prev_time=at
        latest=_rows(snapshot)
        added=changed=removed=0
        sha=snapshot["commit_sha"]
        blob=snapshot["blob_sha"]
        for key in sorted(set(prior)|set(latest)):
            before=prior.get(key)
            after=latest.get(key)
            if after is None and before is not None:
                e={"observed_at_utc":stamp(at),"commit_sha":sha,
                   "live_blob_sha":blob,"kind":"absent",
                   "evidence":"not_present_in_this_git_snapshot_not_DNP"}
                versions.setdefault(key,[]).append(e)
                removed+=1
            elif after is not None and (before is None or canonical_hash(before)!=canonical_hash(after)):
                e={"observed_at_utc":stamp(at),"commit_sha":sha,
                   "live_blob_sha":blob,"kind":"observed",
                   "row":after,"row_sha256":canonical_hash(after)}
                versions.setdefault(key,[]).append(e)
                if before is None: added+=1
                else: changed+=1
        snapshots_out.append({
            "commit_sha":sha,"committed_at_utc":stamp(at),
            "live_updated_at_utc":snapshot["live"]["updated_at_utc"],
            "live_blob_sha":blob,"positive_player_games":len(latest),
            "new_positive_rows":added,"changed_positive_values":changed,
            "rows_disappeared_from_snapshot_NOT_DNP":removed,
        })
        total.update({"new_rows":added,"changed_values":changed,"disappeared":removed})
        prior=latest
    # Git snapshot anchoring: SAME original PR119 public values, not a
    # manufactured earlier source. PR119 first anchored at ~18:09:35.
    anchor={key:events[0] for key,events in first_archive["versions"].items()}
    if (set(anchor)!=set(prior)
            or any(row["row_sha256"]!=canonical_hash(prior[key])
                   for key,row in anchor.items())):
        raise ValueError("Historical Git tip does not reconcile with first row-version archive")
    if (entries[-1]["commit_sha"] != LAST_SHA
            or entries[0]["commit_sha"] != FIRST_SHA
            or instant(first_archive["first_version_archive_at_utc"]) >
               instant(entries[-1]["committed_at_utc"])):
        raise ValueError("Historical Git proof and fixed archive anchors differ")
    first_at=entries[0]["committed_at_utc"]
    report={
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,
        "research_type":"bounded_git_commit_evidence_before_first_row_version_archive",
        "fixed_first_git_sha":FIRST_SHA,"fixed_last_git_sha":LAST_SHA,
        "first_git_proof_at_utc":first_at,
        "last_git_proof_at_utc":entries[-1]["committed_at_utc"],
        "first_row_version_archive_at_utc":first_archive["first_version_archive_at_utc"],
        "snapshots":snapshots_out,
        "versions":dict(sorted(versions.items())),
        "summary":{
            "git_live_snapshots_recovered":len(snapshots_out),
            "unique_positive_player_game_keys":len(versions),
            "positive_value_versions_recovered":sum(
                sum(e["kind"]=="observed" for e in chain) for chain in versions.values()),
            "value_corrections_after_first_git_proof":total["changed_values"],
            "source_rows_disappeared_from_a_snapshot_NOT_DNP":total["disappeared"],
            "first_row_version_archive_keys_exactly_reconciled":len(prior),
            "all_original_git_commit_times_proven_not_provider_published":True,
        },
        "quality_gate":{
            "historical_commit_blobs_anchored_to_original_immutable_git_SHA":True,
            "source_value_first_proven_no_earlier_than_git_commit":True,
            "missing_git_snapshot_value_is_UNKNOWN_not_DNP":True,
            "pre_PR119_value_versions_never_inserted_into_original_archive":True,
            "can_backdate_an_existing_or_new_forecast":False,
            "can_claim_real_prelock_provider_published_time":False,
            "adopt_on_site":False,
        },
        "limitations":[
            "The Git commit SHA proves repository values at the COMMIT time, not the provider publication time.",
            "Only snapshots actually present in this bounded Git history can provide row-value evidence.",
            "Modifications between commits cannot be reconstructed.",
            "Missing row in a snapshot is NOT an explicit DNP or FP=0.",
            "Preissue model deployment and automatic transfer execution are forbidden.",
            "The 2024/25 and 2025/26 historical walk-forwards remain assumption-based, not true first-seen PIT.",
        ],
    }
    report["previously_issued_refresh_evidence_audit"]=audit_nearlock_issuance(
        report,issued.get("issued") or [])
    return report


def run():
    def read(p):return json.loads((DATA/p).read_text(encoding="utf8"))
    target=DATA/"git_preversion_boxscore_proof_research.json"
    if target.exists():
        previous=read(target.name)
        if (previous.get("status")!=STATUS or previous.get("adopt_on_site") is not False or
                previous.get("fixed_first_git_sha")!=FIRST_SHA or
                previous.get("fixed_last_git_sha")!=LAST_SHA):
            raise ValueError("Frozen Git recovery artifact modified")
        return {"already_frozen":True,"summary":previous["summary"],
                "previously_issued_refresh_evidence_audit":
                    previous["previously_issued_refresh_evidence_audit"]["counts"]}
    report=build(git_snapshots(), read("observed_boxscore_versions_research.json"),
                 read("current_season_prelock_refresh_research.json"))
    temp=target.with_suffix(".tmp")
    temp.write_text(json.dumps(report,ensure_ascii=False,separators=(",",":"))+"\n",
                    encoding="utf8")
    temp.replace(target)
    return {"already_frozen":False,"summary":report["summary"],
            "previously_issued_refresh_evidence_audit":
                report["previously_issued_refresh_evidence_audit"]["counts"]}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
