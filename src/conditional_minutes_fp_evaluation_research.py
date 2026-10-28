"""Research-only prospective evaluation of immutable minutes x FP/min forecasts.

Only a completed, ESPN-DNP-checked NBA game and an independently matched
positive-minute Sports.ru-formula boxscore row permit conditional error scoring.
Explicit DNP is counted but NOT scored as conditional FP=0. Unlisted players
remain UNKNOWN, not an inferred absence. Development-2024/25 residual bands
are evaluated as fixed historical bands, never called calibrated P10/P90.
No model selection, retraining, personal data, Firebase or Hosting writes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo
import json

from src.sync import DATA

STATUS = "research_only_not_deployed"
UTC = timezone.utc
ET = ZoneInfo("America/New_York")
SOURCE = "positive_minutes_verified_sportsru_fp"
EXPLICIT = "explicit_espn_didNotPlay_true"
NAMES = ("minutes", "fp_rate", "decomposed_fp", "direct_fp")


def clock(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing UTC provenance")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC provenance") from exc
    if result.utcoffset() is None:
        raise ValueError("Naive provenance clock")
    return result.astimezone(UTC)


def number(value):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("Non-finite observation or prediction")
    return float(value)


def index(rows, name, key_fields=("game_id", "player_id")):
    if not isinstance(rows, list):
        raise ValueError(name + " is not a list")
    out = {}
    for row in rows:
        k = tuple(row[field] for field in key_fields)
        if k in out:
            raise ValueError("Duplicate " + name + " identity")
        out[k] = row
    return out


def profile(outcomes):
    n = Counter(row["outcome"] for row in outcomes)
    total = len(outcomes)
    return {
        "finished_checked": total,
        "played": n["played"],
        "explicit_DNP_not_scored": n["explicit_DNP"],
        "UNKNOWN_not_imputed": n["UNKNOWN"],
        "unknown_fraction": round(n["UNKNOWN"] / total, 6) if total else None,
    }


def metrics(rows):
    if not rows:
        return {"played_scored": 0}
    def mean(values):
        return sum(values) / len(values)
    def scores(field, target):
        errors = [r[field] - r[target] for r in rows]
        return {
            "MAE": round(mean([abs(v) for v in errors]), 4),
            "RMSE": round(sqrt(mean([v*v for v in errors])), 4),
            "prediction_minus_actual_bias": round(mean(errors), 4),
        }
    bands = {}
    for name, target in (("minutes", "actual_minutes"),
                         ("fp", "actual_fp_reconstructed")):
        pairs = [(r["frozen_dev_"+name+"_band"], r[target]) for r in rows]
        bands[name+"_frozen_dev_q90_not_guaranteed"] = {
            "empirical_coverage": round(mean([int(a <= y <= b) for (a,b),y in pairs]), 6),
            "mean_width": round(mean([b-a for (a,b),_ in pairs]), 4),
            "nominal_dev_coverage_not_prospective_claim": 0.90,
        }
    return {
        "played_scored": len(rows),
        "predicted_minutes": scores("predicted_minutes", "actual_minutes"),
        "predicted_FP_per_minute": scores("predicted_rate", "actual_rate"),
        "decomposed_FP": scores("predicted_decomposed_fp", "actual_fp_reconstructed"),
        "direct_FP": scores("predicted_direct_fp", "actual_fp_reconstructed"),
        "direct_minus_decomposed_FP_MAE": round(
            mean([abs(r["predicted_direct_fp"]-r["actual_fp_reconstructed"])
                  -abs(r["predicted_decomposed_fp"]-r["actual_fp_reconstructed"])
                  for r in rows]), 4),
        "frozen_historical_error_bands": bands,
    }


def build(minutes, pplay, cohort, explicit, live, now):
    if now.utcoffset() is None:
        raise ValueError("Evaluation clock must be timezone-aware")
    now = now.astimezone(UTC)
    for name, source in (("minutes", minutes), ("pplay", pplay),
                         ("cohort", cohort), ("explicit DNP", explicit)):
        if (source.get("schema_version") != 1 or source.get("status") != STATUS
                or source.get("adopt_on_site") is not False):
            raise ValueError("Untrusted/deployable " + name)
    if (minutes.get("unconditional_FP_enabled") is not False
            or minutes.get("p_play_assumed_calibrated") is not False
            or pplay.get("population_brier_enabled") is not False
            or cohort.get("representative_of_full_fantasy_population") is not False):
        raise ValueError("Population/deployment flags changed")
    issued = index(minutes.get("issued"), "frozen_minutes_issue")
    shadow = index(pplay.get("issued"), "p_play_first_issued")
    shadow_observed = index(pplay.get("observations"), "p_play_observed")
    labelled = index(cohort.get("records"), "postgame_cohort")
    live_rows = index(live.get("rows"), "reconstructed_boxscore", ("game_id", "id"))
    dnp_events = index(explicit.get("events"), "literal_DNP_events")
    finals = index([g for g in live.get("games", [])
                    if g.get("status") == "final"], "completed_games", ("id",))
    checked_list = explicit.get("checked_final_game_ids")
    if not isinstance(checked_list, list) or len(checked_list) != len(set(checked_list)):
        raise ValueError("Invalid literal DNP audited games")
    checked = set(checked_list)
    if not checked.issubset({k[0] for k in finals}):
        raise ValueError("DNP checked game not completed")
    if len(issued) != minutes.get("issued_total"):
        raise ValueError("Minutes issuance report internally inconsistent")
    if not issued:
        raise ValueError("No frozen prospective issue cohort")
    result = []
    played = []
    unverified = []
    nonplay = []
    by_date = defaultdict(list)
    by_status = defaultdict(list)
    by_position = defaultdict(list)
    by_identity = defaultdict(list)
    for (gid,pid),issue in sorted(issued.items()):
        key = (gid,pid)
        p = shadow.get(key)
        if p is None or p.get("team") != issue.get("team"):
            raise ValueError("Missing first-issued player/team for minutes forecast")
        tip, lock, initial, first = [clock(value) for value in (
            issue["game_utc"], issue["individual_lock_utc"],
            issue["issued_at_utc"], issue["p_play_first_issued_at_utc"])]
        if (p["tipoff_utc"] != issue["game_utc"] or
                p["individual_lock_utc"] != issue["individual_lock_utc"] or
                p["issued_at_utc"] != issue["p_play_first_issued_at_utc"] or
                not (first <= initial < lock < tip) or
                (tip-lock).total_seconds() != 1800 or initial > now):
            raise ValueError("Original immutable pre-lock provenance is invalid")
        if (issue.get("observed_game_outcome") != "UNKNOWN" or
                issue.get("game_day_membership_verified") is not False or
                issue.get("p_play_population_calibrated") is not False or
                issue.get("unconditional_FP_calculated") is not False or
                issue.get("adopt_on_site") is not False or
                issue.get("research_only") is not True or
                issue.get("frozen_rule_hash") != minutes["frozen_rule_hash"] or
                issue.get("historical_source_index_version") !=
                minutes["historical_source_index_version"] or
                issue.get("historical_training_season") != "2025/26" or
                issue.get("historical_source_last_game_date", "9999") >= "2026-07-01"):
            raise ValueError("Issued model illegally revised or future-leaked")
        for name in ("min_if_play", "fp_per_minute_if_play",
                     "decomposed_fp_if_play", "direct_fp_if_play"):
            number(issue[name])
        if number(issue["min_if_play"]) < 0:
            raise ValueError("Negative predicted minutes")
        bands = issue["development_2024_25_error_bands_not_guaranteed"]
        for name in ("minutes_if_play", "fp_if_play"):
            value = bands[name]
            if not isinstance(value, list) or len(value) != 2 or (
                    number(value[0]) > number(value[1])):
                raise ValueError("Malformed immutable development error band")
        if gid not in checked:
            if key in shadow_observed:
                raise ValueError("Postgame p_play outcome without completed audit")
            result.append({"game_id": gid, "player_id": pid,
                           "outcome": "awaiting_or_unchecked"})
            continue
        game = finals[(gid,)]
        if (game["utc"] != issue["game_utc"] or
                issue["team"] not in (game["home"], game["away"]) or tip > now or
                (game.get("et_date") is not None and game.get("et_date", tip.astimezone(ET).date().isoformat()) != tip.astimezone(ET).date().isoformat())):
            raise ValueError("Wrong team, game date or tipoff for finished issue")
        o = labelled.get(key)
        shadow_label = shadow_observed.get(key)
        outcome = "UNKNOWN" if o is None else (
            "played" if o.get("played") is True else "explicit_DNP")
        if o is None and shadow_label is not None:
            raise ValueError("p_play verified label missing from cohort")
        if o is not None:
            if (o["team"] != issue["team"] or
                    o["game_utc"] != issue["game_utc"] or
                    clock(o["source_first_observed_at_utc"]) < tip or
                    clock(o["source_first_observed_at_utc"]) > now or
                    o.get("catalog_team_matches_game") is not True):
                raise ValueError("Postgame label identity/team/source clock inconsistent")
            y = 1 if outcome == "played" else 0
            if (o["participation_label"] != y or shadow_label is None or
                    shadow_label.get("actual_played") != y or
                    shadow_label.get("label_provenance") != (SOURCE if y else EXPLICIT) or
                    shadow_label.get("source_first_observed_at_utc") !=
                    o.get("source_first_observed_at_utc")):
                raise ValueError("p_play independently verified participation disagrees")
        r = {"game_id": gid, "player_id": pid, "team": issue["team"],
             "position": p["position"], "game_utc": issue["game_utc"],
             "et_date": game.get("et_date", tip.astimezone(ET).date().isoformat()), "outcome": outcome,
             "p_play_first_issued_at_utc": p["issued_at_utc"],
             "minutes_issued_at_utc": issue["issued_at_utc"],
             "official_status_first_known_asof_p_play_issue":
             p.get("official_status_first_known_asof_issue") or
             "no_observed_official_status",
             "preissue_club_link_evidence": p["club_link_evidence"]}
        result.append(r)
        by_date[r["et_date"]].append(r)
        by_status[r["official_status_first_known_asof_p_play_issue"]].append(r)
        by_position[r["position"]].append(r)
        by_identity[r["preissue_club_link_evidence"]].append(r)
        if outcome == "UNKNOWN":
            unverified.append(r)
            continue
        if outcome == "explicit_DNP":
            event = dnp_events.get(key)
            if (o.get("evidence") != EXPLICIT or event is None
                    or event["team"] != issue["team"] or
                    clock(event["observed_at_utc"]) > now or
                    key in live_rows):
                raise ValueError("DNP lacks literal individual ESPN evidence")
            nonplay.append({**r, "postgame_first_seen_at_utc":
                            o["source_first_observed_at_utc"],
                            "evidence": EXPLICIT, "not_scored_as_zero_FP": True})
            continue
        actual = live_rows.get(key)
        if (o.get("evidence") != SOURCE or actual is None or
                actual.get("played") is not True or
                actual.get("team") != issue["team"] or
                actual.get("utc") != issue["game_utc"] or
                actual.get("source_url") != o.get("source_url") or
                number(actual.get("minutes")) <= 0 or
                number(actual.get("minutes")) != number(o.get("played_minutes")) or
                number(actual.get("fp")) != number(o.get("sportsru_fp_if_played"))):
            raise ValueError("Positive-minute FP not confirmed in independent live row")
        target = number(o["sportsru_fp_if_played"])
        duration = number(o["played_minutes"])
        played.append({**r, "postgame_first_seen_at_utc":
                       o["source_first_observed_at_utc"],
                       "source_url": o["source_url"],
                       "actual_minutes": duration,
                       "actual_fp_reconstructed": target,
                       "actual_rate": round(target / duration, 8),
                       "predicted_minutes": number(issue["min_if_play"]),
                       "predicted_rate": number(issue["fp_per_minute_if_play"]),
                       "predicted_decomposed_fp": number(issue["decomposed_fp_if_play"]),
                       "predicted_direct_fp": number(issue["direct_fp_if_play"]),
                       "frozen_dev_minutes_band": bands["minutes_if_play"],
                       "frozen_dev_fp_band": bands["fp_if_play"]})
    finished = [r for r in result if r["outcome"] != "awaiting_or_unchecked"]
    counts = profile(finished)
    counts["issued_total"] = len(issued)
    counts["awaiting_or_unchecked"] = len(issued) - len(finished)
    if counts["played"] != len(played) or counts["explicit_DNP_not_scored"] != len(nonplay) or (
            counts["UNKNOWN_not_imputed"] != len(unverified)):
        raise ValueError("Outcome reconciliation error")
    groups = {
        "less_than_15_predicted_minutes": [r for r in played if r["predicted_minutes"] < 15],
        "15_to_under_30_predicted_minutes": [r for r in played if 15 <= r["predicted_minutes"] < 30],
        "30_plus_predicted_minutes": [r for r in played if r["predicted_minutes"] >= 30],
    }
    source_hash = sha256(json.dumps(minutes["issued"], sort_keys=True,
                                    separators=(",", ":"), ensure_ascii=False
                                    ).encode("utf-8")).hexdigest()
    et_n = len({r["et_date"] for r in played})
    return {
        "schema_version": 1,
        "status": STATUS, "model_status": STATUS, "adopt_on_site": False,
        "updated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "target": "minutes_and_reconstructed_Sportsru_FP_given_verified_positive_minutes",
        "population": "frozen_prelock_same_team_minutes_issues_only_NOT_full_fantasy_roster",
        "frozen_minutes_issue_sha256": source_hash,
        "model_frozen_hash": minutes["frozen_rule_hash"],
        "first_issued_source_artifact": "data/conditional_minutes_fp_research.json",
        "cohort_sources": {
            "minutes_issued_updated": minutes.get("updated_at_utc"),
            "p_play_shadow_updated": pplay.get("updated_at_utc"),
            "participation_cohort_updated": cohort.get("updated_at_utc"),
            "explicit_DNP_updated": explicit.get("updated_at_utc"),
            "NBA_live_updated": live.get("updated_at_utc"),
        },
        "summary": {**counts,
                    "played_distinct_games": len({r["game_id"] for r in played}),
                    "played_distinct_ET_dates": et_n,
                    "finished_distinct_ET_dates": len(by_date)},
        "positive_minutes_selected_only_metrics": metrics(played),
        "by_frozen_predicted_minutes_group": {k: metrics(v) for k,v in groups.items()},
        "by_ET_date": {k: {"coverage": profile(v),
                             "conditional_played": metrics(
                                 [r for r in played if r["et_date"] == k])}
                       for k,v in sorted(by_date.items())},
        "missingness_by_first_issued_official_status":
            {k: profile(v) for k,v in sorted(by_status.items())},
        "missingness_by_club_identity":
            {k: profile(v) for k,v in sorted(by_identity.items())},
        "missingness_by_position":
            {k: profile(v) for k,v in sorted(by_position.items())},
        "scored_played": played,
        "explicit_DNP_not_in_conditional_metrics": nonplay,
        "UNKNOWN_unscored": unverified,
        "quality_gate": {
            "at_least_8_independent_ET_dates": et_n >= 8,
            "at_least_100_positive_minute_prospective_cases": len(played) >= 100,
            "reconstructed_FP_is_official_account_credit": False,
            "dev_q90_bands_are_valid_future_predictive_intervals": False,
            "p_play_full_denominator_calibrated": False,
            "unconditional_FP_allowed": False,
            "KEEP_TRANSFER_value_proven": False,
            "adopt_on_site": False,
        },
        "interpretation": [
            "Only verified positive-minute player-games contribute MAE/RMSE/bias; literal DNP is not FP=0 here.",
            "Players absent from an ESPN/NBA row and unavailable games stay UNKNOWN or awaiting.",
            "Sports.ru-formula FP reconstructed from NBA boxscore is not personal credited Sports.ru FP.",
            "Historical 2024/25 q90 absolute residual bands are scored only as frozen diagnostics.",
            "Small number of ET dates makes naive player-level confidence intervals unreliable.",
            "No data-driven parameter tuning, prospective reissue, site deployment, Firestore or transfer action.",
        ],
    }


def run():
    read = lambda name: json.loads((DATA / name).read_text(encoding="utf8"))
    now = datetime.now(UTC)
    report = build(
        read("conditional_minutes_fp_research.json"),
        read("p_play_shadow_research.json"),
        read("participation_cohort_research.json"),
        read("explicit_dnp_research.json"),
        read("live.json"), now)
    target = DATA / "conditional_minutes_fp_evaluation_research.json"
    previous = read(target.name) if target.exists() else {}
    if (not previous or
            {k: v for k,v in report.items() if k != "updated_at_utc"} !=
            {k: v for k,v in previous.items() if k != "updated_at_utc"}):
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf8")
        temp.replace(target)
    summary = report["summary"]
    return {**summary, "research_only": True, "adopt_on_site": False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
