"""Official NBA BoxScoreSummaryV2 InactivePlayers cross-check for #40 OUT unknowns.

Independent *endpoint* within NBA's own provider, not ESPN didNotPlay. Never
convert absence from any table into a negative. Results are a distinct
research archive; personal fantasy data and existing p_play labels untouched.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import re

from src.official_nba_gameday_status_research import (
    code, utc, stamp, digest, STATUS,
)

ROOT = Path(__file__).resolve().parents[1] / "data"
PREFIX = "https://stats.nba.com/stats/boxscoresummaryv2?GameID="
MAX_BYTES = 3_000_000
MAX_GAMES = 18
VERIFIED = "VERIFIED_OFFICIAL_NBA_INACTIVE_LIST"
UNKNOWN = "UNKNOWN"


def request_json(url):
    if not url.startswith(PREFIX) or not re.fullmatch(r"00226\d{5}", url[len(PREFIX):]):
        raise ValueError("Disallowed NBA summary endpoint/game ID")
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
    })
    with urlopen(req, timeout=12) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("NBA summary payload too large")
    return json.loads(raw)


def table(payload, name, must_have):
    sets = payload.get("resultSets")
    if not isinstance(sets, list):
        raise ValueError("NBA resultSets unavailable")
    matches = [s for s in sets if isinstance(s, dict) and s.get("name") == name]
    if len(matches) != 1:
        raise ValueError("Required NBA resultSet missing or duplicated: " + name)
    headers = matches[0].get("headers")
    rows = matches[0].get("rowSet")
    if (not isinstance(headers, list) or not isinstance(rows, list)
            or len(set(headers)) != len(headers) or not must_have.issubset(headers)):
        raise ValueError("Invalid NBA resultSet schema: " + name)
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError("Truncated NBA resultSet row: " + name)
        out.append(dict(zip(headers, row)))
    return out


def validate_summary(payload, nba_game_id, home, away):
    """Require the expected FINAL game, both club/team IDs and explicit rows."""
    if not isinstance(payload, dict):
        raise ValueError("NBA summary response not an object")
    summary = table(payload, "GameSummary",
                    {"GAME_ID", "GAME_STATUS_ID", "HOME_TEAM_ID", "VISITOR_TEAM_ID"})
    if len(summary) != 1 or str(summary[0]["GAME_ID"]) != nba_game_id:
        raise ValueError("NBA summary is not the requested game")
    if str(summary[0]["GAME_STATUS_ID"]) != "3":
        raise ValueError("NBA summary game not final")
    home_id, away_id = [str(summary[0][field])
                       for field in ("HOME_TEAM_ID", "VISITOR_TEAM_ID")]
    if not home_id.isdigit() or not away_id.isdigit() or home_id == away_id:
        raise ValueError("Invalid official team ID pair")
    lines = table(payload, "LineScore", {"TEAM_ID", "TEAM_ABBREVIATION"})
    teams = {}
    for row in lines:
        team_id = str(row["TEAM_ID"])
        abbrev = code(row["TEAM_ABBREVIATION"])
        if team_id in teams:
            raise ValueError("Duplicate line score team")
        teams[team_id] = abbrev
    if len(teams) != 2 or teams != {home_id: home, away_id: away}:
        raise ValueError("NBA LineScore home/away crosswalk disagreement")
    inactive_rows = table(payload, "InactivePlayers",
                          {"PLAYER_ID", "TEAM_ID", "TEAM_ABBREVIATION"})
    inactive = {}
    for row in inactive_rows:
        athlete = str(row["PLAYER_ID"] or "")
        team_id = str(row["TEAM_ID"] or "")
        team = code(row["TEAM_ABBREVIATION"])
        if (not athlete.isdigit() or athlete in inactive
                or team_id not in teams or teams[team_id] != team):
            raise ValueError("Inactive player ID/team missing, duplicated or conflicting")
        inactive[athlete] = {"team": team, "team_id": team_id}
    return {"inactive": inactive, "inactive_count": len(inactive),
            "sha256": digest(payload),
            "teams": {home: home_id, away: away_id}}


def reconcile(previous_nba_report, first_out_report, live, payloads, errors,
              now, previous=None):
    if now.utcoffset() is None:
        raise ValueError("Clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    if (previous_nba_report.get("status") != STATUS
            or previous_nba_report.get("adopt_on_site") is not False
            or previous_nba_report.get("model_training_negative_allowed") is not False
            or first_out_report.get("status") != STATUS
            or first_out_report.get("adopt_on_site") is not False):
        raise ValueError("Upstream research evidence changed unexpectedly")
    old = previous or {}
    if old and (old.get("schema_version") != 1
                or old.get("status") != STATUS or old.get("adopt_on_site") is not False):
        raise ValueError("Incompatible prior NBA inactive result")
    frozen = {(r["game_id"], r["player_id"]):r
              for r in first_out_report.get("records", [])}
    prev_cases = previous_nba_report.get("records", [])
    if not 0 < len(prev_cases) <= 150 or len(frozen) != len(prev_cases):
        raise ValueError("Original 23 OUT queue inconsistent")
    games = {g["id"]: g for g in live.get("games", []) if g.get("status") == "final"}
    if len(games) != sum(g.get("status") == "final" for g in live.get("games", [])):
        raise ValueError("Duplicate live final games")
    prior_rows = {(r["game_id"],r["player_id"]):r for r in old.get("records", [])}
    if len(prior_rows) != len(old.get("records", [])):
        raise ValueError("Duplicate previous evidence")
    outputs = []
    checked = {}
    qa = Counter()
    for row in prev_cases:
        key = (row["game_id"],row["player_id"])
        first = frozen.get(key)
        game = games.get(row["game_id"])
        nba_id = row.get("nba_game_id")
        if (not first or not game or row["game_utc"] != game["utc"]
            or row.get("outcome") not in (UNKNOWN, "VERIFIED_GAME_DAY_INACTIVE", "VERIFIED_ACTIVE_NONPLAY")
            or row.get("team") not in (game["home"],game["away"])
            or not isinstance(nba_id,str) or not re.fullmatch(r"00226\d{5}",nba_id)
            or row.get("p_play_shadow_untouched") is not True
            or first.get("boxscore_athlete_verdict") != "ESPN_person_not_listed_in_two_team_boxscore"
            or utc(game["utc"]) > now):
            raise ValueError("Unsafe or mismatched game/OUT evidence")
        if nba_id not in checked:
            if nba_id in payloads:
                try:
                    checked[nba_id] = validate_summary(payloads[nba_id],nba_id,game["home"],game["away"])
                    qa["verified_official_summary_games"] += 1
                except (ValueError, KeyError, TypeError):
                    errors[nba_id] = "NBA_summary_schema_or_match_invalid"
                    qa["source_unavailable_games"] += 1
                    checked[nba_id] = None
            else:
                qa["source_unavailable_games"] += 1
                checked[nba_id] = None
        indexed = checked[nba_id]
        identity = row.get("identity_nba_person_id")
        method = row.get("identity_NBA_ID_strength")
        if method == "high" and (not str(identity or "").isdigit()):
            raise ValueError("High identity without NBA ID")
        old_item = prior_rows.get(key)
        if old_item and old_item.get("outcome") == VERIFIED:
            outputs.append(old_item)
            continue
        outcome = UNKNOWN
        why = errors.get(nba_id, "NBA_summary_missing_or_invalid") if not indexed else None
        if indexed is not None:
            if method != "high":
                why = "not_high_confidence_NBA_person_link"
            else:
                found = indexed["inactive"].get(str(identity))
                if found is None:
                    why = "NBA_ID_not_in_explicit_InactivePlayers"
                elif found["team"] != row["team"]:
                    why = "NBA_summary_inactive_opposing_team_conflict"
                    qa["conflicts"] += 1
                elif row.get("observed_official_game_played_flag") == "1":
                    why = "NBA_live_positive_minutes_vs_inactive_conflict"
                    qa["conflicts"] += 1
                else:
                    outcome = VERIFIED
        out = {
            "game_id":row["game_id"],"nba_game_id":nba_id,
            "player_id":row["player_id"],"team":row["team"],
            "game_utc":game["utc"],
            "first_prediction_issued_at_utc":row["first_prediction_issued_at_utc"],
            "nba_person_id":identity if method=="high" else None,
            "nba_identity_strength":method,
            "source_url":PREFIX+nba_id,
            "source_first_observed_at_utc":stamp(now) if indexed else None,
            "source_sha256":indexed["sha256"] if indexed else None,
            "official_summary_inactive_total":indexed["inactive_count"] if indexed else None,
            "game_match_complete_and_final":bool(indexed),
            "matched_explicit_official_inactive":outcome==VERIFIED,
            "outcome":outcome,
            "why_unknown":why,
            "conflict_requires_review":why is not None and why.endswith("_conflict"),
            "separate_from_ESPN_didNotPlay":True,
            "model_training_negative":False,
            "research_only":True,
        }
        outputs.append(out)
        qa[outcome] += 1
        if outcome == UNKNOWN:qa[why or "unresolved"] += 1
    keys={(o["game_id"],o["player_id"]) for o in outputs}
    if len(keys)!=len(outputs) or set(frozen)!=keys:
        raise ValueError("Original review population changed")
    if set(prior_rows)-keys:
        raise ValueError("Prior report invented player-games")
    return {
        "schema_version":1,"status":STATUS,"model_status":STATUS,
        "adopt_on_site":False,"updated_at_utc":stamp(now),
        "reference":"23 preissue official OUT unresolved on complete ESPN and NBA live boxscore",
        "source_kind":"NBA_stats_BoxScoreSummaryV2_explicit_InactivePlayers",
        "source_counted_as_independent_endpoint_not_independent_provider":True,
        "original_queue_count":len(outputs),
        "verified_official_summary_games":qa["verified_official_summary_games"],
        "source_unavailable_games":qa["source_unavailable_games"],
        "resolved_confirmed":sum(x["outcome"]==VERIFIED for x in outputs),
        "unresolved_unknown":sum(x["outcome"]==UNKNOWN for x in outputs),
        "conflicts":qa["conflicts"],"qa":dict(qa),
        "records":outputs,
        "existing_p_play_labels_untouched":True,
        "training_negatives_allowed":False,
        "limitations":[
            "NBA official InactivePlayers evidence differs from ESPN didNotPlay=true.",
            "If a player is not in InactivePlayers that absence is UNKNOWN, never participation.",
            "High NBA person ID does not alone prove team tenure; source SAME-GAME matched team does.",
            "Publication timestamp of NBA endpoint unknown; only retrieval time recorded (postgame).",
            "Not a denominator for all available fantasy athletes; no model deployment or claims.",
        ]
    }


def run():
    load=lambda p:json.loads((ROOT/p).read_text(encoding="utf8"))
    official=load("official_nba_gameday_status_research.json")
    out=load("official_out_boxscore_evidence_research.json")
    live=load("live.json")
    path=ROOT/"official_nba_inactive_summary_research.json"
    previous=load(path.name) if path.exists() else {}
    ids=sorted(set(r["nba_game_id"] for r in official["records"]))
    if len(ids)>MAX_GAMES:
        raise ValueError("Too many NBA summary games")
    payloads={}
    failures={}
    for gid in ids:
        try:
            payloads[gid]=request_json(PREFIX+gid)
        except (HTTPError,URLError,TimeoutError,ValueError,OSError) as exc:
            failures[gid]=(f"HTTP_{exc.code}" if isinstance(exc,HTTPError) else type(exc).__name__)
    now=datetime.now(timezone.utc)
    report=reconcile(official,out,live,payloads,failures,now,previous)
    if (not previous or
            {k:v for k,v in report.items() if k!="updated_at_utc"} !=
            {k:v for k,v in previous.items() if k!="updated_at_utc"}):
        tmp=path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(path)
    return {k:report[k] for k in ("original_queue_count","verified_official_summary_games",
              "source_unavailable_games","resolved_confirmed","unresolved_unknown","conflicts","qa")}


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,indent=2))
