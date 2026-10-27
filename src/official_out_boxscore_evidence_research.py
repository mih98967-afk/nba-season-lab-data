"""Independent, postgame verification of official OUT with missing p_play labels.

Requires two distinct sources:
  - NBA official injury PDF status observed before first prediction / game lock
  - ESPN final two-team, positive-minute boxscore and actual ESPN athlete IDs.
A player absent from ESPN boxscore is NOT a verified didNotPlay=true. Such
observations remain UNKNOWN and can never be promoted to p_play negatives here.

Existing fantasy roster, prices, transfers, model and website are never edited.
All outputs are separate, first-observed research evidence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
import json

from src.sync import DATA
from src.espn_adapter import parse_summary, club
from src.explicit_dnp_research import URL as ESPN_URL
from src.prelock_roster_opportunities import (
    validate_espn_snapshots, HIGH, WEAK,
)
from src.rolling_decision_research import (
    instant, stamp, canonical_hash, official_asof,
)

STATUS = "research_only_not_deployed"
MAX_FETCH_GAMES = 18
MAX_QUEUED = 150
LOCK = timedelta(minutes=30)
METHOD = {
    "same_club_independent_ESPN_ID_observed": HIGH,
    "same_club_unique_name_only_observed": WEAK,
}


def _fetch(url):
    if not url.startswith(ESPN_URL) or not url[len(ESPN_URL):].isdigit():
        raise ValueError("Unexpected ESPN game endpoint")
    request = Request(url, headers={
        "User-Agent": "NBA-Season-Lab/1.9 noncommercial research",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=18) as reply:
        raw = reply.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("ESPN full game exceeds size limit")
    return json.loads(raw)


def _checked_game(game, explicit, now):
    gid = game.get("id")
    if (game.get("status") != "final"
            or not str(game.get("espn_id") or "").isdigit()
            or game.get("id") != "espn_" + str(game.get("espn_id"))):
        raise ValueError("Only ESPN-ID matched finalized games are eligible")
    checked = explicit.get("checked_game_evidence", {}).get(gid)
    if gid not in explicit.get("checked_final_game_ids", []) or not checked:
        raise ValueError("Game not fully checked by original DNP pipeline")
    if (checked.get("home"), checked.get("away"), checked.get("game_utc")) != (
            game.get("home"), game.get("away"), game.get("utc")):
        raise ValueError("Original two-team DNP check disagrees with final game")
    if instant(checked["verified_at_utc"]) > now:
        raise ValueError("Check evidence is not yet observed")
    counts = checked.get("game_day_active_player_count", {})
    if any(type(counts.get(team)) is not int or counts[team] < 5
           for team in (game["home"], game["away"])):
        raise ValueError("Original completed two-team active boxscore insufficient")


def _index_summary(payload, game):
    """Verify positive-minute ESPN ID and explicit didNotPlay by exact athlete ID."""
    # This parser independently checks scores, both clubs, required stat fields,
    # and named positive-minute ESPN rows; do not infer negatives from absence.
    positive = parse_summary(payload, game)
    if len(positive) < 10:
        raise ValueError("Incomplete ESPN positive-minute boxscore")
    played = {}
    per_team = Counter()
    for row in positive:
        person = str(row.get("espn_person_id") or "")
        if not person.isdigit() or person in played:
            raise ValueError("Missing/reused ESPN ID in positive-minute boxscore")
        played[person] = row["team"]
        per_team[row["team"]] += 1
    for side in (game["home"], game["away"]):
        if per_team[side] < 5:
            raise ValueError("Both NBA teams need >=5 independently checked active athletes")

    entries = (payload.get("boxscore") or {}).get("players")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("Missing complete two-team ESPN boxscore")
    membership = {}
    seen_clubs = set()
    for side in entries:
        team = club((side.get("team") or {}).get("abbreviation"))
        if team not in (game["home"], game["away"]) or team in seen_clubs:
            raise ValueError("Duplicate/wrong ESPN team")
        seen_clubs.add(team)
        for group in side.get("statistics") or []:
            for row in group.get("athletes") or []:
                person = str((row.get("athlete") or {}).get("id") or "")
                if not person.isdigit():
                    # We cannot use a nameless, missing-ID row to prove
                    # membership/absence of any specific athlete.
                    continue
                if person in membership:
                    raise ValueError("Duplicated ESPN person ID across game rows")
                dnp = row.get("didNotPlay") is True
                membership[person] = {
                    "team": team, "explicit_didNotPlay": dnp,
                    "active_minutes_positive": person in played,
                }
                if person in played and (played[person] != team or dnp):
                    raise ValueError("ESPN explicit DNP contradicts positive-minute athlete")
    if seen_clubs != {game["home"], game["away"]}:
        raise ValueError("ESPN game omitted team")
    if any(person not in membership for person in played):
        raise ValueError("Positive-minute player absent from checked ESPN rows")
    return {
        "played": played,
        "members": membership,
        "fingerprint": canonical_hash({
            "game": game["id"], "teams":sorted(seen_clubs),
            "athletes": sorted((person, v["team"], v["explicit_didNotPlay"],
                                v["active_minutes_positive"])
                               for person, v in membership.items()),
        }),
        "active_by_team": dict(per_team),
    }


def _roster_identity(snapshots, pred):
    """Link ESPN person ID using a capture genuinely visible by prediction time."""
    issue = instant(pred["issued_at_utc"])
    expected_method = METHOD.get(pred.get("club_link_evidence"))
    if expected_method is None:
        return None, "unverified_original_club_identity"
    matches = [snap for captured, snap in snapshots
               if captured <= issue and
               stamp(captured) == pred.get("espn_capture_utc")]
    if len(matches) != 1:
        return None, "missing_exact_original_preissue_roster_snapshot"
    snap = matches[0]
    candidates = [
        (team["club"], a)
        for team in snap["teams"] if
        team["source_status"] == "parsed_not_game_day_eligibility"
        for a in team["athletes"]
        if a.get("sportsru_player_id") == pred["player_id"]
    ]
    if len(candidates) != 1:
        return None, "unresolved_or_conflicting_ESPN_athlete_identity"
    team, athlete = candidates[0]
    if (team != pred["team"] or athlete.get("identity_method") != expected_method
            or not str(athlete.get("espn_person_id") or "").isdigit()
            or athlete.get("catalog_team_at_capture") != pred["team"]):
        return None, "team_or_identity_disagreement_at_original_issue"
    return {
        "person_id": athlete["espn_person_id"],
        "name_at_capture": athlete["display_name"],
        "identity_method": expected_method,
        "roster_first_observed_at_utc": snap["captured_at_utc"],
        "identity_independently_confirmed": expected_method == HIGH,
    }, None


def _outcome(index, espn_id, team):
    record = index["members"].get(espn_id)
    if record and record["team"] != team:
        return "opposing_team_conflict", False
    if espn_id in index["played"]:
        return "positive_minutes_conflicts_with_official_OUT", False
    if record and record["explicit_didNotPlay"]:
        return "ESPN_explicit_didNotPlay_true", True
    if record:
        return "ESPN_listed_without_positive_or_explicit_DNP", False
    return "ESPN_person_not_listed_in_two_team_boxscore", False


def audit(queue, shadow, live, explicit, official, roster_files,
          prior, fetch, now, max_games=MAX_FETCH_GAMES):
    if now.utcoffset() is None:
        raise ValueError("Audit clock must have timezone")
    now = now.astimezone(timezone.utc)
    if (shadow.get("status") != STATUS
            or shadow.get("adopt_on_site") is not False
            or explicit.get("status") != STATUS
            or explicit.get("adopt_on_site") is not False
            or official.get("status") != "official_report_observed_pit_research_only"
            or official.get("adopt_on_site") is not False):
        raise ValueError("Only verified research archives are supported")
    if not isinstance(queue, list) or len(queue) > MAX_QUEUED:
        raise ValueError("Unsafe review queue size")
    if not isinstance(max_games, int) or max_games < 1:
        raise ValueError("Invalid fetch cap")
    if prior and (prior.get("schema_version") != 1 or
                  prior.get("status") != STATUS or
                  prior.get("adopt_on_site") is not False):
        raise ValueError("Existing archived evidence is not research-only")
    previous = list((prior or {}).get("records", []))
    by_key = {}
    for old in previous:
        key = (old.get("game_id"), old.get("player_id"))
        if key in by_key or not all(isinstance(x, str) and x for x in key):
            raise ValueError("Duplicated frozen verification result")
        by_key[key] = old
    roster = validate_espn_snapshots(roster_files, now)
    predictions = {}
    for p in shadow.get("issued", []):
        key = (p.get("game_id"), p.get("player_id"))
        if key in predictions:
            raise ValueError("Duplicated original shadow prediction")
        predictions[key] = p
    observed = {(x["game_id"], x["player_id"])
                for x in shadow.get("observations", [])}
    games = {g["id"]: g for g in live.get("games", [])
             if isinstance(g, dict) and g.get("status") == "final"}
    if len(games) != len([g for g in live.get("games", [])
                         if isinstance(g, dict) and g.get("status") == "final"]):
        raise ValueError("Duplicate finalized games in source")
    fresh = {}
    qa = Counter()
    seen_queue = set()
    for q in queue:
        key = (q.get("game_id"), q.get("player_id"))
        if not all(isinstance(x, str) and x for x in key) or key in seen_queue:
            raise ValueError("Duplicate/invalid OUT review candidate")
        seen_queue.add(key)
        if key in by_key:
            qa["previously_checked_immutable"] += 1
            continue
        if key in observed:
            qa["already_verified_by_original_shadow"] += 1
            continue
        p = predictions.get(key)
        g = games.get(key[0])
        if p is None or g is None or p["team"] != q.get("team"):
            raise ValueError("Queue not grounded in immutable initial prediction")
        if (not q.get("game_verified_final") or
                not q.get("complete_explicit_DNP_audit") or
                q.get("source_observed_status") != "out" or
                p.get("official_status_first_known_asof_issue") != "out" or
                q.get("first_issue_at_utc") != p.get("issued_at_utc") or
                p.get("tipoff_utc") != g.get("utc")):
            raise ValueError("Unsafe or stale review queue")
        issue = instant(p["issued_at_utc"])
        lock = instant(p["individual_lock_utc"])
        if not (issue < lock < instant(g["utc"]) <= now and
                instant(g["utc"]) - lock == LOCK):
            raise ValueError("Impossible pregame evidence clock")
        _checked_game(g, explicit, now)
        first_status = official_asof(official, key[0], key[1],
                                   p["team"], issue)
        latest_status = official_asof(official, key[0], key[1],
                                    p["team"], lock)
        if not first_status or first_status["status"] != "out":
            raise ValueError("Official OUT was not observed by original issue")
        if q.get("official_event_id") != first_status["event_id"]:
            raise ValueError("The queued OUT evidence changed")
        player_id, missing_reason = _roster_identity(roster, p)
        fresh.setdefault(key[0], []).append(
            (q, p, g, first_status, latest_status, player_id, missing_reason))

    fetched = {}
    failed_games = set()
    for gid in sorted(fresh)[:max_games]:
        game = fresh[gid][0][2]
        try:
            index = _index_summary(
                fetch(ESPN_URL + str(game["espn_id"])), game)
        except (ValueError, KeyError, TypeError, OSError, TimeoutError) as exc:
            failed_games.add(gid)
            qa["ESPN_source_unavailable_or_invalid"] += 1
            continue
        fetched[gid] = index
    if len(fresh) > max_games:
        qa["pending_due_to_game_cap"] += len(fresh)-max_games

    additions = []
    for gid, case_list in sorted(fresh.items()):
        index = fetched.get(gid)
        if index is None:
            continue
        for q, p, g, first, latest, identity, reason in case_list:
            if identity is None:
                outcome = "no_verified_ESPN_athlete_identity"
                explicit_dnp = False
            else:
                outcome, explicit_dnp = _outcome(
                    index, identity["person_id"], p["team"])
            if reason:
                qa[reason] += 1
            qa[outcome] += 1
            status_at_lock = latest["status"] if latest else None
            stable_out = status_at_lock == "out"
            if not stable_out:
                qa["official_status_no_longer_observed_OUT_at_lock"] += 1
            if outcome.startswith("positive_minutes") or outcome=="opposing_team_conflict":
                qa["contradictory_evidence_review_required"] += 1
            # Deliberately do NOT promote even a separately observed DNP into
            # the existing production/shadow dataset without its own QA step.
            additions.append({
                "game_id": gid, "player_id": p["player_id"],
                "team": p["team"], "game_utc": p["tipoff_utc"],
                "first_prediction_issued_at_utc": p["issued_at_utc"],
                "first_observed_this_boxscore_at_utc": stamp(now),
                "official_status_at_first_prediction": "out",
                "official_source_event_id_at_issue": first["event_id"],
                "official_source_url": first["source_url"],
                "last_observed_official_status_before_lock": status_at_lock,
                "official_OUT_still_observed_at_lock": stable_out,
                "source_ESPN_game_url": ESPN_URL + str(g["espn_id"]),
                "source_ESPN_boxscore_sha256": index["fingerprint"],
                "source_ESPN_active_player_counts": index["active_by_team"],
                "preissue_roster_identity": identity,
                "identity_problem": reason,
                "boxscore_athlete_verdict": outcome,
                "ESPN_explicit_DNP_by_person_id": explicit_dnp,
                "independent_official_OUT_plus_ESPN_evidence": bool(stable_out and identity),
                "unlisted_is_not_explicit_DNP": True,
                "model_training_negative": False,
                "p_play_target_still_UNKNOWN_in_original_pipeline": True,
                "medical_cause_inferred": False,
            })
    for row in additions:
        key = (row["game_id"], row["player_id"])
        if key in by_key:
            raise ValueError("Attempted overwrite of immutable game evidence")
        by_key[key] = row
    all_records = sorted(by_key.values(), key=lambda x: (x["game_utc"],
                              x["game_id"], x["player_id"]))
    qa["new_checked_player_games"] = len(additions)
    qa["new_checked_games"] = len(fetched)
    qa["failed_games_remain_retryable"] = len(failed_games)
    if len(all_records) != len(by_key):
        raise ValueError("Evidence accounting inconsistent")
    report = {
        "schema_version":1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site":False, "updated_at_utc":stamp(now),
        "scope":"NBA_official_preissue_OUT_vs_independent_ESPN_full_final_boxscore",
        "source_count":2, "confirmed_full_population_DNP":False,
        "existing_p_play_shadow_untouched":True,
        "no_inferred_DNP_from_unlisted_athletes":True,
        "model_training_negative_allowed":False,
        "verified_player_game_evidence":len(all_records),
        "queued_OUT_missing_labels":len(queue),
        "qa_current":dict(qa),
        "by_verdict":dict(Counter(x["boxscore_athlete_verdict"]
                                  for x in all_records)),
        "independent_ESPN_ID_confirmed":sum(
            bool(x["preissue_roster_identity"] and
                 x["preissue_roster_identity"]["identity_independently_confirmed"])
            for x in all_records),
        "first_capture_utc":all_records[0]["first_observed_this_boxscore_at_utc"]
                            if all_records else None,
        "records":all_records,
        "limitations":[
            "ESPN unlisted athlete is not ESPN didNotPlay=true, even if official PDF said OUT.",
            "Most Sports.ru to ESPN links were unique-name-only, not historical verified IDs.",
            "A pregame OUT snapshot may be superseded; store last prelock status separately.",
            "ESPN two-team boxscore validates active minutes, not full game-day NBA contracts.",
            "No labels automatically added to p_play, no model retraining or calibration claims.",
            "Missing network/invalid boxscore is retryable and cannot create a negative.",
        ],
    }
    return report, {
        "new":len(additions), "checked_games":len(fetched),
        "failed_games":len(failed_games), "pending_games":len(fresh)-len(fetched),
        "total":len(all_records), "qa":dict(qa),
    }


def run():
    now = datetime.now(timezone.utc)
    load = lambda name: json.loads((DATA / name).read_text(encoding="utf8"))
    prior_path = DATA / "official_out_boxscore_evidence_research.json"
    prior = load(prior_path.name) if prior_path.exists() else {}
    queue = load("p_play_selection_bias_audit.json")["out_status_missing_review_queue"]
    snapshots = [json.loads(p.read_text(encoding="utf8"))
                 for p in sorted((DATA / "espn_roster_pit").glob("*.json"))]
    report, info = audit(
        queue,load("p_play_shadow_research.json"), load("live.json"),
        load("explicit_dnp_research.json"),
        load("official_injury_status_archive.json"), snapshots,
        prior, _fetch, now)
    if report["records"] != prior.get("records", []):
        tmp = prior_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),
                       encoding="utf8")
        tmp.replace(prior_path)
    return {**info, "research_only":True, "adopt_on_site":False}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
