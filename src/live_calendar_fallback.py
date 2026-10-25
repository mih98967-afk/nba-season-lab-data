"""Strict public ESPN season-calendar fallback for the NBA CDN HTTP 403 case.

A verified, already-published 30-team calendar is safer than silently
replacing the live schedule with []. This module does NOT download from the
internet or access private accounts. Any stale calendar is explicitly flagged.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
MSK = ZoneInfo("Europe/Moscow")
TEAMS = set("ATL BOS BKN CHA CHI CLE DAL DEN DET GSW HOU IND LAC LAL MEM MIA MIL MIN NOP NYK OKC ORL PHI PHX POR SAC SAS TOR UTA WAS".split())
VALID_STATES = {"scheduled", "final", "live", "postponed", "canceled", "cancelled"}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing calendar ISO timestamp")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != dt.timedelta(0):
        raise ValueError("Calendar timestamp must explicitly be UTC")
    return parsed.astimezone(UTC)


def moscow_week(moment):
    local = moment.astimezone(MSK).date()
    return (local - dt.timedelta(days=local.weekday())).isoformat()


def verified_fallback(blob, now=None):
    """Return (copy of valid games, objective quality), else fail closed.

    Staleness is visible, not silently rewritten as a fresh NBA.com success.
    The 30 yet-unassigned NBA Cup games remain absent and never fabricated.
    """
    now = now or dt.datetime.now(UTC)
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware now required")
    now = now.astimezone(UTC)
    if not isinstance(blob, dict) or blob.get("status") != "verified_public_calendar_with_known_gaps":
        raise ValueError("Only validated ESPN season calendar may be used")
    games = blob.get("games")
    if not isinstance(games, list) or not 1100 <= len(games) <= 1230:
        raise ValueError("Full-season coverage outside 1100..1230")
    updated = timestamp(blob.get("updated_at_utc"))
    age_hours = round((now - updated).total_seconds() / 3600, 2)
    if age_hours < -0.25:
        raise ValueError("Calendar validation time is in the future")
    counts = Counter()
    unique_ids = set()
    unique_matchups = set()
    for g in games:
        if not isinstance(g, dict):
            raise ValueError("Calendar contains non-object game")
        event_id = g.get("id")
        if not isinstance(event_id, str) or not event_id.startswith("espn_") or event_id in unique_ids:
            raise ValueError("Calendar game ID missing/duplicated")
        unique_ids.add(event_id)
        home, away = g.get("home"), g.get("away")
        if home not in TEAMS or away not in TEAMS or home == away:
            raise ValueError("Calendar has invalid NBA clubs")
        if g.get("status") not in VALID_STATES:
            raise ValueError("Invalid calendar game status")
        moment = timestamp(g.get("utc"))
        if not isinstance(g.get("epoch"), int) or abs(g["epoch"] - moment.timestamp() * 1000) > 1000:
            raise ValueError("Calendar time/epoch mismatch")
        et_day = moment.astimezone(ET).date().isoformat()
        if g.get("et_date") != et_day or g.get("msk_date") != moment.astimezone(MSK).date().isoformat():
            raise ValueError("Calendar day is not exact in ET/MSK")
        if g.get("msk_week") != moscow_week(moment):
            raise ValueError("Wrong Moscow Monday boundary")
        key = (et_day, home, away)
        if key in unique_matchups:
            raise ValueError("Duplicated same-day NBA matchup")
        unique_matchups.add(key)
        if g["status"] not in ("canceled", "cancelled"):
            counts.update((home, away))
    if set(counts) != TEAMS or min(counts.values()) < 70:
        raise ValueError("Missing NBA teams/insufficient season coverage")
    known_gaps = max(0, 1230 - sum(counts.values()) // 2)
    if known_gaps > 130:
        raise ValueError("Too many unknown NBA games")
    return [dict(g) for g in games], {
        "source": blob.get("source", "ESPN verified season calendar"),
        "validated_at_utc": blob["updated_at_utc"],
        "age_hours": age_hours,
        "freshness": "stale_requires_review" if age_hours > 36 else "fresh",
        "games": len(games),
        "teams": len(counts),
        "unassigned_games": known_gaps,
        "warning": "NBA Cup unassigned fixtures and reschedules are not invented",
        "complete": False if known_gaps else True,
    }
