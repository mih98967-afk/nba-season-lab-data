"""Schema, identity and internal coherence audit; no fitting or feature building."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
CURRENT = OUT / "source/current"


def minutes(v):
    if not v:return 0.
    if ":" in v:
        m, s = v.split(":");return float(m) + float(s) / 60
    return float(v)


def main():
    manifest = json.loads((CURRENT / "manifest.json").read_text())
    missing = [r for r in manifest if r["status"] != "retrieved"]
    if missing:
        report = {"status": "BLOCKED_SOURCE_INTAKE", "failed_sources": missing,
                  "coherent_current_snapshot_verified": False, "feature_frame_built": False,
                  "fit_or_selection_performed": False}
        (OUT / "SOURCE_QA.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2));return
    def read(name):return pd.read_csv(CURRENT / name, dtype=str, keep_default_na=False)
    schedule = read("nba_schedule_2027.csv.gz")
    sc = schedule[schedule.game_id.str.startswith("002")].copy()
    box = read("player_boxscores_2027.csv")
    box = box[box.game_id.str.startswith("002")].copy()
    inactive = read("game_rosters_2027.csv")
    inactive = inactive[inactive.game_id.str.startswith("002")].copy()
    injury = read("injury_report_2027.csv.gz")
    mapping = {r.game_id: r for r in sc.itertuples(index=False)}
    errors = []
    def require(condition, code, details=None):
        if not condition:errors.append({"code": code, "details": details})
    require(not sc.game_id.duplicated().any(), "DUPLICATE_SCHEDULE_GAME")
    require(not box.duplicated(["game_id", "person_id"]).any(), "DUPLICATE_BOXSCORE_PLAYER_GAME")
    require(not inactive.duplicated(["game_id", "player_id"]).any(), "DUPLICATE_INACTIVE_PLAYER_GAME")
    unmapped = sorted(set(box.game_id) - set(mapping))
    require(not unmapped, "BOXSCORE_GAME_NOT_IN_SCHEDULE", unmapped[:20])
    unmapped_inactive = sorted(set(inactive.game_id) - set(mapping))
    require(not unmapped_inactive, "INACTIVE_GAME_NOT_IN_SCHEDULE", unmapped_inactive[:20])
    wrong_box = [];wrong_inactive = []
    for r in box.itertuples(index=False):
        if r.game_id in mapping:
            g = mapping[r.game_id]
            if (r.team_id, r.team_tricode) not in [(g.home_team_id, g.home_team_abbreviation), (g.away_team_id, g.away_team_abbreviation)]:wrong_box.append([r.game_id, r.person_id])
    for r in inactive.itertuples(index=False):
        if r.game_id in mapping:
            g = mapping[r.game_id]
            if (r.team_id, r.team_abbreviation) not in [(g.home_team_id, g.home_team_abbreviation), (g.away_team_id, g.away_team_abbreviation)]:wrong_inactive.append([r.game_id, r.player_id])
    require(not wrong_box, "BOXSCORE_TEAM_IDENTITY_MISMATCH", wrong_box[:20])
    require(not wrong_inactive, "INACTIVE_TEAM_IDENTITY_MISMATCH", wrong_inactive[:20])
    box["_minutes"] = box.minutes.map(minutes)
    played = box[box._minutes > 0].copy()
    components = ["points", "rebounds_total", "assists", "steals", "blocks", "field_goals_made", "free_throws_made", "field_goals_attempted", "free_throws_attempted", "fouls_personal", "turnovers"]
    numeric = played[components].apply(pd.to_numeric, errors="coerce")
    bad_components = numeric.isna().any(axis=1) | (numeric < 0).any(axis=1)
    require(not bad_components.any(), "INVALID_PLAYED_COMPONENTS", int(bad_components.sum()))
    played["_points"] = pd.to_numeric(played.points, errors="coerce")
    explicit_zero = (box._minutes == 0) & box.comment.str.upper().str.match(r"^(DNP|DND|NWT)(?:\b|_|-)")
    unknown_box = (box._minutes == 0) & ~explicit_zero
    conflict = played[["game_id", "person_id"]].merge(inactive[["game_id", "player_id"]], left_on=["game_id", "person_id"], right_on=["game_id", "player_id"])
    require(conflict.empty, "POSITIVE_MINUTES_EXPLICIT_INACTIVE_CONFLICT", conflict.head(20).to_dict("records"))
    hp = pd.to_numeric(sc.home_pts, errors="coerce");ap = pd.to_numeric(sc.away_pts, errors="coerce")
    complete_schedule = sc[hp.notna() & ap.notna() & (hp != ap)].copy()
    aggregates = played.groupby(["game_id", "team_tricode"], observed=True).agg(points=("_points", "sum"), minutes=("_minutes", "sum"))
    missing_complete = [];team_totals = [];coherent_games = []
    for g in complete_schedule.itertuples(index=False):
        valid = True
        for team, expected in [(g.home_team_abbreviation, float(g.home_pts)), (g.away_team_abbreviation, float(g.away_pts))]:
            if (g.game_id, team) not in aggregates.index:
                missing_complete.append([g.game_id, team]);valid = False;continue
            a = aggregates.loc[(g.game_id, team)]
            if abs(a.points - expected) > .01 or a.minutes < 235:
                team_totals.append({"game_id": g.game_id, "team": team, "box_points": float(a.points), "schedule_points": expected, "minutes": float(a.minutes)});valid = False
        if valid:coherent_games.append(g.game_id)
    require(not missing_complete, "FINISHED_SCHEDULE_MISSING_TEAM_BOXSCORE", missing_complete[:20])
    require(not team_totals, "INCOMPLETE_OR_CONFLICTING_TEAM_TOTALS", team_totals[:20])
    # Unresolved IDs are coverage exclusions, not assigned to guessed games/players.
    known_injury = injury[injury.game_id.isin(mapping)].copy()
    weak_identity = (~known_injury.match_method.isin(["exact", "roster"])) | (known_injury.person_id == "")
    injury_team_mismatch = [];injury_date_mismatch = []
    for r in known_injury.itertuples(index=False):
        g = mapping[r.game_id]
        if r.team_id not in [g.home_team_id, g.away_team_id]:injury_team_mismatch.append([r.game_id, r.team_id])
        if r.game_date[:10] != g.game_date[:10]:injury_date_mismatch.append([r.game_id, r.game_date])
    require(not injury_team_mismatch, "INJURY_TEAM_IDENTITY_MISMATCH", injury_team_mismatch[:20])
    require(not injury_date_mismatch, "INJURY_GAME_DATE_MISMATCH", injury_date_mismatch[:20])
    prior = OUT.parents[1] / "research_base/source/current"
    hashes = {}
    for r in manifest:
        name = r["file"];p = CURRENT / name
        old = prior / name
        hashes[name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size,
                        "same_as_preserved_20261116": old.exists() and hashlib.sha256(old.read_bytes()).hexdigest() == r["sha256"]}
    latest_completed = str(complete_schedule.game_date.max()) if len(complete_schedule) else None
    latest_coherent = str(sc.loc[sc.game_id.isin(coherent_games), "game_date"].max()) if coherent_games else None
    report = {
        "status": "INTERNAL_COHERENCE_PASS" if not errors else "INTERNAL_COHERENCE_FAILED",
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "errors": errors,
        "coherent_current_snapshot_verified": not errors,
        "upstream_atomic_version_proven": False,
        "source_freshness_separate_from_fetch_time": True,
        "schedule": {"regular_season_games": len(sc), "dates": [sc.game_date.min(), sc.game_date.max()],
                     "completed_games_with_score": len(complete_schedule), "latest_completed_date": latest_completed,
                     "coherent_completed_games": len(coherent_games), "latest_coherent_completed_date": latest_coherent,
                     "schedule_time_precision": "NBA game date only; no UTC tipoff in this source"},
        "boxscore": {"rows": len(box), "games": box.game_id.nunique(), "players": box.person_id.nunique(),
                     "positive_minute_rows": len(played), "explicit_DNP_comment_rows": int(explicit_zero.sum()),
                     "UNKNOWN_zero_minute_rows": int(unknown_box.sum()), "missing_or_invalid_played_stat_rows": int(bad_components.sum())},
        "inactive": {"explicit_rows": len(inactive), "games": inactive.game_id.nunique(), "positive_minutes_conflicts": len(conflict)},
        "injury": {"raw_version_rows": len(injury), "mapped_game_rows": len(known_injury),
                   "unmapped_or_blank_game_rows": int((~injury.game_id.isin(mapping)).sum()),
                   "weak_or_missing_player_identity_rows": int(weak_identity.sum()),
                   "weak_named_player_identity_rows": int((weak_identity & (known_injury.report_player_name != "")).sum()),
                   "not_yet_submitted_placeholder_rows": int(known_injury.reason.str.contains("NOT YET SUBMITTED", case=False, regex=False).sum()),
                   "latest_report_datetime_source": injury.report_datetime.max(),
                   "earliest_report_datetime_source": injury.report_datetime.min(),
                   "timezone_note": "source report_datetime is naive; do not mistake for UTC", "game_dates": [injury.game_date.min(), injury.game_date.max()]},
        "hashes": hashes, "feature_frame_built": False, "fit_or_selection_performed": False,
        "official_Sports_ru_credits_proven": False,
    }
    (OUT / "SOURCE_QA.json").write_text(json.dumps(report, indent=2, default=int) + "\n")
    print(json.dumps(report, indent=2, default=int))


if __name__ == "__main__":main()
