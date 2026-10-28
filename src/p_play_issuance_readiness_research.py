"""Research-only diagnosis of why no new immutable p_play issues were emitted.

Source-of-truth for eligibility is the existing PIT catalog/ESPN snapshot
contracts. This module *never* issues a forecast, modifies a label, assumes
game-day membership, or marks an absent person as DNP.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from src.sync import DATA
from src.catalog_pit_research import (
    _validated_snapshots as validate_catalog,
    LOCK, HORIZON, MAX_SNAPSHOT_AGE,
)
from src.prelock_roster_opportunities import (
    validate_espn_snapshots, HIGH, WEAK,
)
from src.p_play_shadow_research import _fresh, _prior_input
from src.rolling_decision_research import instant, stamp

STATUS = "research_only_not_deployed"
CANDIDATE_METHODS = {HIGH, WEAK}
# Monitoring threshold only. NOT an NBA game-day eligibility or DNP rule.
URGENT_LOCK_WINDOW = timedelta(hours=24)
MISSING_PIT = {
    "catalog_capture_outside_prelock_36h",
    "fixture_missing_from_captured_catalog",
    "ESPN_capture_outside_prelock_36h",
}


def _fixture_in_snapshot(snap, game_id):
    return next(
        (f for f in snap["future_fixtures_observed"] if f["game_id"] == game_id),
        None,
    )


def diagnose(live, shadow, catalog_snapshots, espn_snapshots, now):
    """Count future scheduled fixtures exactly as of this observation clock."""
    if now.utcoffset() is None:
        raise ValueError("Research clock must be timezone aware")
    now = now.astimezone(timezone.utc)
    if live.get("schema_version") != 4:
        raise ValueError("No validated public NBA live schedule")
    issued, observed, _ = _prior_input(shadow)
    if (shadow.get("status") != STATUS or shadow.get("adopt_on_site") is not False
            or shadow.get("population_brier_enabled") is not False):
        raise ValueError("No research-only immutable p_play source")
    cat = validate_catalog(catalog_snapshots, now)
    espn = validate_espn_snapshots(espn_snapshots, now)
    by_game = defaultdict(set)
    for p in issued:
        gid, pid = p.get("game_id"), p.get("player_id")
        if not isinstance(gid, str) or not isinstance(pid, str):
            raise ValueError("Invalid first-issued forecast key")
        t_issue = instant(p["issued_at_utc"])
        t_lock = instant(p["individual_lock_utc"])
        t_tip = instant(p["tipoff_utc"])
        if (t_issue > now or not t_issue < t_lock < t_tip
                or (t_tip - t_lock).total_seconds() != 1800):
            raise ValueError("Backdated or future first-issued forecast")
        by_game[gid].add(pid)

    fresh = _fresh(live, now)
    unique_games = set()
    fixture_rows = []
    count = Counter()
    monitoring = Counter()
    planned = live.get("schedule")
    if not isinstance(planned, list):
        raise ValueError("Missing public fixtures")
    for g in sorted(planned, key=lambda v: (v["utc"], v["id"])):
        if not isinstance(g, dict) or g.get("status") != "scheduled":
            continue
        gid = g.get("id")
        if not isinstance(gid, str) or not gid or gid in unique_games:
            raise ValueError("Invalid/duplicated scheduled game")
        unique_games.add(gid)
        tip = instant(g["utc"])
        if not now < tip <= now + HORIZON:
            continue
        lock = tip - LOCK
        if not (g.get("home") and g.get("away")
                and g["home"] != g["away"]):
            raise ValueError("Bad future fixture club pairing")

        # These are snapshots that were already captured, not hypothetical
        # future events. Existing pre-lock contracts require age <= 36 h AT LOCK.
        observed_cat = [
            (at, snap, _fixture_in_snapshot(snap, gid))
            for at, snap in cat
            if _fixture_in_snapshot(snap, gid) is not None
            and at <= lock and lock - at <= MAX_SNAPSHOT_AGE
        ]
        eligible_espn = [
            (at, snap) for at, snap in espn
            if at <= lock and lock - at <= MAX_SNAPSHOT_AGE
        ]
        covered_by_any_catalog = any(
            _fixture_in_snapshot(snap, gid) is not None for _, snap in cat
        )
        cat_at = observed_cat[-1][0] if observed_cat else None
        espn_at = eligible_espn[-1][0] if eligible_espn else None
        known_ids = by_game.get(gid, set())
        linked = set()
        matched_strong = matched_weak = 0
        reason = None

        if lock <= now:
            reason = "individual_lock_elapsed"
        elif not observed_cat:
            reason = ("catalog_capture_outside_prelock_36h"
                      if covered_by_any_catalog else "fixture_missing_from_captured_catalog")
        elif (observed_cat[-1][2]["tipoff_utc"] != stamp(tip)
              or observed_cat[-1][2]["home"] != g["home"]
              or observed_cat[-1][2]["away"] != g["away"]):
            reason = "catalog_fixture_rescheduled_or_team_changed"
        elif not eligible_espn:
            reason = "ESPN_capture_outside_prelock_36h"
        else:
            snapshot_cat = observed_cat[-1][1]
            snapshot_espn = eligible_espn[-1][1]
            roster = {}
            for team in snapshot_espn["teams"]:
                for a in team["athletes"]:
                    pid = a.get("sportsru_player_id")
                    if pid is not None:
                        if pid in roster:
                            raise ValueError("Duplicated ESPN person-to-fantasy ID")
                        roster[pid] = (team["club"], a["identity_method"])
            for player in snapshot_cat["catalog_players_proxy"]:
                if player["catalog_team"] not in (g["home"], g["away"]):
                    continue
                who = roster.get(player["player_id"])
                if not who or who[0] != player["catalog_team"]:
                    continue
                if who[1] not in CANDIDATE_METHODS:
                    raise ValueError("Unverified ESPN identity method")
                linked.add(player["player_id"])
                if who[1] == HIGH:
                    matched_strong += 1
                else:
                    matched_weak += 1
            if not linked:
                reason = "no_same_club_cross_source_ID"
            elif not linked - known_ids:
                reason = "all_mapped_players_already_issued"
            elif not fresh:
                reason = "live_or_calendar_source_not_fresh"
            else:
                reason = "new_prelock_candidates_ready"

        count[reason] += 1
        # A 72h diagnostic naturally includes fixtures with >36h remaining.
        # These are NOT late captures. Escalate only within 24h of player lock.
        remaining = lock - now
        if remaining <= timedelta(0):
            monitor = "lock_elapsed_not_actionable"
        elif reason == "all_mapped_players_already_issued":
            monitor = "cross_source_proxy_first_issues_covered"
        elif reason == "new_prelock_candidates_ready":
            monitor = "new_selected_candidates_ready_to_issue"
        elif reason in MISSING_PIT:
            monitor = ("prelock_capture_needed_within_24h"
                       if remaining <= URGENT_LOCK_WINDOW else
                       "awaiting_prospective_snapshot_beyond_24h")
        else:
            monitor = ("other_source_issue_within_24h"
                       if remaining <= URGENT_LOCK_WINDOW else
                       "other_source_issue_beyond_24h")
        monitoring[monitor] += 1
        if timedelta(0) < remaining <= URGENT_LOCK_WINDOW:
            monitoring["all_games_locking_within_24h"] += 1
            if monitor == "cross_source_proxy_first_issues_covered":
                monitoring["proxy_issued_games_locking_within_24h"] += 1
        new_now = len(linked - known_ids) if reason == "new_prelock_candidates_ready" else 0
        count["potential_new_player_games"] += new_now
        count["already_issued_in_upcoming_games"] += len(known_ids)
        count["matched_strong_ID_in_eligible_sources"] += matched_strong
        count["matched_weak_name_in_eligible_sources"] += matched_weak
        fixture_rows.append({
            "game_id": gid,
            "tipoff_utc": stamp(tip),
            "individual_lock_utc": stamp(lock),
            "home": g["home"], "away": g["away"],
            "catalog_capture_utc": stamp(cat_at) if cat_at else None,
            "espn_capture_utc": stamp(espn_at) if espn_at else None,
            "historical_issued_count": len(known_ids),
            "latest_cross_source_mapped_count": len(linked),
            "latest_high_ID_mapped_count": matched_strong,
            "latest_unique_name_only_mapped_count": matched_weak,
            "unissued_mapped_candidates_now": new_now,
            "readiness": reason,
            "hours_until_individual_lock": round(remaining.total_seconds()/3600, 2),
            "operational_capture_monitor": monitor,
        })

    direct_partition = sum(
        v for k, v in count.items()
        if k in {
            "individual_lock_elapsed", "catalog_capture_outside_prelock_36h",
            "fixture_missing_from_captured_catalog",
            "catalog_fixture_rescheduled_or_team_changed",
            "ESPN_capture_outside_prelock_36h", "no_same_club_cross_source_ID",
            "all_mapped_players_already_issued",
            "live_or_calendar_source_not_fresh",
            "new_prelock_candidates_ready",
        }
    )
    if direct_partition != len(fixture_rows):
        raise ValueError("Missing readiness reason for scheduled fixture")
    monitor_states = {
        "lock_elapsed_not_actionable",
        "cross_source_proxy_first_issues_covered",
        "new_selected_candidates_ready_to_issue",
        "prelock_capture_needed_within_24h",
        "awaiting_prospective_snapshot_beyond_24h",
        "other_source_issue_within_24h",
        "other_source_issue_beyond_24h",
    }
    if sum(monitoring[x] for x in monitor_states) != len(fixture_rows):
        raise ValueError("Operational PIT readiness monitor has missing fixtures")
    if (monitoring["prelock_capture_needed_within_24h"] >
            monitoring["all_games_locking_within_24h"]):
        raise ValueError("PIT capture cannot be urgent for future-dated fixtures")
    return {
        "schema_version": 1,
        "status": STATUS, "model_status": STATUS, "adopt_on_site": False,
        "updated_at_utc": stamp(now),
        "target": "research_prelock_issuance_readiness_not_player_game_eligibility",
        "live_feed_updated_at_utc": live.get("updated_at_utc"),
        "calendar_validated_at_utc": (live.get("schedule_quality") or {}).get("validated_at_utc"),
        "source_fresh_for_new_forecasts": fresh,
        "existing_frozen_issues_total": len(issued),
        "existing_verified_outcomes_unchanged": len(observed),
        "catalog_snapshot_count": len(cat),
        "espn_snapshot_count": len(espn),
        "future_scheduled_games_next_72h": len(fixture_rows),
        "readiness_counts": dict(count),
        "operational_capture_monitor_counts": dict(monitoring),
        "operational_monitor_horizon_hours": 24,
        "operational_monitor_is_not_game_day_eligibility": True,
        "per_game": fixture_rows,
        "uncertain_roster_denominator_verified": False,
        "missing_row_does_not_mean_DNP": True,
        "training_negative_from_unknown_permitted": False,
        "new_pplay_model_deployed": False,
        "limitations": [
            "Only future scheduled fixtures within 72h at audit time are checked.",
            "Sports.ru catalog and ESPN current team rosters are preliminary club proxies.",
            "A strong ESPN ID is not a confirmed active NBA game-day roster membership.",
            "No new frozen forecast is actually issued by this diagnostic.",
            "A later roster capture cannot be backdated to earlier individual locks.",
            "A fixture in the next 72h but >36h after the last capture is not necessarily an overdue capture.",
            "Only missing PIT sources with player lock <=24h are escalated; this is an operational warning, not an NBA roster label.",
            "Upcoming games with stale catalog require new independently timed snapshots.",
        ],
    }


def run():
    def read(path):
        return json.loads(path.read_text(encoding="utf8"))
    now = datetime.now(timezone.utc)
    result = diagnose(
        read(DATA / "live.json"),
        read(DATA / "p_play_shadow_research.json"),
        [read(p) for p in sorted((DATA / "catalog_pit").glob("*.json"))],
        [read(p) for p in sorted((DATA / "espn_roster_pit").glob("*.json"))],
        now,
    )
    dest = DATA / "p_play_issuance_readiness_research.json"
    previous = read(dest) if dest.exists() else {}
    without_clock = lambda obj: {
        k: v for k, v in obj.items() if k != "updated_at_utc"
    }
    if not previous or without_clock(previous) != without_clock(result):
        temp = dest.with_suffix(".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf8")
        temp.replace(dest)
    return {
        "status": STATUS,
        "future_scheduled_games_next_72h":
            result["future_scheduled_games_next_72h"],
        "readiness_counts": result["readiness_counts"],
        "first_issued_forecasts_unchanged":
            result["existing_frozen_issues_total"],
        "adopt_on_site": False,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
