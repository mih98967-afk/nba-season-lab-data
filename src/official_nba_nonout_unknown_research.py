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
MAX_CASES = 200


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
    if (len(unknown) != selection.get("unknown_postgame_results")
            or len(unknown) > MAX_CASES
            or ledger.get("overall_selected_opportunity_coverage", {}).get(
                "outcome_UNKNOWN") != len(unknown)):
        raise ValueError("Ledger UNKNOWN denominator drift")
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
    if outkeys != set(out) or len(outkeys) != ledger.get("current_OUT_queue"):
        raise ValueError("Already-reviewed OUT evidence cohort is incomplete")
    return remaining, len(unknown), len(outkeys), dict(by_status), finals


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
    candidates, n_unknown, n_out, by_status, finals = eligible_cases(
        ledger, shadow, selection, existing, identity, live, explicit, now)
    if not candidates:
        raise ValueError("No NON-OUT unknown cohort")
    old = indexed(prior.get("records", []), "old non-OUT research")
    keys = {(r["game_id"], r["player_id"]) for r in candidates}
    if set(old) - keys:
        raise ValueError("Prior research contained deleted/fabricated player-games")
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
            "already_reviewed_official_OUT_excluded": n_out,
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
        },
        "by_first_issued_status": by_status,
        "by_independent_NBA_verdict": dict(counter),
        "source_error_classes_this_run": dict(failures),
        "qa": dict(qa),
        "records": outputs,
        "quality_gate": {
            "full_fantasy_game_day_roster_denominator_verified": False,
            "NBA_game_day_membership_is_prelock_club_tenure": False,
            "separate_official_inactive_is_ESPN_DNP_label": False,
            "UNKNOWN_as_zero_training_allowed": False,
            "population_p_play_calibrated": False,
            "unconditional_FP_enabled": False,
            "adopt_on_site": False,
        },
        "limitations": [
            "Original official-OUT queue stays in its own frozen evidence chain.",
            "Historical high-confidence NBA ID is not independent game-day club tenure.",
            "Official NBA athlete absent from game boxscore remains UNKNOWN, not DNP.",
            "Official NBA inactive/nonplay is separate postgame evidence, never ESPN label.",
            "Source availability and original observed timestamps are first-observed, not backfilled.",
            "Only 26 first-issued non-OUT unknown cases, not whole Sports.ru game-day roster.",
            "No p_play labels/model/Firestore/Hosting/prices/transfers are changed.",
        ],
    }


def run():
    now = datetime.now(timezone.utc)
    load = lambda file: json.loads((DATA / file).read_text(encoding="utf8"))
    path = DATA / "official_nba_nonout_unknown_research.json"
    old = load(path.name) if path.exists() else {}
    schedule, error = None, None
    try:
        schedule = fetch_public_json(SCHEDULE_URL)
    except (OSError, TimeoutError, ValueError, TypeError) as exc:
        error = type(exc).__name__
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
