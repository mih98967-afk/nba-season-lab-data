"""Preregistered historical five-position extension; current outcomes prohibited."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pickle
import sys
import time

import numpy as np
import pandas as pd
import sklearn
from threadpoolctl import threadpool_limits

from position_effects import POSITIONS, build_position_features

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))
sys.path.insert(0, str(ROOT / "research_extension/position"))
from run_general_opponent import ridge, metrics, cluster_gain


def main():
    started = time.time()
    out = HERE / "results"
    full = pd.read_pickle(ROOT / "research_extension/common/feature_frame.pkl")
    if set(full.season.unique()) - {2024, 2025, 2026}:
        raise ValueError("CURRENT_OUTCOMES_PROHIBITED")
    d = full[(full.exante_member == 1) & (full.history_n >= 5)].copy().reset_index(drop=True)
    mapping = json.loads((out / "SEASON_POSITION_MAPPING.json").read_text())
    lookup = {(r["season"], r["nba_person_id"]): r["fantasy_position"] for r in mapping["records"] if r["nba_person_id"]}
    d["fantasy_position"] = [lookup.get((int(y), str(p)), "UNKNOWN") for y, p in zip(d.season, d.pid)]
    coverage = []
    for year, rows in d.groupby("season"):
        played = rows.y_play.eq(1) & rows.y_fp.notna()
        coverage.append({"season": int(year), "eligible_rows": len(rows), "known_position_rows": int(rows.fantasy_position.ne("UNKNOWN").sum()), "played_rows": int(played.sum()), "played_known_position_rows": int((played & rows.fantasy_position.ne("UNKNOWN")).sum()), "eligible_minutes_covered_fraction": float(rows.loc[played & rows.fantasy_position.ne("UNKNOWN"), "y_minutes"].sum() / rows.loc[played, "y_minutes"].sum()) if "y_minutes" in rows else None, "positions": rows.loc[played].fantasy_position.value_counts().to_dict()})
    (out / "FEATURE_POSITION_COVERAGE.json").write_text(json.dumps(coverage, indent=2) + "\n")
    columns = json.loads((BASE / "results_phase2/MODEL_RESEARCH_REPORT.json").read_text())["features"]["context"]
    prior_report = json.loads((ROOT / "research_extension/position/results/GENERAL_OPPONENT_REPORT.json").read_text())
    frame_hash = hashlib.sha256((ROOT / "research_extension/common/feature_frame.pkl").read_bytes()).hexdigest()
    assert prior_report["frame_sha256"] == frame_hash
    nuisance = np.load(ROOT / "research_extension/position/results/pregame_nuisance_predictions.npy")
    assert len(nuisance) == len(d)
    print("MAPPING", json.dumps(coverage), flush=True)
    extra, engine = build_position_features(d, nuisance)
    d = pd.concat([d, extra], axis=1)
    for position in (*POSITIONS, "UNKNOWN"):
        d[f"fantasy_pos_{position}"] = d.fantasy_position.eq(position).astype(int)
    indicators = [f"fantasy_pos_{p}" for p in (*POSITIONS, "UNKNOWN")]
    specs = {"ridge_context": columns, "ridge_context_position": columns + indicators,
             "ridge_context_position_general": columns + indicators + ["adj_general_residual"]}
    for prior in (30, 100):
        specs[f"ridge_context_position_interaction_k{prior}"] = specs["ridge_context_position_general"] + [f"adj_position_residual_k{prior}"]
    played = d.y_play.eq(1) & d.y_fp.notna()
    folds = [("oct_nov_2024", d.season.eq(2024), d.season.eq(2025) & (d.date < "2024-12-01")),
             ("dec_2024", d.date < "2024-12-01", (d.date >= "2024-12-01") & (d.date <= "2024-12-31"))]
    selections, selection_predictions = {}, {}
    with threadpool_limits(limits=1):
        for name, cols in specs.items():
            all_y, all_pred, fold_results = [], [], {}
            for fold_name, train, validate in folds:
                train, validate = train & played, validate & played
                model = ridge().fit(d.loc[train, cols], d.loc[train, "y_fp"] - d.loc[train, "fp10"])
                pred = d.loc[validate, "fp10"].to_numpy() + model.predict(d.loc[validate, cols])
                y = d.loc[validate, "y_fp"].to_numpy()
                all_y.append(y); all_pred.append(pred)
                fold_results[fold_name] = metrics(y, pred)
            selections[name] = {"pooled": metrics(np.concatenate(all_y), np.concatenate(all_pred)), "folds": fold_results}
            selection_predictions[name] = np.concatenate(all_pred)
        chosen = min(selections, key=lambda name: selections[name]["pooled"]["rmse"])
        selection_record = {"chosen_by_development_only": chosen, "selection": selections,
                            "protocol_sha256": hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest()}
        # Write selection before any confirmation/audit outcomes are evaluated.
        (out / "DEVELOPMENT_SELECTION.json").write_text(json.dumps(selection_record, indent=2) + "\n")
        print("SELECTION", json.dumps(selection_record), flush=True)
        train = played & (d.date <= "2024-12-31")
        cal = played & (d.date >= "2025-01-01") & (d.date <= "2025-01-23")
        masks = {"confirmation_2025": played & d.season.eq(2025) & (d.date >= "2025-02-16"), "exposed_audit_2025_26": played & d.season.eq(2026)}
        preds, models, offsets = {}, {}, {}
        for name, cols in specs.items():
            model = ridge().fit(d.loc[train, cols], d.loc[train, "y_fp"] - d.loc[train, "fp10"])
            pred = d.fp10.to_numpy() + model.predict(d[cols])
            offset = float((d.loc[cal, "y_fp"] - pred[cal]).mean())
            preds[name], models[name], offsets[name] = pred + offset, model, offset
    results, paired, subgroups = {}, {}, []
    for split, mask in masks.items():
        y = d.loc[mask, "y_fp"].to_numpy()
        results[split] = {name: metrics(y, pred[mask]) for name, pred in preds.items()}
        paired[split] = {name: {reference: {group: cluster_gain(y, preds[reference][mask], pred[mask], d.loc[mask, group], seed=20261118) for group in ("date", "pid")}
                               for reference in ("ridge_context", "ridge_context_position_general") if name != reference}
                         for name, pred in preds.items() if name != "ridge_context"}
        for position, subgroup in d.loc[mask].groupby("fantasy_position"):
            for name, pred in preds.items():
                subgroups.append({"split": split, "position": position, "model": name, **metrics(subgroup.y_fp, pred[subgroup.index])})
    consistent_gain = chosen != "ridge_context" and all(results[s][chosen][metric] < results[s]["ridge_context"][metric] for s in masks for metric in ("mae", "rmse"))
    interaction_chosen = "interaction" in chosen
    interaction_gain = interaction_chosen and all(results[s][chosen][metric] < results[s]["ridge_context_position_general"][metric] for s in masks for metric in ("mae", "rmse"))
    report = {**selection_record, "status": "historical_candidate_only" if consistent_gain else "position_extension_not_retained", "adopt_on_site": False,
              "production_forecasts_adjusted": False, "five_position_predictive_increment_supported": bool(interaction_gain),
              "future_validation_required": True, "economic_gain_proven": False,
              "results": results, "paired_mae_gain": paired, "calibration_offsets": offsets,
              "coverage": coverage, "feature_count_original": len(columns), "eligible_rows": len(d),
              "nuisance_finite_rows": int(np.isfinite(nuisance).sum()), "frame_sha256": frame_hash,
              "position_mapping_sha256": hashlib.sha256((out / "SEASON_POSITION_MAPPING.json").read_bytes()).hexdigest(),
              "nuisance_sha256": hashlib.sha256((ROOT / "research_extension/position/results/pregame_nuisance_predictions.npy").read_bytes()).hexdigest(),
              "code_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob("*.py")},
              "environment": {"numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__},
              "limitations": ["Season rosters were exported 18 Nov 2026; historical position vintages are retrospective.",
                              "Historical replay and previously exposed 2025/26 audit; no prospective causal or economic evidence.",
                              "Conditional played-game FP ablation alone cannot authorize production promotion.",
                              "Adjusted residuals retain unpredictable minute/rotation noise; uncertainty is not per-game prediction coverage.",
                              "No 2026/27 outcome used for fitting, calibration or candidate selection."],
              "runtime_seconds": time.time() - started}
    (out / "POSITION_RESEARCH_REPORT.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    pd.DataFrame(subgroups).to_csv(out / "position_subgroup_metrics.csv", index=False)
    predout = d[["pid", "game", "date", "season", "team", "opp", "fantasy_position", "y_play", "y_fp"]].copy()
    for name, pred in preds.items():
        predout[name] = pred
    predout.to_csv(out / "position_predictions.csv.gz", index=False, compression="gzip")
    d[["pid", "game", "date", "season", "team", "opp", "fantasy_position", *extra.columns]].to_pickle(out / "position_features.pkl")
    with (out / "position_models.pkl").open("wb") as handle:
        pickle.dump({"models": models, "features": specs, "offsets": offsets, "selected": chosen,
                     "adopt_on_site": False, "position_engine_through_2026_04": engine}, handle)
    print("COMPLETE", report["status"], json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
