"""Refit the locked mean recipe on declared historical data, never current outcomes."""
from pathlib import Path
import hashlib
import json
import os
import pickle
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ.get("NBA_RESEARCH_BASE", ROOT / "research_base")).resolve()
CODE = BASE / "research/match_context"
if not (CODE / "run_phase1.py").is_file():
    CODE = ROOT / "research/match_context"
sys.path.insert(0, str(CODE))
import run_phase1 as original
from run_phase2 import feature_sets
from run_study import fit_predict
from features import build_recency_features

def main():
    out = Path(__file__).resolve().parent
    selection = json.loads((out / "SELECTION_LOCK.json").read_text())
    if selection["selected_recipe"] != "day_ewma":
        raise ValueError("LOCKED_RECIPE_CHANGED")
    common = ROOT / "research_extension/common"
    if hashlib.sha256((common / "feature_frame.pkl").read_bytes()).hexdigest() != selection["source_feature_sha256"]:
        raise ValueError("SOURCE_FRAME_HASH_MISMATCH")
    d = pd.read_pickle(common / "feature_frame.pkl")
    d = d.loc[(d.exante_member == 1) & (d.history_n >= 5) & (d.y_play == 1)].reset_index(drop=True)
    if d.season.max() > 2026:
        raise ValueError("CURRENT_SEASON_FIT_FORBIDDEN")
    cols = feature_sets(d)["context"]
    extra = pd.read_pickle(out / "extra_features.pkl")
    if len(extra) != len(d) or not extra.index.equals(d.index):
        raise ValueError("RECENCY_FRAME_MISALIGNMENT")
    extra_cols = [c for c in extra if c.startswith("ew_d")]
    d = pd.concat([d, extra], axis=1)
    train = d.date <= "2025-12-31"
    cal = d.date.between("2026-01-01", "2026-01-23")
    confirm = d.date >= "2026-02-16"
    model, p = fit_predict(d, cols + extra_cols, train)
    bias = float(np.mean(d.loc[cal, "y_fp"] - p[cal]))
    bundle = {"schema": "nba-recency-conditional-mean-shadow-v1", "model": model,
              "features": cols + extra_cols, "mean_bias": bias,
              "fit_target_max": d.loc[train, "date"].max(),
              "calibration_window": ["2026-01-01", "2026-01-23"],
              "selected_recipe": "day_ewma", "adopt_on_site": False,
              "no_current_season_fit": True,
              "selection_sha256": hashlib.sha256((out / "SELECTION_LOCK.json").read_bytes()).hexdigest()}
    path = out / "refitted_day_ewma_mean.pkl"
    with path.open("wb") as f:
        pickle.dump(bundle, f)
    report = {k: v for k, v in bundle.items() if k != "model"}
    report.update({"model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "train_n": int(train.sum()), "mean_calibration_n": int(cal.sum()),
                   "confirmation_is_previously_exposed": True,
                   "historical_confirmation": original.reg_metrics(d.loc[confirm, "y_fp"], p[confirm] + bias),
                   "not_a_complete_fp_pplay_distribution_release": True,
                   "production_adoption": False})
    original.write_json(out / "REFIT_REPORT.json", report)
    print(json.dumps(original.clean(report)), flush=True)

if __name__ == "__main__":
    main()
