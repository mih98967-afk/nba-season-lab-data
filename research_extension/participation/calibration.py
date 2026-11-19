"""Fixed, historical-only status calibration challengers; no production writes."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit, logit

STATUS_COLUMNS = ["Out", "Doubtful", "Questionable", "Probable", "Available"]


def status_groups(frame: pd.DataFrame) -> np.ndarray:
    """No report/not listed/available are intentionally different states."""
    required = ["inj_report_present", "inj_team_submitted", "inj_unknown_identity", "inj_not_listed"]
    required += ["inj_" + s.lower() for s in STATUS_COLUMNS]
    missing = set(required) - set(frame)
    if missing:
        raise ValueError("MISSING_STATUS_FIELDS: " + ",".join(sorted(missing)))
    values = frame[required].to_numpy(float)
    if not np.isfinite(values).all() or not np.isin(values, [0, 1]).all():
        raise ValueError("INVALID_STATUS_FLAGS")
    onehot = frame[["inj_" + s.lower() for s in STATUS_COLUMNS]].to_numpy(float)
    if (onehot.sum(axis=1) > 1).any():
        raise ValueError("CONFLICTING_STATUS_FLAGS")
    groups = np.full(len(frame), "unresolved_identity", dtype=object)
    submitted = frame.inj_team_submitted.to_numpy() == 1
    present = frame.inj_report_present.to_numpy() == 1
    groups[submitted & (frame.inj_not_listed.to_numpy() == 1)] = "not_listed"
    for status in STATUS_COLUMNS:
        groups[submitted & (frame["inj_" + status.lower()].to_numpy() == 1)] = status
    groups[frame.inj_unknown_identity.to_numpy() == 1] = "unresolved_identity"
    groups[present & ~submitted] = "not_submitted"
    groups[~present] = "no_report"
    return groups


def validate_probabilities(p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    if p.ndim != 1 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("INVALID_PROBABILITIES")
    return p


def validate_quantiles(q, levels, p):
    q = np.asarray(q, dtype=float)
    levels = np.asarray(levels, dtype=float)
    p = validate_probabilities(p)
    if q.ndim != 2 or levels.ndim != 1 or q.shape != (len(p), len(levels)):
        raise ValueError("INVALID_QUANTILE_SHAPE")
    if not np.isfinite(q).all() or not np.isfinite(levels).all():
        raise ValueError("NONFINITE_QUANTILES")
    if len(levels) < 2 or (np.diff(levels) <= 0).any() or levels[0] < 0 or levels[-1] > 1:
        raise ValueError("INVALID_QUANTILE_LEVELS")
    return q, levels, p


def exact_order_quantile(scores, alpha: float) -> float:
    """Split-conformal kth order statistic; infinite when n cannot support level."""
    scores = np.asarray(scores, dtype=float)
    if scores.ndim != 1 or not len(scores) or not np.isfinite(scores).all():
        raise ValueError("INVALID_CALIBRATION_SCORES")
    if not 0 < alpha < 1:
        raise ValueError("INVALID_ALPHA")
    k = math.ceil((len(scores) + 1) * (1 - alpha))
    if k > len(scores):
        return float("inf")
    return float(np.partition(scores, k - 1)[k - 1])


def fit_status_offsets(p, y, groups, penalty=20.0):
    """One ridge-regularized logit intercept per predeclared source/status group."""
    p = validate_probabilities(p)
    y = np.asarray(y, dtype=float)
    groups = np.asarray(groups)
    if y.shape != p.shape or groups.shape != p.shape or not np.isin(y, [0, 1]).all():
        raise ValueError("KNOWN_BINARY_LABELS_REQUIRED")
    if not np.isfinite(penalty) or penalty <= 0:
        raise ValueError("POSITIVE_FIXED_PENALTY_REQUIRED")
    offsets = {}
    z = logit(np.clip(p, .001, .999))
    for group in sorted(set(groups)):
        ix = groups == group
        def derivative(delta):
            return float((expit(z[ix] + delta) - y[ix]).sum() + penalty * delta)
        offsets[str(group)] = float(brentq(derivative, -100., 100.))
    return offsets


def apply_status_offsets(p, groups, offsets):
    p = validate_probabilities(p)
    groups = np.asarray(groups)
    if groups.shape != p.shape:
        raise ValueError("GROUP_SHAPE_MISMATCH")
    delta = np.array([offsets.get(str(g), 0.) for g in groups], dtype=float)
    if not np.isfinite(delta).all():
        raise ValueError("NONFINITE_OFFSET")
    return expit(logit(np.clip(p, .001, .999)) + delta)


def nested_bands(bands):
    """Expand outer 80/95 bands if necessary, never shrink an interval."""
    out = {k: (np.asarray(lo, float).copy(), np.asarray(hi, float).copy()) for k, (lo, hi) in bands.items()}
    for nominal, lower in [(80, 50), (95, 80)]:
        out[nominal] = (np.minimum(out[nominal][0], out[lower][0]),
                        np.maximum(out[nominal][1], out[lower][1]))
    return out


def calibration_masks(frame):
    dates = frame.date.astype(str)
    if (frame.season > 2026).any():
        raise ValueError("CURRENT_SEASON_OUTCOMES_FORBIDDEN")
    return {
        "probability": ((dates >= "2026-01-01") & (dates <= "2026-01-23")).to_numpy(),
        "interval": ((dates >= "2026-01-24") & (dates <= "2026-02-15")).to_numpy(),
        "confirmation": ((dates >= "2026-02-16") & (frame.season == 2026)).to_numpy(),
    }
