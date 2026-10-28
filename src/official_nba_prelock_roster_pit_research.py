"""Prospective official NBA game-specific roster snapshot. Research only.

This is a pre-lock observation of an NBA public LIVE boxscore, not the
publication time or a guarantee of eligibility. Missing/unavailable is UNKNOWN.
Never use after-lock observations as pre-lock evidence.
"""
from datetime import datetime, timedelta, timezone
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from src.official_nba_gameday_status_research import (
    BOX_PREFIX, SCHEDULE_URL, fetch_public_json, official_schedule,
    fixture_match, code, utc, stamp, digest,
)
from src.sync import DATA
from src.rolling_decision_research import canonical_hash
import json
import re

STATUS = "research_only_not_deployed"
LOCK = timedelta(minutes=30)
MAX_GAMES = 16
MAX_BYTES = 5_000_000


def extract_pregame(payload, fixture):
    """Never promote a current NBA roster to a confirmed active game-day denominator."""
    game = payload.get("game")
    if not isinstance(game, dict) or str(game.get("gameId")) != fixture["id"]:
        raise ValueError("Wrong official NBA game ID")
    if str(game.get("gameStatus")) != "1":
        raise ValueError("Not a live pre-final boxscore")
    if abs(utc(game["gameTimeUTC"]) - utc(fixture["utc"])) > timedelta(minutes=5):
        raise ValueError("Official NBA game time mismatch")
    teams = []
    seen = set()
    for side in ("homeTeam", "awayTeam"):
        team = game.get(side) or {}
        club = code(team.get("teamTricode"))
        expected = fixture["home"] if side == "homeTeam" else fixture["away"]
        if club != expected:
            raise ValueError("Official NBA team mismatch")
        people = team.get("players")
        if not isinstance(people, list):
            return None  # Not a complete observable roster; never infer missing players
        ids = []
        for p in people:
            pid = str(p.get("personId") or "")
            if not pid.isdigit() or pid in seen:
                raise ValueError("Invalid or duplicated player ID")
            ids.append(pid)
            seen.add(pid)
        if len(ids) < 8 or len(ids) > 35:
            return None
        teams.append({"club": club, "person_ids": sorted(ids)})
    return teams


def capture(live, schedule, fetch, now, old=None, *, clock=None):
    if now.utcoffset() is None:
        raise ValueError("Capture requires aware clock")
    now = now.astimezone(timezone.utc)
    # Production uses the real clock AFTER each response, never before fetch.
    # Explicit clock injection is only for deterministic offline regression tests.
    clock = clock or (lambda: datetime.now(timezone.utc))
    if live.get("schema_version") != 4:
        raise ValueError("Invalid live source")
    official = official_schedule(schedule)
    old = old or {}
    snapshots = list(old.get("snapshots", []))
    previous = {s["espn_game_id"]: s for s in snapshots}
    if len(previous) != len(snapshots):
        raise ValueError("Duplicate old first observations")
    for s in snapshots:
        if (s.get("adopt_on_site") is not False or s.get("status") != STATUS
                or utc(s["source_first_observed_at_utc"]) > now
                or utc(s["source_first_observed_at_utc"]) >= utc(s["individual_lock_utc"])
                or s.get("game_day_active_eligibility_verified") is not False
                or s.get("missing_player_implies_DNP") is not False
                or s.get("snapshot_hash_sha256") != canonical_hash({
                    k: v for k, v in s.items() if k != "snapshot_hash_sha256"})):
            raise ValueError("Untrusted immutable historical observation")
    qa = Counter({"considered": 0, "new": 0, "unknown_or_unavailable": 0})
    def unavailable(why):
        qa["unknown_or_unavailable"] += 1
        qa[why] += 1
    games = [g for g in live.get("schedule", []) if
             g.get("status") == "scheduled" and g.get("id") not in previous
             and LOCK < utc(g["utc"]) - now <= timedelta(hours=6)]
    for game in sorted(games, key=lambda x: (x["utc"], x["id"]))[:MAX_GAMES]:
        qa["considered"] += 1
        matched, reason = fixture_match(game, official)
        lock = utc(game["utc"]) - LOCK
        if matched is None:
            unavailable("fixture_unmatched_or_ambiguous")
            continue
        if now >= lock:
            unavailable("lock_already_elapsed")
            continue
        try:
            payload = fetch(BOX_PREFIX + matched["id"] + ".json")
            roster = extract_pregame(payload, matched)
        except HTTPError as exc:
            unavailable("nba_box_http_" + str(exc.code))
            continue
        except (URLError, OSError, TimeoutError):
            unavailable("nba_box_network_unavailable")
            continue
        except (ValueError, TypeError, KeyError, AttributeError):
            unavailable("nba_box_schema_or_status_invalid")
            continue
        # Conservative first-observation: the full body has been fetched and
        # parsed. A source request started before lock is NOT sufficient.
        observed_at = clock()
        if observed_at.utcoffset() is None:
            raise ValueError("Naive source completion clock")
        observed_at = observed_at.astimezone(timezone.utc)
        if observed_at < now:
            raise ValueError("Source completion predates job observation clock")
        if observed_at >= lock:
            unavailable("source_finished_at_or_after_lock")
            continue
        if observed_at - now > timedelta(minutes=15):
            unavailable("source_scrape_exceeded_15_minutes")
            continue
        if roster is None:
            unavailable("nba_box_incomplete_pregame_listing")
            continue
        row = {"status": STATUS, "adopt_on_site": False,
               "espn_game_id": game["id"], "nba_game_id": matched["id"],
               "game_utc": game["utc"], "individual_lock_utc": stamp(lock),
               "source_first_observed_at_utc": stamp(observed_at),
               "nba_source_url": BOX_PREFIX + matched["id"] + ".json",
               "source_canonical_sha256": digest(payload),
               "teams": roster,
               "game_day_active_eligibility_verified": False,
               "missing_player_implies_DNP": False,
               "observed_club_listing_only": True}
        row["snapshot_hash_sha256"] = canonical_hash(row)
        snapshots.append(row)
        previous[game["id"]] = row
        qa["new"] += 1
    if qa["new"] + qa["unknown_or_unavailable"] != qa["considered"]:
        raise ValueError("PIT capture diagnostics missing cases")
    return {"schema_version": 1, "status": STATUS, "adopt_on_site": False,
            "source": "official NBA live game-specific boxscore observed before lock",
            "snapshots": sorted(snapshots, key=lambda s: (s["source_first_observed_at_utc"], s["espn_game_id"])),
            "qa": dict(qa), "prelock_game_day_denominator_verified": False,
            "unknown_is_not_DNP": True,
            "model_training_permitted": False,
            "limitations": ["First observation is sealed after each complete source fetch, not its request start or NBA publication.",
                            "A listed player is not necessarily eligible or active.",
                            "Not listed, unavailable, or after lock remains UNKNOWN.",
                            "Never backfill pre-lock observations from completed games."]}


def run():
    load = lambda p: json.loads((DATA / p).read_text(encoding="utf8"))
    path = DATA / "official_nba_prelock_roster_pit_research.json"
    old = load(path.name) if path.exists() else {}
    try:
        schedule = fetch_public_json(SCHEDULE_URL)
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError):
        return {"status": STATUS, "capture": "source_unavailable_UNKNOWN"}
    # The source schedule is fetched first; no future capture can be backdated
    # to the job start or schedule request start.
    result = capture(load("live.json"), schedule, fetch_public_json,
                     datetime.now(timezone.utc), old)
    if result["qa"]["new"]:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
        tmp.replace(path)
    return {"status": STATUS, "qa": result["qa"], "adopt_on_site": False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
