"""Auditable research-only participation-label coverage and independent evidence ledger.

The target is positive NBA minutes in a *specific* game, for the first-issued
Sports.ru candidate population, not "listed in ESPN". Selection is missing
not at random: official OUT and weak IDs have much higher UNKNOWN frequency.

No unknown is turned into DNP, not even if both ESPN and NBA live omit the
athlete, and no prior p_play labels, site, roster, cash or transfers are edited.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from src.rolling_decision_research import instant, stamp
from src.sync import DATA

STATUS = "research_only_not_deployed"
ET = ZoneInfo("America/New_York")
STRONG = "same_club_independent_ESPN_ID_observed"
WEAK = "same_club_unique_name_only_observed"
ALLOWED_LINK = {STRONG, WEAK}
ALLOWED_STATUS = {"out", "doubtful", "questionable", "probable",
                  "available", "no_observed_official_status"}
SEPARATE_NEGATIVE_EVIDENCE = {"VERIFIED_GAME_DAY_INACTIVE",
                              "VERIFIED_ACTIVE_NONPLAY",
                              "VERIFIED_OFFICIAL_NBA_INACTIVE_LIST"}


def _research(source, name):
    if (not isinstance(source, dict) or source.get("status") != STATUS
            or source.get("adopt_on_site") is not False):
        raise ValueError("Untrusted or deployable " + name)


def _index(items, name):
    if not isinstance(items, list):
        raise ValueError("Missing " + name + " rows")
    out = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Malformed " + name)
        key = (item.get("game_id"), item.get("player_id"))
        if (not all(isinstance(x, str) and x for x in key)
                or key in out):
            raise ValueError("Duplicate or invalid " + name + " player-game")
        out[key] = item
    return out


def _pct(n, denominator):
    return round(n / denominator, 6) if denominator else None


def _profile(records):
    c = Counter()
    for row in records:
        c["finished_checked"] += 1
        c[row["outcome"]] += 1
    n = c["finished_checked"]
    known = c["played"] + c["explicit_DNP"]
    return {
        "finished_checked": n, "verified_played": c["played"],
        "verified_explicit_DNP": c["explicit_DNP"],
        "outcome_UNKNOWN": c["UNKNOWN"],
        "unknown_fraction": _pct(c["UNKNOWN"], n),
        "verified_only_played_fraction": _pct(c["played"], known),
        "binary_positive_minutes_fraction_sensitivity_range": [
            _pct(c["played"], n), _pct(c["played"]+c["UNKNOWN"], n)],
        "interval_is_partial_identification_not_confidence_interval": True,
    }


def _after_game(value, game, now, source):
    if value is None:
        return
    observed = instant(value)
    if observed < instant(game["utc"]) or observed > now:
        raise ValueError(source + " has impossible first-observed postgame clock")


def build(shadow, selection, explicit, live, espn, nba_box, nba_inactive, now):
    if now.utcoffset() is None:
        raise ValueError("Clock needs timezone")
    now = now.astimezone(timezone.utc)
    for name, obj in (("pplay", shadow), ("selection", selection),
                      ("explicit", explicit), ("ESPN_OUT", espn),
                      ("NBA_gameday", nba_box), ("NBA_inactive", nba_inactive)):
        _research(obj, name)
    if (shadow.get("population_brier_enabled") is not False
            or selection.get("quality_gate", {}).get("unknown_are_not_DNP") is not True
            or espn.get("no_inferred_DNP_from_unlisted_athletes") is not True
            or nba_box.get("model_training_negative_allowed") is not False
            or nba_inactive.get("training_negatives_allowed") is not False):
        raise ValueError("Research safety flags were changed")
    issued = _index(shadow.get("issued"), "immutable_first_issue")
    observed = _index(shadow.get("observations"), "verified_postgame")
    checked = explicit.get("checked_final_game_ids")
    if not isinstance(checked, list) or len(checked) != len(set(checked)):
        raise ValueError("Invalid completed DNP-checked games")
    checked = set(checked)
    finals = {}
    for game in live.get("games", []):
        if game.get("status") != "final":
            continue
        if game["id"] in finals:
            raise ValueError("Duplicate final match")
        finals[game["id"]] = game
    if not checked.issubset(finals):
        raise ValueError("Source game coverage changed before evaluation")

    outqueue = _index(selection.get("out_status_missing_review_queue"), "selection_OUT_unknown")
    es = _index(espn.get("records"), "independent_ESPN_boxscore")
    nb = _index(nba_box.get("records"), "official_NBA_gameday")
    ina = _index(nba_inactive.get("records"), "NBA_stats_inactive")
    if any(key not in es for key in nb) or any(key not in nb for key in ina):
        raise ValueError("Official NBA evidence has no matched original ESPN review")

    finished = []
    unknown_cases = []
    source_totals = Counter()
    team_stats = defaultdict(list)
    status_stats = defaultdict(list)
    identity_stats = defaultdict(list)
    dates = set()
    for key, p in issued.items():
        at = instant(p["issued_at_utc"])
        lock = instant(p["individual_lock_utc"])
        tip = instant(p["tipoff_utc"])
        if not (at < lock < tip <= now and
                (tip-lock).total_seconds() == 1800):
            # Future predictions must still be before lock but the game may
            # not have started yet; never backdate a not-yet-played match.
            if not (at < lock < tip and at <= now and
                    (tip-lock).total_seconds() == 1800):
                raise ValueError("Invalid frozen first-issued prediction clock")
        if p.get("adopt_on_site") is not False:
            raise ValueError("Shadow forecast incorrectly deployable")
        if p.get("official_observed_at_issue"):
            if instant(p["official_observed_at_issue"]) > at:
                raise ValueError("Official status first observed after prediction")
        if p.get("club_link_evidence") not in ALLOWED_LINK:
            raise ValueError("Unsupported PIT roster identity evidence")
        if key[0] not in checked:
            continue
        game = finals[key[0]]
        if game["utc"] != p["tipoff_utc"] or p["team"] not in (
                game["home"], game["away"]):
            raise ValueError("Frozen player team/tipoff conflicts with final")
        if tip > now:
            raise ValueError("Future game in checked results")
        y = observed.get(key)
        outcome = "UNKNOWN"
        if y is not None:
            if (y.get("tipoff_utc") != p["tipoff_utc"]
                    or type(y.get("actual_played")) is not int
                    or y["actual_played"] not in (0, 1)
                    or y.get("label_provenance") != (
                        "positive_minutes_verified_sportsru_fp"
                        if y["actual_played"] == 1 else
                        "explicit_espn_didNotPlay_true")):
                raise ValueError("Unsupported prospective postgame outcome")
            _after_game(y.get("source_first_observed_at_utc"), game, now,
                        "Verified participation result")
            outcome = "played" if y["actual_played"] else "explicit_DNP"
        status = p.get("official_status_first_known_asof_issue") or "no_observed_official_status"
        if status not in ALLOWED_STATUS:
            raise ValueError("Unknown or changed first-issued official status")
        row = {"game_id": key[0], "player_id": key[1],
               "team": p["team"], "game_utc": game["utc"],
               "first_prediction_issued_at_utc": p["issued_at_utc"],
               "individual_lock_utc": p["individual_lock_utc"],
               "official_status_first_known_by_issue": status,
               "preissue_club_link_evidence": p["club_link_evidence"],
               "outcome": outcome}
        finished.append(row)
        team_stats[p["team"]].append(row)
        status_stats[status].append(row)
        identity_stats[p["club_link_evidence"]].append(row)
        dates.add(tip.astimezone(ET).date().isoformat())

        if outcome != "UNKNOWN":
            continue
        original, game_doc, inactive_doc = es.get(key), nb.get(key), ina.get(key)
        if key in outqueue and status != "out":
            raise ValueError("Official OUT queue conflicts with frozen issue")
        if key not in outqueue and original:
            # Historical #40 evidence can remain append-only if a new
            # source later verifies the outcome. Do not treat as new UNKNOWN.
            continue
        if original is not None:
            if (status != "out" or original["game_utc"] != game["utc"]
                    or original["first_prediction_issued_at_utc"] != p["issued_at_utc"]
                    or original["team"] != p["team"]
                    or original.get("model_training_negative") is not False
                    or not original.get("p_play_target_still_UNKNOWN_in_original_pipeline")):
                raise ValueError("Changed original OUT or inferred training negative")
            _after_game(original.get("first_observed_this_boxscore_at_utc"),
                        game, now, "Independent ESPN boxscore")
            source_totals["ESPN_full_boxscore_reviewed"] += 1
            if original.get("boxscore_athlete_verdict") == "ESPN_person_not_listed_in_two_team_boxscore":
                source_totals["ESPN_unlisted_not_a_DNP"] += 1
            if original.get("ESPN_explicit_DNP_by_person_id") is True:
                source_totals["ESPN_separate_literal_DNP_needs_reconciliation"] += 1
        if game_doc is not None:
            if (original is None or game_doc["game_utc"] != game["utc"]
                    or game_doc["team"] != p["team"]
                    or game_doc.get("p_play_shadow_untouched") is not True
                    or game_doc.get("model_training_negative") is not False):
                raise ValueError("Independent NBA boxscore not attached to same player-game")
            _after_game(game_doc.get("source_observed_at_utc"),game,now,
                        "NBA game-day boxscore")
            source_totals["NBA_live_boxscore_reviewed"] += 1
            if game_doc.get("outcome") in SEPARATE_NEGATIVE_EVIDENCE:
                source_totals["new_separate_NBA_evidence_not_label"] += 1
            if game_doc.get("why_unknown") == "NBA_person_absent_from_game_specific_roster":
                source_totals["NBA_live_unlisted_not_a_DNP"] += 1
            if game_doc.get("why_unknown") == "historical_NBA_ID_not_high_confidence":
                source_totals["NBA_ID_weak_or_unresolved"] += 1
        if inactive_doc is not None:
            if (game_doc is None or inactive_doc["game_utc"] != game["utc"]
                    or inactive_doc["team"] != p["team"]
                    or inactive_doc.get("model_training_negative") is not False):
                raise ValueError("NBA stats inactive summary not same player-game")
            _after_game(inactive_doc.get("source_first_observed_at_utc"),
                        game,now,"Official NBA InactivePlayers")
            source_totals["NBA_stats_inactive_attempted_cases"] += 1
            if inactive_doc.get("outcome") in SEPARATE_NEGATIVE_EVIDENCE:
                source_totals["new_separate_NBA_evidence_not_label"] += 1
            if inactive_doc.get("why_unknown") in ("TimeoutError", "HTTP_403",
                                                    "HTTP_429"):
                source_totals["NBA_stats_source_errors_by_case"] += 1
        unknown_cases.append({
            **row,
            "original_official_OUT_queue": key in outqueue,
            "ESPN_full_boxscore_outcome": (
                original.get("boxscore_athlete_verdict") if original else None),
            "ESPN_full_boxscore_first_observed_utc": (
                original.get("first_observed_this_boxscore_at_utc") if original else None),
            "NBA_live_outcome":game_doc.get("outcome") if game_doc else None,
            "NBA_live_unknown_reason":game_doc.get("why_unknown") if game_doc else None,
            "NBA_live_identity_strength":(
                game_doc.get("identity_NBA_ID_strength") if game_doc else None),
            "NBA_live_first_observed_utc":(
                game_doc.get("source_observed_at_utc") if game_doc else None),
            "NBA_stats_inactive_outcome":(
                inactive_doc.get("outcome") if inactive_doc else None),
            "NBA_stats_inactive_unknown_reason":(
                inactive_doc.get("why_unknown") if inactive_doc else None),
            "NBA_stats_inactive_first_observed_utc": (
                inactive_doc.get("source_first_observed_at_utc") if inactive_doc else None),
            "original_label_still_UNKNOWN":True,
            "new_evidence_not_promoted_to_training_label":True,
        })
    n_known = sum(r["outcome"] != "UNKNOWN" for r in finished)
    if (len(issued) != selection.get("total_issued_predictions")
            or len(finished) != selection.get("finished_checked")
            or n_known != selection.get("verified_postgame_results")
            or len(unknown_cases) != selection.get("unknown_postgame_results")):
        raise ValueError("Selection report is stale relative to first-issued labels")
    if len(outqueue) != selection.get("official_OUT_unknown_review_priority_count"):
        raise ValueError("Original OUT queue accounting changed")
    if {key for key in outqueue} != {
            (r["game_id"], r["player_id"]) for r in unknown_cases
            if r["official_status_first_known_by_issue"] == "out"}:
        raise ValueError("Missing/changed official OUT queue")
    checked_status = {}
    for status, rows in status_stats.items():
        p = _profile(rows)
        actual = selection.get("by_first_observed_official_status", {}).get(status)
        if not isinstance(actual, dict) or (
            p["finished_checked"] != actual.get("finished_checked")
            or p["verified_played"] != actual.get("verified_played", 0)
            or p["verified_explicit_DNP"] != actual.get("explicit_DNP", 0)
            or p["outcome_UNKNOWN"] != actual.get("outcome_UNKNOWN", 0)):
            raise ValueError("Status/label counts disagree with audited selection")
        checked_status[status] = p
    if set(checked_status) != set(selection.get("by_first_observed_official_status", {})):
        raise ValueError("Official status breakdown incomplete")
    all_profile = _profile(finished)
    out_prof = checked_status.get("out", _profile([]))
    no_prof = checked_status.get("no_observed_official_status", _profile([]))
    out_missing = out_prof["unknown_fraction"]
    no_missing = no_prof["unknown_fraction"]
    descriptive_ratio = (
        round(out_missing/no_missing, 4)
        if out_missing is not None and no_missing not in (None, 0) else None)
    return {
        "schema_version":1, "status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"updated_at_utc":stamp(now),
        "target":"positive_minutes_in_exact_NBA_game_on_frozen_fantasy_candidate_proxy",
        "population":"first_issued_prelock_sportsru_catalog_and_ESPN_roster_candidates_with_final_checked_games",
        "overall_selected_opportunity_coverage":all_profile,
        "issued_total_including_future":len(issued),
        "finished_checked_distinct_ET_dates":len(dates),
        "finished_checked_distinct_games":len({r["game_id"] for r in finished}),
        "by_first_issue_official_status":{
            k:checked_status[k] for k in sorted(checked_status)},
        "by_preissue_club_identity":{
            k:_profile(identity_stats[k]) for k in sorted(identity_stats)},
        "by_team":{
            k:_profile(team_stats[k]) for k in sorted(team_stats)},
        "missing_out_vs_no_observed_official_status_ratio_descriptive":
            descriptive_ratio,
        "case_count_from_prior_ESPN_full_boxscore":len(es),
        "case_count_from_NBA_game_day":len(nb),
        "case_count_from_NBA_stats_inactive":len(ina),
        "current_OUT_queue":len(outqueue),
        "current_OUT_reviewed_ESPN":sum(k in es for k in outqueue),
        "current_OUT_reviewed_NBA_live":sum(k in nb for k in outqueue),
        "current_OUT_attempted_NBA_stats":sum(k in ina for k in outqueue),
        "independent_source_coverage":dict(source_totals),
        "unknown_cases":unknown_cases,
        "latest_archived_source_update_utc":{
            "p_play_shadow":shadow.get("updated_at_utc"),
            "selection_bias":selection.get("updated_at_utc"),
            "ESPN_boxscore_review":espn.get("updated_at_utc"),
            "NBA_gameday":nba_box.get("updated_at_utc"),
            "NBA_stats_inactive":nba_inactive.get("updated_at_utc"),
        },
        "quality_gate":{
            "full_game_day_roster_denominator_verified":False,
            "full_population_p_play_quality_proven":False,
            "independent_negative_coverage_sufficient":False,
            "multiple_out_of_time_weeks_evaluated":len(dates)>7 and False,
            "KEEP_TRANSFER_value_proven":False,
            "adopt_on_site":False,
            "training_from_UNKNOWN_allowed":False,
            "no_inference_from_official_OUT_or_unlisted_athletes":True,
        },
        "interpretation":[
            "Missingness by injury status and cross-provider ID is descriptive, not causal.",
            "Even extreme binary sensitivity bounds are only for the selected issued cohort.",
            "An athlete absent from ESPN and NBA live is UNKNOWN, not a verified DNP.",
            "Stats.nba.com timeout is source unavailability, not an athlete status.",
            "Separate official inactive verification is NOT silently imported as ESPN DNP.",
            "Current ESPN team roster and Sports.ru catalog do not prove game-day membership.",
            "One or few ET dates cannot establish future-season calibration or transfer value.",
            "No private roster, Firestore, live model, Hosting, or transfers were changed.",
        ],
    }


def run():
    now = datetime.now(timezone.utc)
    def read(filename):
        return json.loads((DATA / filename).read_text(encoding="utf8"))
    report = build(
        read("p_play_shadow_research.json"),
        read("p_play_selection_bias_audit.json"),
        read("explicit_dnp_research.json"),
        read("live.json"),
        read("official_out_boxscore_evidence_research.json"),
        read("official_nba_gameday_status_research.json"),
        read("official_nba_inactive_summary_research.json"),
        now)
    target = DATA / "participation_evidence_ledger_research.json"
    previous = read(target.name) if target.exists() else {}
    if (not previous or
            {k:v for k,v in report.items() if k!="updated_at_utc"} !=
            {k:v for k,v in previous.items() if k!="updated_at_utc"}):
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2), encoding="utf8")
        temp.replace(target)
    return {
        "finished_checked":report["overall_selected_opportunity_coverage"]["finished_checked"],
        "unknown":report["overall_selected_opportunity_coverage"]["outcome_UNKNOWN"],
        "first_issue_ET_dates":report["finished_checked_distinct_ET_dates"],
        "OUT_queue":report["current_OUT_queue"],
        "proven_negative_reclassifications":0,
        "research_only":True,"adopt_on_site":False,
    }


if __name__ == "__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
