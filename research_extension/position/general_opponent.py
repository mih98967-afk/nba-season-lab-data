"""Strictly earlier-date opponent residual features for a matched Ridge ablation."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


@dataclass
class ResidualState:
    day: pd.Timestamp | None = None
    weight: float = 0.0
    weighted_residual: float = 0.0
    weighted_square: float = 0.0
    game_weight_sq: float = 0.0
    games: int = 0

    def decay_to(self, day, half_life):
        if self.day is not None:
            elapsed = (day - self.day).days
            if elapsed < 0:
                raise ValueError("RESIDUAL_TIME_TRAVEL")
            decay = 2.0 ** (-elapsed / half_life)
            self.weight *= decay
            self.weighted_residual *= decay
            self.weighted_square *= decay
            self.game_weight_sq *= decay * decay
        self.day = day

    def summarize(self, prior_strength):
        if self.weight <= 0:
            return dict(residual=0.0, weighted_n=0.0, effective_games=0.0, dispersion=0.0, shrunk_fraction=0.0)
        mean = self.weighted_residual / self.weight
        variance = max(0.0, self.weighted_square / self.weight - mean * mean)
        return dict(residual=self.weighted_residual / (self.weight + prior_strength), weighted_n=self.weight, effective_games=self.weight * self.weight / max(self.game_weight_sq, 1e-12), dispersion=math.sqrt(variance), shrunk_fraction=self.weight / (self.weight + prior_strength))

    def update_game(self, residuals):
        values = np.asarray(residuals, float)
        values = values[np.isfinite(values)]
        if len(values) == 0:
            return
        n = len(values)
        game_mean = float(values.mean())
        self.weight += n
        self.weighted_residual += float(values.sum())
        # Dispersion is between opponent-game means, not IID player-game noise.
        self.weighted_square += n * game_mean * game_mean
        self.game_weight_sq += n * n
        self.games += 1


def opponent_residual_features(frame, pregame_expectation, prior_strength=50.0, half_life=60.0):
    if prior_strength <= 0 or half_life <= 0:
        raise ValueError("INVALID_SHRINKAGE_OR_DECAY")
    needed = {"date", "opp", "game", "y_play", "y_fp"}
    if not needed.issubset(frame.columns):
        raise ValueError("MISSING_RESIDUAL_COLUMNS")
    if len(frame) != len(pregame_expectation):
        raise ValueError("RESIDUAL_ALIGNMENT_MISMATCH")
    d = frame.reset_index(drop=True)
    predicted = np.asarray(pregame_expectation, float)
    states = defaultdict(ResidualState)
    columns = ["residual", "weighted_n", "effective_games", "dispersion", "shrunk_fraction"]
    output = np.zeros((len(d), len(columns)), float)
    for day_text, daily in d.groupby("date", sort=True):
        day = pd.Timestamp(day_text)
        for opp, rows in daily.groupby("opp", sort=False):
            state = states[opp]
            state.decay_to(day, half_life)
            values = state.summarize(prior_strength)
            output[rows.index] = [values[col] for col in columns]
        # Batch updates after *every* prediction for this date. Multiple games
        # and teams on a date cannot contaminate each other's features.
        for (opp, _game), rows in daily.groupby(["opp", "game"], sort=False):
            ix = rows.index[(rows.y_play == 1) & rows.y_fp.notna()]
            residual = d.loc[ix, "y_fp"].to_numpy(float) - predicted[ix]
            states[opp].update_game(residual)
    return pd.DataFrame(output, index=frame.index, columns=["adj_opp_" + c for c in columns])
