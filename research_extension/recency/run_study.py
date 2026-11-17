"""Run only the fixed historical candidate set in PROTOCOL_RECENCY_20261117.md."""
from pathlib import Path
import hashlib
import json
import os
import pickle
import sys
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base")).resolve()
CODE = ORIGINAL / "research/match_context"
if not (CODE / "run_phase1.py").is_file():
    CODE = ROOT / "research/match_context"
sys.path.insert(0, str(CODE))
import run_phase1 as original
from run_phase2 import feature_sets, regression
from features import build_recency_features, training_weights

OUT = Path(__file__).resolve().parent
COMMON = ROOT / "research_extension/common"
SEED = 20261117

def save(name, obj):
    original.write_json(OUT / name, obj)

def fit_predict(d, cols, train, half_life=None):
    w = training_weights(d.loc[train, "date"], half_life)
    model = regression("ridge")
    model.fit(d.loc[train, cols], d.loc[train, "y_fp"] - d.loc[train, "fp10"],
              standardscaler__sample_weight=w, ridge__sample_weight=w)
    return model, d.fp10.to_numpy() + model.predict(d[cols])

def paired(y, anchor, challenger, groups, *, squared=False):
    delta = ((y - anchor) ** 2 - (y - challenger) ** 2) if squared else (np.abs(y - anchor) - np.abs(y - challenger))
    a = pd.DataFrame({"group": np.asarray(groups), "delta": delta}).groupby("group").delta.agg(["sum", "count"])
    vals = a.to_numpy()
    rng = np.random.default_rng(SEED)
    samples = np.empty(2000)
    for i in range(len(samples)):
        v = vals[rng.integers(0, len(vals), len(vals))]
        samples[i] = v[:, 0].sum() / v[:, 1].sum()
    return {"point": float(delta.mean()), "ci95": np.quantile(samples, [.025, .975]).tolist(),
            "clusters": len(vals), "draws": len(samples), "positive_is_improvement": True}

def main():
    start = time.time()
    frame = pd.read_pickle(COMMON / "feature_frame.pkl")
    raw = pd.read_pickle(COMMON / "raw.pkl")
    d = frame.loc[(frame.exante_member == 1) & (frame.history_n >= 5) & (frame.y_play == 1)].reset_index(drop=True)
    assert d.season.max() == 2026 and d.date.max() < "2026-10-01"
    anchor_cols = feature_sets(d)["context"]
    extra = build_recency_features(d, raw)
    d = pd.concat([d, extra], axis=1)
    print(f"Recency features built: {len(d)} rows, {len(extra.columns)} new features", flush=True)
    extra.to_pickle(OUT / "extra_features.pkl")
    ew = list(extra.columns)
    games = [c for c in ew if c.startswith("ew_g")]
    days = [c for c in ew if c.startswith("ew_d")]
    minutes = [c for c in ew if c.endswith(("_minutes", "_minutes_sd", "_effective_n"))]
    rate = [c for c in ew if c.endswith(("_rate", "_effective_n"))]
    specs = {"anchor": (anchor_cols, None), "game_ewma": (anchor_cols + games, None),
             "day_ewma": (anchor_cols + days, None), "game_day_ewma": (anchor_cols + ew, None),
             "minutes_ewma": (anchor_cols + minutes, None), "rate_ewma": (anchor_cols + rate, None),
             "sample_decay_90": (anchor_cols, 90), "sample_decay_180": (anchor_cols, 180),
             "game_day_sample180": (anchor_cols + ew, 180)}
    folds = {"A": (d.season == 2024, (d.season == 2025) & (d.date <= "2024-11-30")),
             "B": (d.date <= "2024-11-30", (d.date >= "2024-12-01") & (d.date <= "2024-12-31"))}
    metrics = {}
    dev_pred = {}
    y = d.y_fp.to_numpy()
    dev = np.zeros(len(d), bool)
    for _, valid in folds.values():
        dev |= valid.to_numpy()
    for name, (cols, half) in specs.items():
        p = np.full(len(d), np.nan)
        metrics[name] = {"features": len(cols), "sample_half_life": half, "folds": {}}
        for fold, (train, valid) in folds.items():
            assert d.loc[train, "date"].max() < d.loc[valid, "date"].min()
            _, pred = fit_predict(d, cols, train, half)
            p[valid] = pred[valid]
            metrics[name]["folds"][fold] = original.reg_metrics(y[valid], pred[valid])
        metrics[name]["pooled"] = original.reg_metrics(y[dev], p[dev])
        dev_pred[name] = p
        print(name, metrics[name]["pooled"], flush=True)
    winner = min(specs, key=lambda n: (round(metrics[n]["pooled"]["rmse"], 8), metrics[n]["features"], n != "anchor"))
    selection = {"selected_recipe": winner, "selection_metric": "pooled_development_RMSE", "candidates": metrics,
                 "protocol_sha256": hashlib.sha256((ROOT / "research_extension/PROTOCOL_RECENCY_20261117.md").read_bytes()).hexdigest(),
                 "source_feature_sha256": hashlib.sha256((COMMON / "feature_frame.pkl").read_bytes()).hexdigest(),
                 "locked_before_confirm_audit": True, "no_current_season_tuning": True}
    save("SELECTION_LOCK.json", selection)
    print("RECIPE LOCKED", winner, flush=True)
    train = d.date <= "2024-12-31"
    pcal = (d.date >= "2025-01-01") & (d.date <= "2025-01-23")
    models, pred, biases = {}, {"last10": d.fp10.to_numpy()}, {}
    for name in dict.fromkeys(("anchor", winner)):
        cols, half = specs[name]
        model, p = fit_predict(d, cols, train, half)
        bias = float(np.mean(y[pcal] - p[pcal]))
        models[name] = model
        biases[name] = bias
        pred[name] = p + bias
    splits = {"confirmation_2024_25": (d.season == 2025) & (d.date >= "2025-02-16"),
              "exposed_historical_audit_2025_26": d.season == 2026}
    report = {"status": "historical_research_only", "adopt_on_site": False, "real_KEEP_TRANSFER_gain_proven": False,
              "selection": selection, "mean_bias_corrections": biases,
              "cohort": {"played_rows": len(d), "players": d.pid.nunique(), "games": d.game.nunique(),
                         "history_requirement": ">=5 previous played games; prior-team opportunity"},
              "evaluations": {}, "subgroups": {}, "descriptive_ranking_not_fantasy_backtest": {}}
    for split, mask in splits.items():
        result = {"metrics": {n: original.reg_metrics(y[mask], p[mask]) for n, p in pred.items()}, "paired_vs_anchor": {}}
        for grouping in ("date", "pid"):
            result["paired_vs_anchor"][grouping] = {"MAE_gain": paired(y[mask], pred["anchor"][mask], pred[winner][mask], d.loc[mask, grouping]),
                                                     "MSE_gain": paired(y[mask], pred["anchor"][mask], pred[winner][mask], d.loc[mask, grouping], squared=True)}
        report["evaluations"][split] = result
        for subgroup, s in {"minutes_under15": d.min10 < 15, "minutes15to28": d.min10.between(15, 28, inclusive="left"),
                            "minutes28plus": d.min10 >= 28, "return7days": d.days_since_play >= 7,
                            "large_minutes_change": abs(d.minutes_trend) >= 5, "b2b": d.team_b2b == 1,
                            "history5to9": d.history_n < 10, "questionable": d.inj_questionable == 1}.items():
            ix = mask & s
            if ix.sum():
                report["subgroups"].setdefault(split, {})[subgroup] = {n: original.reg_metrics(y[ix], pred[n][ix]) for n in dict.fromkeys(("anchor", winner))}
        for name, p in pred.items():
            ranking = d.loc[mask, ["date", "y_fp"]].copy()
            ranking["prediction"] = p[mask]
            scores = [g.nlargest(10, "prediction").y_fp.sum() for _, g in ranking.groupby("date")]
            report["descriptive_ranking_not_fantasy_backtest"].setdefault(split, {})[name] = {"dates": len(scores), "top10_actual_mean": float(np.mean(scores))}
    confirm = report["evaluations"]["confirmation_2024_25"]["metrics"]
    qualifies = winner != "anchor" and confirm[winner]["rmse"] < confirm["anchor"]["rmse"]
    report["decision"] = {"historical_candidate_qualifies_for_further_research": qualifies,
                          "selected_recipe": winner, "production_adoption": False,
                          "future_validation_required": True, "no_second_selection_on_confirmation_or_audit": True}
    report["limitations"] = ["All historical seasons were previously inspected; this is incremental exploratory evidence.",
                              "Final archived source versions are not proven historical publication vintages.",
                              "No <5-history/cold-start coverage, no Sports.ru credited-ledger equivalence.",
                              "Conditional played FP only; P(play), weekly intervals and economic utility are separate.",
                              "Daily top10 ranking ignores prices, slots, locks and transfer limits."]
    report["runtime_seconds"] = time.time() - start
    save("REPORT.json", report)
    out_predictions = d.loc[splits["confirmation_2024_25"] | splits["exposed_historical_audit_2025_26"], ["pid", "game", "date", "season", "y_fp", "min10"]].copy()
    for name, p in pred.items():
        out_predictions[name] = p[out_predictions.index]
    out_predictions.to_csv(OUT / "predictions.csv.gz", index=False)
    with (OUT / "historical_candidate_models.pkl").open("wb") as f:
        pickle.dump({"models": models, "feature_sets": {n: specs[n][0] for n in models}, "mean_bias": biases, "selected": winner, "fit_until": "2024-12-31"}, f)
    print(json.dumps({"decision": report["decision"], "evaluations": report["evaluations"], "runtime": report["runtime_seconds"]}), flush=True)

if __name__ == "__main__":
    main()
