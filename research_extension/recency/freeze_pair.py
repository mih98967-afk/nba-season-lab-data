"""Immutable next-slate paired forecast; never score or fit current-season outcomes."""
from pathlib import Path
import datetime as dt
import hashlib
import json
import os
import pickle
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base")).resolve()
CODE = BASE / "research/match_context"
if not (CODE / "run_phase1.py").is_file():
    CODE = ROOT / "research/match_context"
sys.path.insert(0, str(CODE))
from infer import load_verified
from infer_near import predict_near, near_features
import current_validation as cv
from features import build_recency_features

UTC = dt.timezone.utc
ORIGINAL_FORECAST_SHA = "5aa81fa5db8f8a4e240cce3ec2477fad17626822c5eea2c02f39dab1b932a0cb"

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def utc(value):
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIME_FORBIDDEN")
    return parsed.astimezone(UTC)

def validate_target(row, game, issued):
    if pd.notna(row.get("y_play")) or pd.notna(row.get("y_fp")):
        raise ValueError("KNOWN_TARGET_OUTCOME_FORBIDDEN")
    if int(row["horizon_days"]) != 0 or row["issue_date"] != row["date"]:
        raise ValueError("NEAR_GAME_LEAD_RELABEL_FORBIDDEN")
    if {row["team"], row["opp"]} != {game["home"], game["away"]}:
        raise ValueError("SCHEDULE_TEAM_MISMATCH")
    tip = utc(game["utc"])
    if str(tip.astimezone(ZoneInfo("America/New_York")).date()) != row["date"]:
        raise ValueError("SCHEDULE_DATE_MISMATCH")
    if game["status"] != "scheduled" or tip <= issued + dt.timedelta(minutes=30):
        raise ValueError("LOCKED_STARTED_OR_UNCONFIRMED")

def immutable_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with path.open("xb") as f:
        f.write(data)
    return hashlib.sha256(data).hexdigest()

def main():
    fresh = ROOT / "research_extension/fresh_20261117"
    frame_path = fresh / "feature_frame.pkl"
    source = fresh / "source"
    out = ROOT / "research_extension/prospective_20261117"
    if (out / "forecasts.json").exists():
        raise ValueError("IMMUTABLE_COMMITMENT_EXISTS")
    if digest(BASE / "prospective_20261116/forecasts.json") != ORIGINAL_FORECAST_SHA:
        raise ValueError("ORIGINAL_FORECAST_CHANGED")
    d = pd.read_pickle(frame_path)
    d = d.loc[(d.horizon_days == 0) & (d.issue_date.astype(str) == "2026-11-17") & d.y_play.isna() & d.y_fp.isna()].copy().reset_index(drop=True)
    for col in ("pid", "game", "date", "issue_date", "team", "opp", "name"):
        d[col] = d[col].astype(str)
    if d.empty:
        raise ValueError("NO_FUTURE_NEAR_GAME_ROWS")
    anchor, card = load_verified(BASE / "results_near_latest")
    refit_path = ROOT / "research_extension/recency/refitted_day_ewma_mean.pkl"
    refit_card = json.loads((refit_path.parent / "REFIT_REPORT.json").read_text())
    if digest(refit_path) != refit_card["model_sha256"]:
        raise ValueError("RECENCY_MODEL_HASH_MISMATCH")
    with refit_path.open("rb") as f:
        challenger = pickle.load(f)
    if not challenger["no_current_season_fit"] or challenger["fit_target_max"] != "2025-12-31":
        raise ValueError("INVALID_FIT_PROVENANCE")
    cv.ASOF_DATE = "2026-11-17"
    _, raw, _, _ = cv.load_current_combined(source)
    # All histories are strictly before the feature's NBA date; the actual time
    # at which this source was observed is recorded separately below.
    extra = build_recency_features(d, raw)
    prepared = near_features(d, complete_team_groups=True)
    prediction = predict_near(anchor, d, complete_team_groups=True)
    augmented = pd.concat([prepared, extra], axis=1)
    new_mean = d.fp10.to_numpy() + challenger["model"].predict(augmented[challenger["features"]]) + challenger["mean_bias"]
    live_path = source / "data/live.json"
    live = json.loads(live_path.read_text())
    calendar = {}
    for game in live["schedule"]:
        key = (str(utc(game["utc"]).astimezone(ZoneInfo("America/New_York")).date()), frozenset((game["home"], game["away"])))
        calendar.setdefault(key, []).append(game)
    issued = dt.datetime.now(UTC)
    manifest = json.loads((source / "current/manifest.json").read_text())
    if len(manifest) != 4 or any(s["status"] != "retrieved" for s in manifest):
        raise ValueError("INCOMPLETE_CURRENT_SOURCE_INTAKE")
    source_observed = max(utc(s["fetched_at_utc"]) for s in manifest)
    capture = json.loads((fresh / "CAPTURE_SUMMARY.json").read_text())
    capture_completed = utc(capture["completed_at_utc"])
    if source_observed > issued or capture_completed > issued:
        raise ValueError("SOURCE_FROM_FUTURE")
    rows = []
    rejected = {}
    for i, row in enumerate(d.to_dict("records")):
        candidates = calendar.get((row["date"], frozenset((row["team"], row["opp"]))), [])
        if len(candidates) != 1:
            rejected["no_unique_calendar_join"] = rejected.get("no_unique_calendar_join", 0) + 1
            continue
        game = candidates[0]
        try:
            validate_target(row, game, issued)
        except ValueError as exc:
            rejected[str(exc)] = rejected.get(str(exc), 0) + 1
            continue
        pred = prediction.iloc[i]
        values = {k: float(pred[k]) for k in prediction if k in ("p_play", "mean_if_play", "expected_fp") or k.startswith(("conditional_lo", "conditional_hi", "lo", "hi"))}
        if not all(np.isfinite(v) for v in values.values()) or not 0 <= values["p_play"] <= 1 or not np.isfinite(new_mean[i]):
            raise ValueError("NONFINITE_FORECAST")
        common = {"nba_player_id": row["pid"], "nba_game_id": row["game"], "calendar_game_id": game["id"],
                  "tipoff_utc": game["utc"], "date_ET": row["date"], "feature_date_ET": row["issue_date"],
                  "lead_days": 0, "issued_to_tipoff_hours": (utc(game["utc"]) - issued).total_seconds() / 3600,
                  "team": row["team"], "opponent": row["opp"], "player_name": row["name"],
                  "baseline_last10": float(row["fp10"]), "baseline_history_p_play": float(row["obs_play_rate25"]),
                  "distribution_model_sha256": card["model_sha256"]}
        rows.append({**common, "model_role": "near_primary_20261117", "mean_model_sha256": card["model_sha256"], **values})
        updated = dict(values, mean_if_play=float(new_mean[i]), expected_fp=float(values["p_play"] * new_mean[i]))
        rows.append({**common, "model_role": "near_day_ewma_challenger_20261117", "mean_model_sha256": refit_card["model_sha256"], **updated})
    if not rows:
        raise ValueError("NO_UNLOCKED_FORECASTS")
    payload = {"schema": "nba-recency-paired-prospective-v1", "issued_at_utc": issued.isoformat(),
               "feature_date_ET": "2026-11-17", "feature_history_rule": "strictly earlier NBA dates; current sources captured before actual issuance",
               "source_observed_at_utc_lower_bound": source_observed.isoformat(),
               "source_capture_completed_at_utc": capture_completed.isoformat(),
               "source_datetime_timezone_proven": False, "adopt_on_site": False,
               "source_schedule_complete": False, "official_sportsru_credit_verified": False,
               "real_KEEP_TRANSFER_gain_proven": False, "owner_data_used": False,
               "same_p_play_and_quantiles_for_both_means": True,
               "records": rows, "rejections": rejected,
               "sources": {"current_manifest_sha256": digest(source / "current/manifest.json"),
                           "calendar_sha256": digest(live_path), "feature_frame_sha256": digest(frame_path),
                           "original_forecast_sha256": ORIGINAL_FORECAST_SHA},
               "limitations": ["No guarantee of historically atomic upstream snapshots; internal identities and completed team totals checked.",
                               "Injury archive report times are source-naive; conservative original date cutoff retained.",
                               "Only the conditional mean differs; unchanged quantile models are separate components.",
                               "Near-game only; no claim about cold starts, 7/14/21/28-day totals, Sports.ru credits or transfer utility."]}
    sha = immutable_write(out / "forecasts.json", payload)
    commitment = {"schema": payload["schema"], "issued_at_utc": payload["issued_at_utc"], "sha256": sha,
                  "records": len(rows), "distinct_player_games": len(rows) // 2,
                  "distinct_games": len({r["nba_game_id"] for r in rows}),
                  "minimum_tipoff_utc": min(r["tipoff_utc"] for r in rows),
                  "mean_models": {"anchor": card["model_sha256"], "day_ewma": refit_card["model_sha256"]},
                  "adopt_on_site": False, "no_current_outcomes_fit_or_calibration": True,
                  "same_p_play_and_quantiles_for_both_means": True}
    immutable_write(out / "COMMITMENT.json", commitment)
    print(json.dumps(commitment, indent=2), flush=True)

if __name__ == "__main__":
    main()
