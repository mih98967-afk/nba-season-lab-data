"""Incremental exponential summaries from strictly earlier played games."""
from __future__ import annotations
import numpy as np
import pandas as pd

GAME_HALFLIVES = (3, 8, 20)
DAY_HALFLIVES = (7, 21, 60)

def weighted_history(history, target_date, *, kind, half_life):
    if kind not in ("games", "days") or half_life <= 0:
        raise ValueError("INVALID_WEIGHTING")
    h = history.loc[(history.date < target_date) & (history.played == 1)].sort_values(["date", "game"]).tail(100)
    if h.empty:
        return {"fp": np.nan, "minutes": np.nan, "rate": np.nan,
                "fp_sd": np.nan, "minutes_sd": np.nan, "effective_n": 0.0}
    if kind == "games":
        age = np.arange(len(h) - 1, -1, -1, dtype=float)
    else:
        age = (pd.Timestamp(target_date) - pd.to_datetime(h.date)).dt.days.to_numpy(float)
        age -= age.min()  # a shared normalization constant; avoids underflow
    w = np.exp2(-age / half_life)
    w /= w.sum()
    fp = h.fp.to_numpy(float)
    minutes = h.minutes.to_numpy(float)
    if not np.isfinite(fp).all() or not np.isfinite(minutes).all() or (minutes <= 0).any():
        raise ValueError("INVALID_PLAYED_HISTORY")
    mf, mm = np.dot(w, fp), np.dot(w, minutes)
    return {"fp": float(mf), "minutes": float(mm), "rate": float(mf / mm),
            "fp_sd": float(np.sqrt(np.dot(w, (fp - mf) ** 2))),
            "minutes_sd": float(np.sqrt(np.dot(w, (minutes - mm) ** 2))),
            "effective_n": float(1 / np.dot(w, w))}

def build_recency_features(targets, raw):
    """Do not inspect target outcomes, minutes, team, or position."""
    sources = {str(k): g.sort_values(["date", "game"]).reset_index(drop=True)
               for k, g in raw.loc[raw.played == 1].groupby("pid", sort=False)}
    output = np.empty((len(targets), 6 * 6), dtype=float)
    families = [("g", "games", h) for h in GAME_HALFLIVES] + [("d", "days", h) for h in DAY_HALFLIVES]
    fields = ("fp", "minutes", "rate", "fp_sd", "minutes_sd", "effective_n")
    cols = [f"ew_{prefix}{h}_{field}" for prefix, _, h in families for field in fields]
    # Each source group is immutable; date search excludes *all* same-date games.
    for pid, indices in targets.groupby("pid", sort=False).indices.items():
        hist = sources.get(str(pid))
        if hist is None:
            output[indices, :] = np.nan
            output[np.ix_(indices, [i for i, n in enumerate(cols) if n.endswith("effective_n")])] = 0
            continue
        dates = hist.date.to_numpy(str)
        fs = hist.fp.to_numpy(float)
        ms = hist.minutes.to_numpy(float)
        ordinals = pd.to_datetime(hist.date).to_numpy(dtype="datetime64[D]").astype(int)
        for row_i in indices:
            date = str(targets.iloc[row_i].date)
            stop = np.searchsorted(dates, date, side="left")
            start = max(0, stop - 100)
            fp, minutes = fs[start:stop], ms[start:stop]
            if not len(fp):
                output[row_i] = [v for _ in families for v in (np.nan, np.nan, np.nan, np.nan, np.nan, 0.)]
                continue
            day_ages = ordinals[stop - 1] - ordinals[start:stop]
            game_ages = np.arange(len(fp) - 1, -1, -1, dtype=float)
            values = []
            for _, kind, h in families:
                w = np.exp2(-(game_ages if kind == "games" else day_ages) / h)
                w /= w.sum()
                mf, mm = np.dot(w, fp), np.dot(w, minutes)
                values.extend((mf, mm, mf / mm,
                               np.sqrt(np.dot(w, (fp - mf) ** 2)),
                               np.sqrt(np.dot(w, (minutes - mm) ** 2)), 1 / np.dot(w, w)))
            output[row_i] = values
    return pd.DataFrame(output, columns=cols, index=targets.index)

def training_weights(dates, half_life):
    dates = pd.to_datetime(dates)
    if half_life is None:
        return np.ones(len(dates))
    if half_life <= 0:
        raise ValueError("INVALID_TRAIN_HALF_LIFE")
    delta = (dates.max() - dates).dt.days.to_numpy(float)
    w = np.exp2(-delta / half_life)
    return w / w.mean()
