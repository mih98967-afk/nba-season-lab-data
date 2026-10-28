"""Read-only bridge from existing FIRST-ISSUED NBA shadows to transfer research.

Does NOT estimate unconditional FP, player availability, real transfer profit,
player pricing, true game-day club tenure or any user's fantasy roster.
Only uses prospective issued records, NOT historical outcomes or revised scores.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone, time
from math import isfinite
from zoneinfo import ZoneInfo
import json

from src.sync import DATA
from src.keep_transfer_economic_replay import moment, ensure, STATUS
from src.live_calendar_fallback import TEAMS

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
MAX_SOURCE_AGE = timedelta(hours=8)
MAX_CALENDAR_AGE = timedelta(hours=36)
LOCK = timedelta(minutes=30)
POSITIONS = {"PG", "SG", "SF", "PF", "C"}
EVIDENCE = {"same_club_independent_ESPN_ID_observed",
            "same_club_unique_name_only_observed"}


def et_end(now):
    local = now.astimezone(ET)
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday + timedelta(days=7), time(), ET).astimezone(UTC)


def source_guard(source, kind):
    ensure(isinstance(source, dict) and source.get("schema_version") == 1
           and source.get("status") == STATUS
           and source.get("adopt_on_site") is False,
           "INVALID_RESEARCH_" + kind)


def index_issues(source, name):
    rows = source.get("issued")
    ensure(isinstance(rows, list), "MISSING_" + name + "_ISSUES")
    index = {}
    for row in rows:
        ensure(isinstance(row, dict), "MALFORMED_" + name + "_ISSUE")
        key = (row.get("game_id"), row.get("player_id"))
        ensure(all(isinstance(part, str) and part for part in key)
               and key not in index, "DUPLICATE_OR_INVALID_" + name + "_ISSUE")
        index[key] = row
    return index


def build(live, pplay, conditional, cutoff):
    now = moment(cutoff)
    ensure(isinstance(live, dict) and live.get("schema_version") == 4,
           "BAD_LIVE_SCHEMA")
    source_guard(pplay, "PPLAY")
    source_guard(conditional, "CONDITIONAL")
    ensure(pplay.get("population_brier_enabled") is False
           and pplay.get("full_game_day_roster_denominator_verified") is False
           and conditional.get("unconditional_FP_enabled") is False,
           "UNSUPPORTED_UNCONDITIONAL_FP_CLAIM")
    observed = moment(live.get("updated_at_utc"))
    quality = live.get("schedule_quality") or {}
    validated = moment(quality.get("validated_at_utc"))
    ensure(observed <= now and validated <= now and
           now - observed <= MAX_SOURCE_AGE and
           now - validated <= MAX_CALENDAR_AGE and
           quality.get("freshness") == "fresh",
           "STALE_OR_FUTURE_PUBLIC_CALENDAR")
    period_end = et_end(now)
    raw = live.get("schedule")
    ensure(isinstance(raw, list), "MISSING_PUBLIC_SCHEDULE")
    fixtures = {}
    for item in raw:
        ensure(isinstance(item, dict) and
               isinstance(item.get("id"), str) and item.get("id") not in fixtures,
               "DUPLICATE_OR_INVALID_PUBLIC_FIXTURE")
        fixtures[item["id"]] = item
    relevant = {}
    for gid, game in fixtures.items():
        tip = moment(game.get("utc"))
        if not (now < tip < period_end) or game.get("status") != "scheduled":
            continue
        ensure(game.get("home") in TEAMS and game.get("away") in TEAMS
               and game.get("home") != game.get("away"),
               "INVALID_FUTURE_CLUB_FIXTURE")
        relevant[gid] = {"utc": tip, "home": game["home"], "away": game["away"]}
    p_index = index_issues(pplay, "PPLAY")
    c_index = index_issues(conditional, "CONDITIONAL")
    qa = Counter()
    rows = []
    for (gid, pid), issue in sorted(p_index.items()):
        game = relevant.get(gid)
        if game is None:
            continue
        tip = game["utc"]
        p_issued = moment(issue.get("issued_at_utc"))
        lock = moment(issue.get("individual_lock_utc"))
        original_tip = moment(issue.get("tipoff_utc"))
        if (p_issued > now):
            qa["p_play_issue_not_yet_observed"] += 1
            continue
        ensure(p_issued < lock == tip - LOCK and original_tip == tip,
               "PPLAY_ISSUANCE_OR_FIXTURE_NOT_PROSPECTIVE")
        team = issue.get("team")
        pos = issue.get("position")
        ensure(team in (game["home"], game["away"]) and pos in POSITIONS,
               "PPLAY_TEAM_OR_POSITION_CONFLICT")
        ensure(issue.get("club_link_evidence") in EVIDENCE,
               "UNVERIFIED_CROSS_SOURCE_IDENTITY")
        qa["p_play_selected_issued"] += 1
        if issue["club_link_evidence"] == "same_club_independent_ESPN_ID_observed":
            qa["strong_ESPN_ID_at_first_issue"] += 1
        row = {
            "game_id": gid, "player_id": pid, "team_at_issue_proxy": team,
            "position_at_issue_proxy": pos,
            "tipoff_utc": tip.isoformat(),
            "p_play_first_issued_at_utc": p_issued.isoformat(),
            "club_link_evidence": issue["club_link_evidence"],
            "p_play_selected_listed_proxy_not_population_calibrated": True,
            "conditional_first_issued_at_utc": None,
            "fp_if_play_first_issued": None,
            "full_game_day_membership_verified": False,
            "unconditional_expected_fp_validated": False,
            "economic_transfer_ready": False,
        }
        conditional_issue = c_index.get((gid, pid))
        if conditional_issue is not None:
            issued = moment(conditional_issue.get("issued_at_utc"))
            if issued > now:
                qa["conditional_issue_after_decision_excluded"] += 1
            else:
                ensure(p_issued <= issued < lock,
                       "CONDITIONAL_ISSUANCE_AFTER_LOCK_OR_BEFORE_PPLAY")
                ensure(moment(conditional_issue.get("game_utc")) == tip
                       and conditional_issue.get("team") == team,
                       "CONDITIONAL_GAME_OR_CLUB_CONFLICT")
                fp = conditional_issue.get("direct_fp_if_play")
                ensure(type(fp) in (int, float) and isfinite(fp),
                       "INVALID_CONDITIONAL_FP")
                row["conditional_first_issued_at_utc"] = issued.isoformat()
                row["fp_if_play_first_issued"] = fp
                qa["matched_conditional_if_play"] += 1
        else:
            qa["p_play_issued_without_conditional"] += 1
        rows.append(row)
    ensure(qa["matched_conditional_if_play"] <= qa["p_play_selected_issued"],
           "CONDITIONAL_ISSUE_COUNT_EXCEEDS_PPLAY")
    return {
        "schema_version": 1, "status": STATUS, "adopt_on_site": False,
        "decision_asof_utc": now.isoformat(),
        "period_end_utc": period_end.isoformat(),
        "research_target": "prospective frozen coverage, not forecast ranking",
        "source_live_updated_at_utc": live["updated_at_utc"],
        "source_schedule_validated_at_utc": quality["validated_at_utc"],
        "scheduled_future_games_in_ET_week": len(relevant),
        "frozen_coverage": dict(qa),
        "observed_player_games": rows,
        "source_schedule_complete": quality.get("complete") is True,
        "model_population_pplay_calibrated": False,
        "unconditional_FP_from_conditional_not_allowed": True,
        "price_coverage_prospectively_verified": False,
        "club_at_game_verified": False,
        "user_roster_loaded": False,
        "valid_KEEP_TRANSFER_backtest_possible": False,
        "limitations": [
            "Selected ESPN-list appearance proxy is not calibrated p_play.",
            "FP if playing is NOT unconditional FP and cannot be ranked as a transfer gain.",
            "Only frozen first-issue values before the decision; observations and postgame outcomes ignored.",
            "Current static catalog start_price is NOT a decision-time sell/buy quote.",
            "Team and position reflect archived PIT proxy, not verified club tenure at each future game.",
            "No personal Firestore, roster, price, Sports.ru trades, or site modifications.",
        ]
    }


def run():
    read = lambda name: json.loads((DATA/name).read_text(encoding="utf8"))
    now = datetime.now(UTC).isoformat()
    result = build(read("live.json"), read("p_play_shadow_research.json"),
                   read("conditional_minutes_fp_research.json"), now)
    return {k: result[k] for k in ("status", "decision_asof_utc", "period_end_utc",
                                   "scheduled_future_games_in_ET_week", "frozen_coverage",
                                   "price_coverage_prospectively_verified",
                                   "valid_KEEP_TRANSFER_backtest_possible")}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
