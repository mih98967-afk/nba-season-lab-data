"""Prospective versioned played-FP shadow forecasts (Sports.ru scoring).

* Conditional FP when a player ACTUALLY plays; never infer DNP from a missing row.
* Forecast revisions are append-only, with genuine UTC issue timestamps.
* Every current-season feature must match a recorded rolling-observation hash.
* Historical source is audited 2025/26, never outcomes of the target season.
* Official reports and Telegram are provenance-only; NO medical inference.
* No user roster, prices, Firestore, Sports.ru mutations, or site deployment.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from random import Random
from zoneinfo import ZoneInfo

from src.sync import DATA
from src.rolling_decision_research import (
    canonical_hash, instant, official_asof, player_games, stamp, telegram_asof,
)

UTC = timezone.utc
HORIZON = timedelta(hours=72)
LOCK = timedelta(minutes=30)
MAX_SCHEDULE_AGE = timedelta(hours=36)
MAX_LIVE_AGE = timedelta(hours=8)
MAX_ROLLING_AGE = timedelta(hours=8)
LIMIT = 80000


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf8"))


def history_means(index):
    """Prior-season verified Sports.ru FP, not an NBA default scoring system."""
    if index.get("status") != "complete" or len(index.get("player_shards", {})) < 200:
        raise ValueError("Historical coverage missing")
    out = {}
    files = sorted(set(index["player_shards"].values()))
    for file in files:
        if not file.startswith("shard_") or "/" in file:
            raise ValueError("Invalid history shard path")
        blob = read("history/" + file)
        if blob.get("version") != index.get("version"):
            raise ValueError("Historical version mismatch")
        for pid, seasons in blob["players"].items():
            last = next((s for s in seasons if s.get("season") == "2025/26"), None)
            if not last or last.get("games", 0) < 10:
                continue
            seq = last.get("game_log")
            if not isinstance(seq, list) or len(seq) != last["games"]:
                continue
            fp = [float(r["fp"]) for r in seq]
            if not all(math.isfinite(v) for v in fp):
                continue
            out[pid] = round(sum(fp[-20:]) / len(fp[-20:]), 4)
    return out


def check_freshness(live, rolling, now):
    """Never trust a 'fresh' label without checking the absolute source clock."""
    quality = live.get("schedule_quality") or {}
    if quality.get("freshness") != "fresh":
        raise ValueError("Calendar is not validated fresh")
    try:
        calendar_at = instant(quality["validated_at_utc"])
        live_at = instant(live["updated_at_utc"])
        rolling_at = instant(rolling["updated_at_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Missing trustworthy source timestamps") from exc
    if any(t > now for t in (calendar_at, live_at, rolling_at)):
        raise ValueError("Future-dated input not allowed")
    if now - calendar_at > MAX_SCHEDULE_AGE:
        raise ValueError("Calendar is stale in absolute UTC time")
    if now - live_at > MAX_LIVE_AGE:
        raise ValueError("Live boxscore ingestion is stale")
    if now - rolling_at > MAX_ROLLING_AGE:
        raise ValueError("Rolling as-of capture is stale")
    if rolling.get("schema_version") != 1 or not rolling.get("snapshots"):
        raise ValueError("Missing immutable-time observation archive")
    if instant(rolling["snapshots"][-1]["captured_at_utc"]) != rolling_at:
        raise ValueError("Rolling archive latest capture timestamp does not match")


def verified_current_form(live, rolling, now):
    """Exclude ALL recent rows of a player if any row changed since capture.

    The rolling archive has a hash of the canonical row. It does NOT retain
    earlier versions' FP values, so on a hash mismatch we must abstain rather
    than reconstruct a false historical feature.
    """
    source, rejected = player_games(live, now)
    stored_hashes = rolling.get("row_hashes") or {}
    first_seen = rolling.get("row_first_seen_at_utc") or {}
    final = {g.get("id"): g for g in live.get("games", [])
             if isinstance(g, dict) and g.get("status") == "final"}
    grouped = defaultdict(list)
    tainted = set()
    qa = Counter(rejected)
    for (game_id, pid), row in source.items():
        key = game_id + "|" + pid
        actual_hash = canonical_hash(row)
        try:
            seen_at = instant(first_seen[key])
        except (ValueError, KeyError, TypeError):
            seen_at = None
        game = final.get(game_id)
        if (stored_hashes.get(key) != actual_hash or seen_at is None or
            seen_at > now or game is None or
            row["team"] not in (game.get("home"), game.get("away"))):
            qa["unverified_current_row"] += 1
            tainted.add(pid)
            continue
        grouped[pid].append((instant(row["utc"]), game_id, row["fp"], key, actual_hash, row["team"]))
    for pid in tainted:
        grouped.pop(pid, None)
    for seq in grouped.values():
        seq.sort(key=lambda r: (r[0], r[1]))
    return grouped, tainted, dict(qa)


def _last_version(issued):
    latest = {}
    for e in issued:
        if not isinstance(e, dict):
            raise ValueError("Malformed old prediction")
        key = (e.get("game_id"), e.get("player_id"))
        if not all(isinstance(x, str) and x for x in key):
            raise ValueError("Old prediction has invalid IDs")
        current = latest.get(key)
        if current is None or instant(e["issued_at_utc"]) > instant(current["issued_at_utc"]):
            latest[key] = e
    return latest


def _legacy_changed(previous, item, official, telegram, asof):
    """Compare legacy v1 without rewriting or inventing source fingerprints."""
    for k in ("team", "game_utc_at_issue", "baseline_fp_if_play",
              "candidate_fp_if_play", "observed_current_played_games"):
        if previous.get(k) != item.get(k):
            return True
    old_time = instant(previous["issued_at_utc"])
    # The old record did not record known status; only trigger if a new report
    # or news item was first observed AFTER that original prediction.
    for signal in (official, telegram):
        if signal and instant(signal["first_seen_at_utc"]) > old_time:
            return True
    return False


def issue(prior, live, catalog, history, rolling, now, official=None, telegram=None):
    if now.utcoffset() is None:
        raise ValueError("Aware issue time required")
    now = now.astimezone(UTC)
    check_freshness(live, rolling, now)
    official = official or {}
    telegram = telegram or {}
    if prior is None:
        prior = {"schema_version": 2, "status": "research_only_not_deployed",
                 "adopt_on_site": False, "issued": []}
    if prior.get("schema_version") not in (1, 2) or prior.get("adopt_on_site") is not False:
        raise ValueError("Unsafe prior prediction archive")
    old_issued = prior.get("issued")
    if not isinstance(old_issued, list) or len(old_issued) > LIMIT:
        raise ValueError("Invalid or oversized old forecast list")
    latest = _last_version(old_issued)
    form, tainted, rejected = verified_current_form(live, rolling, now)
    players = defaultdict(list)
    for p in catalog.get("players", []):
        if p.get("team") and p.get("id"):
            players[p["team"]].append(p)
    issued = list(old_issued)
    counts = Counter()
    revisions = Counter()
    for g in live["schedule"]:
        if g.get("status") != "scheduled":
            continue
        game_time = instant(g["utc"])
        if not now + LOCK < game_time <= now + HORIZON:
            continue
        for club in (g["home"], g["away"]):
            for person in players[club]:
                pid = person["id"]
                key = (g["id"], pid)
                if pid in tainted:
                    counts["abstain_uncaptured_changed_boxscore"] += 1
                    continue
                baseline = history.get(pid)
                if not isinstance(baseline, (int, float)) or not math.isfinite(baseline):
                    counts["without_verified_prior_season"] += 1
                    continue
                observed = form.get(pid, [])
                if observed and observed[-1][-1] != club:
                    counts["abstain_catalog_vs_recent_played_team"] += 1
                    continue
                last5 = observed[-5:]
                candidate = round((baseline * 10 + sum(r[2] for r in last5)) /
                                  (10 + len(last5)), 4)
                status = official_asof(official, g["id"], pid, club, now)
                news = telegram_asof(telegram, pid, now)
                item = {
                    "game_id": g["id"], "player_id": pid, "team": club,
                    "game_utc_at_issue": g["utc"], "issued_at_utc": stamp(now),
                    "baseline_fp_if_play": baseline,
                    "candidate_fp_if_play": candidate,
                    "observed_current_played_games": len(observed),
                    "historical_source": "2025/26 verified FP last20 (played only)",
                    "club_evidence": "current_Sports_ru_catalog_not_historical_roster_verified",
                    "no_play_probability": True,
                    "source_model_version": "paired_conditional_fp_v2",
                    "official_report_asof": status,
                    "telegram_unverified_asof": news,
                }
                item["feature_signature"] = canonical_hash({
                    "game_id": g["id"], "player_id": pid, "team": club,
                    "game_utc": g["utc"], "baseline": baseline,
                    "candidate": candidate,
                    "observed_count": len(observed),
                    "last_five_verified_row_hashes": [(v[3], v[4]) for v in last5],
                    "official_event_id": status["event_id"] if status else None,
                    "telegram_event_id": news["event_id"] if news else None,
                })
                prev = latest.get(key)
                if prev:
                    old_time = instant(prev["issued_at_utc"])
                    if now <= old_time:
                        counts["same_or_earlier_issue_time"] += 1
                        continue
                    if prev.get("feature_signature"):
                        if prev["feature_signature"] == item["feature_signature"]:
                            counts["no_feature_change"] += 1
                            continue
                    elif not _legacy_changed(prev, item, status, news, now):
                        counts["legacy_unchanged"] += 1
                        continue
                    item["revision_number"] = int(prev.get("revision_number", 1)) + 1
                    item["revision_reason"] = (
                        "observed_fp_or_source_evidence_changed"
                        if prev.get("feature_signature") else "v1_new_observation"
                    )
                    counts["revisions"] += 1
                    revisions[item["revision_reason"]] += 1
                else:
                    item["revision_number"] = 1
                    item["revision_reason"] = "first_forecast"
                    counts["new_player_game_forecasts"] += 1
                issued.append(item)
                latest[key] = item
                if len(issued) > LIMIT:
                    raise ValueError("Prospective prediction archive exceeded safe bound")
    result = {**prior, "schema_version": 2, "updated_at_utc": stamp(now),
              "issued": issued, "status": "research_only_not_deployed",
              "adopt_on_site": False,
              "prediction_semantics": "Sports.ru FP conditional on playing, NO p_play",
              "revision_semantics": "append-only; same player-game may have several distinct pre-lock versions",
              "paired_audit_semantics": "evaluate each player-game once; first and last version compared separately",
              "source_integrity": "current stats require exact rolling captured row hashes",
              "first_observed_current_results_source":
                  "rolling_decision_research.row_first_seen_at_utc",
              "candidate_not_tuned_to_2026_27_outcomes": True,
              "last_issue_qa": {**dict(counts),
                                "input_current_row_qc": rejected,
                                "player_ids_abstained_due_source_mismatch": len(tainted),
                                "revision_reasons": dict(revisions)}}
    return result, result["last_issue_qa"]


def _source_known_at_issue(version):
    """A later-seen official/Telegram event cannot appear in an earlier issue.

    This also protects independently imported legacy archives. Never use the
    PDF report date alone if its first-observed timestamp is later.
    """
    issue_at = instant(version["issued_at_utc"])
    for name, clocks in (
        ("official_report_asof", ("first_seen_at_utc", "report_at_utc")),
        ("telegram_unverified_asof", ("first_seen_at_utc", "published_at_utc")),
    ):
        evidence = version.get(name)
        if evidence is None:
            continue
        if not isinstance(evidence, dict) or not evidence.get("first_seen_at_utc"):
            return False
        try:
            if any(instant(evidence[field]) > issue_at for field in clocks):
                return False
        except (KeyError, ValueError, TypeError):
            return False
    return True


def _game_cluster_gain_interval(compared, draws=2000, seed=20261026):
    """Exploratory resampling of WHOLE NBA games, not independent athletes.

    In a game, minutes, pace, victory bonuses and team context correlate the
    two clubs' fantasy scores. Point gain is baseline MAE minus candidate MAE.
    One game cannot provide a game-cluster uncertainty interval.
    """
    by_game = defaultdict(list)
    for (game_id, _), actual, _, latest in compared:
        by_game[game_id].append(
            abs(float(latest["baseline_fp_if_play"]) - actual) -
            abs(float(latest["candidate_fp_if_play"]) - actual))
    games = [by_game[k] for k in sorted(by_game)]
    if len(games) < 2:
        return None
    random = Random(seed)
    outcomes = []
    for _ in range(draws):
        chosen = [games[random.randrange(len(games))] for _ in games]
        total = sum(sum(group) for group in chosen)
        count = sum(len(group) for group in chosen)
        outcomes.append(total / count)
    outcomes.sort()
    low = outcomes[int((draws - 1) * 0.025)]
    high = outcomes[int((draws - 1) * 0.975)]
    return {
        "lower": round(low, 4), "upper": round(high, 4),
        "n_game_clusters": len(games), "resamples": draws, "seed": seed,
        "unit": "FP_per_verified_played_player_game",
        "method": "game_cluster_bootstrap_percentile_95_exploratory",
        "not_proof_of_generalization": True,
    }


def audit(pred, live, now):
    """Independent, paired audit; one player-game, never one row per revision."""
    if now.utcoffset() is None:
        raise ValueError("Aware audit time required")
    now = now.astimezone(UTC)
    all_groups = defaultdict(list)
    qa = Counter()
    for p in pred.get("issued", []):
        try:
            key = (p["game_id"], p["player_id"])
            issued = instant(p["issued_at_utc"])
            tip = instant(p["game_utc_at_issue"])
            if not all(isinstance(v, str) and v for v in key):
                raise ValueError("Missing game/player")
            b = float(p["baseline_fp_if_play"])
            c = float(p["candidate_fp_if_play"])
            if not math.isfinite(b) or not math.isfinite(c):
                raise ValueError("Non-finite forecast")
        except (KeyError, ValueError, TypeError):
            qa["invalid_prediction"] += 1
            continue
        if issued >= tip - LOCK:
            qa["after_individual_lock"] += 1
            continue
        if not _source_known_at_issue(p):
            qa["post_issue_source_leak_or_invalid_provenance"] += 1
            continue
        all_groups[key].append(p)

    final = {g.get("id"): g for g in live.get("games", [])
             if isinstance(g, dict) and g.get("status") == "final"}
    observed = defaultdict(list)
    for r in live.get("rows", []):
        if isinstance(r, dict):
            observed[(r.get("game_id"), r.get("id"))].append(r)

    compared = []
    per_status = Counter()
    multiple_versions = 0
    for key, versions in sorted(all_groups.items()):
        versions.sort(key=lambda p: (instant(p["issued_at_utc"]), p.get("revision_number", 1)))
        if any(a["issued_at_utc"] == b["issued_at_utc"] for a, b in zip(versions, versions[1:])):
            qa["conflicting_same_timestamp_versions"] += 1
            continue
        if len(versions) > 1:
            multiple_versions += 1
        earliest, latest = versions[0], versions[-1]
        tip = instant(latest["game_utc_at_issue"])
        if tip > now:
            qa["future_game"] += 1
            continue
        game = final.get(key[0])
        if not game:
            qa["not_verified_final"] += 1
            continue
        if game.get("utc") != latest["game_utc_at_issue"]:
            qa["rescheduled_or_tipoff_changed"] += 1
            continue
        if any(v.get("game_utc_at_issue") != latest["game_utc_at_issue"]
               or v.get("team") != latest["team"] for v in versions):
            qa["conflicting_fixture_or_team_revision"] += 1
            continue
        if latest["team"] not in (game.get("home"), game.get("away")):
            qa["predicted_team_not_in_final_game"] += 1
            continue
        matches = observed.get(key, [])
        if len(matches) != 1:
            qa["unknown_unmatched_or_dnp"] += 1
            continue
        row = matches[0]
        if row.get("team") != latest["team"] or row.get("played") is not True:
            qa["unknown_team_or_participation"] += 1
            continue
        try:
            if float(row["minutes"]) <= 0 or not isinstance(row["minutes"], (int, float)):
                raise ValueError("No minutes")
            actual = float(row["fp"])
            if not math.isfinite(actual):
                raise ValueError("Not finite")
        except (KeyError, ValueError, TypeError):
            qa["invalid_played_fp"] += 1
            continue
        compared.append((key, actual, earliest, latest))
        if latest.get("official_report_asof"):
            per_status["official_context_present"] += 1
        if latest.get("telegram_unverified_asof"):
            per_status["telegram_context_present_unverified"] += 1

    def metric(which, kind):
        if not compared:
            return None
        errors = [float(p[kind]) - actual for _, actual, first, last in compared
                  for p in [first if which == "first" else last]]
        return {
            "n": len(errors),
            "mae": round(sum(abs(e) for e in errors) / len(errors), 4),
            "rmse": round(math.sqrt(sum(e * e for e in errors) / len(errors)), 4),
            "bias_forecast_minus_actual": round(sum(errors) / len(errors), 4),
        }

    first_baseline = metric("first", "baseline_fp_if_play")
    first_candidate = metric("first", "candidate_fp_if_play")
    last_baseline = metric("last", "baseline_fp_if_play")
    last_candidate = metric("last", "candidate_fp_if_play")
    n = len(compared)
    days_et = set()
    for (game_id, _), _, _, _ in compared:
        game = final[game_id]
        day = game.get("et_date")
        if not isinstance(day, str) or len(day) != 10:
            day = instant(game["utc"]).astimezone(
                ZoneInfo("America/New_York")).date().isoformat()
        days_et.add(day)
    game_count = len({key[0] for key, _, _, _ in compared})
    player_count = len({key[1] for key, _, _, _ in compared})
    revisions_evaluated = [(key, actual, first, last)
                           for key, actual, first, last in compared
                           if first["issued_at_utc"] != last["issued_at_utc"]]
    candidate_revision_gain = (
        round(sum(abs(float(first["candidate_fp_if_play"]) - actual) -
                  abs(float(last["candidate_fp_if_play"]) - actual)
                  for _, actual, first, last in revisions_evaluated) /
              len(revisions_evaluated), 4)
        if revisions_evaluated else None)
    paired_gain = (round(sum(
        abs(float(last["baseline_fp_if_play"]) - actual) -
        abs(float(last["candidate_fp_if_play"]) - actual)
        for _, actual, _, last in compared) / n, 4) if n else None)
    ci = _game_cluster_gain_interval(compared)
    # These minimums are conservative exploratory guardrails, NOT a claim
    # that their satisfaction alone establishes out-of-time model quality.
    longitudinal_coverage = len(days_et) >= 4 and game_count >= 20
    revision_sample_ready = (len(revisions_evaluated) >= 30 and
                             len(days_et) >= 4)
    improvement = (round(100 * (last_baseline["mae"] - last_candidate["mae"]) /
                         last_baseline["mae"], 2)
                   if n >= 30 and last_baseline["mae"] > 0 else None)
    return {
        "schema_version": 3, "status": "research_only_not_deployed",
        "evaluated_at_utc": stamp(now),
        "issued_rows": len(pred.get("issued", [])),
        "unique_player_game_forecasts": len(all_groups),
        "player_games_with_revisions": multiple_versions,
        "paired_played_games": n,
        "baseline_mae": last_baseline["mae"] if last_baseline else None,
        "candidate_mae": last_candidate["mae"] if last_candidate else None,
        "first_issue": {"baseline": first_baseline, "candidate": first_candidate},
        "latest_prelock_issue": {"baseline": last_baseline, "candidate": last_candidate},
        "latest_candidate_mae_improvement_pct_descriptive_only": improvement,
        "paired_reliability": {
            "unit_of_analysis": "one_played_player_game_even_if_revised",
            "independent_resampling_unit": "completed_NBA_game",
            "distinct_completed_games": game_count,
            "distinct_players": player_count,
            "distinct_ET_game_dates": len(days_et),
            "ET_dates_seen": sorted(days_et),
            "played_player_games_with_evaluable_prelock_revisions":
                len(revisions_evaluated),
            "first_to_last_candidate_mae_gain_on_revised_only_fp":
                candidate_revision_gain,
            "first_to_last_revision_quality_evaluable": revision_sample_ready,
            "candidate_vs_baseline_paired_mae_gain_fp": paired_gain,
            "game_cluster_95pct_gain_interval_fp": ci,
            "candidate_gain_excludes_zero_in_exploratory_interval":
                bool(ci and ci["lower"] > 0 and longitudinal_coverage),
            "longitudinal_games_and_dates_gate": longitudinal_coverage,
            "full_population_and_decision_value_gate": False,
            "adoption_ready": False,
            "cautions": [
                "Only played outcomes from selected completed games; no population p_play or DNP denominator.",
                "Players in one NBA game are correlated; 130 player-games on one ET date are not 130 independent game days.",
                "Game-bootstrap interval is descriptive and unreliable with very few dates/clusters.",
                "Unobserved revised predictions cannot establish that updates improve decision-time forecasts.",
                "No actual Sports.ru price, account, KEEP/TRANSFER regret or net weekly FP is evaluated.",
            ],
        },
        "qa": dict(qa), "source_context_in_evaluated": dict(per_status),
        "sample_sufficient_for_adoption": False,
        "full_fantasy_population_coverage_proven": False,
        "adopt_on_site": False,
        "warning": "Only validated played games. Unknown DNP/missing rows excluded; "
                   "repeated revisions not independent; no Brier/KEEP-transfer gain proven.",
    }


def run():
    now = datetime.now(UTC)
    archive_path = DATA / "played_fp_shadow_predictions.json"
    old = json.loads(archive_path.read_text(encoding="utf8")) if archive_path.exists() else None
    live = read("live.json")
    issued, issue_qa = issue(
        old, live, read("catalog.json"),
        history_means(read("history/index.json")),
        read("rolling_decision_research.json"), now,
        read("official_injury_status_archive.json"),
        read("telegram_archive.json"),
    )
    result = audit(issued, live, now)
    for path, value in [(archive_path, issued),
                        (DATA / "played_fp_shadow_audit.json", result)]:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf8")
        tmp.replace(path)
    return {"issue": issue_qa, "audit": {
        k: result[k] for k in ("status", "issued_rows",
                               "unique_player_game_forecasts", "paired_played_games",
                               "player_games_with_revisions", "qa")}}
if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
