"""Precommitted, research-only OUT-OF-TIME p_play paired evaluation.

This compares three immutable forecast scores on the SAME player x game;
it cannot fit a model, replace labels, change fantasy teams or deploy to site.

A selected ESPN boxscore is NOT the whole eligible fantasy population.
Official OUT, player missing from NBA/ESPN, or a finished game with no
explicit outcome stays UNKNOWN. Sharp binary-label bounds are *not* confidence
intervals and cannot repair selection into the forecast population.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from math import log, log1p, isfinite
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo
import json

from src.sync import DATA
from src.rolling_decision_research import instant, stamp

STATUS = "research_only_not_deployed"
ET = ZoneInfo("America/New_York")
LOCK = timedelta(minutes=30)
HIGH_ID = "same_club_independent_ESPN_ID_observed"
FIELDS = (
    "current_baseline",
    "current_candidate",
    "frozen_historical_appearance_proxy",
)
PAIRS = (
    ("current_candidate", "current_baseline"),
    ("frozen_historical_appearance_proxy", "current_candidate"),
    ("frozen_historical_appearance_proxy", "current_baseline"),
)
SEED = 20261027
DRAWS = 1000
# Frozen, deliberately strict screening minimum; passing this alone never
# authorizes publication because verified full-population DNP coverage is absent.
MIN_CONFIRMED = 100
MIN_INDEPENDENT_ET_DATES = 8
MIN_FULL_POPULATION_ET_DATES = 28
MIN_FULL_POPULATION_CONFIRMED = 700
MAX_MISSING_FRACTION = 0.05
MAX_OUT_MISSING_FRACTION = 0.10


def _require_archive(source, name):
    if (not isinstance(source, dict)
            or source.get("schema_version") != 1
            or source.get("status") != STATUS
            or source.get("adopt_on_site") is not False):
        raise ValueError("Untrusted/deployable " + name)


def _rows(items, name):
    if not isinstance(items, list):
        raise ValueError("Missing " + name)
    result = {}
    for r in items:
        if not isinstance(r, dict):
            raise ValueError("Malformed " + name)
        key = (r.get("game_id"), r.get("player_id"))
        if (not all(isinstance(x, str) and x for x in key)
                or key in result):
            raise ValueError("Repeated/invalid " + name + " player-game")
        result[key] = r
    return result


def _prob(value):
    if type(value) not in (float, int) or not isfinite(value) or not 0 < value < 1:
        raise ValueError("Invalid frozen probability")
    return float(value)


def _loss(p, y, measure):
    if type(y) is not int or y not in (0, 1):
        raise ValueError("Nonbinary/unknown outcome passed to score")
    if measure == "Brier":
        return (p - y) ** 2
    if measure == "logloss":
        return -(y * log(p) + (1-y) * log1p(-p))
    raise ValueError("Unknown proper loss")


def _date(tip):
    return instant(tip).astimezone(ET).date().isoformat()


def _status(p):
    return p.get("official_status_first_known_asof_issue") or "no_observed_official_status"


def _pct(num, den):
    return round(num / den, 6) if den else None


def _summary(rows):
    c = Counter(x["classification"] for x in rows)
    completed = c["verified_pair"] + c["UNKNOWN"] + c["waiting_historical_reconciliation"]
    return {
        "issued": len(rows),
        "awaiting_finished_checked_game": c["awaiting_finished_checked_game"],
        "final_game_not_independently_DNP_checked": c["final_game_not_independently_DNP_checked"],
        "finished_checked": completed,
        "verified_pairs": c["verified_pair"],
        "outcome_UNKNOWN": c["UNKNOWN"],
        "waiting_historical_reconciliation": c["waiting_historical_reconciliation"],
        "label_missing_or_waiting_fraction": _pct(
            c["UNKNOWN"] + c["waiting_historical_reconciliation"], completed
        ),
        "known_positive": sum(x["actual_played"] == 1 for x in rows
                              if x["classification"] == "verified_pair"),
        "known_explicit_DNP": sum(x["actual_played"] == 0 for x in rows
                                  if x["classification"] == "verified_pair"),
    }


def _scores(rows):
    confirmed = [r for r in rows if r["classification"] == "verified_pair"]
    if not confirmed:
        return None
    values = {}
    for measure in ("Brier", "logloss"):
        values[measure] = {
            model: round(
                sum(_loss(r["probabilities"][model], r["actual_played"], measure)
                    for r in confirmed) / len(confirmed), 6)
            for model in FIELDS
        }
    return {
        "scope": "strict_same_game_same_person_verified_selected_only",
        "verified_player_games": len(confirmed),
        "verified_ET_dates": len({_date(r["tipoff_utc"]) for r in confirmed}),
        "verified_NBA_games": len({r["game_id"] for r in confirmed}),
        "mean_proper_losses": values,
        "not_population_p_play_calibration": True,
        "cannot_ignore_unknown_for_adoption": True,
    }


def _sharp_bounds(rows):
    """Sharp attainable binary-outcome gain bounds on a FIXED completed cohort.

    For every missing y, independently evaluate both y=0 and y=1, then
    sum casewise min/max. No fabricated labels, no independence assumption.
    A pair name (candidate, baseline) means a POSITIVE gain favors candidate.
    """
    done = [r for r in rows if r["classification"] in (
        "verified_pair", "UNKNOWN", "waiting_historical_reconciliation"
    )]
    if not done:
        return None
    result = {}
    for measure in ("Brier", "logloss"):
        pair_values = {}
        for first, second in PAIRS:
            low = high = 0.0
            for r in done:
                p, q = r["probabilities"][first], r["probabilities"][second]
                ys = ([r["actual_played"]] if r["classification"] == "verified_pair"
                      else [0, 1])
                possibilities = [_loss(q, y, measure)-_loss(p, y, measure)
                                 for y in ys]
                low += min(possibilities)
                high += max(possibilities)
            pair_values[first + "_over_" + second] = {
                "lower_gain": round(low/len(done), 6),
                "upper_gain": round(high/len(done), 6),
                "positive_favors": first,
                "both_labels_allowed_for_each_UNKNOWN": True,
            }
        result[measure] = pair_values
    return {
        "completed_checked_pair_denominator": len(done),
        "verified_pairs": sum(r["classification"] == "verified_pair" for r in done),
        "unknown_or_pending_labels": sum(r["classification"] != "verified_pair" for r in done),
        "sharp_missing_label_gain_range": result,
        "not_a_confidence_interval": True,
        "does_not_correct_unissued_player_selection": True,
    }


def _date_bootstrap(rows):
    """Uncertainty is resampled by whole ET date, NOT by correlated players."""
    known = [r for r in rows if r["classification"] == "verified_pair"]
    groups = defaultdict(list)
    for r in known:
        groups[_date(r["tipoff_utc"])].append(r)
    if len(groups) < MIN_INDEPENDENT_ET_DATES or len(known) < MIN_CONFIRMED:
        return None
    items = [groups[k] for k in sorted(groups)]
    rng = Random(SEED)
    results = {}
    for measure in ("Brier", "logloss"):
        results[measure] = {}
        for first, second in PAIRS:
            diffs = []
            for _ in range(DRAWS):
                draw = [items[rng.randrange(len(items))] for __ in items]
                selected = [r for date_rows in draw for r in date_rows]
                gain = sum(
                    _loss(r["probabilities"][second], r["actual_played"], measure)
                    - _loss(r["probabilities"][first], r["actual_played"], measure)
                    for r in selected
                )/len(selected)
                diffs.append(gain)
            diffs.sort()
            results[measure][first + "_over_" + second] = {
                "95pct_date_cluster_interval": [
                    round(diffs[24], 6), round(diffs[974], 6)
                ],
                "positive_favors": first,
            }
    return {
        "ET_dates_resampled": len(items), "known_player_games": len(known),
        "draws": DRAWS, "fixed_seed": SEED, "resampling_unit": "entire_NBA_ET_date",
        "selected_label_bootstrap_only": True,
        "intervals": results,
    }


def evaluate(shadow, history, explicit, live, now):
    if now.utcoffset() is None:
        raise ValueError("Aware evaluation clock required")
    now = now.astimezone(timezone.utc)
    for name, source in (("p_play_shadow", shadow),
                         ("historical_frozen", history),
                         ("explicit_DNP", explicit)):
        _require_archive(source, name)
    if (shadow.get("population_brier_enabled") is not False
            or history.get("population_p_play_calibrated") is not False
            or history.get("keep_transfer_value_proven") is not False
            or history.get("historical_model_trained_on_logged_appearance_NOT_DNP") is not True
            or history.get("frozen_model_selection_season") != "2024/25"
            or history.get("historical_source_season") != "2025/26"):
        raise ValueError("Model source gates changed")
    shadow_issued = _rows(shadow.get("issued"), "first_issued_shadow")
    h_issued = _rows(history.get("issued"), "historical_issued")
    s_observed = _rows(shadow.get("observations"), "verified_shadow_outcomes")
    h_observed = _rows(history.get("observed"), "historical_verified_outcomes")
    if (set(h_issued) - set(shadow_issued)
            or set(s_observed) - set(shadow_issued)
            or set(h_observed) - set(h_issued)):
        raise ValueError("Orphan prospectively issued/observed player-game")
    checked_ids = explicit.get("checked_final_game_ids")
    if (not isinstance(checked_ids, list)
            or len(checked_ids) != len(set(checked_ids))):
        raise ValueError("Untrusted DNP-checked fixture IDs")
    checked = set(checked_ids)
    finals = {}
    for g in live.get("games", []):
        if g.get("status") != "final":
            continue
        if g.get("id") in finals:
            raise ValueError("Duplicate final game")
        finals[g["id"]] = g
    if not checked.issubset(finals):
        raise ValueError("Independently DNP-checked game missing final scoreboard")
    if (len(history.get("issued", [])) != history.get("summary", {}).get("issued_total")
            or len(history.get("observed", [])) != history.get("summary", {}).get("matched_verified_labels")
            or len(shadow_issued) != shadow.get("summary", {}).get("issued_prelock_forecasts")):
        raise ValueError("Research issue/label denominators changed")

    pairs = []
    for key in sorted(h_issued):
        h = h_issued[key]
        p = shadow_issued[key]
        tip = instant(p["tipoff_utc"])
        lock = instant(p["individual_lock_utc"])
        original_at = instant(p["issued_at_utc"])
        historical_at = instant(h["historical_proxy_issued_at_utc"])
        if (not (original_at <= historical_at < lock < tip)
                or tip-lock != LOCK or historical_at > now
                or h["individual_lock_utc"] != p["individual_lock_utc"]
                or h["original_pplay_issued_at_utc"] != p["issued_at_utc"]
                or h["game_utc"] != p["tipoff_utc"]
                or h["club_at_2026_issue"] != p["team"]
                or h["position"] != p["position"]
                or h["identity"] != HIGH_ID
                or p["club_link_evidence"] != HIGH_ID
                or h["frozen_configuration_sha256"] !=
                    history["historical_frozen_configuration_sha256"]
                or h.get("adopt_on_site") is not False
                or p.get("adopt_on_site") is not False):
            raise ValueError("Historical issue is not a truly pre-lock paired score")
        probabilities = {
            "current_baseline": _prob(p["baseline_p_selected_listed_proxy"]),
            "current_candidate": _prob(p["candidate_p_selected_listed_proxy"]),
            "frozen_historical_appearance_proxy":
                _prob(h["historical_score_dev_calibrated"]),
        }
        if (probabilities["current_baseline"] != _prob(h["current_pplay_baseline_frozen"])
                or probabilities["current_candidate"] !=
                    _prob(h["current_pplay_candidate_frozen"])):
            raise ValueError("Frozen historical comparison used changed current p_play values")
        first_official = p.get("official_observed_at_issue")
        if first_official and instant(first_official) > original_at:
            raise ValueError("Official status was observed after p_play first issue")
        source_obs = s_observed.get(key)
        prior_obs = h_observed.get(key)
        if prior_obs and not source_obs:
            raise ValueError("Historical observation lacks independently verified p_play label")
        if source_obs is not None:
            y = source_obs.get("actual_played")
            if (type(y) is not int or y not in (0, 1)
                    or source_obs.get("tipoff_utc") != p["tipoff_utc"]
                    or source_obs.get("club_link_evidence_at_issue") != HIGH_ID
                    or source_obs.get("label_provenance") !=
                        ("positive_minutes_verified_sportsru_fp" if y else
                         "explicit_espn_didNotPlay_true")):
                raise ValueError("Illegitimate or changed explicit outcome")
            t_label = instant(source_obs["source_first_observed_at_utc"])
            if not tip <= t_label <= now:
                raise ValueError("Postgame result from future/pregame")
            if key[0] not in checked or key[0] not in finals:
                raise ValueError("Verification label for a game not independently checked")
        if prior_obs:
            if (prior_obs.get("actual_played") != source_obs["actual_played"]
                    or prior_obs.get("source_first_observed_at_utc") !=
                       source_obs["source_first_observed_at_utc"]
                    or prior_obs.get("game_utc") != p["tipoff_utc"]):
                raise ValueError("Different labels across frozen research archives")
        game = finals.get(key[0])
        classification = "awaiting_finished_checked_game"
        if game is not None:
            if (game["utc"] != p["tipoff_utc"]
                    or p["team"] not in (game["home"], game["away"])):
                raise ValueError("Final fixture contradicted paired original forecast")
            if key[0] not in checked:
                classification = "final_game_not_independently_DNP_checked"
            elif source_obs is None:
                classification = "UNKNOWN"
            elif prior_obs is None:
                classification = "waiting_historical_reconciliation"
            else:
                classification = "verified_pair"
        row = {
            "game_id": key[0], "player_id": key[1],
            "tipoff_utc": p["tipoff_utc"],
            "first_issue_utc": p["issued_at_utc"],
            "historical_issue_utc": h["historical_proxy_issued_at_utc"],
            "ET_date": _date(p["tipoff_utc"]),
            "official_status_asof_first_issue": _status(p),
            "probabilities": probabilities,
            "classification": classification,
            "actual_played": (source_obs["actual_played"] if
                              classification == "verified_pair" else None),
        }
        pairs.append(row)

    by_date = defaultdict(list)
    by_status = defaultdict(list)
    for row in pairs:
        by_date[row["ET_date"]].append(row)
        by_status[row["official_status_asof_first_issue"]].append(row)
    completed_checked = [r for r in pairs
                         if r["classification"] in (
                             "verified_pair", "UNKNOWN",
                             "waiting_historical_reconciliation")]
    confirmed = [r for r in completed_checked if r["classification"] == "verified_pair"]
    summary = _summary(pairs)
    missing_fraction = summary["label_missing_or_waiting_fraction"]
    OUT = _summary(by_status.get("out", []))
    status_out_missing = OUT["label_missing_or_waiting_fraction"]
    multi_date_ready = (
        len({_date(r["tipoff_utc"]) for r in confirmed}) >= MIN_INDEPENDENT_ET_DATES
        and len(confirmed) >= MIN_CONFIRMED
    )
    full_ready = (
        len({_date(r["tipoff_utc"]) for r in confirmed}) >=
            MIN_FULL_POPULATION_ET_DATES
        and len(confirmed) >= MIN_FULL_POPULATION_CONFIRMED
        and missing_fraction is not None
        and missing_fraction <= MAX_MISSING_FRACTION
        and status_out_missing is not None
        and status_out_missing <= MAX_OUT_MISSING_FRACTION
    )
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False,
        "updated_at_utc": stamp(now),
        "protocol_frozen_before_first_historical_paired_outcome": True,
        "model_selection_frozen_season": "2024/25",
        "historical_source_holdout": "2025/26",
        "prospective_eval_season": "2026/27",
        "historical_model_frozen_sha256":
            history["historical_frozen_configuration_sha256"],
        "target": "positive_minutes_vs_explicit_ESPN_DNP_in_selected_prospective_population",
        "population": "historical_same_club_high_ESPN_ID_overlap_NOT_full_fantasy_roster",
        "p_play_first_issued_total": len(shadow_issued),
        "historical_prelock_overlapping_issued_total": len(pairs),
        "overlap_fraction_of_issued": _pct(len(pairs), len(shadow_issued)),
        "paired_cohort": summary,
        "by_first_issue_injury_status": {
            k: _summary(by_status[k]) for k in sorted(by_status)
        },
        "by_NBA_ET_date": {
            date: {**_summary(by_date[date]),
                   "verified_only_loss": _scores(by_date[date])}
            for date in sorted(by_date)
        },
        "verified_only_matched_proper_scores": _scores(pairs),
        "sharp_unknown_label_sensitivity": _sharp_bounds(pairs),
        "ET_date_cluster_bootstrap_if_sufficient": _date_bootstrap(pairs),
        "fixed_protocol_gates": {
            "min_ET_dates_to_show_cluster_bootstrap": MIN_INDEPENDENT_ET_DATES,
            "min_known_labels_to_show_cluster_bootstrap": MIN_CONFIRMED,
            "full_population_candidate_min_ET_dates": MIN_FULL_POPULATION_ET_DATES,
            "full_population_candidate_min_known": MIN_FULL_POPULATION_CONFIRMED,
            "max_completed_unknown_fraction": MAX_MISSING_FRACTION,
            "max_completed_OUT_unknown_fraction": MAX_OUT_MISSING_FRACTION,
            "longitudinal_selected_label_screen_ready": multi_date_ready,
            "numerical_coverage_thresholds_met": full_ready,
            "actual_full_game_day_membership_denominator_verified": False,
            "multiple_source_complete_DNP_population_verified": False,
            "representative_population_p_play_validated": False,
            "actual_keep_transfer_backtest_verified": False,
            "adopt_on_site": False,
        },
        "no_fitted_parameters_updated": True,
        "unknown_never_mapped_to_DNP": True,
        "report_is_research_only": True,
        "notes": [
            "The 2024/25-calibrated historical proxy was trained on logged appearance, not true DNP.",
            "Only the exact same player-game with both genuinely pre-lock issued forecasts is compared.",
            "The historical forecast may be issued later than the current shadow forecast.",
            "Unconfirmed completed outcomes are UNKNOWN; not an NBA inactive/negative training label.",
            "Sharp range treats every completed missing binary outcome as either 0 or 1 without imputing.",
            "The sharp range is within the selected overlap only; it does not correct player selection.",
            "Bootstrap resamples entire ET dates; with fewer than eight it is suppressed.",
            "Even numerical success cannot bypass missing full game-day roster denominator.",
            "No official injury or Telegram weight, FP optimization, or real transfer claim is supported.",
            "No website, personal Firestore, roster, prices, or transfers are mutated.",
        ],
    }


def run():
    def load(name):
        return json.loads((DATA / name).read_text(encoding="utf8"))
    now = datetime.now(timezone.utc)
    report = evaluate(
        load("p_play_shadow_research.json"),
        load("historical_prior_prospective_shadow_research.json"),
        load("explicit_dnp_research.json"),
        load("live.json"), now,
    )
    target = DATA / "p_play_precommitted_paired_evaluation_research.json"
    old = load(target.name) if target.exists() else {}
    if (not old or
            {k:v for k,v in old.items() if k!="updated_at_utc"} !=
            {k:v for k,v in report.items() if k!="updated_at_utc"}):
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf8")
        tmp.replace(target)
    return {
        "total_pplay": report["p_play_first_issued_total"],
        "historical_overlap": report["historical_prelock_overlapping_issued_total"],
        "completed_checked": report["paired_cohort"]["finished_checked"],
        "verified_pair_labels": report["paired_cohort"]["verified_pairs"],
        "missing_or_pending": report["paired_cohort"]["outcome_UNKNOWN"]
            + report["paired_cohort"]["waiting_historical_reconciliation"],
        "ET_dates": len(report["by_NBA_ET_date"]),
        "adopt_on_site": report["adopt_on_site"],
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
