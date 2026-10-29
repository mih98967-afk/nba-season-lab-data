"""Research-only second-stage NBA game-specific evidence for NON-OUT unknowns.

Original official-OUT unknowns have their own immutable source chain. This
work checks OTHER first-issued p_play unknowns, never substitutes game-day NBA
membership for pre-lock club tenure, and never promotes a separate NBA source
verdict into p_play or a Sports.ru DNP/zero. Missing player/weak ID/timeouts
stay UNKNOWN. First postgame observations and source hashes are append-only.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from src.sync import DATA
from src.official_nba_gameday_status_research import (
    STATUS, SCHEDULE_URL, BOX_PREFIX, MAX_GAMES, official_schedule,
    fixture_match, official_box, fetch_public_json, verdict, utc, stamp,
    digest,
)

NO_RESULT = "UNKNOWN"
SEPARATE = {"VERIFIED_GAME_DAY_INACTIVE", "VERIFIED_ACTIVE_NONPLAY"}
RETRY = timedelta(hours=24)
# Bound upstream network review by MAX_GAMES, never the number of genuine UNKNOWN rows.


def indexed(rows, name):
    if not isinstance(rows, list):
        raise ValueError("Missing " + name)
    index = {}
    for row in rows:
        key = (row["game_id"], row["player_id"])
        if key in index:
            raise ValueError("Duplicate " + name + " player-game")
        index[key] = row
    return index


def archive_verified_resolutions(prior, old, active_keys, shadow, now):
    """Move only newly ESPN-verified first issues to immutable source history.

    Never drop earlier independent NBA evidence or treat an NBA status,
    unavailable player, or absent boxscore row as a new p_play label.
    """
    forecasts = indexed(shadow.get("issued"), "original frozen first issues")
    labels = indexed(shadow.get("observations"), "independently verified p_play labels")
    past = prior.get("resolved_verified_history", [])
    if not isinstance(past, list):
        raise ValueError("Historical source archive is not a list")
    resolved = {}

    def evidence(source):
        key = (source.get("game_id"), source.get("player_id"))
        first = forecasts.get(key)
        observed = labels.get(key)
        if (key in active_keys or first is None or observed is None
                or source.get("team") != first.get("team")
                or source.get("game_utc") != first.get("tipoff_utc")
                or source.get("first_prediction_issued_at_utc") != first.get("issued_at_utc")
                or source.get("individual_lock_utc") != first.get("individual_lock_utc")
                or source.get("original_p_play_club_link") != first.get("club_link_evidence")
                or source.get("p_play_outcome_still_UNKNOWN") is not True
                or source.get("model_training_negative") is not False
                or source.get("adopt_on_site") is not False):
            raise ValueError("Prior UNKNOWN may not be removed without original verified label")
        y = observed.get("actual_played")
        expected = ("positive_minutes_verified_sportsru_fp" if y == 1 and type(y) is int
                    else "explicit_espn_didNotPlay_true" if y == 0 and type(y) is int
                    else None)
        seen = observed.get("source_first_observed_at_utc")
        if (expected is None or observed.get("label_provenance") != expected
                or observed.get("tipoff_utc") != first.get("tipoff_utc")
                or not isinstance(seen, str)
                or not utc(first["tipoff_utc"]) <= utc(seen) <= now):
            raise ValueError("Removed non-OUT case lacks separately verified ESPN outcome")
        if source.get("source_first_observed_at_utc") is not None:
            source_at = utc(source["source_first_observed_at_utc"])
            if not utc(first["tipoff_utc"]) <= source_at <= now:
                raise ValueError("Historical independent source observed outside game window")
        return observed

    for record in past:
        if not isinstance(record, dict) or not isinstance(record.get("source_case"), dict):
            raise ValueError("Malformed prior resolved-source archive")
        source = record["source_case"]
        key = (source.get("game_id"), source.get("player_id"))
        if key in resolved or key in old:
            raise ValueError("Historical resolved source duplicated or returned to active")
        label = evidence(source)
        if (record.get("source_case_sha256") != digest(source)
                or record.get("p_play_verified_actual_played") != label["actual_played"]
                or record.get("p_play_label_provenance") != label["label_provenance"]
                or record.get("p_play_source_first_observed_at_utc") !=
                   label["source_first_observed_at_utc"]
                or not isinstance(record.get("archived_after_verification_at_utc"), str)
                or not utc(label["source_first_observed_at_utc"]) <=
                    utc(record["archived_after_verification_at_utc"]) <= now):
            raise ValueError("Historical archived source or verified evidence was edited")
        resolved[key] = record

    newly_archived = 0
    for key in sorted(set(old) - active_keys):
        source = old[key]
        label = evidence(source)
        resolved[key] = {
            "source_case": source,
            "source_case_sha256": digest(source),
            "p_play_verified_actual_played": label["actual_played"],
            "p_play_label_provenance": label["label_provenance"],
            "p_play_source_first_observed_at_utc": label["source_first_observed_at_utc"],
            "archived_after_verification_at_utc": stamp(now),
        }
        newly_archived += 1
    return [resolved[key] for key in sorted(resolved)], newly_archived


def eligible_cases(ledger, shadow, selection, existing, identity, live, explicit, now):
    for name, item in (("ledger", ledger), ("p_play", shadow),
                       ("selection", selection), ("NBA prior OUT", existing),
                       ("explicit DNP", explicit)):
        if item.get("status") != STATUS or item.get("adopt_on_site") is not False:
            raise ValueError("Untrusted/deployable " + name)
    if (ledger.get("quality_gate", {}).get("training_from_UNKNOWN_allowed") is not False
            or existing.get("model_training_negative_allowed") is not False
            or shadow.get("population_brier_enabled") is not False):
        raise ValueError("Missing negative-label safeguards")
    unknown = indexed(ledger.get("unknown_cases"), "ledger UNKNOWN")
    # This is a full, dynamic cohort. A network review batch cap must not
    # discard UNKNOWN cases when more games become final.
    count = len(unknown)
    selected_count = selection.get("unknown_postgame_results")
    covered_count = ledger.get("overall_selected_opportunity_coverage", {}).get(
        "outcome_UNKNOWN")
    if count != selected_count:
        raise ValueError(
            f"UNKNOWN_COUNT_MISMATCH: ledger={count} selection={selected_count}")
    if count != covered_count:
        raise ValueError(
            f"LEDGER_SUMMARY_MISMATCH: ledger={count} coverage={covered_count}")
    predictions = indexed(shadow.get("issued"), "first issued")
    observations = indexed(shadow.get("observations"), "verified outcomes")
    finals = {g["id"]: g for g in live.get("games", [])
              if g.get("status") == "final"}
    checked = set(explicit.get("checked_final_game_ids") or [])
    if (len(finals) != sum(g.get("status") == "final" for g in live.get("games", []))
            or not checked.issubset(finals)):
        raise ValueError("Missing or repeated completed game")
    out = indexed(existing.get("records"), "official OUT reviewed")
    source_people = identity.get("players")
    if not isinstance(source_people, dict):
        raise ValueError("Identity source missing")
    all_high = [str(x["nba_id"]) for x in source_people.values()
                if x.get("confidence") == "high" and x.get("nba_id")]
    if len(all_high) != len(set(all_high)):
        raise ValueError("Repeated high-confidence NBA person")
    outkeys = set()
    remaining = []
    by_status = Counter()
    for key, row in sorted(unknown.items()):
        g = finals.get(key[0])
        p = predictions.get(key)
        if (row.get("outcome") != NO_RESULT or not row.get("original_label_still_UNKNOWN")
                or not row.get("new_evidence_not_promoted_to_training_label")
                or key in observations or g is None or key[0] not in checked
                or p is None or row["team"] != p["team"]
                or row["game_utc"] != g["utc"]
                or p["tipoff_utc"] != g["utc"]
                or p["team"] not in (g["home"], g["away"])
                or row["first_prediction_issued_at_utc"] != p["issued_at_utc"]
                or row["individual_lock_utc"] != p["individual_lock_utc"]
                or not (utc(p["issued_at_utc"]) <
                        utc(p["individual_lock_utc"]) <
                        utc(p["tipoff_utc"]) <= now)
                or (utc(p["tipoff_utc"]) - utc(p["individual_lock_utc"])).total_seconds() != 1800):
            raise ValueError("UNKNOWN row, team, first issue or source clock contradicted")
        status = row["official_status_first_known_by_issue"]
        if status == "out":
            outkeys.add(key)
            continue
        by_status[status] += 1
        meta = source_people.get(key[1]) or {}
        high = (meta.get("confidence") == "high"
                and str(meta.get("nba_id") or "").isdigit())
        remaining.append({
            "game_id": key[0], "player_id": key[1],
            "team": p["team"], "game_utc": p["tipoff_utc"],
            "first_prediction_issued_at_utc": p["issued_at_utc"],
            "individual_lock_utc": p["individual_lock_utc"],
            "original_p_play_club_link": p["club_link_evidence"],
            "official_status_first_known_asof_issue": status,
            "historical_identity_strength": meta.get("confidence") or "unresolved",
            "historical_nba_id_if_high": str(meta["nba_id"]) if high else None,
            "NBA_ID_method": meta.get("method"),
        })
    # The selected OUT/UNKNOWN cohort grows whenever more games are checked.
    # Independent official-NBA review is a *historical subset* of this cohort,
    # not a mandatory same-run prerequisite for reviewing NON-OUT cases.
    if len(outkeys) != ledger.get("current_OUT_queue"):
        raise ValueError("LEDGER_OUT_QUEUE_MISMATCH")
    if existing.get("original_OUT_unknown_queue") != len(out):
        raise ValueError("Historical official OUT source denominator changed")
    reviewed_current = outkeys & set(out)
    historical_reviewed = set(out) - outkeys
    for key, source in out.items():
        first = predictions.get(key)
        if (first is None
                or first.get("official_status_first_known_asof_issue") != "out"
                or source.get("team") != first.get("team")
                or source.get("game_utc") != first.get("tipoff_utc")
                or source.get("first_prediction_issued_at_utc") != first.get("issued_at_utc")
                or source.get("model_training_negative") is not False
                or source.get("p_play_shadow_untouched") is not True):
            raise ValueError("Independent OUT review conflicts with frozen first issue")
        if key in historical_reviewed:
            # A previously reviewed OUT row can leave today's UNKNOWN cohort
            # only after a separately evidenced ESPN/Sports.ru p_play label.
            label = observations.get(key)
            y = label.get("actual_played") if label else None
            expected = ("positive_minutes_verified_sportsru_fp"
                        if type(y) is int and y == 1 else
                        "explicit_espn_didNotPlay_true"
                        if type(y) is int and y == 0 else None)
            observed_at = label.get("source_first_observed_at_utc") if label else None
            if (expected is None
                    or label.get("label_provenance") != expected
                    or label.get("tipoff_utc") != first["tipoff_utc"]
                    or not isinstance(observed_at, str)
                    or not utc(first["tipoff_utc"]) <= utc(observed_at) <= now):
                raise ValueError("Historical OUT exited UNKNOWN without verified label")
    out_coverage = {
        "reviewed_current": len(reviewed_current),
        "pending_current": len(outkeys - reviewed_current),
        "historical_verified": len(historical_reviewed),
    }
    return remaining, len(unknown), len(outkeys), dict(by_status), finals, out_coverage


def build(ledger, shadow, selection, existing, identity, live, explicit,
          schedule_payload, fetch_box, now, previous=None, schedule_error=None,
          max_games=MAX_GAMES):
    if now.utcoffset() is None:
        raise ValueError("Naive research clock")
    now = now.astimezone(timezone.utc)
    if type(max_games) is not int or not 1 <= max_games <= MAX_GAMES:
        raise ValueError("Unbounded official boxscore fetch")
    prior = previous or {}
    if prior and (prior.get("schema_version") != 1 or
                  prior.get("status") != STATUS or
                  prior.get("adopt_on_site") is not False):
        raise ValueError("Prior research artifact is unsafe")
    candidates, n_unknown, n_out, by_status, finals, out_coverage = eligible_cases(
        ledger, shadow, selection, existing, identity, live, explicit, now)
    if not candidates:
        raise ValueError("No NON-OUT unknown cohort")
    old = indexed(prior.get("records", []), "old non-OUT research")
    keys = {(r["game_id"], r["player_id"]) for r in candidates}
    history, newly_resolved = archive_verified_resolutions(
        prior, old, keys, shadow, now)
    old_lock = {(r["game_id"], r["player_id"]): r for r in candidates}
    final = {}
    needs = defaultdict(list)
    qa = Counter()
    for c in candidates:
        key = c["game_id"], c["player_id"]
        previous_row = old.get(key)
        if previous_row:
            if any(previous_row.get(k) != v for k, v in c.items()):
                raise ValueError("Immutable original player/team/pregame evidence changed")
            if previous_row.get("p_play_outcome_still_UNKNOWN") is not True or (
                    previous_row.get("model_training_negative") is not False or
                    previous_row.get("adopt_on_site") is not False):
                raise ValueError("Old separate source illegally promoted a label")
            last_source = previous_row.get("source_first_observed_at_utc")
            if last_source:
                if not (utc(c["game_utc"]) <= utc(last_source) <= now):
                    raise ValueError("Old verified source was observed before tipoff")
                final[key] = previous_row
                qa["preserved_prior_game_specific_source"] += 1
                continue
            retried = previous_row.get("source_last_attempt_at_utc")
            if retried and utc(retried) <= now and now - utc(retried) < RETRY:
                final[key] = previous_row
                qa["deferred_source_retry_24h"] += 1
                continue
            if retried and utc(retried) > now:
                raise ValueError("Historical fetch attempt came from future")
        needs[c["game_id"]].append(c)
    schedule = None
    if schedule_payload is not None:
        schedule = official_schedule(schedule_payload)
    fetched = {}
    attempted = 0
    matched = 0
    failures = Counter()
    for gid in sorted(needs)[:max_games]:
        attempted += 1
        g = finals[gid]
        match, reason = ((None, "NBA_schedule_source_unavailable")
                         if schedule is None else fixture_match(g, schedule))
        if match is None:
            fetched[gid] = (None, reason, None, None)
            failures[reason] += 1
            continue
        matched += 1
        url = BOX_PREFIX + match["id"] + ".json"
        try:
            parsed = official_box(fetch_box(url), match, g)
            fetched[gid] = (parsed, None, match, url)
        except (OSError, TimeoutError, ValueError, KeyError, TypeError) as exc:
            fetched[gid] = (None, "NBA_boxscore_unavailable_or_invalid", match, url)
            failures[type(exc).__name__] += 1
    for c in candidates:
        key = c["game_id"], c["player_id"]
        if key in final:
            continue
        packed = fetched.get(c["game_id"])
        if packed is None:
            row = {**c, "independent_NBA_verdict": "UNKNOWN",
                   "why_unknown": "not_fetched_due_to_game_cap",
                   "source_last_attempt_at_utc": None,
                   "source_first_observed_at_utc": None,
                   "source_url": None, "source_game_id": None,
                   "source_canonical_sha256": None,
                   "official_game_day_team_membership_verified": False,
                   "conflict_requires_review": False}
            qa["pending_due_to_game_cap"] += 1
        else:
            source, reason, match, url = packed
            outcome, why, conflict = ("UNKNOWN", reason, False)
            has_member = False
            if source:
                outcome, why, conflict = verdict(
                    source["players"], c["team"],
                    c["historical_nba_id_if_high"], {})
                person = source["players"].get(
                    c["historical_nba_id_if_high"]) if c["historical_nba_id_if_high"] else None
                has_member = bool(person and person["team"] == c["team"])
            row = {
                **c, "independent_NBA_verdict": outcome,
                "why_unknown": why, "conflict_requires_review": conflict,
                "official_game_day_team_membership_verified": has_member,
                "source_last_attempt_at_utc": stamp(now),
                "source_first_observed_at_utc": stamp(now) if source else None,
                "source_url": url if source else None,
                "source_game_id": match["id"] if source else None,
                "source_canonical_sha256": source["canonical_source_sha256"] if source else None,
            }
        row.update({
            "p_play_outcome_still_UNKNOWN": True,
            "model_training_negative": False,
            "adopt_on_site": False,
        })
        final[key] = row
    outputs = [final[k] for k in sorted(final)]
    if len(outputs) != len(candidates):
        raise ValueError("Incomplete NON-OUT evidence denominator")
    counter = Counter(r["independent_NBA_verdict"] for r in outputs)
    verified_members = sum(r["official_game_day_team_membership_verified"] for r in outputs)
    verified_nonplay = sum(r["independent_NBA_verdict"] in SEPARATE for r in outputs)
    if any(r["p_play_outcome_still_UNKNOWN"] is not True or
           r["model_training_negative"] is not False for r in outputs):
        raise ValueError("Unintended p_play label promotion")
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "population": "first_issued_pplay_finished_checked_selected_UNKNOWN_non_OUT_only",
        "source": "NBA official game-specific two-team final boxscore; separate from ESPN didNotPlay",
        "source_schedule_url": SCHEDULE_URL,
        "summary": {
            "all_finished_p_play_UNKNOWN": n_unknown,
            "already_reviewed_official_OUT_excluded": out_coverage["reviewed_current"],
            "pending_official_OUT_independent_review_excluded": out_coverage["pending_current"],
            "total_official_OUT_UNKNOWN_excluded": n_out,
            "historical_official_OUT_now_independently_verified": out_coverage["historical_verified"],
            "new_non_OUT_review_cohort": len(candidates),
            "strong_historical_NBA_ID": sum(x["historical_nba_id_if_high"] is not None for x in candidates),
            "nonhigh_historical_NBA_ID": sum(x["historical_nba_id_if_high"] is None for x in candidates),
            "distinct_non_OUT_games": len({x["game_id"] for x in candidates}),
            "sources_successfully_observed_cases": sum(bool(x["source_first_observed_at_utc"]) for x in outputs),
            "game_day_team_membership_verified_separately": verified_members,
            "separate_NBA_inactive_or_nonplay_evidence_NOT_pplay_labels": verified_nonplay,
            "source_games_attempted_this_run": attempted,
            "source_games_matched_NBA_schedule": matched,
            "source_games_failed_this_run": sum(failures.values()),
            "source_games_pending_cap_this_run": max(0,len(needs)-max_games),
            "p_play_negative_labels_created": 0,
            "previous_non_OUT_cases_now_independently_ESPN_verified": newly_resolved,
            "historical_verified_resolution_source_records_preserved": len(history),
        },
        "by_first_issued_status": by_status,
        "by_independent_NBA_verdict": dict(counter),
        "source_error_classes_this_run": dict(failures),
        "qa": dict(qa),
        "records": outputs,
        "resolved_verified_history": history,
        "quality_gate": {
            "full_fantasy_game_day_roster_denominator_verified": False,
            "NBA_game_day_membership_is_prelock_club_tenure": False,
            "separate_official_inactive_is_ESPN_DNP_label": False,
            "UNKNOWN_as_zero_training_allowed": False,
            "verified_source_history_preserved": True,
            "pending_OUT_review_kept_UNKNOWN": True,
            "population_p_play_calibrated": False,
            "unconditional_FP_enabled": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "Original reviewed official-OUT queue stays frozen; new OUT cases remain UNKNOWN and pending independent review.",
            "Historical high-confidence NBA ID is not independent game-day club tenure.",
            "Official NBA athlete absent from game boxscore remains UNKNOWN, not DNP.",
            "Official NBA inactive/nonplay is separate postgame evidence, never ESPN label.",
            "Source availability and original observed timestamps are first-observed, not backfilled.",
            "The currently active non-OUT denominator is dynamic, while verified resolved source cases are retained immutably.",
            "No p_play labels/model/Firestore/Hosting/prices/transfers are changed.",
        ],
    }


def run(allow_network=True):
    now = datetime.now(timezone.utc)
    load = lambda file: json.loads((DATA / file).read_text(encoding="utf8"))
    path = DATA / "official_nba_nonout_unknown_research.json"
    old = load(path.name) if path.exists() else {}
    schedule, error = None, None
    if allow_network:
        try:
            schedule = fetch_public_json(SCHEDULE_URL)
        except (OSError, TimeoutError, ValueError, TypeError) as exc:
            error = type(exc).__name__
    else:
        error = "no_network_offline_validation"
    report = build(
        load("participation_evidence_ledger_research.json"),
        load("p_play_shadow_research.json"),
        load("p_play_selection_bias_audit.json"),
        load("official_nba_gameday_status_research.json"),
        load("identity.json"), load("live.json"),
        load("explicit_dnp_research.json"),
        schedule, fetch_public_json, now, old, schedule_error=error)
    if not old or {
        k:v for k,v in report.items() if k != "updated_at_utc"
    } != {
        k:v for k,v in old.items() if k != "updated_at_utc"
    }:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        temp.replace(path)
    return {"summary":report["summary"], "separate_source_only":True,
            "adopt_on_site":False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
