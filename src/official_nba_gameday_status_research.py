"""Research-only independent NBA game-specific roster/inactive evidence.

The NBA's postgame Live Boxscore has game-specific player IDs and ACTIVE /
INACTIVE fields. An athlete *missing* from it, even if officially OUT before
the game, remains UNKNOWN. Never rewrite ESPN DNP, p_play, user data or site.

All time-sensitive *features* stay frozen in earlier PIT archives; this
module captures only postgame evidence, observed at actual retrieval time.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
import re

BASE = Path(__file__).resolve().parents[1] / "data"
STATUS = "research_only_not_deployed"
SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"
BOX_PREFIX = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_"
MAX_GAMES = 18
MAX_CASES = 150
VERIFIED = {"VERIFIED_GAME_DAY_INACTIVE", "VERIFIED_ACTIVE_NONPLAY"}
TEAM_ALIASES = {"GS": "GSW", "NY": "NYK", "SA": "SAS", "NO": "NOP",
                "WSH": "WAS", "UTAH": "UTA"}
from src.live_calendar_fallback import TEAMS


def utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing provenance time")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Naive provenance time")
    return parsed.astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(payload):
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def code(raw):
    return TEAM_ALIASES.get(str(raw or "").upper(), str(raw or "").upper())


def fetch_public_json(url):
    if url == SCHEDULE_URL:
        limit = 14_000_000
    elif (url.startswith(BOX_PREFIX) and url.endswith(".json")
          and re.fullmatch(r"\d{10}", url[len(BOX_PREFIX):-5])):
        limit = 5_000_000
    else:
        raise ValueError("Unsupported official source URL")
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:158.0) Gecko/20100101 Firefox/158.0",
        "Referer": "https://www.nba.com/",
        "Accept": "application/json",
    })
    with urlopen(req, timeout=23) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Official payload exceeds bounded source size")
    return json.loads(body)


def official_schedule(payload):
    """Independent ESPN->NBA fixture crosswalk; not by guessed NBA game ID."""
    dates = (payload.get("leagueSchedule") or payload.get("scheduleLeagueV2") or {}).get("gameDates")
    if not isinstance(dates, list) or not 100 <= len(dates) <= 400:
        raise ValueError("Official NBA season calendar missing/incomplete")
    out = []
    seen_ids = set()
    for date in dates:
        if not isinstance(date.get("games"), list):
            raise ValueError("Incomplete gameDate on NBA schedule")
        for game in date["games"]:
            gid = str(game.get("gameId") or "")
            if not re.fullmatch(r"00226\d{5}", gid):
                continue  # 2026/27 NBA regular season, not preseason/playoffs.
            if gid in seen_ids:
                raise ValueError("Repeated official NBA game ID")
            seen_ids.add(gid)
            home = code((game.get("homeTeam") or {}).get("teamTricode"))
            away = code((game.get("awayTeam") or {}).get("teamTricode"))
            if home not in TEAMS or away not in TEAMS:
                # Unassigned NBA Cup fixtures are not usable as match evidence.
                # They are not losses, DNP or assigned clubs.
                continue
            if home == away:
                raise ValueError("Same-club NBA official fixture")
            out.append({"id": gid, "home": home, "away": away,
                        "utc": stamp(utc(game["gameDateTimeUTC"]))})
    if len(out) < 1000:
        raise ValueError("Too few NBA regular season games in official schedule")
    return out


def fixture_match(game, schedule):
    tip = utc(game["utc"])
    candidate = [x for x in schedule if
                 x["home"] == game["home"] and x["away"] == game["away"]
                 and abs(utc(x["utc"]) - tip) <= timedelta(minutes=5)]
    if len(candidate) == 1:
        return candidate[0], None
    return None, ("official_NBA_game_id_not_matched" if not candidate
                  else "ambiguous_official_fixture_match")


def parse_minutes(raw):
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        raise ValueError("Non-string minutes")
    if re.fullmatch(r"\d+:\d{2}(?:\.\d+)?", raw):
        a, b = raw.split(":")
        return 60 * int(a) + float(b)
    matched = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", raw)
    if matched and (matched.group(1) or matched.group(2)):
        return 60 * int(matched.group(1) or 0) + float(matched.group(2) or 0)
    raise ValueError("Unrecognized NBA official minutes format")


def official_box(payload, official, espn_game):
    """Full two-team final, validated ID/time/team/positive-minute population."""
    game = payload.get("game")
    if not isinstance(game, dict):
        raise ValueError("No NBA game data")
    if str(game.get("gameId")) != official["id"] or str(game.get("gameStatus")) != "3":
        raise ValueError("NBA boxscore ID or FINAL state disagrees")
    if abs(utc(game["gameTimeUTC"]) - utc(espn_game["utc"])) > timedelta(minutes=5):
        raise ValueError("NBA and ESPN game clocks disagree")
    players = {}
    by_side = {}
    team_ids = set()
    for field, expected in (("homeTeam", espn_game["home"]),
                            ("awayTeam", espn_game["away"])):
        team = game.get(field) or {}
        actual = code(team.get("teamTricode"))
        teamid = str(team.get("teamId") or "")
        if actual != expected or not teamid.isdigit() or teamid in team_ids:
            raise ValueError("Official NBA home/away team conflict")
        team_ids.add(teamid)
        entries = team.get("players")
        if not isinstance(entries, list) or len(entries) < 7:
            raise ValueError("Missing game-day player roster")
        pos = 0
        for p in entries:
            person = str(p.get("personId") or "")
            if not person.isdigit() or person in players:
                raise ValueError("Duplicated/missing NBA person ID")
            status = p.get("status")
            played = str(p.get("played") or "")  # exact published flag, no guess
            if status not in ("ACTIVE", "INACTIVE") or played not in ("0", "1"):
                raise ValueError("Unsupported NBA official status or played flag")
            minutes = parse_minutes((p.get("statistics") or {}).get("minutes"))
            if (played == "0" and minutes is not None and minutes > 0) or (
                    status == "INACTIVE" and played == "1"):
                raise ValueError("Contradictory official played/inactive row")
            if played == "1":
                if minutes is None or minutes <= 0:
                    raise ValueError("Played flag without positive minutes")
                pos += 1
            players[person] = {
                "team": expected, "team_id": teamid,
                "status": status, "played": played,
                "positive_minutes": bool(minutes is not None and minutes > 0),
                "not_playing_reason": p.get("notPlayingReason"),
            }
        if pos < 5:
            raise ValueError("Incomplete official player minutes for team")
        by_side[expected] = pos
    return {"players": players, "active_by_team": by_side,
            "canonical_source_sha256": digest(payload)}


def verdict(person, expected_team, nba_id, previous_espn):
    if not nba_id:
        return "UNKNOWN", "historical_NBA_ID_not_high_confidence", False
    row = person.get(nba_id)
    if row is None:
        return "UNKNOWN", "NBA_person_absent_from_game_specific_roster", False
    if row["team"] != expected_team:
        return "UNKNOWN", "NBA_official_opposing_team_tenure_conflict", True
    if row["played"] == "1":
        # #40 independently checked full ESPN box and did not find a played row.
        return "UNKNOWN", "NBA_positive_minutes_conflict_with_prior_ESPN", True
    if row["status"] == "INACTIVE" and row["played"] == "0":
        return "VERIFIED_GAME_DAY_INACTIVE", None, False
    reason = str(row.get("not_playing_reason") or "").upper()
    if (row["status"] == "ACTIVE" and row["played"] == "0"
            and reason.startswith(("DNP", "DND", "NWT"))):
        return "VERIFIED_ACTIVE_NONPLAY", None, False
    return "UNKNOWN", "NBA_active_without_explicit_nonplay_reason", False


def build(evidence, identity, live, explicit, schedule_payload, box_fetch,
          now, previous=None, schedule_error=None, max_games=MAX_GAMES):
    if now.utcoffset() is None:
        raise ValueError("Research clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if (evidence.get("status") != STATUS or evidence.get("adopt_on_site") is not False
            or not evidence.get("no_inferred_DNP_from_unlisted_athletes")
            or not evidence.get("existing_p_play_shadow_untouched")
            or explicit.get("status") != STATUS
            or explicit.get("adopt_on_site") is not False):
        raise ValueError("Untrusted original #40/DNP evidence")
    originals = evidence.get("records")
    if (not isinstance(originals, list) or not 0 < len(originals) <= MAX_CASES
            or not isinstance(max_games, int) or not 1 <= max_games <= MAX_GAMES):
        raise ValueError("Out-of-bounds original OUT queue")
    if previous and (previous.get("schema_version") != 1
                     or previous.get("status") != STATUS
                     or previous.get("adopt_on_site") is not False):
        raise ValueError("Unsafe previous research state")
    verified_espn_games = set(explicit.get("checked_final_game_ids") or [])
    live_games = {g["id"]: g for g in live.get("games", [])
                  if g.get("status") == "final"}
    if len(live_games) != sum(g.get("status") == "final" for g in live.get("games", [])):
        raise ValueError("Duplicate finished fixture in live NBA data")
    meta = identity.get("players")
    if not isinstance(meta, dict):
        raise ValueError("NBA identity mapping unavailable")
    high_ids = [str(v["nba_id"]) for v in meta.values()
                if v.get("confidence") == "high" and v.get("nba_id")]
    if len(set(high_ids)) != len(high_ids):
        raise ValueError("Duplicate high-confidence NBA person links")
    old = {}
    for r in (previous or {}).get("records", []):
        key = (r.get("game_id"), r.get("player_id"))
        if key in old or not all(isinstance(x, str) for x in key):
            raise ValueError("Duplicated prior research record")
        old[key] = r
    source_rows = []
    seen = set()
    games = defaultdict(list)
    for r in originals:
        key = (r.get("game_id"), r.get("player_id"))
        if key in seen or not all(isinstance(x, str) and x for x in key):
            raise ValueError("Duplicate source OUT row")
        seen.add(key)
        game = live_games.get(r["game_id"])
        if (game is None or r["game_id"] not in verified_espn_games
                or game["utc"] != r.get("game_utc")
                or r.get("team") not in (game["home"], game["away"])
                or r.get("boxscore_athlete_verdict")
                   != "ESPN_person_not_listed_in_two_team_boxscore"
                or r.get("p_play_target_still_UNKNOWN_in_original_pipeline") is not True
                or r.get("model_training_negative") is not False
                or utc(r["first_prediction_issued_at_utc"]) >=
                   utc(game["utc"]) - timedelta(minutes=30)):
            raise ValueError("Original queue no longer supported by verified evidence")
        games[r["game_id"]].append(r)
        source_rows.append(r)
    if set(old) - seen:
        raise ValueError("Previous report cannot invent independent player-games")
    qa = Counter()
    if schedule_payload is None:
        matches = {}
        qa["source_failures"] += 1
    else:
        schedule = official_schedule(schedule_payload)
        matches = {gid: fixture_match(live_games[gid], schedule)
                   for gid in games}
    gathered = {}
    for gid in sorted(games)[:max_games]:
        match, reason = matches.get(gid, (None, "NBA_schedule_unavailable"))
        if match is None:
            gathered[gid] = (None, reason)
            if reason != "NBA_schedule_unavailable":
                qa["fixture_missing_or_ambiguous"] += 1
            continue
        try:
            url = BOX_PREFIX + match["id"] + ".json"
            index = official_box(box_fetch(url), match, live_games[gid])
            gathered[gid] = ((match, index, url), None)
            qa["official_game_sources_checked"] += 1
        except (OSError, TimeoutError, ValueError, TypeError, KeyError) as exc:
            gathered[gid] = (None, "NBA_official_game_source_unavailable_or_invalid")
            qa["source_failures"] += 1
    records = []
    for r in source_rows:
        key = (r["game_id"], r["player_id"])
        older = old.get(key)
        if older and older.get("outcome") in VERIFIED:
            records.append(older)
            qa["previously_verified_immutable"] += 1
            continue
        info, reason = gathered.get(r["game_id"], (None, "game_fetch_cap_reached"))
        person_meta = meta.get(r["player_id"]) or {}
        strong = (person_meta.get("confidence") == "high"
                  and str(person_meta.get("nba_id") or "").isdigit())
        nba_id = str(person_meta["nba_id"]) if strong else None
        outcome, why, conflict = "UNKNOWN", reason, False
        src = {}
        if info:
            matched, index, url = info
            outcome, why, conflict = verdict(index["players"], r["team"], nba_id, r)
            src = {"nba_game_id": matched["id"], "source_url": url,
                   "source_schedule_url": SCHEDULE_URL,
                   "schedule_canonical_sha256": digest(schedule_payload),
                   "official_box_canonical_sha256":
                       index["canonical_source_sha256"],
                   "source_observed_at_utc": stamp(now),
                   "official_positive_minutes_by_team": index["active_by_team"]}
        row_at_game = index["players"].get(nba_id) if info and nba_id else None
        row = {
            "game_id": r["game_id"], "player_id": r["player_id"],
            "team": r["team"], "game_utc": r["game_utc"],
            "first_prediction_issued_at_utc": r["first_prediction_issued_at_utc"],
            "official_OUT_at_issue_source": r["official_source_url"],
            "official_OUT_at_lock_from_frozen_evidence":
                r.get("official_OUT_still_observed_at_lock"),
            "original_ESPN_boxscore_url": r["source_ESPN_game_url"],
            "original_ESPN_boxscore_fingerprint":
                r["source_ESPN_boxscore_sha256"],
            "identity_nba_person_id": nba_id,
            "identity_NBA_ID_strength": "high" if strong else
                ("medium" if person_meta.get("nba_id") else "unresolved"),
            "identity_NBA_mapping_method": person_meta.get("method"),
            "observed_official_game_team": row_at_game["team"] if row_at_game else None,
            "observed_official_game_player_status":
                row_at_game["status"] if row_at_game else None,
            "observed_official_game_played_flag":
                row_at_game["played"] if row_at_game else None,
            "observed_official_game_nonplay_reason":
                row_at_game["not_playing_reason"] if row_at_game else None,
            "game_day_team_membership_verified": bool(row_at_game and
                row_at_game["team"] == r["team"]),
            "outcome": outcome, "why_unknown": why,
            "conflict_requires_review": conflict,
            "model_training_negative": False,
            "p_play_shadow_untouched": True,
            "research_only": True,
            **src,
        }
        records.append(row)
        if conflict:
            qa["conflicts"] += 1
        if outcome == "UNKNOWN":
            qa["unresolved_unknown"] += 1
            qa[why or "UNKNOWN"] += 1
        else:
            qa["resolved_confirmed"] += 1
            qa[outcome] += 1
    verified = sum(r["outcome"] in VERIFIED for r in records)
    if verified + sum(r["outcome"] == "UNKNOWN" for r in records) != len(originals):
        raise ValueError("Outcome denominator mismatch")
    qa["resolved_confirmed"] = verified
    qa["unresolved_unknown"] = len(originals) - verified
    report = {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "target": "postgame_official_NBA_game_specific_roster_status_not_ESPN_DNP",
        "original_OUT_unknown_queue": len(originals),
        "official_game_sources_checked_this_run":
            qa["official_game_sources_checked"],
        "resolved_confirmed": verified,
        "unresolved_unknown": len(originals) - verified,
        "conflicts": sum(bool(x["conflict_requires_review"]) for x in records),
        "source_failures": qa["source_failures"],
        "source_schedule_error": schedule_error if schedule_payload is None else None,
        "qa": dict(qa),
        "records": records,
        "existing_p_play_labels_untouched": True,
        "model_training_negative_allowed": False,
        "game_day_inactive_not_equal_ESPN_explicit_DNP": True,
        "reconciled_population_denominator_verified": False,
        "limitations": [
            "Only #40 original preissue-OUT/UNKNOWN queue; not complete fantasy roster.",
            "Historical high-confidence NBA ID maps person, but does not prove club tenure.",
            "Only an actual official game-specific same-club player row proves membership.",
            "Official NBA INACTIVE is separate from ESPN didNotPlay=true.",
            "Missing from official NBA game roster or weak identity remains UNKNOWN.",
            "NBA boxscore was first observed postgame; NEVER use as pregame feature.",
            "A conflict across independent sources requires review, not a zero label.",
            "No outcome or model is deployed, and no private data is accessed.",
        ],
    }
    return report


def run(dry_run=False):
    now = datetime.now(timezone.utc)
    read = lambda p: json.loads((BASE / p).read_text(encoding="utf-8"))
    prior_path = BASE / "official_nba_gameday_status_research.json"
    old = read(prior_path.name) if prior_path.exists() else {}
    schedule_error = None
    try:
        schedule = fetch_public_json(SCHEDULE_URL)
    except (OSError, TimeoutError, ValueError, TypeError) as exc:
        schedule = None
        schedule_error = ("HTTP_" + str(exc.code)) if isinstance(exc, HTTPError) else type(exc).__name__
    report = build(read("official_out_boxscore_evidence_research.json"),
                   read("identity.json"), read("live.json"),
                   read("explicit_dnp_research.json"),
                   schedule, fetch_public_json, now, old,
                   schedule_error=schedule_error)
    if not dry_run:
        if (not old or
                {k: v for k, v in report.items() if k != "updated_at_utc"} !=
                {k: v for k, v in old.items() if k != "updated_at_utc"}):
            tmp = prior_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(prior_path)
    return {key: report[key] for key in (
        "original_OUT_unknown_queue", "resolved_confirmed",
        "unresolved_unknown", "conflicts", "source_failures",
        "official_game_sources_checked_this_run", "source_schedule_error")}


if __name__ == "__main__":
    import sys
    print(json.dumps(run(dry_run="--dry-run" in sys.argv),
                     ensure_ascii=False, indent=2))
