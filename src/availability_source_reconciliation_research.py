"""Read-only, strictly reconciled ledger of ALL first-issued p_play UNKNOWN sources.

Correlates an already-audited 27-case preissue-OUT queue with the 26
non-OUT source reviews, without backfilling/fabricating historical player
team tenure or promoting any separate NBA status into ESPN DNP. A complete
source fetch only proves a game-specific roster was examined: absence from
it is NOT verified player nonparticipation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re

from src.sync import DATA
from src.rolling_decision_research import instant, stamp

STATUS = "research_only_not_deployed"
ET = ZoneInfo("America/New_York")
SEPARATE_NONPLAY = {
    "VERIFIED_GAME_DAY_INACTIVE", "VERIFIED_ACTIVE_NONPLAY",
    "VERIFIED_OFFICIAL_NBA_INACTIVE_LIST",
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def ensure_research(obj, name):
    if (not isinstance(obj, dict) or obj.get("status") != STATUS
            or obj.get("adopt_on_site") is not False):
        raise ValueError(name + " not research-only")


def index(rows, name):
    if not isinstance(rows, list):
        raise ValueError(name + " records absent")
    output = {}
    for row in rows:
        key = row.get("game_id"), row.get("player_id")
        if (not all(isinstance(x, str) and x for x in key)
                or key in output):
            raise ValueError("Malformed/duplicate " + name)
        output[key] = row
    return output


def observed_after_tip(value, tipoff, now, name):
    if value is None:
        return False
    dt = instant(value)
    if not instant(tipoff) <= dt <= now:
        raise ValueError("Impossible source observation clock: " + name)
    return True


def source_class(verdict, why, conflict):
    if conflict:
        return "quarantine_cross_source_or_club_conflict"
    if verdict in SEPARATE_NONPLAY:
        return "separate_NBA_nonplay_needs_label_reconciliation"
    if verdict != "UNKNOWN":
        raise ValueError("Unrecognized official NBA verdict")
    if why == "NBA_person_absent_from_game_specific_roster":
        return "athlete_unlisted_in_NBA_game_box_NOT_DNP"
    if why == "historical_NBA_ID_not_high_confidence":
        return "unreliable_NBA_person_identity_NOT_DNP"
    if not why or any(token in why.lower() for token in (
            "unavailable", "timeout", "http", "invalid", "cap", "missing")):
        return "source_unavailable_or_undetermined_NOT_DNP"
    return "other_unresolved_NBA_source_NOT_DNP"


def build(ledger, nonout, nba_out, nba_inactive, selection, shadow, now):
    if now.utcoffset() is None:
        raise ValueError("Naive research time")
    now = now.astimezone(timezone.utc)
    for name,obj in (("ledger",ledger),("nonout",nonout),("nba_out",nba_out),
                     ("nba_inactive",nba_inactive),("selection",selection),
                     ("p_play",shadow)):
        ensure_research(obj,name)
    if (nonout.get("quality_gate",{}).get("UNKNOWN_as_zero_training_allowed") is not False
            or nonout.get("summary",{}).get("p_play_negative_labels_created") != 0
            or nba_out.get("model_training_negative_allowed") is not False
            or nba_inactive.get("training_negatives_allowed") is not False
            or ledger.get("quality_gate",{}).get("training_from_UNKNOWN_allowed") is not False
            or shadow.get("population_brier_enabled") is not False):
        raise ValueError("Negative-label or deployment safeguard compromised")
    pindex = index(shadow.get("issued"), "original frozen p_play issues")
    labels = index(shadow.get("observations"), "verified p_play labels")
    unknown = index(ledger.get("unknown_cases"), "finished unknown")
    out = index(nba_out.get("records"), "original official OUT")
    non = index(nonout.get("records"), "independent non-OUT")
    ina = index(nba_inactive.get("records"), "separate NBA inactive")
    out_keys = {key for key,row in unknown.items()
                if row.get("official_status_first_known_by_issue") == "out"}
    non_keys = set(unknown) - out_keys
    if (set(out) != out_keys or set(ina) != out_keys or set(non) != non_keys
            or out_keys & non_keys
            or len(unknown) != selection.get("unknown_postgame_results")
            or len(unknown) != ledger["overall_selected_opportunity_coverage"]["outcome_UNKNOWN"]
            or len(out_keys) != ledger.get("current_OUT_queue")
            or len(pindex) != selection.get("total_issued_predictions")
            or len(labels) != selection.get("verified_postgame_results")
            or len(pindex) != ledger.get("issued_total_including_future")
            or nonout["summary"]["all_finished_p_play_UNKNOWN"] != len(unknown)
            or nonout["summary"]["already_reviewed_official_OUT_excluded"] != len(out_keys)
            or nonout["summary"]["new_non_OUT_review_cohort"] != len(non_keys)):
        raise ValueError("Active unknown or frozen cohort accounting differs")
    records = []
    overall = Counter()
    by_status = defaultdict(Counter)
    by_et = defaultdict(Counter)
    by_preissue_link = defaultdict(Counter)
    for key in sorted(unknown):
        row = unknown[key]
        p = pindex.get(key)
        if p is None or key in labels:
            raise ValueError("Known/missing original p_play issue incorrectly UNKNOWN")
        tip = p["tipoff_utc"]
        issued = instant(p["issued_at_utc"])
        lock = instant(p["individual_lock_utc"])
        if (not (issued < lock < instant(tip) <= now)
                or (instant(tip)-lock).total_seconds() != 1800
                or row.get("outcome") != "UNKNOWN"
                or row.get("original_label_still_UNKNOWN") is not True
                or row.get("new_evidence_not_promoted_to_training_label") is not True
                or row.get("team") != p.get("team")
                or row.get("game_utc") != tip
                or row.get("first_prediction_issued_at_utc") != p["issued_at_utc"]
                or row.get("individual_lock_utc") != p["individual_lock_utc"]
                or row.get("preissue_club_link_evidence") != p.get("club_link_evidence")):
            raise ValueError("Mutated frozen issue, initial team or target")
        is_out = key in out_keys
        original = out[key] if is_out else non[key]
        if is_out:
            if (original.get("game_utc") != tip
                    or original.get("first_prediction_issued_at_utc") != p["issued_at_utc"]
                    or original.get("team") != p["team"]
                    or original.get("outcome") not in {"UNKNOWN"} | SEPARATE_NONPLAY
                    or original.get("model_training_negative") is not False
                    or original.get("p_play_shadow_untouched") is not True):
                raise ValueError("Original OUT official source changed")
            src_verdict = original["outcome"]
            src_why = original.get("why_unknown")
            conflict = original.get("conflict_requires_review") is True
            observed = original.get("source_observed_at_utc")
            src_sha = original.get("official_box_canonical_sha256")
            roster_member = original.get("game_day_team_membership_verified")
            if roster_member not in (True, False):
                raise ValueError("Malformed official OUT game-specific identity")
            inactive = ina[key]
            if (inactive.get("team") != p["team"]
                    or inactive.get("game_utc") != tip
                    or inactive.get("first_prediction_issued_at_utc") != p["issued_at_utc"]
                    or inactive.get("model_training_negative") is not False
                    or inactive.get("outcome") not in {"UNKNOWN"} | SEPARATE_NONPLAY
                    or inactive.get("separate_from_ESPN_didNotPlay") is not True):
                raise ValueError("NBA inactive status contradicts issued player-game")
            observed_after_tip(inactive.get("source_first_observed_at_utc"),
                               tip, now, "NBA Stats InactivePlayers")
            stats_reason = inactive.get("why_unknown")
            stats_verified = inactive["outcome"] in SEPARATE_NONPLAY
            if stats_verified and not inactive.get("matched_explicit_official_inactive"):
                raise ValueError("NBA inactive verified without explicit person row")
        else:
            if (original.get("game_utc") != tip
                    or original.get("first_prediction_issued_at_utc") != p["issued_at_utc"]
                    or original.get("individual_lock_utc") != p["individual_lock_utc"]
                    or original.get("team") != p["team"]
                    or original.get("original_p_play_club_link") != p["club_link_evidence"]
                    or original.get("official_status_first_known_asof_issue") !=
                       row["official_status_first_known_by_issue"]
                    or original.get("p_play_outcome_still_UNKNOWN") is not True
                    or original.get("model_training_negative") is not False
                    or original.get("adopt_on_site") is not False):
                raise ValueError("Independent non-OUT evidence is not first-issued")
            src_verdict = original["independent_NBA_verdict"]
            src_why = original.get("why_unknown")
            conflict = original.get("conflict_requires_review") is True
            observed = original.get("source_first_observed_at_utc")
            src_sha = original.get("source_canonical_sha256")
            roster_member = original.get("official_game_day_team_membership_verified")
            if roster_member not in (True, False):
                raise ValueError("Malformed non-OUT game-day membership")
            stats_verified = False
            stats_reason = "not_queried_for_non_OUT"
        sourced = observed_after_tip(observed, tip, now, "NBA official game-specific box")
        if sourced:
            if not isinstance(src_sha, str) or not SHA256.fullmatch(src_sha):
                raise ValueError("Claimed observed NBA source lacks SHA256")
        elif src_sha is not None:
            raise ValueError("Source fingerprint without verified observation")
        if src_verdict in SEPARATE_NONPLAY and not roster_member:
            raise ValueError("NBA nonplay requires game-specific matched same team athlete")
        if src_verdict == "UNKNOWN" and stats_verified and not is_out:
            raise ValueError("Inactive verification not attached to original OUT case")
        source_reason = source_class(src_verdict, src_why, conflict)
        et = instant(tip).astimezone(ET).date().isoformat()
        status = row["official_status_first_known_by_issue"]
        preissue_link = row["preissue_club_link_evidence"]
        overall[source_reason] += 1
        overall["source_game_observed"] += int(sourced)
        overall["game_day_member_verified"] += int(roster_member)
        overall["nba_stats_verified_separate_nonplay"] += int(stats_verified)
        overall["original_out"] += int(is_out)
        overall["non_out"] += int(not is_out)
        by_status[status][source_reason] += 1
        by_et[et][source_reason] += 1
        by_preissue_link[preissue_link][source_reason] += 1
        records.append({
            "game_id": key[0], "player_id": key[1], "team": p["team"],
            "ET_date": et, "game_utc": tip, "first_issued_at_utc": p["issued_at_utc"],
            "first_issue_official_status": status, "preissue_club_link": preissue_link,
            "source_branch": "official_OUT_independent" if is_out else "non_OUT_independent",
            "official_NBA_game_specific_verdict": src_verdict,
            "official_NBA_unknown_reason": src_why,
            "evidence_class_NOT_training_label": source_reason,
            "official_NBA_game_source_observed_at_utc": observed,
            "official_NBA_game_source_sha256": src_sha,
            "game_day_same_club_membership_verified": roster_member,
            "separate_NBA_stats_inactive_verdict": ina[key]["outcome"] if is_out else None,
            "NBA_stats_source_reason": stats_reason,
            "p_play_result_still_UNKNOWN": True,
            "training_negative_created": False,
        })
    if len(records) != len(unknown):
        raise ValueError("Incomplete evidence reconstruction")
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "target": "source_provenance_for_unlabelled_first_issued_pplay_cases",
        "population": "first_issued_finished_checked_UNKNOWN_selected_proxy_NOT_all_game_day_players",
        "source_branches": ["official_OUT_independent", "non_OUT_independent"],
        "summary": {
            "finished_checked": selection["finished_checked"],
            "verified_pplay_labels_untouched": len(labels),
            "UNKNOWN_checked": len(records),
            "OUT_branch": len(out_keys),
            "non_OUT_branch": len(non_keys),
            "game_specific_NBA_boxscore_observed": overall["source_game_observed"],
            "game_day_same_club_membership_verified": overall["game_day_member_verified"],
            "separate_NBA_stats_explicit_inactive_not_promoted": overall["nba_stats_verified_separate_nonplay"],
            "new_pplay_DNP_labels": 0,
            "source_class_counts": {
                key: count for key,count in sorted(overall.items())
                if key not in {"source_game_observed", "game_day_member_verified",
                               "nba_stats_verified_separate_nonplay", "original_out", "non_out"}},
            "distinct_ET_dates_with_UNKNOWN": len(by_et),
        },
        "by_first_issued_official_status": {
            k:dict(v) for k,v in sorted(by_status.items())},
        "by_ET_date": {k:dict(v) for k,v in sorted(by_et.items())},
        "by_preissue_club_identity": {
            k:dict(v) for k,v in sorted(by_preissue_link.items())},
        "case_records": records,
        "quality_gate": {
            "game_day_roster_denominator_validated": False,
            "source_observed_is_not_game_day_player_membership": True,
            "historical_ID_is_not_pregame_club_tenure": True,
            "NBA_inactive_is_not_automatically_ESPN_DNP": True,
            "unconditional_pplay_calibrated": False,
            "can_train_UNKNOWN_as_zero": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "All currently unresolved 53 first-issued cases are source-triaged only, not labelled.",
            "NBA boxscore successfully fetched does not show unlisted athlete belongs to team.",
            "26 non-OUT rows and 27 OUT rows are mutually exclusive frozen review cohorts.",
            "Actual NBA Stats endpoint remains unavailable if retrieval times out.",
            "Historical NBA ID can be strong even when game-day same-team roster lacks person.",
            "This is selected first-issued opportunities, NOT denominator for all roster choices.",
            "No Firestore, site model, Sports.ru credited FP, private roster or transfers changed.",
        ],
    }


def run():
    now = datetime.now(timezone.utc)
    read = lambda name:json.loads((DATA/name).read_text(encoding="utf8"))
    report = build(
        read("participation_evidence_ledger_research.json"),
        read("official_nba_nonout_unknown_research.json"),
        read("official_nba_gameday_status_research.json"),
        read("official_nba_inactive_summary_research.json"),
        read("p_play_selection_bias_audit.json"),
        read("p_play_shadow_research.json"), now)
    target = DATA/"availability_source_reconciliation_research.json"
    old = read(target.name) if target.exists() else {}
    if not old or {k:v for k,v in report.items() if k!="updated_at_utc"} != {
            k:v for k,v in old.items() if k!="updated_at_utc"}:
        tmp=target.with_suffix(".tmp")
        tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(target)
    return {**report["summary"],"research_only":True,"adopt_on_site":False}

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
