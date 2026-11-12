"""Prospective, research-only 2026/27 minutes form challenger.

A new challenger is issued ONLY alongside a genuinely fresh immutable 2025/26
minutes forecast, before the individual T-30 lock. It blends that historical
minutes forecast with verified same-team current-season played minutes whose
*actual first-observed timestamps* predate the original frozen issuance. It never
reconstructs what was known at an old issue time or treats absence as DNP.

The unoptimized 5-game prior strength is an exploratory choice made after early
2026/27 results: all comparisons are exploratory until tested on later dates.
No population P(play), unconditional FP, personal prices, transfers or deploy.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import json

from src.sync import DATA
from src.rolling_decision_research import instant, stamp, canonical_hash

STATUS = "research_only_not_deployed"
MODEL = {
    "name": "current_season_minutes_shrunk_to_frozen_2025_26_v1",
    "min_current_same_club_played_games": 3,
    "max_recent_current_played_games": 5,
    "frozen_prior_strength_in_games": 5,
    "max_baseline_to_challenger_issue_lag_seconds": 1200,
    "prospective_only_after_model_creation": True,
    "model_selection_on_2026_27_outcomes": False,
    "negative_labels_from_missing_allowed": False,
}
MODEL_HASH = canonical_hash(MODEL)


def number(x):
    if type(x) not in (int, float) or not isfinite(x):
        raise ValueError("Nonfinite minutes or FP in challenger source")
    return float(x)


def unique(rows, name):
    if not isinstance(rows, list):
        raise ValueError("Invalid " + name)
    result = {}
    for row in rows:
        key = (row.get("game_id"), row.get("player_id"))
        if not all(isinstance(v, str) and v for v in key) or key in result:
            raise ValueError("Duplicate or malformed " + name)
        result[key] = row
    return result


def source_rows(live, rolling, now):
    """Only first-observed positive minutes in verified final game, same club."""
    if (live.get("schema_version") != 4
            or rolling.get("schema_version") != 1
            or rolling.get("adopt_on_site") is not False):
        raise ValueError("Unverified public or rolling source")
    first = rolling.get("row_first_seen_at_utc")
    if not isinstance(first, dict):
        raise ValueError("Missing real as-of timestamps")
    finals = {g["id"]: g for g in live.get("games", [])
              if isinstance(g, dict) and g.get("status") == "final"}
    if len(finals) != sum(g.get("status") == "final" for g in live.get("games", [])):
        raise ValueError("Duplicated final game")
    observed = defaultdict(list)
    keys = set()
    for row in live.get("rows", []):
        if row.get("played") is not True:
            continue
        game_id, player_id = row.get("game_id"), row.get("id")
        if not all(isinstance(v, str) and v for v in (game_id, player_id)):
            raise ValueError("Played row missing identity")
        key = (game_id, player_id)
        if key in keys:
            raise ValueError("Duplicate played source row")
        keys.add(key)
        game = finals.get(game_id)
        if game is None or row.get("utc") != game.get("utc"):
            raise ValueError("Played row not verified against completed fixture")
        if row.get("team") not in (game.get("home"), game.get("away")):
            raise ValueError("Played team not on completed fixture")
        mins = number(row.get("minutes"))
        if not 0 < mins <= 70:
            raise ValueError("Invalid positive played minutes")
        seen_str = first.get(f"{game_id}|{player_id}")
        if seen_str is None:
            continue  # Cannot pretend we knew a row at its tipoff.
        seen, tip = instant(seen_str), instant(game["utc"])
        if seen < tip:
            raise ValueError("Rolling first-seen predates played game's tipoff")
        if seen > now:
            continue
        observed[player_id, row["team"]].append({
            "game_id": game_id, "game_utc": stamp(tip),
            "first_seen_at_utc": stamp(seen),
            "minutes": mins,
        })
    for rows in observed.values():
        rows.sort(key=lambda r: (r["game_utc"], r["game_id"]))
    return observed


def metrics(rows):
    if not rows:
        return {"played_scored": 0}
    n = len(rows)
    def stats(base, candidate, actual):
        eb = [number(r[base])-number(r[actual]) for r in rows]
        ec = [number(r[candidate])-number(r[actual]) for r in rows]
        return {
            "baseline_MAE": round(sum(abs(x) for x in eb)/n, 4),
            "challenger_MAE": round(sum(abs(x) for x in ec)/n, 4),
            "baseline_prediction_minus_actual_bias": round(sum(eb)/n, 4),
            "challenger_prediction_minus_actual_bias": round(sum(ec)/n, 4),
            "paired_MAE_gain_positive_favors_challenger": round(
                sum(abs(x)-abs(y) for x,y in zip(eb,ec))/n, 4),
        }
    return {
        "played_scored": n,
        "minutes": stats("baseline_minutes", "challenger_minutes", "actual_minutes"),
        "reconstructed_FP_given_played": stats(
            "baseline_decomposed_fp", "challenger_decomposed_fp",
            "actual_fp_reconstructed"),
    }



def _revision_proof(first, previous_effective, latest, history, now):
    """Only allow changed numeric played results with genuinely archived versions.

    Preserve the original observed outcome. Prove both the preceding and the
    corrected NBA row values against immutable independent capture timestamps.
    """
    fields = ("game_id", "player_id", "et_date", "team", "position",
              "postgame_first_seen_at_utc", "label_source")
    if any(latest[k] != first[k] for k in fields):
        raise ValueError("Revised player-game identity or postgame clock changed")
    if not isinstance(history, list) or len(history) < 2:
        raise ValueError("Changed played outcome has no independent value-version history")
    def matches(version, outcome):
        row = version.get("row", {})
        return (row.get("game_id") == first["game_id"]
                and row.get("player_id") == first["player_id"]
                and row.get("team") == first["team"]
                and number(row.get("minutes")) == number(outcome["actual_minutes"])
                and number(row.get("fp")) == number(outcome["actual_fp_reconstructed"])
                and canonical_hash(row) == version.get("row_sha256"))
    newest = history[-1]
    clock = instant(newest["version_observed_at_utc"])
    if (clock > now or clock < instant(first["postgame_first_seen_at_utc"])
            or not matches(newest, latest)):
        raise ValueError("Updated played outcome does not match a verified later source row")
    previous_versions = [v for v in history[:-1]
                         if instant(v["version_observed_at_utc"]) < clock
                         and matches(v, previous_effective)]
    if not previous_versions:
        raise ValueError("Previous independently observed played value was not archived")
    previous_version = previous_versions[-1]
    return {
        "game_id": first["game_id"], "player_id": first["player_id"],
        "original_outcome_sha256": canonical_hash(first),
        "previous_actual_minutes": number(previous_effective["actual_minutes"]),
        "previous_actual_fp_reconstructed": number(previous_effective["actual_fp_reconstructed"]),
        "latest_actual_minutes": number(latest["actual_minutes"]),
        "latest_actual_fp_reconstructed": number(latest["actual_fp_reconstructed"]),
        "previous_row_sha256": previous_version["row_sha256"],
        "previous_version_observed_at_utc": previous_version["version_observed_at_utc"],
        "latest_row_sha256": newest["row_sha256"],
        "latest_version_observed_at_utc": newest["version_observed_at_utc"],
        "adopt_on_site": False,
    }


def _check_archived_revisions(rows, original_issues, original_outcomes, versions, now):
    if not isinstance(rows, list):
        raise ValueError("Invalid played-revision archive")
    if rows and not isinstance(versions, dict):
        raise ValueError("Archived revisions lost their source version archive")
    grouped = defaultdict(list)
    for row in rows:
        key = (row.get("game_id"), row.get("player_id"))
        if key not in original_issues or key not in original_outcomes:
            raise ValueError("Orphan corrected player-game outcome")
        first = original_outcomes[key]
        old = grouped[key][-1] if grouped[key] else None
        prior = dict(first,
                     actual_minutes=old["latest_actual_minutes"] if old else first["actual_minutes"],
                     actual_fp_reconstructed=old["latest_actual_fp_reconstructed"] if old else first["actual_fp_reconstructed"])
        latest = dict(first, actual_minutes=row["latest_actual_minutes"],
                      actual_fp_reconstructed=row["latest_actual_fp_reconstructed"])
        history = versions.get(key[0]+"|"+key[1], [])
        matching = [i for i,v in enumerate(history)
                    if v.get("row_sha256") == row.get("latest_row_sha256")
                    and v.get("version_observed_at_utc") == row.get("latest_version_observed_at_utc")]
        if len(matching) != 1:
            raise ValueError("Previously sealed boxscore correction version disappeared")
        proof = _revision_proof(first, prior, latest, history[:matching[0]+1], now)
        if proof != row:
            raise ValueError("Previously sealed played correction was modified")
        if old and instant(row["latest_version_observed_at_utc"]) <= instant(old["latest_version_observed_at_utc"]):
            raise ValueError("Played source revisions must increase in real observed time")
        grouped[key].append(row)
    return grouped


def build(previous, frozen, rolling, live, evaluation, now, source_versions=None):
    if now.utcoffset() is None:
        raise ValueError("Research challenger requires timezone-aware now")
    now = now.astimezone(timezone.utc)
    if (frozen.get("schema_version") != 1
            or frozen.get("status") != STATUS
            or frozen.get("adopt_on_site") is not False
            or frozen.get("unconditional_FP_enabled") is not False
            or evaluation.get("status") != STATUS
            or evaluation.get("adopt_on_site") is not False
            or evaluation.get("quality_gate", {}).get("adopt_on_site") is not False):
        raise ValueError("Source deployed or not a frozen played-only research model")
    original = unique(frozen.get("issued"), "original frozen minutes issues")
    expected_source_hash = canonical_hash(frozen["issued"])
    if (evaluation.get("frozen_minutes_issue_sha256") != expected_source_hash
            or len(evaluation.get("scored_played", [])) !=
            evaluation.get("summary", {}).get("played")):
        raise ValueError("Minutes source and independently verified played evaluation disagree")
    scored = unique(evaluation["scored_played"], "independent played results")
    literal_dnp = unique(evaluation.get("explicit_DNP_not_in_conditional_metrics", []),
                         "verified DNP exclusions")
    unknown = unique(evaluation.get("UNKNOWN_unscored", []), "genuinely UNKNOWN")
    if set(scored) & set(literal_dnp) or set(scored) & set(unknown) or set(literal_dnp) & set(unknown):
        raise ValueError("One player-game assigned multiple labels")
    if previous:
        if (previous.get("schema_version") != 1
                or previous.get("status") != STATUS
                or previous.get("adopt_on_site") is not False
                or previous.get("model_sha256") != MODEL_HASH):
            raise ValueError("Challenger archive version changed")
    old_issued = unique((previous or {}).get("issued", []), "archived challenger issues")
    old_outcomes = unique((previous or {}).get("observed", []), "archived challenger outcomes")
    if not set(old_outcomes).issubset(old_issued):
        raise ValueError("Orphan challenger outcome")
    for key, item in old_issued.items():
        original_item = original.get(key)
        if (original_item is None
                or item.get("model_sha256") != MODEL_HASH
                or item.get("original_minutes_issue_sha256") != canonical_hash(original_item)
                or item.get("adopt_on_site") is not False
                or item.get("source_all_current_minutes_first_seen_pre_issue") is not True):
            raise ValueError("Immutable prelock challenger issue was changed")
        issued, base, lock = [instant(item[k]) for k in
                              ("challenger_issued_at_utc", "original_minutes_issued_at_utc",
                               "individual_lock_utc")]
        if (not base <= issued < lock
                or not 0 <= (issued-base).total_seconds() <=
                MODEL["max_baseline_to_challenger_issue_lag_seconds"]):
            raise ValueError("Challenger was backdated or moved past lock")
    new = []
    qa = Counter()
    by_player = source_rows(live, rolling, now)
    for key, base in sorted(original.items()):
        if key in old_issued:
            qa["existing_unchanged"] += 1
            continue
        tip, lock, initial = [instant(base[k]) for k in
                               ("game_utc", "individual_lock_utc", "issued_at_utc")]
        if (tip-lock).total_seconds() != 1800 or initial >= lock:
            raise ValueError("Frozen original issue violates individual lock")
        lag = (now-initial).total_seconds()
        if lag < 0:
            qa["original_issue_in_future_no_backdate"] += 1
            continue
        if now >= lock or now >= tip:
            qa["original_issue_no_longer_prelock"] += 1
            continue
        if lag > MODEL["max_baseline_to_challenger_issue_lag_seconds"]:
            qa["original_issue_stale_over_20_minutes_no_backfill"] += 1
            continue
        qa["fresh_original_prelock_issues"] += 1
        prior_mins = number(base["min_if_play"])
        rate = number(base["fp_per_minute_if_play"])
        if not 0 <= prior_mins <= 70:
            raise ValueError("Invalid frozen 2025/26 minute forecast")
        candidates = [r for r in by_player.get((base["player_id"],base["team"]), [])
                      if instant(r["first_seen_at_utc"]) <= initial
                      and instant(r["game_utc"]) < initial]
        sample = candidates[-MODEL["max_recent_current_played_games"]:]
        if len(sample) < MODEL["min_current_same_club_played_games"]:
            qa["insufficient_current_same_team_verified_played_form"] += 1
            continue
        qa["fresh_original_issues_with_sufficient_same_team_form"] += 1
        n = len(sample)
        fresh = sum(r["minutes"] for r in sample)/n
        strength = MODEL["frozen_prior_strength_in_games"]
        combined = (strength*prior_mins+n*fresh)/(strength+n)
        item = {
            "game_id": key[0], "player_id": key[1],
            "team": base["team"], "game_utc": base["game_utc"],
            "individual_lock_utc": base["individual_lock_utc"],
            "original_minutes_issued_at_utc": base["issued_at_utc"],
            "challenger_issued_at_utc": stamp(now),
            "model_sha256": MODEL_HASH,
            "original_minutes_issue_sha256": canonical_hash(base),
            "baseline_minutes": prior_mins,
            "baseline_decomposed_fp": number(base["decomposed_fp_if_play"]),
            "historical_rate_used_unchanged": rate,
            "current_same_team_played_n": n,
            "current_minutes_mean": round(fresh, 6),
            "source_played_rows_known_at_issue": sample,
            "source_asof_sha256": canonical_hash(sample),
            "challenger_minutes": round(combined, 5),
            "challenger_decomposed_fp": round(combined*rate, 5),
            "source_all_current_minutes_first_seen_pre_issue": True,
            "posthoc_exploratory_model_not_pre_registered_before_season": True,
            "outcome_at_issue": "UNKNOWN",
            "unconditional_FP_allowed": False,
            "model_training_negative": False,
            "adopt_on_site": False,
        }
        old_issued[key] = item
        new.append(item)
        qa["new_genuinely_prelock_challengers"] += 1
    versions = None
    if source_versions is not None:
        if (source_versions.get("schema_version") != 1
                or source_versions.get("status") != STATUS
                or source_versions.get("adopt_on_site") is not False
                or not isinstance(source_versions.get("versions"), dict)):
            raise ValueError("No authenticated boxscore value-version source")
        versions = source_versions["versions"]
    revisions = list((previous or {}).get("observed_corrections", []))
    grouped_revisions = _check_archived_revisions(
        revisions, old_issued, old_outcomes, versions, now)
    new_outcomes = dict(old_outcomes)
    for key, row in scored.items():
        issue = old_issued.get(key)
        if issue is None:
            continue
        tip = instant(issue["game_utc"])
        seen = instant(row["postgame_first_seen_at_utc"])
        if (row.get("team") != issue["team"]
                or row.get("game_utc") != issue["game_utc"]
                or seen < tip or seen > now
                or seen < instant(issue["challenger_issued_at_utc"])
                or number(row["actual_minutes"]) <= 0):
            raise ValueError("Played outcome fails identity or after-issue source clock")
        outcome = {
            "game_id": key[0], "player_id": key[1],
            "et_date": row["et_date"], "team": issue["team"],
            "position": row["position"],
            "actual_minutes": number(row["actual_minutes"]),
            "actual_fp_reconstructed": number(row["actual_fp_reconstructed"]),
            "postgame_first_seen_at_utc": row["postgame_first_seen_at_utc"],
            "baseline_minutes": issue["baseline_minutes"],
            "challenger_minutes": issue["challenger_minutes"],
            "baseline_decomposed_fp": issue["baseline_decomposed_fp"],
            "challenger_decomposed_fp": issue["challenger_decomposed_fp"],
            "model_sha256": MODEL_HASH,
            "label_source": "positive_minutes_verified_sportsru_fp",
        }
        original_outcome = new_outcomes.get(key)
        if original_outcome is None:
            new_outcomes[key] = outcome
            continue
        past = grouped_revisions.get(key, [])
        effective = (dict(original_outcome,
            actual_minutes=past[-1]["latest_actual_minutes"],
            actual_fp_reconstructed=past[-1]["latest_actual_fp_reconstructed"])
            if past else original_outcome)
        if effective == outcome:
            continue
        if versions is None:
            raise ValueError("Changed played outcome lacks verified source versions")
        proof = _revision_proof(
            original_outcome, effective, outcome, versions.get(key[0]+"|"+key[1]), now)
        if past and instant(proof["latest_version_observed_at_utc"]) <= instant(past[-1]["latest_version_observed_at_utc"]):
            raise ValueError("Played revision is not a newly observed version")
        revisions.append(proof)
        grouped_revisions.setdefault(key, []).append(proof)
    for key in old_outcomes:
        if key not in scored:
            raise ValueError("Previously verified challenger outcome disappeared")
    all_issued = sorted(old_issued.values(), key=lambda r: (
        r["game_utc"], r["game_id"], r["player_id"]))
    all_observed = sorted(new_outcomes.values(), key=lambda r: (
        r["et_date"], r["game_id"], r["player_id"]))
    per_date = defaultdict(list)
    for row in all_observed:
        per_date[row["et_date"]].append(row)
    n_dnp = len(set(old_issued) & set(literal_dnp))
    n_unknown = len(set(old_issued) & set(unknown))
    awaiting = len(old_issued) - len(all_observed) - n_dnp - n_unknown
    if awaiting < 0:
        raise ValueError("Research outcome denominator drift")
    quality = {
        "independent_ET_dates_at_least_8": len(per_date) >= 8,
        "scored_NBA_games_at_least_24":
            len({r["game_id"] for r in all_observed}) >= 24,
        "verified_played_at_least_100": len(all_observed) >= 100,
        "valid_external_future_season_model_improvement": False,
        "season_2026_27_model_selection_independent_of_prior_outcomes": False,
        "selected_played_only_not_full_fantasy_population": True,
        "initial_played_observations_preserved": True,
        "revised_boxscores_append_only": True,
        "calibrated_unconditional_FP_allowed": False,
        "adopt_on_site": False,
    }
    result = {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "model_sha256": MODEL_HASH, "frozen_exploratory_structure": MODEL,
        "source_frozen_minutes_issue_sha256": expected_source_hash,
        "issued": all_issued, "observed": all_observed,
        "observed_corrections": revisions,
        "summary": {
            "issued_total": len(all_issued), "new_issued_this_run": len(new),
            "played_verified": len(all_observed),
            "independently_versioned_correction_events": len(revisions),
            "corrected_player_games": len(grouped_revisions),
            "literal_DNP_excluded": n_dnp,
            "UNKNOWN_not_imputed": n_unknown,
            "awaiting_or_unchecked": awaiting,
            "independent_scored_ET_dates": len(per_date),
            "scored_NBA_games": len({r["game_id"] for r in all_observed}),
        },
        "issue_QA": dict(qa),
        "source_clock_QA": {
            "latest_original_frozen_issue_at_utc": max(
                (x["issued_at_utc"] for x in original.values()), default=None),
            "max_baseline_to_challenger_issue_lag_seconds":
                MODEL["max_baseline_to_challenger_issue_lag_seconds"],
            "current_minutes_first_seen_must_be_by_original_issue": True,
            "no_retroactive_issue": True,
        },
        "played_only_paired_metrics": metrics(all_observed),
        "by_ET_date": {k:metrics(v) for k,v in sorted(per_date.items())},
        "quality_gate": quality,
        "limitations": [
            "Only genuinely new minute issues within 20 minutes of baseline are compared.",
            "Current-season played minutes have archived first-seen times before issuance.",
            "All negative/missing/DNP outcomes are excluded from conditional FP metrics.",
            "Historical paired metrics use FIRST observed played FP, with later corrected boxscores quarantined in an append-only separate audit.",
            "The 5-game prior shrinkage was defined after first 2026/27 results.",
            "No proof that role adjustment or unconditional FP improves future decisions.",
            "No model retraining, Firebase, Sports.ru prices, personal accounts or transfers.",
        ],
    }
    return result


def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    target = DATA/"current_season_minutes_shadow_research.json"
    prior = read(target.name) if target.exists() else {}
    report = build(
        prior, read("conditional_minutes_fp_research.json"),
        read("rolling_decision_research.json"), read("live.json"),
        read("conditional_minutes_fp_evaluation_research.json"),
        datetime.now(timezone.utc), read("observed_boxscore_versions_research.json"))
    if (not prior or {k:v for k,v in report.items() if k!="updated_at_utc"} !=
            {k:v for k,v in prior.items() if k!="updated_at_utc"}):
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf8")
        temp.replace(target)
    return {"summary":report["summary"],"research_only":True,
            "adopt_on_site":False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
