"""Evaluate both locked cohorts against immutable 18-Nov outcomes; never fit."""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, json, math, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))
# Shared scorer code belongs to the existing research checkpoint.
SHARED = HERE.parent / "prospective"
sys.path.insert(0, str(SHARED))
from score_frozen import (EXPECTED_SHA, load_frozen, identity_crosswalk, unique_index,
                         outcome_for, evaluate, metrics, prob_metrics, sha, utc)
from score_archive import archive_outcome, quarantine_overlap, participation_only

NEW_SHA = "9b3cd732075d06c99ff0c3a30a2bd861ff606b0787c6de98d15302f93fa61ebb"
NEW_ROLES = ("near_primary_20261117", "near_day_ewma_challenger_20261117")
KNOWN = {"PLAYED", "EXPLICIT_DNP", "OFFICIAL_INACTIVE"}
SEED = 20261118
DRAWS = 4000


def locked_new(path):
    if sha(path) != NEW_SHA: raise ValueError("NEW_FREEZE_HASH_MISMATCH")
    freeze = json.loads(path.read_text())
    issued = utc(freeze["issued_at_utc"])
    if utc(freeze["source_capture_completed_at_utc"]) > issued:
        raise ValueError("SOURCE_AFTER_ISSUANCE")
    groups = collections.defaultdict(dict)
    for row in freeze["records"]:
        key = (row["nba_player_id"], row["nba_game_id"], row["lead_days"])
        if row["model_role"] in groups[key]: raise ValueError("DUPLICATE_PAIR_ROLE")
        if issued + dt.timedelta(minutes=30) >= utc(row["tipoff_utc"]):
            raise ValueError("NOT_PRELOCK")
        if not 0 <= row["p_play"] <= 1: raise ValueError("INVALID_PPLAY")
        if not math.isclose(row["mean_if_play"] * row["p_play"], row["expected_fp"], abs_tol=1e-9):
            raise ValueError("MEAN_PROBABILITY_PRODUCT_MISMATCH")
        groups[key][row["model_role"]] = row
    pair_fields = ["nba_player_id", "nba_game_id", "calendar_game_id", "date_ET", "tipoff_utc", "feature_date_ET", "team", "opponent", "lead_days", "p_play", "distribution_model_sha256", "baseline_last10", "baseline_history_p_play"]
    pair_fields += [p + k + str(n) for n in (50, 80, 95) for p in ("", "conditional_") for k in ("lo", "hi")]
    for roles in groups.values():
        if set(roles) != set(NEW_ROLES): raise ValueError("INCOMPLETE_PAIR")
        a, b = (roles[role] for role in NEW_ROLES)
        if any(a[k] != b[k] for k in pair_fields): raise ValueError("UNPAIRED_NONMEAN_COMPONENT")
        for row in (a, b):
            for n in (50, 80, 95):
                for prefix in ("", "conditional_"):
                    if row[prefix + "lo" + str(n)] > row[prefix + "hi" + str(n)]:
                        raise ValueError("CROSSED_INTERVAL")
    return freeze


def clustered_difference(rows, baseline, candidate, label, metric="mae"):
    """Paired loss gain (baseline minus candidate); resample entire NBA games."""
    if not rows: return {"n": 0}
    groups = sorted({r["nba_game_id"] for r in rows})
    index = {g: i for i, g in enumerate(groups)}
    y = np.array([label(r) for r in rows], dtype=float)
    pb = np.array([baseline(r) for r in rows], dtype=float)
    pc = np.array([candidate(r) for r in rows], dtype=float)
    loss = np.abs if metric == "mae" else np.square
    b, c = loss(pb - y), loss(pc - y)
    sums_b = np.zeros(len(groups)); sums_c = np.zeros(len(groups)); sizes = np.zeros(len(groups))
    for i, r in enumerate(rows):
        j = index[r["nba_game_id"]]; sums_b[j] += b[i]; sums_c[j] += c[i]; sizes[j] += 1
    transform = np.sqrt if metric == "rmse" else lambda v: v
    point = float(transform(b.mean()) - transform(c.mean()))
    out = {"n": len(rows), "games": len(groups), "NBA_dates": sorted({r["date_ET"] for r in rows}),
           "metric": metric, "positive_gain_favors_candidate": True, "paired_gain": point,
           "game_cluster_percentile_95CI": None, "bootstrap_draws": DRAWS, "seed": SEED,
           "small_game_cluster_count": len(groups) < 20,
           "date_cluster_CI": None, "date_cluster_inference_withheld_below_5_dates": True}
    if len(groups) >= 2:
        rng = np.random.default_rng(SEED)
        picks = rng.integers(len(groups), size=(DRAWS, len(groups)))
        den = sizes[picks].sum(axis=1)
        delta = transform(sums_b[picks].sum(axis=1) / den) - transform(sums_c[picks].sum(axis=1) / den)
        out["game_cluster_percentile_95CI"] = np.quantile(delta, [.025, .975]).tolist()
    out["date_point_gains"] = {}
    for date in out["NBA_dates"]:
        use = np.array([r["date_ET"] == date for r in rows])
        out["date_point_gains"][date] = float(transform(b[use].mean()) - transform(c[use].mean()))
    return out


def uncertainty(rows):
    played = [r for r in rows if r["outcome_archive"] == "PLAYED"]
    fp = [r for r in rows if r["outcome_archive"] in KNOWN]
    participation = [r for r in rows if r["participation_verified"] is not None]
    return {
        "conditional_mae": clustered_difference(played, lambda r: r["baseline_fp10"], lambda r: r["mean_if_play"], lambda r: r["y_fp"]),
        "conditional_rmse": clustered_difference(played, lambda r: r["baseline_fp10"], lambda r: r["mean_if_play"], lambda r: r["y_fp"], "rmse"),
        "unconditional_mae": clustered_difference(fp, lambda r: r["baseline_fp10"] * r["baseline_p_play"], lambda r: r["expected_fp"], lambda r: r["y_fp"]),
        "unconditional_rmse": clustered_difference(fp, lambda r: r["baseline_fp10"] * r["baseline_p_play"], lambda r: r["expected_fp"], lambda r: r["y_fp"], "rmse"),
        "participation_brier": clustered_difference(participation, lambda r: r["baseline_p_play"], lambda r: r["p_play"], lambda r: r["participation_verified"], "brier")}


def describe(rows):
    result = {"strict_ESPN": evaluate([{**r, "y_fp": r["espn_y_fp"]} for r in rows], "outcome_espn"), "archive_reconciled": evaluate(rows, "outcome_archive"),
              "participation_with_separate_FP_conflicts": participation_only(rows),
              "archive_unknown_reasons": dict(collections.Counter(r["archive_reason"] for r in rows if r["outcome_archive"] == "UNKNOWN")),
              "ESPN_unknown_reasons": dict(collections.Counter(r["reason"] for r in rows if r["outcome_espn"] == "UNKNOWN")),
              "source_overlap": dict(collections.Counter(r["espn_archive_overlap"] for r in rows)),
              "paired_uncertainty_vs_research_baseline": uncertainty(rows)}
    return result


def pair_comparison(rows):
    ix = unique_index(rows, ["model_role", "nba_player_id", "nba_game_id", "lead_days"])
    pairs = []
    for a in rows:
        if a["model_role"] != NEW_ROLES[0]: continue
        b = ix[(NEW_ROLES[1], a["nba_player_id"], a["nba_game_id"], str(a["lead_days"]))]
        if (a["outcome_archive"], a["y_fp"], a["participation_verified"]) != (b["outcome_archive"], b["y_fp"], b["participation_verified"]):
            raise ValueError("PAIR_LABEL_MISMATCH")
        pairs.append({**a, "candidate_mean_if_play": b["mean_if_play"], "candidate_expected_fp": b["expected_fp"]})
    played = [r for r in pairs if r["outcome_archive"] == "PLAYED"]
    known = [r for r in pairs if r["outcome_archive"] in KNOWN]
    result = {"unique_pairs": len(pairs), "same_p_play_and_intervals_verified": True,
              "conditional": {"n": len(played), "anchor": metrics([r["y_fp"] for r in played], [r["mean_if_play"] for r in played]), "day_ewma": metrics([r["y_fp"] for r in played], [r["candidate_mean_if_play"] for r in played])},
              "unconditional": {"n": len(known), "anchor": metrics([r["y_fp"] for r in known], [r["expected_fp"] for r in known]), "day_ewma": metrics([r["y_fp"] for r in known], [r["candidate_expected_fp"] for r in known])},
              "paired_uncertainty": {}}
    for prefix, group, a, b in (("conditional", played, "mean_if_play", "candidate_mean_if_play"), ("unconditional", known, "expected_fp", "candidate_expected_fp")):
        for metric in ("mae", "rmse"):
            result["paired_uncertainty"][prefix + "_" + metric] = clustered_difference(group, lambda r: r[a], lambda r: r[b], lambda r: r["y_fp"], metric)
    return result


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", type=Path, default=BASE); ap.add_argument("--source", type=Path, default=HERE / "source"); ap.add_argument("--snapshot", type=Path, default=HERE / "current_snapshot"); ap.add_argument("--output", type=Path, default=HERE / "results"); a = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    oldpath = a.base / "prospective_20261116/forecasts.json"
    newpath = HERE.parent / "prospective_20261117/forecasts.json"
    old = load_frozen(oldpath); new = locked_new(newpath)
    qa = json.loads((a.source.parent / "SOURCE_QA.json").read_text())
    if not qa["coherent_current_snapshot_verified"]: raise ValueError("SOURCE_QA_FAILED")
    manifest = json.loads((a.source / "current/manifest.json").read_text())
    for item in manifest:
        p = a.source / "current" / item["file"]
        if item["status"] != "retrieved" or sha(p) != item["sha256"] or p.stat().st_size != item["bytes"]: raise ValueError("SOURCE_HASH_MISMATCH")
        if utc(item["fetched_at_utc"]) > now: raise ValueError("SOURCE_CAPTURE_IN_FUTURE")
    read = lambda name: json.loads((a.snapshot / "data" / name).read_text())
    live, identity, dnp, official = [read(n) for n in ("live.json", "identity.json", "explicit_dnp_research.json", "official_nba_nonout_unknown_research.json")]
    github = json.loads((HERE / "GITHUB_INPUT_MANIFEST.json").read_text())
    if utc(live["updated_at_utc"]) > now: raise ValueError("LIVE_AFTER_EVALUATION")
    live["game_index"] = unique_index(live["games"], ["id"]); live["row_index"] = unique_index(live["rows"], ["game_id", "id"])
    dnp["event_index"] = unique_index(dnp["events"], ["game_id", "player_id"])
    off = unique_index(official["records"], ["game_id", "player_id"]); idmap = identity_crosswalk(identity)
    code = a.base / "research/match_context"
    if not code.exists(): code = ROOT / "research/match_context"
    sys.path.insert(0, str(code.resolve()))
    import current_validation
    current_validation.ASOF_DATE = "2026-11-18"
    games, raw, sourceqa, _ = current_validation.load_current_combined(a.source)
    gi = unique_index(games[games.season == 2027].to_dict("records"), ["game"])
    ri = unique_index(raw[raw.season == 2027].to_dict("records"), ["game", "pid"])
    frame = pd.read_pickle(a.base / "results_current/feature_frame.pkl")
    frame = frame[frame.y_play.isna() & frame.y_fp.isna()]
    bi = {(str(r.pid), str(r.game), int(r.horizon_days), str(r.issue_date)): r for r in frame.itertuples()}
    all_rows = {}
    for cohort, freeze in (("original_20261116", old), ("paired_20261117", new)):
        rows = []
        for f in freeze["records"]:
            if cohort == "original_20261116":
                b = bi[(f["nba_player_id"], f["nba_game_id"], f["lead_days"], f["feature_date_ET"])]
                baseline_fp, baseline_p = float(b.fp10), float(b.obs_play_rate25)
            else: baseline_fp, baseline_p = f["baseline_last10"], f["baseline_history_p_play"]
            espn = outcome_for(f, live, dnp, off, idmap, now)
            archive = archive_outcome(f, gi, ri, now)
            merged = quarantine_overlap({**f, **archive, "baseline_fp10": baseline_fp, "baseline_p_play": baseline_p}, espn)
            # Keep each layer's numeric outcome separate; evaluate helpers are passed a layer-specific copy.
            merged.update({k: v for k, v in espn.items() if k != "y_fp"})
            merged["espn_y_fp"] = espn["y_fp"]
            game = live["game_index"].get((f["calendar_game_id"],))
            merged["observed_schedule_tipoff_utc"] = game.get("utc") if game else None
            merged["frozen_tipoff_matches_observed"] = bool(game and utc(game["utc"]) == utc(f["tipoff_utc"]))
            merged["actual_issue_to_observed_tipoff_hours"] = (utc(game["utc"]) - utc(freeze["issued_at_utc"])).total_seconds() / 3600 if game else None
            if game and merged["actual_issue_to_observed_tipoff_hours"] <= .5:
                raise ValueError("CURRENT_TIMING_BREAKS_PRELOCK")
            rows.append(merged)
        all_rows[cohort] = rows
    report = {"schema": "nba-frozen-prospective-20261118-v1", "evaluated_at_utc": now.isoformat(), "evaluation_only": True,
              "adopt_on_site": False, "fit_or_calibration_performed": False, "outcome_tuning_performed": False,
              "official_Sports_ru_credits_proven": False, "real_KEEP_TRANSFER_gain_proven": False,
              "old_forecast_sha256": sha(oldpath), "new_forecast_sha256": sha(newpath), "original_forecast_bytes_unchanged": True,
              "source_main_commit": github.get("commit", github.get("main_sha")), "source_manifest_sha256": sha(a.source / "current/manifest.json"),
              "live_updated_at_utc": live["updated_at_utc"], "source_qa_2027": sourceqa["2027"],
              "source_kind": "NBA-derived archives plus optional additive direct official NBA finals, reconciled to exact current-main ESPN-derived rows",
              "selected_source_QA_sha256": sha(a.source.parent / "SOURCE_QA.json"),
              "baseline_kind": "frozen last10 FP and historical observed participation; not exact deployed app runtime",
              "limitations": ["Only two NBA dates have completed; no date-cluster confidence interval or robust promotion proof", "Game bootstrap is descriptive with only five or eight games per cohort", "Source archives can incorporate later stat corrections; no atomic source vintage guarantee", "FP targets reconstruct the NBA formula and are not independent official Sports.ru credited points", "UNKNOWN and conflicting FP remain excluded with explicit denominators; agreed participation survives FP-only conflicts", "No owner transactions, prices, quota or economic gain tested", "Week/player multi-game predictive intervals are not validated by these one-game-per-player cohorts"],
              "cohorts": {}}
    for cohort, rows in all_rows.items():
        elapsed = [r for r in rows if r["outcome_archive"] != "FUTURE"]
        entry = {"records": len(rows), "elapsed_records": len(elapsed), "elapsed_player_games": len({(r["nba_player_id"], r["nba_game_id"]) for r in elapsed}), "elapsed_games": len({r["nba_game_id"] for r in elapsed}), "elapsed_ET_dates": sorted({r["date_ET"] for r in elapsed}), "by_role_and_lead": {}, "source_conflicts": [r for r in elapsed if r["espn_archive_overlap"] == "CONFLICT"], "changed_tipoffs": [r for r in elapsed if not r["frozen_tipoff_matches_observed"]]}
        for role, lead in sorted({(r["model_role"], r["lead_days"]) for r in rows}):
            group = [r for r in rows if (r["model_role"], r["lead_days"]) == (role, lead)]
            description = describe(group)
            # Strict ESPN outcome values must never be overwritten by archive values/conflict masking.
            description["strict_ESPN"] = evaluate([{**r, "y_fp": r["espn_y_fp"]} for r in group], "outcome_espn")
            entry["by_role_and_lead"][role + ":lead" + str(lead)] = description
        if cohort == "paired_20261117": entry["paired_mean_challenger_comparison"] = pair_comparison(rows)
        report["cohorts"][cohort] = entry
    a.output.mkdir(parents=True, exist_ok=True)
    for cohort, rows in all_rows.items():
        (a.output / (cohort + "_scored_records.json")).write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False) + "\n")
    (a.output / "PROSPECTIVE_REPORT.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps({"elapsed": {k: {x: v[x] for x in ("elapsed_records", "elapsed_player_games", "elapsed_games", "elapsed_ET_dates")} for k, v in report["cohorts"].items()}, "new_pair": report["cohorts"]["paired_20261117"]["paired_mean_challenger_comparison"]}, indent=2))


if __name__ == "__main__": main()
