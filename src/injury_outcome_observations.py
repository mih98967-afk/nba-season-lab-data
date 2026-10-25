"""Prospective NBA injury-report outcome audit; research only, never p_play deployment.

Unit of analysis is ONE (Sports.ru player_id, scheduled NBA game_id), not an
individual PDF observation. Statuses must be independently first-observed
before player lock. Missing active-boxscore rows remain UNKNOWN, never DNP.
Telegram is unconfirmed, player-level context (NOT verified for this game).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
from src.sync import DATA

UTC = timezone.utc
MSK = ZoneInfo("Europe/Moscow")
STATUS = {"out", "doubtful", "questionable", "probable", "available"}
MIN_TEAM_PLAYERS = 5


def instant(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if moment.utcoffset() is None:
        raise ValueError("Naive timestamp")
    return moment.astimezone(UTC)


def utc_string(moment):
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def monday_deadline(tipoff):
    """Sports.ru weekly decision Monday 15:00 MSK, NOT the individual lock."""
    local = tipoff.astimezone(MSK)
    monday = local.date() - timedelta(days=local.weekday())
    return datetime(monday.year, monday.month, monday.day, 15, tzinfo=MSK).astimezone(UTC)


def telegram_context(telegram, player_id, tipoff, lock, now):
    """Only player-level context, never a fixture/team-specific medical fact."""
    options = []
    for e in (telegram or {}).get("events", []):
        if not isinstance(e, dict) or e.get("player_ids") != [player_id]:
            continue
        if e.get("match_quality") != "full_name" or e.get("verification") != "unconfirmed_telegram":
            continue
        if not str(e.get("url", "")).startswith("https://t.me/nba_injurynews/"):
            continue
        try:
            published, seen = instant(e["published_at"]), instant(e["first_seen_at"])
        except (KeyError, ValueError, TypeError):
            continue
        if published > lock or seen > lock or seen > now:
            continue
        if published < tipoff - timedelta(hours=72):
            continue
        options.append((max(published, seen), str(e.get("id", "")), e, published, seen))
    if not options:
        return None
    _, event_id, e, published, seen = max(options, key=lambda p: (p[0], p[1]))
    return {
        "signal_id": event_id,
        "status": e.get("status"),
        "published_at": utc_string(published),
        "first_seen_at": utc_string(seen),
        "url": e.get("url"),
        "fixture_verified": False,
        "verification": "unconfirmed_player_context_only",
    }


def evaluate(archive, live, now, telegram=None):
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware now required")
    now = now.astimezone(UTC)
    if archive.get("status") != "official_report_observed_pit_research_only":
        raise ValueError("Wrong official injury archive status")
    if not isinstance(live.get("rows"), list) or not isinstance(live.get("games"), list):
        raise ValueError("Missing live outcomes")

    # Published schedule is used to check fixture identity and tipoff if supplied.
    fixtures = {g.get("id"): g for g in live.get("schedule", [])
                if isinstance(g, dict) and g.get("id")}
    final = {g.get("id"): g for g in live["games"]
             if isinstance(g, dict) and g.get("status") == "final"}
    box = defaultdict(list)
    for row in live["rows"]:
        if isinstance(row, dict) and row.get("game_id") and row.get("id"):
            box[row["game_id"]].append(row)

    qa = Counter()
    cohorts = defaultdict(list)
    unique_event_ids = set()
    for e in archive.get("events", []):
        if not isinstance(e, dict):
            qa["malformed"] += 1
            continue
        event_id = e.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            qa["missing_event_id"] += 1
            continue
        if event_id in unique_event_ids:
            qa["duplicate_event_id"] += 1
            continue
        unique_event_ids.add(event_id)
        if e.get("status") not in STATUS:
            qa["invalid_status"] += 1
            continue
        if not all(isinstance(e.get(key), str) and e[key] for key in
                   ("game_id", "player_id", "team", "home", "away")):
            qa["missing_identity_or_club"] += 1
            continue
        if e["home"] == e["away"] or e["team"] not in (e["home"], e["away"]):
            qa["team_fixture_mismatch"] += 1
            continue
        try:
            tipoff = instant(e["tipoff_utc"])
            seen = instant(e["first_seen_at_utc"])
            reported = instant(e["report_at_utc"])
        except (KeyError, ValueError, TypeError):
            qa["invalid_timestamp"] += 1
            continue
        locked_at = tipoff - timedelta(minutes=30)
        if seen > locked_at or reported > locked_at:
            qa["not_known_before_lock"] += 1
            continue
        if seen > now or reported > now:
            qa["not_observed_yet"] += 1
            continue
        fixture = fixtures.get(e["game_id"])
        if fixture:
            if (fixture.get("home"), fixture.get("away")) != (e["home"], e["away"]):
                qa["schedule_club_conflict"] += 1
                continue
            try:
                if instant(fixture["utc"]) != tipoff:
                    qa["schedule_tipoff_changed"] += 1
                    continue
            except (KeyError, ValueError, TypeError):
                qa["schedule_invalid_tipoff"] += 1
                continue
        cohorts[(e["game_id"], e["player_id"])].append((e, tipoff, seen, reported))

    by_status = defaultdict(Counter)
    records = []
    for (game_id, player_id), versions in sorted(cohorts.items()):
        clubs = {(v[0]["team"], v[0]["home"], v[0]["away"], v[1]) for v in versions}
        if len(clubs) != 1:
            qa["conflicting_player_team_or_fixture"] += 1
            continue
        if len(versions) > 1:
            qa["superseded_pdf_observations"] += len(versions) - 1
            qa["player_games_with_multiple_reports"] += 1
        if len({v[0]["status"] for v in versions}) > 1:
            qa["player_games_with_status_revision"] += 1

        e, tipoff, seen, reported = max(
            versions, key=lambda v: (max(v[2], v[3]), v[3], str(v[0]["event_id"])))
        locked_at = tipoff - timedelta(minutes=30)
        weekly = monday_deadline(tipoff)
        weekly_known = (weekly <= locked_at and seen <= weekly and reported <= weekly)
        if weekly_known:
            qa["known_at_monday_15_msk"] += 1
        else:
            qa["not_known_at_monday_15_msk"] += 1

        row = {
            "game_id": game_id, "player_id": player_id, "team": e["team"],
            "home": e["home"], "away": e["away"],
            "tipoff_utc": utc_string(tipoff), "individual_lock_utc": utc_string(locked_at),
            "weekly_deadline_utc": utc_string(weekly),
            "official_known_by_weekly_deadline": weekly_known,
            "official_status": e["status"], "official_event_id": e["event_id"],
            "official_report_at_utc": utc_string(reported),
            "official_first_seen_at_utc": utc_string(seen),
            "official_source_url": e.get("source_url"),
            "official_versions_observed_before_lock": len(versions),
            "telegram_context": telegram_context(telegram, player_id, tipoff, locked_at, now),
            "outcome": "unknown", "membership_evidence": "unknown",
        }
        if row["telegram_context"]:
            qa["telegram_context_unverified"] += 1
        if tipoff > now:
            row["outcome"] = "future_game"
            qa["future_game"] += 1
        elif game_id not in final:
            row["outcome"] = "not_verified_final"
            qa["not_verified_final"] += 1
        elif (final[game_id].get("home"), final[game_id].get("away")) != (e["home"], e["away"]):
            row["outcome"] = "game_team_mismatch"
            qa["game_team_mismatch"] += 1
        else:
            team_counts = Counter(b.get("team") for b in box.get(game_id, [])
                                  if b.get("played") is True)
            if team_counts[e["home"]] < MIN_TEAM_PLAYERS or team_counts[e["away"]] < MIN_TEAM_PLAYERS:
                row["outcome"] = "incomplete_active_boxscore"
                qa["insufficient_team_boxscore"] += 1
            else:
                candidates = [b for b in box[game_id]
                              if b.get("id") == player_id and b.get("team") == e["team"]]
                if len(candidates) == 0:
                    row["outcome"] = "missing_row_unknown"
                    qa["missing_row_unknown"] += 1
                elif (len(candidates) == 1 and candidates[0].get("played") is True
                      and isinstance(candidates[0].get("minutes"), (int, float))
                      and candidates[0]["minutes"] > 0
                      and isinstance(candidates[0].get("fp"), (int, float))):
                    row["outcome"] = "played_verified"
                    row["membership_evidence"] = "same_team_game_matched_active_boxscore"
                    row["minutes"] = candidates[0]["minutes"]
                    row["sports_ru_fp"] = candidates[0]["fp"]
                else:
                    row["outcome"] = "ambiguous_boxscore"
                    qa["ambiguous_boxscore"] += 1

        by_status[e["status"]][row["outcome"]] += 1
        records.append(row)

    positives = sum(r["outcome"] == "played_verified" for r in records)
    missing = sum(r["outcome"] == "missing_row_unknown" for r in records)
    return {
        "schema_version": 2,
        "status": "prospective_observation_only_no_model_adoption",
        "model_status": "research_only_not_deployed",
        "updated_at_utc": utc_string(now),
        "unit_of_analysis": "unique_sports_ru_player_id_x_verified_scheduled_game_id",
        "archive_report_events": len(archive.get("events", [])),
        "eligible_unique_player_games": len(records),
        "verified_played": positives,
        "verified_dnp": 0,
        "unlisted_unknown": missing,
        "qa": dict(qa),
        "by_status": {k: dict(v) for k, v in sorted(by_status.items())},
        "records": records,
        "outcome_policy": "Only exact played+positive minutes+same team+Sports.ru FP is positive; no independently verified negative labels yet.",
        "telegram_policy": "Context only; lacks independently established team and fixture, not used as ground truth.",
        "sample_sufficient_for_brier": False,
        "full_fantasy_pool_coverage_proven": False,
        "adopt_on_site": False,
        "warning": "No Brier/logloss/FP gain inferred from report-listed positives and unknown missing rows.",
    }


def run():
    archive = json.loads((DATA / "official_injury_status_archive.json").read_text(encoding="utf8"))
    live = json.loads((DATA / "live.json").read_text(encoding="utf8"))
    tg_path = DATA / "telegram_archive.json"
    telegram = json.loads(tg_path.read_text(encoding="utf8")) if tg_path.exists() else {}
    result = evaluate(archive, live, datetime.now(UTC), telegram)
    dest = DATA / "injury_outcome_observations.json"
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    tmp.replace(dest)
    return {key: result[key] for key in
            ("status", "eligible_unique_player_games", "verified_played", "verified_dnp", "unlisted_unknown", "qa")}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
