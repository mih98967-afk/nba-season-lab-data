"""Conservative public ESPN explicit DNP audit, with game-day team and ID checks.

Only ESPN didNotPlay=true in a two-team final-game boxscore is a negative label.
A missing boxscore listing is UNKNOWN. First-observed times are recorded when
the collector actually sees the evidence; prior records remain append-only.
No inference about cause of DNP, no model deployment or fantasy account writes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import json
import re
import unicodedata

from src.sync import DATA
from src.rolling_decision_research import instant, stamp
from src.espn_adapter import club

URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="
MIN_ACTIVE_PER_CLUB = 5
MAX_GAMES_PER_RUN = 36


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def identity_aliases(identity, catalog=None):
    """Unambiguous English names from independent Sports.ru catalog/identity."""
    sources = defaultdict(dict)
    for pid, entry in (identity or {}).get("players", {}).items():
        name = norm(entry.get("english"))
        if name:
            sources[name][pid] = "identity_verified_english"
    for p in (catalog or {}).get("players", []):
        pid = p.get("id")
        name = norm(p.get("english"))
        if pid and name and pid not in sources[name]:
            sources[name][pid] = "sportsru_catalog_english"
    aliases = {
        name: next(iter(pids.items()))
        for name, pids in sources.items() if len(pids) == 1
    }
    names_for_pid = defaultdict(set)
    for name, (pid, _) in aliases.items():
        names_for_pid[pid].add(name)
    return aliases, names_for_pid


def identity_map(identity):
    """Legacy name matching utility; ambiguous names are excluded."""
    aliases, _ = identity_aliases(identity)
    return {name: pid for name, (pid, _) in aliases.items()}


def observed_active_espn_ids(live, identity, catalog=None):
    """An ESPN athlete ID can be used only after a NAMED, PLAYED match.

    NBA Stats IDs and ESPN person IDs are different namespaces. This mapping
    is never assembled from NBA Stats IDs and is never considered pregame news.
    """
    aliases, names_for_pid = identity_aliases(identity, catalog)
    _ = aliases
    finals = {g.get("id"): g for g in live.get("games", [])
              if isinstance(g, dict) and g.get("status") == "final"}
    espn_to_sports = defaultdict(set)
    sports_to_espn = defaultdict(set)
    for r in live.get("rows", []):
        if not isinstance(r, dict) or r.get("played") is not True:
            continue
        pid, espn = r.get("id"), str(r.get("espn_person_id") or "")
        game = finals.get(r.get("game_id"))
        if not pid or not espn.isdigit() or not game:
            continue
        if r.get("team") not in (game.get("home"), game.get("away")):
            continue
        if norm(r.get("name")) not in names_for_pid.get(pid, set()):
            continue
        try:
            if float(r["minutes"]) <= 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        espn_to_sports[espn].add(pid)
        sports_to_espn[pid].add(espn)
    return {
        espn: next(iter(pids))
        for espn, pids in espn_to_sports.items()
        if len(pids) == 1 and
        len(sports_to_espn[next(iter(pids))]) == 1
    }


def explicit_rows(payload, game, identity, observed_at, espn_index=None, catalog=None):
    """Verify both teams and explicitly listed DNPs in THIS game only."""
    if game.get("status") != "final" or not str(game.get("espn_id") or "").isdigit():
        raise ValueError("Only verified final ESPN match IDs accepted")
    comp = ((payload.get("header") or {}).get("competitions") or [{}])[0]
    sides = {}
    for side in comp.get("competitors") or []:
        code = club((side.get("team") or {}).get("abbreviation"))
        key = side.get("homeAway")
        if key in ("home", "away"):
            if key in sides:
                raise ValueError("Duplicate ESPN scoreboard side")
            sides[key] = code
    if sides != {"home": game["home"], "away": game["away"]}:
        raise ValueError("ESPN matchup does not match finalized game")
    entries = (payload.get("boxscore") or {}).get("players") or []
    if len(entries) != 2:
        raise ValueError("Complete two-club ESPN boxscore required")
    aliases, names_for_pid = identity_aliases(identity, catalog)
    espn_index = espn_index or {}
    qa = Counter()
    out = {}
    clubs_seen = set()
    seen_athlete_ids = set()
    for side in entries:
        team = club((side.get("team") or {}).get("abbreviation"))
        if team not in (game["home"], game["away"]) or team in clubs_seen:
            raise ValueError("Duplicate or unknown ESPN club")
        clubs_seen.add(team)
        for group in side.get("statistics") or []:
            for row in group.get("athletes") or []:
                if row.get("didNotPlay") is not True:
                    continue
                athlete = row.get("athlete") or {}
                display_name = (athlete.get("displayName") or
                                athlete.get("fullName") or "").strip()
                display_norm = norm(display_name)
                espn = str(athlete.get("id") or "")
                if not display_norm:
                    qa["missing_athlete_name"] += 1
                    continue
                if espn and espn in seen_athlete_ids:
                    raise ValueError("Duplicate ESPN athlete ID within DNP boxscore")
                if espn:
                    seen_athlete_ids.add(espn)
                matched = aliases.get(display_norm)
                from_id = espn_index.get(espn) if espn.isdigit() else None
                if from_id is not None:
                    # ESPN's ID was previously paired with a verified named
                    # active Sports.ru appearance. If current name disagrees,
                    # quarantine instead of silently trusting either source.
                    if display_norm not in names_for_pid.get(from_id, set()):
                        qa["espn_id_name_disagreement"] += 1
                        continue
                    if matched is not None and matched[0] != from_id:
                        qa["espn_id_name_identity_conflict"] += 1
                        continue
                    pid = from_id
                    method = "verified_espn_id_from_named_active_game"
                elif matched is not None:
                    pid, method = matched
                    method = method + "_unique_name_only"
                else:
                    qa["unmatched_or_ambiguous_name"] += 1
                    continue
                key = (game["id"], pid)
                if key in out:
                    raise ValueError("Same Sports.ru athlete duplicated within one ESPN DNP game")
                out[key] = {
                    "game_id": game["id"], "player_id": pid, "team": team,
                    "home": game["home"], "away": game["away"],
                    "game_utc": game["utc"],
                    "observed_at_utc": stamp(observed_at),
                    "evidence": "explicit_espn_didNotPlay_true",
                    "source_url": URL + str(game["espn_id"]),
                    "espn_person_id": espn if espn.isdigit() else None,
                    "espn_display_name": display_name,
                    "identity_method": method,
                    "game_day_club_evidence": "explicit_espn_team_boxscore",
                    "is_medical_diagnosis": False,
                }
                qa[method] += 1
    if clubs_seen != {game["home"], game["away"]}:
        raise ValueError("Incomplete ESPN two-club boxscore")
    return list(out.values()), dict(qa)


def gather(live, identity, prior, fetch, now, max_games=MAX_GAMES_PER_RUN,
           catalog=None):
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware capture time required")
    now = now.astimezone(timezone.utc)
    if prior and (prior.get("schema_version") != 1 or
                  prior.get("adopt_on_site") is not False):
        raise ValueError("Unexpected prior research archive")
    previous = prior or {}
    existing = previous.get("events", [])
    if not isinstance(existing, list) or not isinstance(max_games, int) or max_games < 1:
        raise ValueError("Invalid prior events / game cap")
    retained = {}
    for entry in existing:
        key = (entry.get("game_id"), entry.get("player_id"))
        if not all(isinstance(k, str) and k for k in key) or key in retained:
            raise ValueError("Untrusted duplicate prior player-game evidence")
        retained[key] = entry
    checked_list = previous.get("checked_final_game_ids", [])
    if not isinstance(checked_list, list) or len(set(checked_list)) != len(checked_list):
        raise ValueError("Invalid previously verified game roster")
    checked = set(checked_list)
    qa = Counter(previous.get("qa", {}))
    qa_current = Counter()
    processed = 0
    links = observed_active_espn_ids(live, identity, catalog)
    active = defaultdict(set)
    for row in live.get("rows", []):
        if isinstance(row, dict) and row.get("played") is True and row.get("id"):
            active[(row.get("game_id"), row.get("team"))].add(row["id"])
    games = sorted(
        (g for g in live.get("games", [])
         if g.get("status") == "final" and g.get("espn_id") and
         g.get("id") not in checked),
        key=lambda g: (g.get("utc", ""), g["id"])
    )
    by_game = dict(previous.get("checked_game_evidence", {}))
    for game in games[:max_games]:
        try:
            if (len(active[game["id"], game["home"]]) < MIN_ACTIVE_PER_CLUB or
                    len(active[game["id"], game["away"]]) < MIN_ACTIVE_PER_CLUB):
                raise ValueError("Incomplete active player data for final game")
            if instant(game["utc"]) > now:
                raise ValueError("Game has not started at capture time")
            entries, flags = explicit_rows(
                fetch(URL + str(game["espn_id"])), game,
                identity, now, links, catalog)
            # Do not publish any new DNP if it contradicts an actually played
            # row. This is checked BEFORE recording the game as verified.
            for entry in entries:
                if entry["player_id"] in active[game["id"], entry["team"]]:
                    raise ValueError("Explicit DNP conflicts with played FP")
                key = (entry["game_id"], entry["player_id"])
                if key in retained:
                    raise ValueError("Duplicate across verified research games")
        except (ValueError, KeyError, TypeError, OSError, TimeoutError) as exc:
            qa_current["unverified_boxscore_attempt"] += 1
            continue
        for entry in entries:
            retained[(entry["game_id"], entry["player_id"])] = entry
        qa_current.update(flags)
        checked.add(game["id"])
        processed += 1
        by_game[game["id"]] = {
            "verified_at_utc": stamp(now), "home": game["home"],
            "away": game["away"], "game_utc": game["utc"],
            "explicit_dnp_matched": len(entries),
            "game_day_active_player_count": {
                game["home"]: len(active[game["id"], game["home"]]),
                game["away"]: len(active[game["id"], game["away"]])
            },
            "identity_qa": flags,
        }
    # Re-check even prior archived negatives against every current active row.
    positive = {(r.get("game_id"), r.get("id")) for r in live.get("rows", [])
                if isinstance(r, dict) and r.get("played") is True}
    conflicts = positive.intersection(retained)
    if conflicts:
        raise ValueError("Explicit DNP conflicts with actually played row: " +
                         str(len(conflicts)))
    qa.update(qa_current)
    result = {
        "schema_version": 1, "status": "research_only_not_deployed",
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "checked_final_game_ids": sorted(checked),
        "checked_game_evidence": by_game,
        "events": sorted(retained.values(), key=lambda e: (e["game_id"], e["player_id"])),
        "qa": dict(qa), "qa_current_run": dict(qa_current),
        "source": "ESPN two-team completed game boxscore, explicit didNotPlay only",
        "identity_provenance": "ESPN person IDs from named active games when available, else unique English names",
        "warning": "No inferred DNP for missing players; verified AFTER the game, NOT pre-game knowledge; no medical diagnosis or FP mutation.",
    }
    return result, {
        "new_games_checked": processed,
        "total_games_checked": len(checked),
        "confirmed_explicit_dnp_total": len(retained),
        "new_explicit_dnp": len(retained) - len(existing),
        "identity_links_from_active": len(links),
        "qa_current": dict(qa_current),
    }


def fetch_json(url):
    if not url.startswith(URL) or not url[len(URL):].isdigit():
        raise ValueError("Unexpected public boxscore endpoint")
    req = Request(url, headers={"User-Agent": "NBA-Season-Lab/1.7 public-research"})
    with urlopen(req, timeout=18) as response:
        raw = response.read(2000001)
        if len(raw) > 2000000:
            raise ValueError("ESPN response too large")
    return json.loads(raw)


def run():
    load = lambda name: json.loads((DATA / name).read_text(encoding="utf8"))
    dest = DATA / "explicit_dnp_research.json"
    previous = load(dest.name) if dest.exists() else {}
    result, summary = gather(
        load("live.json"), load("identity.json"),
        previous, fetch_json, datetime.now(timezone.utc),
        catalog=load("catalog.json"))
    if result != previous:
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf8")
        tmp.replace(dest)
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
