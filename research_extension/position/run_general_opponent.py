"""Declared matched general-opponent experiment; never opens current outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pickle
import time

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from general_opponent import opponent_residual_features

ROOT = Path(__file__).resolve().parents[2]
RESEARCH_BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base"))


def ridge():
    return make_pipeline(SimpleImputer(), StandardScaler(), Ridge(alpha=500.0))


def metrics(y, pred):
    y, pred = np.asarray(y, float), np.asarray(pred, float)
    err = pred - y
    return dict(n=len(y), mae=float(np.mean(abs(err))), rmse=float(np.sqrt(np.mean(err**2))), bias=float(np.mean(err)))


def cluster_gain(y, baseline, candidate, groups, seed=20261117):
    delta = np.abs(np.asarray(y) - baseline) - np.abs(np.asarray(y) - candidate)
    units = pd.DataFrame({"group": np.asarray(groups), "delta": delta}).groupby("group").delta.agg(["sum", "count"]).to_numpy()
    rng = np.random.default_rng(seed)
    gains = []
    for _ in range(1000):
        sample = units[rng.integers(0, len(units), len(units))]
        gains.append(sample[:, 0].sum() / sample[:, 1].sum())
    return dict(point=float(delta.mean()), low=float(np.quantile(gains, .025)), high=float(np.quantile(gains, .975)), clusters=len(units))


def prequential_mean(frame, columns, minimum_training=1000):
    """Monthly nuisance fits are strictly trained before target month."""
    predictions = np.full(len(frame), np.nan)
    records = []
    months = frame.date.str[:7]
    played = frame.y_play.eq(1) & frame.y_fp.notna()
    for month in sorted(months.unique()):
        train = (frame.date < month + "-01") & played
        target = months.eq(month)
        if train.sum() < minimum_training:
            records.append({"month": month, "train_n": int(train.sum()), "predicted_n": 0, "reason": "insufficient_prior_training"})
            continue
        model = ridge().fit(frame.loc[train, columns], frame.loc[train, "y_fp"] - frame.loc[train, "fp10"])
        predictions[target] = frame.loc[target, "fp10"] + model.predict(frame.loc[target, columns])
        records.append({"month": month, "train_n": int(train.sum()), "train_max_date": frame.loc[train, "date"].max(), "prediction_min_date": frame.loc[target, "date"].min(), "predicted_n": int(target.sum())})
    return predictions, records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=Path, default=ROOT / "research_extension/common/feature_frame.pkl")
    ap.add_argument("--original-report", type=Path, default=RESEARCH_BASE / "results_phase2/MODEL_RESEARCH_REPORT.json")
    ap.add_argument("--output", type=Path, default=Path(__file__).with_name("results"))
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    d = pd.read_pickle(args.frame)
    if set(d.season.unique()) - {2024, 2025, 2026}:
        raise ValueError("CURRENT_SEASON_OUTCOMES_PROHIBITED")
    d = d[(d.exante_member == 1) & (d.history_n >= 5)].copy().reset_index(drop=True)
    columns = json.loads(args.original_report.read_text())["features"]["context"]
    assert not any(c.startswith("inj_") for c in columns)
    played = d.y_play.eq(1) & d.y_fp.notna()
    with threadpool_limits(limits=1):
        pre, pre_records = prequential_mean(d, columns)
        np.save(args.output / "pregame_nuisance_predictions.npy", pre)
        (args.output / "PREQUENTIAL_FITS.json").write_text(json.dumps(pre_records, indent=2) + "\n")
        print("PREQUENTIAL_READY", int(np.isfinite(pre).sum()), "of", len(d), flush=True)
        specs = {"ridge_context": list(columns)}
        for prior in (50, 150):
            extra = opponent_residual_features(d, pre, prior_strength=prior, half_life=60)
            name = f"adj_opp_residual_k{prior}"
            d[name] = extra.adj_opp_residual
            specs[f"ridge_context_generic_k{prior}"] = columns + [name]
            if prior == 50:
                extra.to_csv(args.output / "opponent_feature_diagnostics.csv.gz", index=False, compression="gzip")
        folds = [("oct_nov_2024", d.season.eq(2024), d.season.eq(2025) & (d.date < "2024-12-01")), ("dec_2024", d.date < "2024-12-01", (d.date >= "2024-12-01") & (d.date <= "2024-12-31"))]
        selections = {}
        for name, cols in specs.items():
            all_y, all_pred = [], []
            fold_scores = {}
            for fold_name, train, validation in folds:
                train, validation = train & played, validation & played
                model = ridge().fit(d.loc[train, cols], d.loc[train, "y_fp"] - d.loc[train, "fp10"])
                pred = d.loc[validation, "fp10"].to_numpy() + model.predict(d.loc[validation, cols])
                y = d.loc[validation, "y_fp"].to_numpy()
                all_y.append(y)
                all_pred.append(pred)
                fold_scores[fold_name] = metrics(y, pred)
            selections[name] = {"pooled": metrics(np.concatenate(all_y), np.concatenate(all_pred)), "folds": fold_scores}
        chosen = min(selections, key=lambda n: selections[n]["pooled"]["rmse"])
        print("SELECTION", json.dumps(selections), "CHOSEN", chosen, flush=True)
        tr = played & (d.date <= "2024-12-31")
        pcal = played & (d.date >= "2025-01-01") & (d.date <= "2025-01-23")
        test_masks = {"confirmation_2025": played & d.season.eq(2025) & (d.date >= "2025-02-16"), "exposed_audit_2025_26": played & d.season.eq(2026)}
        predict, fitted, offsets = {}, {}, {}
        # Audit all two declared competitors transparently; only development
        # choice counts as selection. Audit cannot pick a replacement winner.
        for name, cols in specs.items():
            model = ridge().fit(d.loc[tr, cols], d.loc[tr, "y_fp"] - d.loc[tr, "fp10"])
            pred = d.fp10.to_numpy() + model.predict(d[cols])
            offset = float(np.mean(d.loc[pcal, "y_fp"] - pred[pcal]))
            predict[name], fitted[name], offsets[name] = pred + offset, model, offset
        results, paired = {}, {}
        for split, mask in test_masks.items():
            y = d.loc[mask, "y_fp"].to_numpy()
            results[split] = {name: metrics(y, p[mask]) for name, p in predict.items()}
            paired[split] = {name: {group: cluster_gain(y, predict["ridge_context"][mask], pred[mask], d.loc[mask, group]) for group in ["date", "pid"]} for name, pred in predict.items() if name != "ridge_context"}
        selected_improves = chosen != "ridge_context" and all(results[s][chosen]["rmse"] < results[s]["ridge_context"]["rmse"] and results[s][chosen]["mae"] < results[s]["ridge_context"]["mae"] for s in test_masks)
        report = {"status": "shadow_candidate_needs_future_validation" if selected_improves else "generic_opponent_extension_not_retained", "adopt_on_site": False, "five_position_difficulty_validated": False, "real_KEEP_TRANSFER_gain_proven": False, "selection": selections, "chosen_by_development_only": chosen, "retained_as_research_candidate": selected_improves, "results": results, "paired_mae_gain": paired, "mean_calibration_offsets": offsets, "nuisance_fit_count": sum(r["predicted_n"] > 0 for r in pre_records), "nuisance_missing_rows": int(np.isnan(pre).sum()), "eligible_rows": len(d), "played_rows": int(played.sum()), "feature_count_original": len(columns), "frame_sha256": hashlib.sha256(args.frame.read_bytes()).hexdigest(), "protocol_sha256": hashlib.sha256(Path(__file__).with_name("PROTOCOL_POSITION_GENERAL.md").read_bytes()).hexdigest(), "code_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob("*.py")}, "environment": {"numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__}, "limits": ["Historical replay, not pregame-captured source vintages", "2025/26 already exposed; not independent prospective evidence", "No current-season outcomes read", "Prediction residual adjustment is not a causal defensive effect", "Five-position historical mapping unavailable", "P(play), intervals and economic utility not tested by this mean-only ablation"], "runtime_seconds": time.time() - started}
        (args.output / "GENERAL_OPPONENT_REPORT.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        predout = d[["pid", "game", "date", "season", "team", "opp", "y_play", "y_fp"]].copy()
        for name, pred in predict.items():
            predout[name] = pred
        predout.to_csv(args.output / "general_predictions.csv.gz", index=False, compression="gzip")
        with (args.output / "general_opponent_models.pkl").open("wb") as handle:
            pickle.dump({"models": fitted, "features": specs, "calibration_offsets": offsets, "selected": chosen, "adopt_on_site": False, "protocol_sha256": report["protocol_sha256"]}, handle)
        opponent_rows = []
        for split, mask in test_masks.items():
            for opp, subgroup in d.loc[mask].groupby("opp"):
                ix = subgroup.index
                opponent_rows.append(dict(split=split, opponent=opp, n=len(ix), baseline_mae=metrics(d.loc[ix, "y_fp"], predict["ridge_context"][ix])["mae"], selected_mae=metrics(d.loc[ix, "y_fp"], predict[chosen][ix])["mae"], baseline_bias=metrics(d.loc[ix, "y_fp"], predict["ridge_context"][ix])["bias"], selected_bias=metrics(d.loc[ix, "y_fp"], predict[chosen][ix])["bias"]))
        pd.DataFrame(opponent_rows).to_csv(args.output / "opponent_subgroups.csv", index=False)
        print("COMPLETE", report["status"], json.dumps(results), flush=True)


if __name__ == "__main__":
    main()
