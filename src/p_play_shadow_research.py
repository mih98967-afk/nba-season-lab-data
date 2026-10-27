"""Pre-registered, research-only, prospective participation proxy shadow v1.

Issue a frozen score BEFORE individual lock for players observed in both
Sports.ru catalog-proxy and ESPN team-roster snapshots. The target for
descriptive evaluation is *a verified played or explicit DNP boxscore label*,
NOT an observed full-roster NBA p_play probability. ESPN lists only a selected
set; UNKNOWN is never interpreted as 0, so no population Brier, calibrated
p_play or production decision is permitted.

Scores: a global selected-cohort Laplace (1,1) prior; a player-history
candidate shrunk by exactly 12 pseudo-observations toward that same prior.
Both are explicitly uncalibrated statistical controls, not clinical injury
risk estimates. Injury/Telegram context is logged as-of but not weighted.
Only first-observed, postgame labels known BEFORE issue can be features.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from random import Random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math

from src.sync import DATA
from src.prelock_roster_opportunities import build as opportunity_build, HIGH, WEAK
from src.rolling_decision_research import instant, stamp, official_asof, telegram_asof
from src.catalog_pit_research import LOCK, MAX_SCHEDULE_AGE, MAX_LIVE_AGE
from src.espn_roster_pit import STATUS

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
SCHEMA = 1
SHRINKAGE = 12
ADMISSIBLE = {"same_club_independent_ESPN_ID_observed",
              "same_club_unique_name_only_observed"}
NO_DEPLOY = "research_only_not_deployed"


def _now(value):
    if value.utcoffset() is None:
        raise ValueError("Aware UTC issue/evaluation time required")
    return value.astimezone(UTC)


def _time(value):
    return instant(value)


def _verified_past(cohort, cutoff):
    """Chronologically honest selected-history counts; no inferred DNPs."""
    out = []
    seen_keys = set()
    qa = Counter()
    for r in cohort.get("records", []):
        if not isinstance(r, dict):
            raise ValueError("Malformed historical participation record")
        key = r.get("game_id"), r.get("player_id")
        if (not all(isinstance(k, str) and k for k in key)
                or key in seen_keys):
            raise ValueError("Duplicate selected historical player-game")
        seen_keys.add(key)
        label = r.get("participation_label")
        proof = ("positive_minutes_verified_sportsru_fp" if label == 1 else
                 "explicit_espn_didNotPlay_true" if label == 0 else None)
        if r.get("evidence") != proof:
            raise ValueError("Untrusted past participation label")
        try:
            tip = _time(r["game_utc"])
            observed = _time(r["source_first_observed_at_utc"])
        except (KeyError, TypeError, ValueError):
            qa["no_first_observed_timestamp"] += 1
            continue
        if observed < tip:
            raise ValueError("Historical outcome observed before its game started")
        if tip >= cutoff or observed > cutoff:
            qa["future_or_not_yet_observed_label_excluded"] += 1
            continue
        if not isinstance(r.get("team"), str) or not r.get("team"):
            raise ValueError("Missing historical team")
        out.append((r["player_id"], int(label), observed))
    return out, dict(qa)


def _fresh(live, now):
    if live.get("schema_version") != 4:
        return False
    quality = live.get("schedule_quality") or {}
    if quality.get("freshness") != "fresh":
        return False
    # A refreshed live boxscore/fixture list must be recent (8 h), while a
    # separately validated full-season schedule may be up to 36 h old. These
    # are the same PIT freshness limits used by catalog_pit_research; applying
    # the 8 h live limit to the calendar silently prevented new forecasts.
    try:
        live_at = _time(live.get("updated_at_utc"))
        calendar_at = _time(quality.get("validated_at_utc"))
    except (ValueError, TypeError):
        return False
    if (live_at > now or calendar_at > now
            or calendar_at > live_at
            or now - live_at > MAX_LIVE_AGE
            or now - calendar_at > MAX_SCHEDULE_AGE):
        return False
    return True


def _prior_input(prior):
    if not prior:
        return [], [], {}
    if (prior.get("schema_version") != SCHEMA
            or prior.get("status") != NO_DEPLOY
            or prior.get("adopt_on_site") is not False
            or prior.get("population_brier_enabled") is not False):
        raise ValueError("Untrusted prior model artifact")
    issued, observed = prior.get("issued"), prior.get("observations")
    if not isinstance(issued, list) or not isinstance(observed, list):
        raise ValueError("Invalid prior immutable archives")
    if len({(p.get("game_id"), p.get("player_id")) for p in issued}) != len(issued):
        raise ValueError("Duplicate archived prelock prediction")
    if len({(o.get("game_id"), o.get("player_id")) for o in observed}) != len(observed):
        raise ValueError("Duplicate archived postgame observation")
    issued_keys = {(p["game_id"], p["player_id"]) for p in issued}
    if any((o.get("game_id"), o.get("player_id")) not in issued_keys for o in observed):
        raise ValueError("Orphan evaluated label")
    if any(p.get("adopt_on_site") not in (None, False) for p in issued):
        raise ValueError("A historical shadow forecast was marked for deployment")
    return list(issued), list(observed), prior


def _issues(report, cohort, official, telegram, now, issued):
    """Frozen first-issue scoring: never use contemporary or later outcomes."""
    old_keys = {(x["game_id"], x["player_id"]) for x in issued}
    past, history_qa = _verified_past(cohort, now)
    positives = sum(y for _, y, _ in past)
    negatives = len(past) - positives
    baseline = (positives + 1) / (positives + negatives + 2)
    player = defaultdict(lambda: [0, 0])
    for pid, label, _ in past:
        player[pid][label] += 1
    additions = []
    qa = Counter()
    for row in report.get("records", []):
        key = row["game_id"], row["player_id"]
        lock = _time(row["individual_lock_utc"])
        tip = _time(row["game_utc"])
        if key in old_keys:
            qa["already_issued_immutable"] += 1
            continue
        if tip - lock != LOCK:
            raise ValueError("Invalid individual game lock boundary")
        if now >= lock:
            qa["already_locked_not_issued"] += 1
            continue
        kind = row.get("club_cross_source_evidence")
        if kind not in ADMISSIBLE:
            qa["no_independent_same_club_link"] += 1
            continue
        catalog_at = _time(row["catalog_capture_utc"])
        espn_at = _time(row["espn_roster_capture_utc"])
        if max(catalog_at, espn_at) > now or max(catalog_at, espn_at) > lock:
            raise ValueError("A roster proxy was first captured after prediction/lock")
        team = row["team_in_catalog_snapshot"]
        if not isinstance(team, str) or not team:
            raise ValueError("Unknown prospective team")
        pid = key[1]
        negative, positive = player[pid]
        n = negative + positive
        candidate = (SHRINKAGE * baseline + positive) / (SHRINKAGE + n)
        if not (0 < baseline < 1 and 0 < candidate < 1):
            raise ValueError("Invalid shadow probability score")
        official_e = official_asof(official, key[0], pid, team, now)
        telegram_e = telegram_asof(telegram, pid, now)
        additions.append({
            "game_id": key[0], "player_id": pid, "team": team,
            "position": row["fantasy_position"],
            "tipoff_utc": row["game_utc"],
            "individual_lock_utc": row["individual_lock_utc"],
            "issued_at_utc": stamp(now),
            "catalog_capture_utc": row["catalog_capture_utc"],
            "espn_capture_utc": row["espn_roster_capture_utc"],
            "club_link_evidence": kind,
            "baseline_p_selected_listed_proxy": round(baseline, 6),
            "candidate_p_selected_listed_proxy": round(candidate, 6),
            "historical_selected_played_n": positive,
            "historical_selected_explicit_dnp_n": negative,
            "historical_selected_global_played_n": positives,
            "historical_selected_global_explicit_dnp_n": negatives,
            "official_status_first_known_asof_issue": (official_e or {}).get("status"),
            "official_observed_at_issue": (official_e or {}).get("first_seen_at_utc"),
            "telegram_status_unconfirmed_asof_issue": (telegram_e or {}).get("status"),
            "telegram_observed_at_issue": (telegram_e or {}).get("first_seen_at_utc"),
            "medical_context_not_weighted": True,
            "population_probability_calibrated": False,
            "adopt_on_site": False,
        })
        qa["new_eligible_issues"] += 1
    return additions, {**history_qa, **dict(qa)}


def _observations(issued, existing, live, cohort, explicit, now):
    finals = {g["id"]: g for g in live.get("games", [])
              if isinstance(g, dict) and g.get("status") == "final"
              and isinstance(g.get("id"), str)}
    checked = explicit.get("checked_final_game_ids")
    if not isinstance(checked, list) or len(set(checked)) != len(checked):
        raise ValueError("Invalid checked-game participation coverage")
    checked = set(checked)
    if len(checked) != cohort.get("summary", {}).get("verified_full_boxscores_checked"):
        raise ValueError("Postgame sources not coherent")
    indexed = {}
    for r in cohort.get("records", []):
        k = r.get("game_id"), r.get("player_id")
        if k in indexed:
            raise ValueError("Duplicate postgame selected observation")
        indexed[k] = r
    observed = {(o["game_id"], o["player_id"]): o for o in existing}
    qa = Counter()
    for issue in issued:
        key = issue["game_id"], issue["player_id"]
        g = finals.get(key[0])
        if not g:
            qa["game_not_verified_final"] += 1
            continue
        if (g["utc"] != issue["tipoff_utc"] or
                (issue["team"] not in (g.get("home"), g.get("away")))):
            qa["game_rescheduled_or_club_changed"] += 1
            continue
        if key[0] not in checked:
            qa["final_not_explicit_DNP_checked"] += 1
            continue
        r = indexed.get(key)
        if not r:
            qa["no_explicit_outcome_UNKNOWN"] += 1
            continue
        if (r.get("team"), r.get("position"), r.get("game_utc")) != (
                issue["team"], issue["position"], issue["tipoff_utc"]):
            qa["actual_club_position_or_fixture_conflict_UNKNOWN"] += 1
            continue
        label = r.get("participation_label")
        expected = ("positive_minutes_verified_sportsru_fp" if label == 1 else
                    "explicit_espn_didNotPlay_true" if label == 0 else None)
        if expected is None or r.get("evidence") != expected:
            raise ValueError("Unproven postgame label")
        try:
            observed_at = _time(r["source_first_observed_at_utc"])
        except (KeyError, TypeError, ValueError):
            qa["postgame_label_missing_real_first_seen_clock_UNKNOWN"] += 1
            continue
        tip = _time(issue["tipoff_utc"])
        if observed_at < tip:
            raise ValueError("Outcome leaked before game")
        if observed_at > now:
            qa["postgame_label_not_yet_observed_UNKNOWN"] += 1
            continue
        if key in observed:
            if (observed[key]["actual_played"] != label or
                    observed[key]["source_first_observed_at_utc"] != stamp(observed_at)):
                raise ValueError("Previously evaluated outcome was silently revised")
            continue
        observed[key] = {
            "game_id": key[0], "player_id": key[1],
            "tipoff_utc": issue["tipoff_utc"],
            "actual_played": label, "label_provenance": expected,
            "source_first_observed_at_utc": stamp(observed_at),
            "evaluated_at_utc": stamp(now),
            "club_link_evidence_at_issue": issue["club_link_evidence"],
            "baseline_p_selected_listed_proxy":
                issue["baseline_p_selected_listed_proxy"],
            "candidate_p_selected_listed_proxy":
                issue["candidate_p_selected_listed_proxy"],
        }
        qa["new_verified_outcomes"] += 1
    return sorted(observed.values(), key=lambda r: (r["tipoff_utc"], r["game_id"], r["player_id"])), dict(qa)


def _prospective_metrics(observations):
    """Descriptive paired losses, with whole NBA games as bootstrap units."""
    if not observations:
        return None
    grouped = defaultdict(list)
    for o in observations:
        y = o["actual_played"]
        if type(y) is not int or y not in (0, 1):
            raise ValueError("Invalid played outcome")
        game = o["game_id"]
        p0 = float(o["baseline_p_selected_listed_proxy"])
        p1 = float(o["candidate_p_selected_listed_proxy"])
        if not all(0 < p < 1 and math.isfinite(p) for p in (p0,p1)):
            raise ValueError("Invalid saved probability")
        b0 = (p0-y)**2
        b1 = (p1-y)**2
        l0 = -(y*math.log(p0)+(1-y)*math.log1p(-p0))
        l1 = -(y*math.log(p1)+(1-y)*math.log1p(-p1))
        grouped[game].append((b0,b1,l0,l1))
    groups = [grouped[k] for k in sorted(grouped)]
    items = [row for group in groups for row in group]
    n = len(items)
    dates = {_time(x["tipoff_utc"]).astimezone(ET).date().isoformat() for x in observations}
    result = {
        "scope": "selected_prelock_predictions_with_independently_observed_explicit_postgame_labels",
        "player_games":n, "NBA_games":len(groups), "ET_dates":len(dates),
        "baseline_Brier":round(sum(x[0] for x in items)/n,6),
        "candidate_Brier":round(sum(x[1] for x in items)/n,6),
        "baseline_logloss":round(sum(x[2] for x in items)/n,6),
        "candidate_logloss":round(sum(x[3] for x in items)/n,6),
        "no_population_calibration_claim":True,
        "no_inferred_DNP":True,
        "sufficient_for_longitudinal_adoption":False,
    }
    if len(groups)>1:
        rng = Random(20261027)
        boots = [[],[]]
        for _ in range(1000):
            draw = [groups[rng.randrange(len(groups))] for _ in groups]
            values = [x for group in draw for x in group]
            boots[0].append(sum(x[0]-x[1] for x in values)/len(values))
            boots[1].append(sum(x[2]-x[3] for x in values)/len(values))
        for b in boots:b.sort()
        result["NBA_game_cluster_bootstrap_95pct_gain"] = {
            "Brier":[round(boots[0][24],6),round(boots[0][974],6)],
            "logloss":[round(boots[1][24],6),round(boots[1][974],6)],
            "seed":20261027, "draws":1000,
            "few_independent_game_dates_caution":len(dates)<4,
        }
    else:
        result["NBA_game_cluster_bootstrap_95pct_gain"] = None
    return result


def _metrics(observations):
    games = {x["game_id"] for x in observations}
    dates = {_time(x["tipoff_utc"]).astimezone(ET).date().isoformat()
             for x in observations}
    high = [o for o in observations if
            o["club_link_evidence_at_issue"] ==
            "same_club_independent_ESPN_ID_observed"]
    summary = {"verified_selected_labels": len(observations),
               "verified_selected_distinct_games": len(games),
               "verified_selected_distinct_ET_dates": len(dates),
               "high_identity_verified_labels": len(high),
               "low_identity_verified_labels": len(observations)-len(high)}
    # No retrospective score is a population Brier/true p_play calibration.
    # Screening floors ONLY permit a plainly selected-cohort descriptive score.
    permitted = (len(high) >= 40 and
                 len({o["game_id"] for o in high}) >= 3 and
                 len({_time(o["tipoff_utc"]).astimezone(ET).date().isoformat()
                      for o in high}) >= 2)
    if not permitted:
        return summary, None
    def brier(field):
        return sum((o[field] - o["actual_played"]) ** 2 for o in high) / len(high)
    base = brier("baseline_p_selected_listed_proxy")
    candidate = brier("candidate_p_selected_listed_proxy")
    return summary, {
        "scope": "selected_verified_boxscore_label_AND_high_prelock_ESPN_ID",
        "n": len(high), "games": len({o["game_id"] for o in high}),
        "ET_dates": len({_time(o["tipoff_utc"]).astimezone(ET).date().isoformat()
                         for o in high}),
        "baseline_selected_sample_brier": round(base, 6),
        "candidate_selected_sample_brier": round(candidate, 6),
        "candidate_minus_baseline_selected_brier": round(candidate-base, 6),
        "population_Brier_not_supported": True,
        "not_a_calibrated_p_play_validation": True,
        "not_evidence_of_KEEP_TRANSFER_value": True,
    }


def advance(prior, live, cohort, explicit, catalog_snapshots, espn_snapshots,
            official, telegram, now):
    now = _now(now)
    issued, observations, previous = _prior_input(prior)
    if (cohort.get("status") != STATUS or cohort.get("adopt_on_site") is not False or
            explicit.get("schema_version") != 1 or explicit.get("adopt_on_site") is not False or
            official.get("status") != "official_report_observed_pit_research_only" or
            telegram.get("status") != "observed_unconfirmed_research_archive"):
        raise ValueError("Untrusted upstream research sources")
    report = opportunity_build(live, cohort, explicit, catalog_snapshots,
                               espn_snapshots, now, official, telegram)
    if _fresh(live, now):
        additions, issuer_qa = _issues(report, cohort, official, telegram, now, issued)
    else:
        additions, issuer_qa = [], {"source_not_fresh_no_issue": True}
    issued += additions
    observations, outcome_qa = _observations(issued, observations, live,
                                              cohort, explicit, now)
    if previous and not additions and not outcome_qa.get("new_verified_outcomes"):
        return previous, {"result": "no_new_issue_or_verified_outcome",
                          "issued_total": len(issued), "evaluated_total": len(observations)}
    summary, selected_metric = _metrics(observations)
    prospective_metrics = _prospective_metrics(observations)
    result = {
        "schema_version": SCHEMA, "status": NO_DEPLOY,
        "model_status": NO_DEPLOY, "adopt_on_site": False,
        "updated_at_utc": stamp(now),
        "first_issue_at_utc": (issued[0]["issued_at_utc"] if issued else None),
        "model": "selected_cohort_laplace_global_vs_12_shrinkage_player_history",
        "shrinkage_pseudo_observations": SHRINKAGE,
        "target_semantics": "postgame_explicit_positive_or_didNotPlay_in_selected_ESPN_boxscore",
        "full_game_day_roster_denominator_verified": False,
        "population_brier_enabled": False,
        "full_population_calibration_evidence": False,
        "keep_transfer_value_demonstrated": False,
        "official_injury_and_telegram_weights_applied": False,
        "issued": issued, "observations": observations,
        "summary": {
            "issued_prelock_forecasts": len(issued),
            "observed_verifiable_player_games": len(observations),
            "unknown_future_or_unlisted": len(issued) - len(observations),
            **summary
        },
        "source_quality_qa": issuer_qa,
        "outcome_qa": outcome_qa,
        "selected_cohort_descriptive_metrics_only": selected_metric,
        "all_verified_selected_prelock_prospective_metrics": prospective_metrics,
        "limitations": [
            "ESPN boxscore-list labels form a selected sample, not all fantasy player-games.",
            "Static catalog and ESPN roster are not official active game-day lists.",
            "Global and per-player score use ONLY independently first-observed earlier explicit labels.",
            "Unlisted, conflicting identity or unmatched outcomes are UNKNOWN, never 0/DNP.",
            "Reported official injuries and unverified Telegram are qualitative PIT context only.",
            "Even a favorable Brier on selected cases cannot justify deploying p_play or KEEP/TRANSFER.",
        ],
    }
    return result, {"result": "new_observation",
                    "issued_new": len(additions),
                    "evaluated_new": outcome_qa.get("new_verified_outcomes", 0),
                    "issued_total": len(issued),
                    "evaluated_total": len(observations),
                    "selected_metric_enabled": selected_metric is not None}


def run():
    def read(path):
        return json.loads(path.read_text(encoding="utf8"))
    target = DATA/"p_play_shadow_research.json"
    prior = read(target) if target.exists() else {}
    now = datetime.now(UTC)
    output, summary = advance(
        prior, read(DATA/"live.json"),
        read(DATA/"participation_cohort_research.json"),
        read(DATA/"explicit_dnp_research.json"),
        [read(p) for p in sorted((DATA/"catalog_pit").glob("*.json"))],
        [read(p) for p in sorted((DATA/"espn_roster_pit").glob("*.json"))],
        read(DATA/"official_injury_status_archive.json"),
        read(DATA/"telegram_archive.json"), now)
    if output != prior:
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(output, ensure_ascii=False,
                                   separators=(",", ":")), encoding="utf8")
        temp.replace(target)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
