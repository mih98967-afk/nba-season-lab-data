"""Public-source readiness for Sports.ru KEEP/TRANSFER research.

Read-only input: existing tracked public research JSON. Writes one compact
research-only data report in the atomic NBA sync. Never reads private rosters,
Firestore or a Sports.ru account. Prices are UNKNOWN, not startup prices.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from src.sync import DATA
from src.keep_transfer_economic_replay import InsufficientEvidence, STATUS
from src.keep_transfer_public_bridge import build

OUTFILE = "keep_transfer_public_readiness_research.json"
SOURCES = {
    "live": "live.json",
    "p_play_first_issues": "p_play_shadow_research.json",
    "conditional_first_issues": "conditional_minutes_fp_research.json",
}
NO_DEPLOY = {
    "status": STATUS,
    "adopt_on_site": False,
    "real_KEEP_TRANSFER_gain_proven": False,
    "unconditional_FP_validated": False,
    "population_p_play_calibrated": False,
    "personal_roster_accessed": False,
    "historical_prices_inferred": False,
    "new_model_deployed": False,
}


def public_report(source, source_hashes, cutoff):
    result = {"schema_version": 1, **NO_DEPLOY,
              "decision_asof_utc": cutoff,
              "source_content_sha256": source_hashes,
              "research_scope": "readiness of frozen public player-game data only",
              "source_audit": {"sportsru_credited_FP_in_public_sources": False,
                               "verified_decision_time_sell_buy_prices": False,
                               "verified_owner_roster_and_cash": False,
                               "verified_owner_quota_and_unlock": False,
                               "verified_game_day_club_tenure": False}}
    try:
        bridge = build(source["live"], source["p_play_first_issues"],
                       source["conditional_first_issues"], cutoff)
    except (InsufficientEvidence, ValueError, TypeError, KeyError) as error:
        return {**result, "phase": "BLOCKED_PUBLIC_SOURCE",
                "blocking_reason": str(error),
                "selected_player_games": None,
                "conditional_if_play_player_games": None,
                "scheduled_upcoming_ET_week_games": None,
                "valid_KEEP_TRANSFER_backtest_possible": False}
    counts = Counter()
    game_rows = {}
    upcoming = bridge["scheduled_future_games_in_ET_week"]
    for row in bridge["observed_player_games"]:
        counts["p_play_selected_first_issued"] += 1
        gid = row["game_id"]
        game = game_rows.setdefault(gid, {
            "game_id": gid, "tipoff_utc": row["tipoff_utc"],
            "selected_p_play": 0, "conditional_if_play": 0,
            "strong_ESPN_ID": 0, "weak_name_only": 0})
        game["selected_p_play"] += 1
        if row["club_link_evidence"] == "same_club_independent_ESPN_ID_observed":
            counts["strong_ESPN_ID"] += 1
            game["strong_ESPN_ID"] += 1
        else:
            counts["weak_name_only"] += 1
            game["weak_name_only"] += 1
        if row["fp_if_play_first_issued"] is not None:
            counts["conditional_if_play"] += 1
            game["conditional_if_play"] += 1
    selected = counts["p_play_selected_first_issued"]
    conditional = counts["conditional_if_play"]
    if (selected != bridge["frozen_coverage"].get("p_play_selected_issued", 0)
            or conditional != bridge["frozen_coverage"].get("matched_conditional_if_play", 0)
            or selected != counts["strong_ESPN_ID"] + counts["weak_name_only"]
            or len(game_rows) > upcoming):
        raise ValueError("Research bridge coverage denominator inconsistent")
    return {
        **result,
        "phase": "PUBLIC_FROZEN_COVERAGE_ONLY",
        "scheduled_upcoming_ET_week_games": upcoming,
        "selected_player_games": selected,
        "conditional_if_play_player_games": conditional,
        "strong_ESPN_ID_issued": counts["strong_ESPN_ID"],
        "weak_name_only_issued": counts["weak_name_only"],
        "unmatched_conditional_or_not_yet_issued": selected-conditional,
        "source_schedule_complete": bridge["source_schedule_complete"],
        "source_live_updated_at_utc": bridge["source_live_updated_at_utc"],
        "source_schedule_validated_at_utc": bridge["source_schedule_validated_at_utc"],
        "by_game_with_selected_issues": sorted(game_rows.values(),
                                              key=lambda x: (x["tipoff_utc"], x["game_id"])),
        "blocking_reasons": [
            "No prospectively verified Sports.ru acquisition/sale prices",
            "No owner-verified and consented account roster, cash, quota and locks",
            "Only selected-list appearance proxy; no calibrated full-population p_play",
            "Only conditional-on-playing FP; no verified unconditional FP",
            "No independent game-day player club tenure or full roster denominator",
            "No Sports.ru credited FP outcome denominator for economic replay",
            *(["Incomplete future season schedule; week completeness cannot be assumed"]
              if not bridge["source_schedule_complete"] else []),
        ],
        "valid_KEEP_TRANSFER_backtest_possible": False,
    }


def load_public_sources(base=DATA):
    sources, fingerprints = {}, {}
    for key, file in SOURCES.items():
        raw = (Path(base) / file).read_bytes()
        fingerprints[key] = sha256(raw).hexdigest()
        sources[key] = json.loads(raw)
    return sources, fingerprints


def verify_persisted(base=DATA):
    """Verify the archived report against EXACT bytes of the same public inputs.

    No current-time re-evaluation: use the original decision clock to ensure
    an atomic main publication cannot contain an outdated or forged report.
    """
    path = Path(base) / OUTFILE
    report = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(report, dict):
        raise ValueError("Invalid published research report")
    sources, fingerprints = load_public_sources(base)
    if report.get("source_content_sha256") != fingerprints:
        raise ValueError("KEEP/TRANSFER source SHA mismatch")
    if report.get("status") != STATUS or report.get("adopt_on_site") is not False:
        raise ValueError("KEEP/TRANSFER report must remain research-only")
    expected = public_report(sources, fingerprints, report.get("decision_asof_utc"))
    if report != expected:
        raise ValueError("KEEP/TRANSFER archived report is not reproducible")
    return {"status": STATUS, "verified_public_source_hashes": len(fingerprints),
            "phase": report["phase"], "adopt_on_site": False}


def run(base=DATA, *, persist=False, asof=None):
    sources, fingerprints = load_public_sources(base)
    decision = asof or datetime.now(timezone.utc).isoformat()
    report = public_report(sources, fingerprints, decision)
    if persist:
        path = Path(base) / OUTFILE
        old = json.loads(path.read_text(encoding="utf8")) if path.exists() else None
        if old != report:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf8")
            tmp.replace(path)
    return {key: report.get(key) for key in
            ("status", "phase", "decision_asof_utc",
             "scheduled_upcoming_ET_week_games", "selected_player_games",
             "conditional_if_play_player_games", "valid_KEEP_TRANSFER_backtest_possible",
             "blocking_reason")}


if __name__ == "__main__":
    import sys
    if "--verify" in sys.argv:
        response = verify_persisted()
    else:
        response = run(persist="--publish" in sys.argv)
    print(json.dumps(response, ensure_ascii=False, indent=2))
