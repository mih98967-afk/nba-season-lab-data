"""Prospective Sports.ru *catalog proxy* and fixture first-observation evidence.

NOT a confirmed NBA active roster. In particular, data/catalog.json is a
cached/static Sports.ru Fantasy catalog; capturing it today cannot prove
club membership in a game played yesterday or even eligibility tomorrow.

Save a new timestamped immutable snapshot, only from *now onward*, while
the public game schedule is verified fresh. Evaluate later finalized games
against a snapshot that truly existed before the game's individual lock.
A missed player listing is UNKNOWN, never a DNP/zero.
No new p_play model, no public site, no Firestore, no fantasy transactions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import math

from src.sync import DATA
from src.rolling_decision_research import canonical_hash, instant, stamp, official_asof, telegram_asof
from src.live_calendar_fallback import TEAMS

UTC = timezone.utc
MSK = ZoneInfo("Europe/Moscow")
LOCK = timedelta(minutes=30)
HORIZON = timedelta(hours=72)
MAX_SCHEDULE_AGE = timedelta(hours=36)
MAX_LIVE_AGE = timedelta(hours=8)
MAX_SNAPSHOT_AGE = timedelta(hours=36)
STATUS = "research_only_not_deployed"
POSITIONS = {"C", "PF", "SF", "SG", "PG"}
UNKNOWN = "unknown_outcome_or_unverified_game_day_membership"
SOURCE = "repo_data_catalog_static_proxy_NOT_verified_game_day_roster"


def _when(value):
    return instant(value)


def _catalog(catalog):
    people = catalog.get("players") if isinstance(catalog, dict) else None
    if not isinstance(people, list) or len(people) < 400:
        raise ValueError("Full public NBA fantasy catalog required")
    seen = set()
    out = []
    for p in people:
        if not isinstance(p, dict):
            raise ValueError("Malformed catalog player")
        pid, team, position = p.get("id"), p.get("team"), p.get("pos")
        if (not isinstance(pid, str) or not pid or pid in seen or
            team not in TEAMS or position not in POSITIONS):
            raise ValueError("Nonunique player, invalid club or position")
        seen.add(pid)
        out.append({"player_id": pid, "catalog_team": team, "position": position})
    if {p["catalog_team"] for p in out} != TEAMS:
        raise ValueError("Catalog does not cover all 30 NBA clubs")
    return sorted(out, key=lambda p: p["player_id"])


def capture(catalog, live, now):
    """Create a unique, non-backdated snapshot (caller persists once per MSK day)."""
    if now.utcoffset() is None:
        raise ValueError("Capture time must include timezone")
    now = now.astimezone(UTC)
    if live.get("schema_version") != 4 or not isinstance(live.get("schedule"), list):
        raise ValueError("Invalid public live feed")
    quality = live.get("schedule_quality") or {}
    if quality.get("freshness") != "fresh":
        raise ValueError("Calendar is not freshly validated")
    validated = _when(quality.get("validated_at_utc"))
    observed = _when(live.get("updated_at_utc"))
    if (validated > now or observed > now or
        now - validated > MAX_SCHEDULE_AGE or now - observed > MAX_LIVE_AGE):
        raise ValueError("Stale or future-dated source: cannot claim a PIT capture")
    people = _catalog(catalog)
    planned = []
    known = set()
    for game in live["schedule"]:
        if not isinstance(game, dict) or game.get("status") != "scheduled":
            continue
        if not isinstance(game.get("id"), str) or not game["id"]:
            raise ValueError("Scheduled game has invalid ID")
        try:
            tip = _when(game["utc"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Scheduled game lacks UTC tipoff") from exc
        if not (now + LOCK < tip <= now + HORIZON):
            continue
        home, away = game.get("home"), game.get("away")
        if home not in TEAMS or away not in TEAMS or home == away:
            raise ValueError("Invalid upcoming matchup")
        if game["id"] in known:
            raise ValueError("Duplicate scheduled game within capture window")
        known.add(game["id"])
        planned.append({"game_id": game["id"], "tipoff_utc": stamp(tip),
                        "home": home, "away": away})
    planned.sort(key=lambda x: (x["tipoff_utc"], x["game_id"]))
    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "snapshot_date_msk": now.astimezone(MSK).date().isoformat(),
        "captured_at_utc": stamp(now), "source_catalog": SOURCE,
        "catalog_original_published_at_utc": None,
        "game_day_club_membership_verified": False,
        "active_roster_eligibility_verified": False,
        "source_live_updated_at_utc": stamp(observed),
        "schedule_validated_at_utc": stamp(validated),
        "calendar_source": quality.get("source"),
        "catalog_content_hash_sha256": canonical_hash(people),
        "catalog_players": len(people), "all_30_teams_present": True,
        "catalog_players_proxy": people, "future_fixtures_observed": planned,
        "future_fixtures_count": len(planned),
        "limitations": [
            "Catalog is a cached identity/club proxy, not confirmed NBA roster eligibility.",
            "Snapshot clock is the actual first capture, never assumed Sports.ru publication time.",
            "Only exact fixtures seen before individual lock may enter a later coverage report.",
            "Unknown or unlisted player is never DNP/zero FP.",
        ],
    }


def _validated_snapshots(snapshots, now):
    if not isinstance(snapshots, list):
        raise ValueError("Snapshot list missing")
    out = []
    dates = {}
    for s in snapshots:
        if (not isinstance(s, dict) or s.get("schema_version") != 1 or
            s.get("status") != STATUS or s.get("adopt_on_site") is not False or
            s.get("source_catalog") != SOURCE or
            s.get("game_day_club_membership_verified") is not False or
            s.get("active_roster_eligibility_verified") is not False):
            raise ValueError("Untrusted or deployable catalog snapshot")
        captured = _when(s.get("captured_at_utc"))
        date_msk = captured.astimezone(MSK).date().isoformat()
        if captured > now or s.get("snapshot_date_msk") != date_msk or dates.get(date_msk, 0) >= 2:
            raise ValueError("Future/renamed/duplicate daily capture")
        dates[date_msk] = dates.get(date_msk, 0) + 1
        people = s.get("catalog_players_proxy")
        if not isinstance(people, list) or len(people) < 400:
            raise ValueError("Invalid snapshot catalog")
        ids = set()
        teams = set()
        for p in people:
            if not isinstance(p, dict):
                raise ValueError("Invalid player in stored snapshot")
            pid, team, pos = p.get("player_id"), p.get("catalog_team"), p.get("position")
            if not isinstance(pid, str) or not pid or pid in ids or team not in TEAMS or pos not in POSITIONS:
                raise ValueError("Snapshot has invalid player/club/position")
            ids.add(pid); teams.add(team)
        if teams != TEAMS or s.get("catalog_players") != len(people):
            raise ValueError("Snapshot club/player count inconsistent")
        if canonical_hash(people) != s.get("catalog_content_hash_sha256"):
            raise ValueError("Historical snapshot content was changed")
        seen = set()
        fixtures = s.get("future_fixtures_observed")
        if not isinstance(fixtures, list):
            raise ValueError("Snapshot fixtures missing")
        for f in fixtures:
            if not isinstance(f, dict) or not isinstance(f.get("game_id"), str):
                raise ValueError("Invalid stored fixture")
            tip = _when(f["tipoff_utc"])
            if (tip <= captured + LOCK or tip > captured + HORIZON or
                f["game_id"] in seen or f.get("home") not in TEAMS or
                f.get("away") not in TEAMS or f["home"] == f["away"]):
                raise ValueError("Snapshot has impossible/repeated fixture")
            seen.add(f["game_id"])
        if len(fixtures) != s.get("future_fixtures_count"):
            raise ValueError("Snapshot fixture count inconsistent")
        out.append((captured, s))
    out.sort(key=lambda p: p[0])
    if any(b[0] - a[0] < timedelta(hours=4) and a[0].astimezone(MSK).date() == b[0].astimezone(MSK).date() for a,b in zip(out,out[1:])):
        raise ValueError("Same-day PIT captures too close to be independently scheduled")
    return out


def evaluate(live, cohort, explicit, snapshots, now, official=None, telegram=None):
    """Evaluate as-of club proxies against *postgame*-verified explicit outcomes.

    No historical catalog snapshot -> no denominator. A snapshot seen after a
    lock may never be retrofitted to that already played game.
    """
    if now.utcoffset() is None:
        raise ValueError("Evaluation requires timezone")
    now = now.astimezone(UTC)
    snaps = _validated_snapshots(snapshots, now)
    if (cohort.get("schema_version") != 1 or cohort.get("status") != STATUS or
        cohort.get("adopt_on_site") is not False or
        explicit.get("schema_version") != 1 or explicit.get("adopt_on_site") is not False):
        raise ValueError("Input cohorts not research-only verified")
    checked = explicit.get("checked_final_game_ids")
    if (not isinstance(checked, list) or not checked or
        len(set(checked)) != len(checked) or
        len(checked) != cohort.get("summary", {}).get("verified_full_boxscores_checked")):
        raise ValueError("DNP/cohort checked-game snapshots disagree")
    finals = {}
    for g in live.get("games", []):
        if not isinstance(g, dict) or g.get("status") != "final":
            continue
        if not isinstance(g.get("id"), str) or g["id"] in finals:
            raise ValueError("Duplicate final game ID")
        finals[g["id"]] = g
    for gid in checked:
        if gid not in finals or _when(finals[gid]["utc"]) > now:
            raise ValueError("Checked game missing verified final fixture")
    labels = {}
    for r in cohort.get("records", []):
        if not isinstance(r, dict):
            raise ValueError("Malformed cohort record")
        key = (r.get("game_id"), r.get("player_id"))
        if not all(isinstance(v, str) and v for v in key) or key in labels or key[0] not in checked:
            raise ValueError("Bad/duplicate verified label")
        game = finals[key[0]]
        if (r.get("team") not in (game["home"], game["away"]) or
            r.get("game_utc") != game["utc"] or
            r.get("participation_label") not in (0, 1)):
            raise ValueError("Verified outcome contradicts game fixture")
        if (r["participation_label"] == 1 and r.get("evidence") != "positive_minutes_verified_sportsru_fp") or (
            r["participation_label"] == 0 and r.get("evidence") != "explicit_espn_didNotPlay_true"):
            raise ValueError("Untrusted positive/negative label provenance")
        first = r.get("source_first_observed_at_utc")
        if first and not (_when(game["utc"]) <= _when(first) <= now):
            raise ValueError("Outcome first-observed clock is impossible")
        labels[key] = r
    if len(labels) != cohort.get("summary", {}).get("listed_player_game_labels"):
        raise ValueError("Verified labels omitted or duplicated")
    if official is not None and official.get("status") != "official_report_observed_pit_research_only":
        raise ValueError("Untrusted official injury evidence")
    if telegram is not None and telegram.get("status") != "observed_unconfirmed_research_archive":
        raise ValueError("Untrusted Telegram evidence")

    qa = Counter()
    by_team = defaultdict(Counter)
    by_position = defaultdict(Counter)
    rows = []
    outside = []
    sampled_games = []
    for gid in sorted(checked, key=lambda k: (finals[k]["utc"], k)):
        g = finals[gid]
        lock = _when(g["utc"]) - LOCK
        earlier = [(captured, snap) for captured, snap in snaps if captured <= lock]
        if not earlier:
            qa["no_prelock_snapshot"] += 1
            continue
        captured, snap = earlier[-1]
        if lock - captured > MAX_SNAPSHOT_AGE:
            qa["stale_prelock_snapshot"] += 1
            continue
        original = next((f for f in snap["future_fixtures_observed"]
                         if f["game_id"] == gid), None)
        if original is None:
            qa["fixture_not_seen_in_latest_prelock_capture"] += 1
            continue
        if (original["tipoff_utc"] != stamp(_when(g["utc"])) or
            original["home"] != g["home"] or original["away"] != g["away"]):
            qa["fixture_changed_since_capture"] += 1
            continue
        qa["games_with_prelock_proxy_and_matching_fixture"] += 1
        sampled_games.append(gid)
        matched = set()
        for p in snap["catalog_players_proxy"]:
            team = p["catalog_team"]
            if team not in (g["home"], g["away"]):
                continue
            pid = p["player_id"]
            key = gid, pid
            evidence = labels.get(key)
            compatible = bool(evidence and evidence["team"] == team and
                              evidence["position"] == p["position"])
            if compatible:
                matched.add(key)
                outcome = "played_verified" if evidence["participation_label"] else "explicit_dnp_verified"
            else:
                outcome = UNKNOWN
            official_status = official_asof(official, gid, pid, team, lock) if official else None
            tg_context = telegram_asof(telegram, pid, lock) if telegram else None
            row = {
                "game_id": gid, "player_id": pid, "game_utc": g["utc"],
                "individual_lock_utc": stamp(lock), "prelock_catalog_capture_utc": stamp(captured),
                "prelock_schedule_seen": True, "catalog_club_asof_snapshot": team,
                "fantasy_position_asof_snapshot": p["position"],
                "roster_membership": "UNVERIFIED_CACHED_CATALOG_PROXY",
                "outcome_verified_after_game": outcome,
                "outcome_evidence": evidence.get("evidence") if compatible else None,
                "outcome_first_observed_at_utc": evidence.get("source_first_observed_at_utc") if compatible else None,
                "official_status_known_before_lock": official_status.get("status") if official_status else None,
                "official_event_id": official_status.get("event_id") if official_status else None,
                "telegram_unverified_context_before_lock": bool(tg_context),
                "missing_or_unlisted_NEVER_implies_DNP": True,
            }
            rows.append(row)
            for count in (qa, by_team[team], by_position[p["position"]]):
                count["catalog_proxy_candidate_player_games"] += 1
                count[outcome] += 1
                if official_status:
                    count["official_prelock_known"] += 1
                if tg_context:
                    count["unverified_telegram_context_prelock"] += 1
        for key, evidence in labels.items():
            if key[0] == gid and key not in matched:
                outside.append({
                    "game_id": gid, "player_id": key[1],
                    "actual_boxscore_club": evidence["team"],
                    "label": evidence["participation_label"],
                    "evidence": evidence["evidence"],
                    "reason": "club_position_or_membership_not_in_prelock_catalog_proxy",
                })
    qa["verified_labels_outside_prelock_catalog_proxy"] = len(outside)
    qa["all_verified_outcomes_in_checked_games"] = len(labels)
    qa["checked_final_games"] = len(checked)
    qa["snapshots_available"] = len(snaps)
    qa["player_cards_observed_in_latest_snapshot"] = snaps[-1][1]["catalog_players"] if snaps else 0
    qa["unknown_outcomes_not_negative_labels"] = qa[UNKNOWN]
    if (qa["played_verified"] + qa["explicit_dnp_verified"] +
        qa["verified_labels_outside_prelock_catalog_proxy"] >
            qa["all_verified_outcomes_in_checked_games"]):
        raise ValueError("More negative/positive outcomes than verified evidence")

    return {
        "schema_version": 1, "status": STATUS, "model_status": STATUS,
        "adopt_on_site": False, "updated_at_utc": stamp(now),
        "scope": "actual_first_seen_catalog_and_schedule_proxy_before_individual_lock",
        "sampling_unit": "player_x_exact_final_game_if_game_seen_before_lock",
        "summary": dict(qa),
        "by_team": {k: dict(by_team[k]) for k in sorted(by_team)},
        "by_position": {k: dict(by_position[k]) for k in sorted(by_position)},
        "snapshotted_checked_final_games": sampled_games,
        "records": rows, "verified_outcomes_outside_proxy": outside,
        "outcome_evidence_available_after_game_only": True,
        "historical_backfill_allowed": False,
        "true_game_day_membership_or_active_roster_verified": False,
        "calibrated_p_play_available": False,
        "full_population_dnp_recall_verified": False,
        "brier_or_logloss_enabled": False,
        "keep_transfer_advantage_claim_allowed": False,
        "limitations": [
            "Before first snapshot there is no trustworthy historical club-as-of; such games are excluded.",
            "Static Sports.ru fantasy catalog team is not a verified active NBA roster or true eligibility set.",
            "Missing unlisted player remains UNKNOWN even after a verified two-team ESPN boxscore.",
            "Official PDF and Telegram were first observed before lock; neither proves actual participation.",
            "The time of first captured catalog data is not the time Sports.ru published or changed it.",
            "No p_play fitting, calibration, injury diagnosis, or fantasy transfer suggestion is authorized.",
        ],
    }


def next_capture_slot(directory, now, *, reserve_evening=True):
    """Choose an append-only MSK-day slot without consuming both too early.

    This is an operational scheduling rule, not evidence that the underlying
    static Sports.ru catalog was updated by Sports.ru at capture time.
    """
    if now.utcoffset() is None:
        raise ValueError("PIT capture decision requires timezone-aware time")
    now = now.astimezone(UTC)
    moscow = now.astimezone(MSK)
    day = moscow.date().isoformat()
    first = directory / (day + ".json")
    second = directory / (day + "_2.json")
    if second.exists() and not first.exists():
        raise ValueError("Second PIT file exists without immutable first")
    if second.exists():
        return None, "daily_two_capture_limit", day
    if not first.exists():
        return first, "first_capture", day
    previous = json.loads(first.read_text(encoding="utf8"))
    first_at = instant(previous.get("captured_at_utc"))
    if first_at > now or first_at.astimezone(MSK).date() != moscow.date():
        raise ValueError("First PIT has a future or wrong-day timestamp")
    if now - first_at < timedelta(hours=4):
        return None, "four_hour_cooldown", day
    # Save the second immutable slot for evening/night NBA fixtures.
    # Do not exhaust it at an early 4-hour polling cycle.
    if reserve_evening and moscow.hour < 16:
        return None, "second_capture_reserved_until_16_msk", day
    return second, "second_capture", day


def run(*, capture_only=False, evaluate_only=False, reserve_evening=True):
    if capture_only and evaluate_only:
        raise ValueError("Choose either PIT capture-only or evaluation-only")
    now = datetime.now(UTC)
    load = lambda name: json.loads((DATA / name).read_text(encoding="utf8"))
    directory = DATA / "catalog_pit"
    live = load("live.json")
    directory.mkdir(parents=True, exist_ok=True)
    existing = [load("catalog_pit/" + p.name) for p in sorted(directory.glob("*.json"))]
    # Validate history before any write. A bad old snapshot must not be
    # silently ignored when the hourly backup executes.
    _validated_snapshots(existing, now)
    created = False
    decision = "evaluation_only"
    if not evaluate_only:
        target, decision, day = next_capture_slot(
            directory, now, reserve_evening=reserve_evening)
        if target is not None:
            snapshot = capture(load("catalog.json"), live, now)
            if snapshot["snapshot_date_msk"] != day:
                raise ValueError("PIT capture crossed Moscow calendar day")
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(snapshot, ensure_ascii=False,
                                      separators=(",", ":")), encoding="utf8")
            if target.exists():
                raise ValueError("Refusing to replace immutable catalog PIT")
            tmp.replace(target)
            created = True
    snapshots = [load("catalog_pit/" + p.name)
                 for p in sorted(directory.glob("*.json"))]
    _validated_snapshots(snapshots, now)
    if capture_only:
        return {"status": STATUS, "new_snapshot": created,
                "capture_decision": decision, "snapshots": len(snapshots),
                "catalog_proxy_only": True, "adopt_on_site": False,
                "fantasy_account_mutation": False}
    result = evaluate(live, load("participation_cohort_research.json"),
                      load("explicit_dnp_research.json"), snapshots, now,
                      load("official_injury_status_archive.json"),
                      load("telegram_archive.json"))
    target = DATA / "catalog_pit_coverage_research.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf8")
    tmp.replace(target)
    return {"status": STATUS, "new_snapshot": created,
            "capture_decision": decision, "snapshots": len(snapshots),
            "summary": result["summary"], "catalog_proxy_only": True,
            "p_play_deployed": False, "fantasy_account_mutation": False}

if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
