#!/usr/bin/env python3
"""Execute predeclared status calibration on preserved historical sources only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import pickle
import sys
import time

import numpy as np
import pandas as pd
from scipy.special import logit
from sklearn.metrics import brier_score_loss, log_loss

from calibration import (STATUS_COLUMNS, apply_status_offsets, calibration_masks,
                         exact_order_quantile, fit_status_offsets, nested_bands,
                         status_groups, validate_quantiles)

EXPECTED_MODEL = "70d288d753184916f354e3916016c7c6b0907da32bfcbf92ddcdcb22fb536c25"
SEED = 20261117


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def clean(obj):
    if isinstance(obj, dict): return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (tuple, list)): return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray): return clean(obj.tolist())
    if isinstance(obj, (np.bool_,)): return bool(obj)
    if isinstance(obj, (np.integer,)): return int(obj)
    if isinstance(obj, (np.floating, float)): return float(obj) if np.isfinite(obj) else None
    return obj


def save(path, obj):
    pathlib.Path(path).write_text(json.dumps(clean(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def probability_metrics(y, p):
    if not len(y): return {"n": 0}
    bins = []
    b = np.minimum((p * 10).astype(int), 9)
    for i in range(10):
        ix = b == i
        if ix.any(): bins.append({"n": int(ix.sum()), "mean_prediction": float(p[ix].mean()), "observed": float(y[ix].mean())})
    return {"n": len(y), "brier": brier_score_loss(y, p),
            "logloss": log_loss(y, np.clip(p, .001, .999), labels=[0, 1]),
            "mean_prediction": p.mean(), "play_rate": y.mean(),
            "ece": sum(v["n"] * abs(v["mean_prediction"] - v["observed"]) for v in bins) / len(y),
            "reliability": bins}


def paired_gain(delta, groups):
    g = pd.DataFrame({"g": np.asarray(groups), "d": delta}).groupby("g", observed=True).d.agg(["sum", "count"])
    v = g.to_numpy();rng = np.random.default_rng(SEED)
    scores = []
    for _ in range(2000):
        z = v[rng.integers(0, len(v), len(v))]
        scores.append(z[:, 0].sum() / z[:, 1].sum())
    return {"gain": delta.mean(), "low95": np.quantile(scores, .025), "high95": np.quantile(scores, .975), "clusters": len(v)}


def interval_scores(y, lo, hi, alpha):
    return hi - lo + (2 / alpha) * (np.maximum(lo - y, 0) + np.maximum(y - hi, 0))


def interval_metrics(y, lo, hi, alpha):
    if not len(y): return {"n": 0}
    return {"n": len(y), "coverage": np.mean((y >= lo) & (y <= hi)),
            "width": np.mean(hi - lo), "interval_score": interval_scores(y, lo, hi, alpha).mean(),
            "below": np.mean(y < lo), "above": np.mean(y > hi)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", type=pathlib.Path, required=True)
    ap.add_argument("--base", type=pathlib.Path, default=pathlib.Path(os.environ.get("NBA_RESEARCH_BASE", "research_base")))
    ap.add_argument("--output", type=pathlib.Path, default=pathlib.Path("research_extension/participation/results"))
    args = ap.parse_args();started = time.time();args.output.mkdir(parents=True, exist_ok=True)
    model_path = args.base / "results_near_latest/research_models.pkl"
    if sha(model_path) != EXPECTED_MODEL: raise ValueError("FROZEN_MODEL_HASH_MISMATCH")
    code = args.base / "research/match_context"
    if not (code / "run_phase1.py").is_file():
        code = pathlib.Path(__file__).resolve().parents[2] / "research/match_context"
    sys.path.insert(0, str(code.resolve()))
    with model_path.open("rb") as f: bundle = pickle.load(f)
    full = pd.read_pickle(args.frame)
    # Explicit hard guard first, before date filtering can hide forbidden input.
    if (full.season > 2026).any(): raise ValueError("CURRENT_SEASON_FRAME_FORBIDDEN")
    d = full[(full.exante_member == 1) & (full.history_n >= 5) & (full.date >= "2026-01-01")].reset_index(drop=True)
    masks = calibration_masks(d);groups = status_groups(d)
    known = d.y_play.notna().to_numpy();played = (d.y_play == 1).to_numpy();yp = d.y_play.to_numpy();yf = d.y_fp.to_numpy()
    if not np.isfinite(yf[known]).all(): raise ValueError("KNOWN_OUTCOME_MISSING_FP")
    rawp = bundle["participation_model"].predict_proba(d[bundle["participation_features"]])[:, 1]
    p = bundle["participation_calibrator"].predict_proba(logit(np.clip(rawp, .001, .999)).reshape(-1, 1))[:, 1]
    qlevels = np.array(bundle["quantile_levels"])
    rawq = np.sort(np.column_stack([d.fp10.to_numpy() + bundle["quantile_models"][q].predict(d[bundle["quantile_features"]]) for q in qlevels]), axis=1)
    validate_quantiles(rawq, qlevels, p)
    pc = masks["probability"] & known
    offsets = fit_status_offsets(p[pc], yp[pc], groups[pc], penalty=20.)
    corrected = apply_status_offsets(p, groups, offsets)
    confirm = masks["confirmation"];ix = confirm & known
    prob = {"retained": probability_metrics(yp[ix], p[ix]), "status_intercept": probability_metrics(yp[ix], corrected[ix])}
    delta = (yp[ix] - p[ix]) ** 2 - (yp[ix] - corrected[ix]) ** 2
    gains = {col: paired_gain(delta, d.loc[ix, col].to_numpy()) for col in ["date", "pid"]}
    status_results = {}
    for g in sorted(set(groups)):
        sub = confirm & (groups == g);obs = sub & known
        status_results[g] = {"opportunities": sub.sum(), "known": obs.sum(), "unknown": (sub & ~known).sum(),
                             "retained": probability_metrics(yp[obs], p[obs]),
                             "status_intercept": probability_metrics(yp[obs], corrected[obs])}
    un = confirm & ~known
    g0 = p[un] ** 2 - corrected[un] ** 2;g1 = (1 - p[un]) ** 2 - (1 - corrected[un]) ** 2
    unknown_bounds = {"low": (delta.sum() + np.minimum(g0, g1).sum()) / confirm.sum(),
                      "high": (delta.sum() + np.maximum(g0, g1).sum()) / confirm.sum()}
    prob_gate = (prob["status_intercept"]["brier"] < prob["retained"]["brier"] and
                 prob["status_intercept"]["logloss"] < prob["retained"]["logloss"] and gains["date"]["low95"] > 0 and
                 all(r["known"] < 100 or r["status_intercept"]["brier"] - r["retained"]["brier"] <= .01 for r in status_results.values()))
    bands = {"retained": {}, "status_symmetric": {}, "status_asymmetric": {}}
    adjustments = {};ic = masks["interval"] & played
    for nominal in [50, 80, 95]:
        alpha = 1 - nominal / 100
        # Original float keys are exactly .5/.2/.05, not subtraction artifacts.
        key = {50: .5, 80: .2, 95: .05}[nominal]
        li = int(np.argmin(abs(qlevels - alpha / 2)));ui = int(np.argmin(abs(qlevels - (1 - alpha / 2))))
        lo, hi = rawq[:, li], rawq[:, ui];glob = float(bundle["conditional_offsets"][key])
        bands["retained"][nominal] = (lo - glob, hi + glob)
        sym = np.full(len(d), glob);lower = sym.copy();upper = sym.copy();adjustments[nominal] = {"global": glob, "groups": {}}
        for g in sorted(set(groups)):
            sub = ic & (groups == g);n = int(sub.sum())
            entry = {"n": n, "eligible": n >= 60}
            if n >= 60:
                joint = max(glob, exact_order_quantile(np.maximum(lo[sub] - yf[sub], yf[sub] - hi[sub]), alpha))
                left = max(glob, exact_order_quantile(lo[sub] - yf[sub], alpha / 2))
                right = max(glob, exact_order_quantile(yf[sub] - hi[sub], alpha / 2))
                if not np.isfinite([joint, left, right]).all(): raise ValueError("NONFINITE_BAND_CALIBRATION")
                on = groups == g;sym[on] = joint;lower[on] = left;upper[on] = right
                entry.update(symmetric=joint, lower=left, upper=right)
            adjustments[nominal]["groups"][g] = entry
        bands["status_symmetric"][nominal] = (lo - sym, hi + sym)
        bands["status_asymmetric"][nominal] = (lo - lower, hi + upper)
    for name in ["status_symmetric", "status_asymmetric"]: bands[name] = nested_bands(bands[name])
    interval_results = {};interval_gains = {};interval_gates = {}
    cplay = confirm & played;qplay = cplay & (groups == "Questionable")
    for name, levels in bands.items():
        interval_results[name] = {"overall": {}, "by_status": {}}
        for nominal, (lo, hi) in levels.items():
            alpha = 1 - nominal / 100
            interval_results[name]["overall"][nominal] = interval_metrics(yf[cplay], lo[cplay], hi[cplay], alpha)
            for g in sorted(set(groups)):
                sub = cplay & (groups == g)
                interval_results[name]["by_status"].setdefault(g, {})[nominal] = interval_metrics(yf[sub], lo[sub], hi[sub], alpha)
        if name != "retained":
            blo, bhi = bands["retained"][80];lo, hi = levels[80]
            idelta = interval_scores(yf[cplay], blo[cplay], bhi[cplay], .2) - interval_scores(yf[cplay], lo[cplay], hi[cplay], .2)
            interval_gains[name] = {col: paired_gain(idelta, d.loc[cplay, col].to_numpy()) for col in ["date", "pid"]}
            bq = interval_results["retained"]["by_status"]["Questionable"][80]
            cq = interval_results[name]["by_status"]["Questionable"][80]
            bo = interval_results["retained"]["overall"][80];co = interval_results[name]["overall"][80]
            interval_gates[name] = (abs(cq["coverage"] - .8) < abs(bq["coverage"] - .8) and cq["interval_score"] < bq["interval_score"]
                                    and co["interval_score"] <= bo["interval_score"] and interval_gains[name]["date"]["low95"] > 0)
    report = {"status": "exploratory_historical_calibration_only", "adopt_on_site": False, "real_KEEP_TRANSFER_gain_proven": False,
              "no_2026_27_outcomes_used": True, "model_sha256": EXPECTED_MODEL, "feature_frame_sha256": sha(args.frame),
              "protocol_sha256": sha(pathlib.Path(__file__).with_name("PROTOCOL_20261117.md")),
              "cohort": {split: {"opportunities": m.sum(), "known": (m & known).sum(), "played": (m & played).sum(), "unknown": (m & ~known).sum()} for split, m in masks.items()},
              "probability_offsets": offsets, "probability_confirmation": prob, "probability_gain": gains,
              "probability_by_status": status_results, "probability_unknown_brier_gain_bounds": unknown_bounds,
              "probability_eligible_for_future_frozen_comparison": prob_gate,
              "interval_adjustments": adjustments, "conditional_interval_confirmation": interval_results,
              "interval_score_gain_80": interval_gains, "interval_eligible_for_future_frozen_comparison": interval_gates,
              "limitations": ["Reused historical 2025/26 confirmation, not independent prospective validation",
                              "Only observed prior-team membership and >=5 appearances, not full fantasy population",
                              "Unknown participation labels are not imputed as DNP",
                              "No new unconditional or weekly interval calibration claim",
                              "NBA reconstructed FP are not official Sports.ru credits",
                              "Original models and committed future forecasts remain unchanged"],
              "runtime_seconds": time.time() - started}
    save(args.output / "CALIBRATION_REPORT.json", report)
    save(args.output / "CALIBRATION_PARAMETERS.json", {"model_sha256": EXPECTED_MODEL, "pplay_offsets": offsets, "interval_adjustments": adjustments,
                                                     "adopt_on_site": False, "protocol_sha256": report["protocol_sha256"]})
    out = d[["pid", "game", "date", "team", "opp", "y_play", "y_fp"]].copy();out["status_group"] = groups
    out["pplay_retained"] = p;out["pplay_status_intercept"] = corrected
    for name, levels in bands.items():
        for nominal, (lo, hi) in levels.items():out[f"{name}_lo{nominal}"] = lo;out[f"{name}_hi{nominal}"] = hi
    out.to_csv(args.output / "historical_calibration_predictions.csv.gz", index=False)
    print(json.dumps(clean({k: report[k] for k in ["cohort", "probability_confirmation", "probability_gain", "probability_eligible_for_future_frozen_comparison", "interval_eligible_for_future_frozen_comparison", "runtime_seconds"]}), indent=2))


if __name__ == "__main__": main()
