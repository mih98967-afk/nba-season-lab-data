"""Prospective rolling NBA decision clock and data-ingestion snapshots.

Research only. A usable decision can happen at ANY checked time in the Moscow
calendar week, not only Monday 15:00. Forecast inputs change when a finalized
match is FIRST OBSERVED in a live feed, not retrospectively at tip-off.
No prices, rosters, transfers, personal accounts or medical probabilities.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
from src.sync import DATA

UTC = timezone.utc
MSK = ZoneInfo("Europe/Moscow")
LOCK = timedelta(minutes=30)
PREVIOUS_GAME_REVIEW = timedelta(hours=12)
VALID_STATUSES = {"out", "doubtful", "questionable", "probable", "available"}


def instant(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string with timezone")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return t.astimezone(UTC)


def stamp(t):
    if t.utcoffset() is None:
        raise ValueError("Timezone-aware moment required")
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf8")).hexdigest()


def week_key(t):
    local = t.astimezone(MSK)
    return (local.date() - timedelta(days=local.weekday())).isoformat()


def transfer_clock(club, schedule, asof):
    """Timing evidence only, NEVER 'transfer is executable'.

    After kickoff, Sports.ru unlock time is unverified. The Monday 15:00
    reference is deliberately absent from eligibility. Both OUT and IN
    candidates must be evaluated at the SAME proposed transfer timestamp.
    """
    if not isinstance(club, str) or not club:
        return {"status": "unknown_team", "can_claim_executable": False}
    if asof.utcoffset() is None:
        raise ValueError("Timezone required")
    asof = asof.astimezone(UTC)
    fixtures = []
    for g in schedule or []:
        if not isinstance(g, dict) or club not in (g.get("home"), g.get("away")):
            continue
        if g.get("status") in ("canceled", "cancelled"):
            continue
        try:
            t = instant(g["utc"])
        except (ValueError, KeyError, TypeError):
            continue
        fixtures.append(t)
    if not fixtures:
        return {"status": "unknown_schedule_or_team", "can_claim_executable": False}
    if any(t - LOCK <= asof < t for t in fixtures):
        return {"status": "blocked_30_minutes_before_game", "can_claim_executable": False}
    if any(t <= asof < t + PREVIOUS_GAME_REVIEW for t in fixtures):
        return {"status": "postgame_unlock_unverified", "can_claim_executable": False}
    return {"status": "no_scheduled_lock_detected_manual_sportsru_check",
            "can_claim_executable": False}


def official_asof(archive, game_id, player_id, club, cutoff):
    """Only exact player, fixture, club and independently observed reports."""
    cutoff = cutoff.astimezone(UTC)
    choices = []
    for e in (archive or {}).get("events", []):
        if not isinstance(e, dict):
            continue
        if (e.get("game_id"), e.get("player_id"), e.get("team")) != (game_id, player_id, club):
            continue
        if e.get("status") not in VALID_STATUSES:
            continue
        try:
            seen, reported, tip = (instant(e[k]) for k in
                                   ("first_seen_at_utc", "report_at_utc", "tipoff_utc"))
        except (ValueError, KeyError, TypeError):
            continue
        if max(seen, reported) > cutoff or max(seen, reported) >= tip:
            continue
        if e.get("team") not in (e.get("home"), e.get("away")):
            continue
        choices.append((max(seen, reported), reported, str(e.get("event_id", "")), e, seen))
    if not choices:
        return None
    effective, reported, event_id, e, seen = max(choices, key=lambda x: (x[0], x[1], x[2]))
    return {"status": e["status"], "report_at_utc": stamp(reported),
            "first_seen_at_utc": stamp(seen), "event_id": event_id,
            "source": "official_pdf_observed", "source_url": e.get("source_url"),
            "known_asof_utc": stamp(cutoff)}


def telegram_asof(archive, player_id, cutoff, lookback=timedelta(hours=72)):
    """Player-level unverified news: NOT a game-specific confirmed status."""
    cutoff = cutoff.astimezone(UTC)
    candidates = []
    for e in (archive or {}).get("events", []):
        if not isinstance(e, dict) or e.get("player_ids") != [player_id]:
            continue
        if (e.get("verification") != "unconfirmed_telegram" or
            e.get("match_quality") != "full_name" or
            not str(e.get("url", "")).startswith("https://t.me/nba_injurynews/")):
            continue
        try:
            seen = instant(e["first_seen_at"])
            published = instant(e["published_at"])
        except (ValueError, KeyError, TypeError):
            continue
        if seen > cutoff or published > cutoff or published < cutoff - lookback:
            continue
        candidates.append((max(seen, published), str(e.get("id", "")), e, seen, published))
    if not candidates:
        return None
    _, event_id, e, seen, published = max(candidates, key=lambda r: (r[0], r[1]))
    return {"status": e.get("status"), "first_seen_at_utc": stamp(seen),
            "published_at_utc": stamp(published), "event_id": event_id,
            "source": "unconfirmed_telegram_player_only", "fixture_verified": False}


def available_evidence(live, official, telegram, asof):
    """Player-game examples available NOW, without reconstructing past decisions."""
    quality = live.get("schedule_quality") or {}
    if quality.get("freshness") != "fresh":
        return {"status": "calendar_not_verified_fresh", "candidates": 0,
                "official_known": 0, "telegram_player_context": 0,
                "blocked_or_unverified_clock": 0}
    games = {g.get("id"): g for g in live.get("schedule", [])
             if isinstance(g, dict) and g.get("id")}
    cohorts = {(e.get("game_id"), e.get("player_id"), e.get("team"))
               for e in official.get("events", []) if isinstance(e, dict)
               and e.get("game_id") and e.get("player_id") and e.get("team")}
    counts = Counter()
    for game_id, player_id, club in cohorts:
        game = games.get(game_id)
        if not game:
            counts["missing_fixture"] += 1
            continue
        try:
            tip = instant(game["utc"])
        except (ValueError, KeyError, TypeError):
            counts["invalid_fixture"] += 1
            continue
        if asof >= tip - LOCK:
            counts["already_locked_or_started"] += 1
            continue
        if transfer_clock(club, live["schedule"], asof)["status"] != "no_scheduled_lock_detected_manual_sportsru_check":
            counts["blocked_or_unverified_clock"] += 1
            continue
        counts["candidates"] += 1
        if official_asof(official, game_id, player_id, club, asof):
            counts["official_known"] += 1
        if telegram_asof(telegram, player_id, asof):
            counts["telegram_player_context"] += 1
    return {"status": "research_source_coverage_only_no_transfer_permission",
            **{k: counts[k] for k in ("candidates", "official_known",
                 "telegram_player_context", "blocked_or_unverified_clock",
                 "already_locked_or_started", "missing_fixture", "invalid_fixture")}}


def player_games(live, now):
    """Only actually observed played rows with Sports.ru FP; no inferred zeros."""
    selected = {}
    excluded = Counter()
    for row in live.get("rows", []):
        if not isinstance(row, dict):
            excluded["not_an_object"] += 1
            continue
        key = (row.get("game_id"), row.get("id"))
        try:
            if not all(isinstance(k, str) and k for k in key):
                raise ValueError("No player or game ID")
            when = instant(row["utc"])
            if when > now:
                raise ValueError("Future game row")
            if row.get("played") is not True:
                raise ValueError("Not verified played")
            if not isinstance(row.get("minutes"), (int, float)) or row["minutes"] <= 0:
                raise ValueError("Missing played minutes")
            if not isinstance(row.get("fp"), (int, float)) or not (-150 <= row["fp"] <= 250):
                raise ValueError("Invalid Sports.ru FP")
            if not isinstance(row.get("team"), str) or not row["team"]:
                raise ValueError("Missing NBA team")
        except (KeyError, TypeError, ValueError):
            excluded["invalid_or_future"] += 1
            continue
        if key in selected:
            raise ValueError("Duplicate player-game rows; refuse snapshot")
        selected[key] = {"game_id": key[0], "player_id": key[1],
                         "team": row["team"], "fp": row["fp"],
                         "minutes": row["minutes"], "utc": stamp(when)}
    return selected, dict(excluded)


def advance(prior, live, official, telegram, now):
    """Immutable-time research checkpoint: never claim earlier knowledge.

    Snapshots run when newly ingested boxscores or first-seen source changes
    occur. Initial input is a BOOTSTRAP, not a historical PIT backtest.
    """
    if now.utcoffset() is None:
        raise ValueError("Aware now required")
    now = now.astimezone(UTC)
    when = stamp(now)
    if live.get("schema_version") != 4 or not isinstance(live.get("schedule"), list):
        raise ValueError("Invalid live feed schema")
    live_at = instant(live["updated_at_utc"])
    if live_at > now + timedelta(minutes=5):
        raise ValueError("Live feed date is in the future")
    if (prior or {}).get("schema_version") not in (None, 1):
        raise ValueError("Unknown research archive version")
    previous = prior or {}
    checkpoints = list(previous.get("snapshots", []))
    if checkpoints and now <= instant(checkpoints[-1]["captured_at_utc"]):
        raise ValueError("Snapshots must advance in UTC; no backdating")
    current, excluded = player_games(live, now)
    previous_hashes = dict(previous.get("row_hashes", {}))
    current_hashes = {f"{gid}|{pid}": canonical_hash(v) for (gid, pid), v in current.items()}
    disappeared = set(previous_hashes) - set(current_hashes)
    if disappeared:
        raise ValueError("Previously observed FP rows disappeared; preserve archive")
    changed = [key for key in current_hashes if current_hashes[key] != previous_hashes.get(key)]
    corrected = [key for key in changed if key in previous_hashes]

    # Keep the earliest real capture time for a score row. Corrections are
    # versioned as later snapshots, never rewritten into the earlier cutoff.
    first_seen = dict(previous.get("row_first_seen_at_utc", {}))
    for key in changed:
        first_seen.setdefault(key, when)

    events = []
    for e in official.get("events", []):
        if not isinstance(e, dict):
            continue
        try:
            if max(instant(e["first_seen_at_utc"]), instant(e["report_at_utc"])) <= now:
                events.append((str(e.get("event_id")), str(e.get("status")),
                               e["first_seen_at_utc"], e["report_at_utc"]))
        except (ValueError, KeyError, TypeError):
            continue
    news = []
    for e in telegram.get("events", []):
        if not isinstance(e, dict):
            continue
        try:
            if max(instant(e["first_seen_at"]), instant(e["published_at"])) <= now:
                news.append((str(e.get("id")), e["first_seen_at"], e["published_at"],
                             str(e.get("status"))))
        except (ValueError, KeyError, TypeError):
            continue
    evidence_hash = canonical_hash({"official": sorted(events), "telegram": sorted(news)})
    if not changed and evidence_hash == previous.get("evidence_hash") and checkpoints:
        return previous, {"result": "no_new_observation", "captured_at_utc": checkpoints[-1]["captured_at_utc"]}

    groups = defaultdict(list)
    for entry in current.values():
        groups[entry["player_id"]].append(entry)
    updated_players = sorted({key.split("|", 1)[1] for key in changed})
    form = {}
    for pid in updated_players:
        rows = sorted(groups[pid], key=lambda r: (r["utc"], r["game_id"]))
        recent = rows[-5:]
        form[pid] = {"current_season_played_games": len(rows),
                     "last_5_played_game_fp_mean": round(sum(r["fp"] for r in recent)/len(recent), 3),
                     "last_observed_game_utc": rows[-1]["utc"],
                     "feature_only_not_p_play": True}

    completed = {g.get("id") for g in live.get("games", [])
                 if isinstance(g, dict) and g.get("status") == "final" and g.get("id")}
    indexed = defaultdict(set)
    for game_id, player_id in current:
        indexed[game_id].add(player_id)
    ingested = {game_id for game_id in completed if len(indexed.get(game_id, [])) >= 10}
    old_ingested = set(previous.get("observed_final_game_ids", []))
    if old_ingested - ingested:
        raise ValueError("Previously observed final games disappeared")
    new_finals = sorted(ingested - old_ingested)
    observed_evidence = available_evidence(live, official, telegram, now)
    checkpoint = {
        "captured_at_utc": when,
        "input_live_updated_at_utc": stamp(live_at),
        "input_age_hours": round((now-live_at).total_seconds()/3600, 2),
        "calendar_freshness_at_capture": (live.get("schedule_quality") or {}).get("freshness", "unknown"),
        "bootstrap_prior_matches_not_retroactively_available": not bool(checkpoints),
        "newly_observed_final_games": new_finals,
        "new_or_changed_player_game_rows": len(changed),
        "corrected_rows": len(corrected),
        "changed_player_count": len(updated_players),
        "rolling_played_fp_form_features": form,
        "official_observed_events": len(events),
        "unconfirmed_telegram_observed_events": len(news),
        "injury_context_asof_capture": observed_evidence,
        "not_a_calibrated_expected_fp_prediction": True,
    }
    checkpoints.append(checkpoint)
    result = {
        "schema_version": 1,
        "status": "research_only_not_deployed",
        "model_status": "research_only_not_deployed",
        "adopt_on_site": False,
        "updated_at_utc": when,
        "first_capture_at_utc": checkpoints[0]["captured_at_utc"],
        "observation_semantics": "Only changes FIRST OBSERVED at capture, never at game tipoff. A 4-hour workflow is not real-time.",
        "transaction_semantics": "Any intraweek time subject to exact player locks and manual Sports.ru price, quota, unlock and confirmed-roster checks. Monday 15 is not a universal trade gate.",
        "features_semantics": "Observed played-game FP form only; no calibrated p_play or expected fantasy FP; not a transfer backtest.",
        "row_hashes": current_hashes,
        "row_first_seen_at_utc": first_seen,
        "observed_final_game_ids": sorted(ingested),
        "evidence_hash": evidence_hash,
        "snapshots": checkpoints,
        "invalid_rows_excluded_latest": excluded,
    }
    return result, {"result": "new_capture", "captured_at_utc": when,
                    "newly_observed_final_games": len(new_finals),
                    "rows_changed": len(changed), "captures": len(checkpoints)}


def run():
    def read(name):
        return json.loads((DATA/name).read_text(encoding="utf8"))
    target = DATA/"rolling_decision_research.json"
    old = json.loads(target.read_text(encoding="utf8")) if target.exists() else {}
    out, summary = advance(old, read("live.json"),
                           read("official_injury_status_archive.json"),
                           read("telegram_archive.json"), datetime.now(UTC))
    if out != old:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                       encoding="utf8")
        tmp.replace(target)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
