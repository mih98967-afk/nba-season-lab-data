"""Lagged opponent-by-Sports.ru-position residuals with explicit shrinkage.

An adjusted association, not an estimate of causal defensive ability. Every
feature is emitted before any outcome on its NBA game date updates a state.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

POSITIONS = ("PG", "SG", "SF", "PF", "C")


@dataclass
class ResidualState:
    day: pd.Timestamp | None = None
    weight: float = 0.0
    total: float = 0.0
    game_weight_square: float = 0.0
    player_weight_square: float = 0.0
    game_square: float = 0.0
    games: int = 0
    player_games: int = 0
    players: set = field(default_factory=set)
    latest_date: str | None = None

    def decay_to(self, day, half_life):
        day = pd.Timestamp(day)
        if self.day is not None:
            elapsed = (day - self.day).days
            if elapsed < 0:
                raise ValueError("RESIDUAL_TIME_TRAVEL")
            factor = 2.0 ** (-elapsed / half_life)
            self.weight *= factor
            self.total *= factor
            self.game_weight_square *= factor * factor
            self.player_weight_square *= factor * factor
            self.game_square *= factor
        self.day = day

    def update(self, residuals, players, day):
        residuals = np.asarray(residuals, float)
        valid = np.isfinite(residuals)
        residuals = residuals[valid]
        if not len(residuals):
            return
        n = len(residuals)
        self.weight += n
        self.total += float(residuals.sum())
        self.game_weight_square += n * n
        self.player_weight_square += n
        self.game_square += n * float(residuals.mean()) ** 2
        self.games += 1
        self.player_games += n
        self.players.update(str(p) for p in np.asarray(players)[valid])
        self.latest_date = str(day)[:10]

    def mean(self):
        return self.total / self.weight if self.weight > 0 else 0.0

    def support(self):
        neff = self.weight ** 2 / self.game_weight_square if self.game_weight_square > 0 else 0.0
        variance = max(0.0, self.game_square / self.weight - self.mean() ** 2) if self.weight else 0.0
        return {"weighted_player_games": self.weight,
                "effective_games": neff,
                "effective_player_games": self.weight ** 2 / self.player_weight_square if self.player_weight_square else 0.0,
                "n_games": self.games, "n_player_games": self.player_games,
                "n_players": len(self.players), "latest_game_date": self.latest_date,
                "between_game_sd": math.sqrt(variance)}


class PositionalResidualEngine:
    def __init__(self, half_life=60.0, overall_prior=150.0, interaction_priors=(30.0, 100.0)):
        if min([half_life, overall_prior, *interaction_priors]) <= 0:
            raise ValueError("INVALID_SHRINKAGE_OR_DECAY")
        self.half_life = half_life
        self.overall_prior = overall_prior
        self.interaction_priors = tuple(interaction_priors)
        self.global_state = ResidualState()
        self.opponents = defaultdict(ResidualState)
        self.positions = defaultdict(ResidualState)
        self.cells = defaultdict(ResidualState)

    def feature(self, opponent, position, day):
        states = [self.global_state, self.opponents[opponent]]
        if position in POSITIONS:
            states += [self.positions[position], self.cells[(opponent, position)]]
        for state in states:
            state.decay_to(day, self.half_life)
        global_mean = self.global_state.mean()
        opponent_state = self.opponents[opponent]
        overall = (opponent_state.total - opponent_state.weight * global_mean) / (opponent_state.weight + self.overall_prior)
        result = {"adj_general_residual": overall}
        if position not in POSITIONS:
            for prior in self.interaction_priors:
                result[f"adj_position_residual_k{int(prior)}"] = 0.0
            result.update(position_known=0.0, cell_weighted_n=0.0, cell_effective_games=0.0)
            return result
        position_mean = self.positions[position].mean() - global_mean
        cell = self.cells[(opponent, position)]
        # Remove the unshrunk marginal opponent mean from the interaction.
        # Subtracting its shrunk feature would leak a general opponent main
        # effect into every positional cell when the overall prior is large.
        opponent_mean = opponent_state.mean() - global_mean
        centered = cell.total - cell.weight * (global_mean + opponent_mean + position_mean)
        for prior in self.interaction_priors:
            result[f"adj_position_residual_k{int(prior)}"] = centered / (cell.weight + prior)
        result.update(position_known=1.0, cell_weighted_n=cell.weight,
                      cell_effective_games=cell.support()["effective_games"])
        return result

    def update_day(self, daily):
        """Call only after all predictions for the date have been emitted."""
        if daily.empty:
            return
        if daily.date.nunique() != 1:
            raise ValueError("UPDATE_REQUIRES_SINGLE_DATE")
        day = daily.date.iloc[0]
        # A game is the cluster unit. Global/position states include both teams;
        # opponent/cell states include only players facing that opponent.
        for _, rows in daily.groupby("game", sort=False):
            self.global_state.decay_to(day, self.half_life)
            self.global_state.update(rows.residual, rows.pid, day)
        for opp, opp_rows in daily.groupby("opp", sort=False):
            for _, rows in opp_rows.groupby("game", sort=False):
                state = self.opponents[opp]
                state.decay_to(day, self.half_life)
                state.update(rows.residual, rows.pid, day)
        for pos, pos_rows in daily[daily.fantasy_position.isin(POSITIONS)].groupby("fantasy_position", sort=False):
            for _, rows in pos_rows.groupby("game", sort=False):
                state = self.positions[pos]
                state.decay_to(day, self.half_life)
                state.update(rows.residual, rows.pid, day)
            for (opp, _), rows in pos_rows.groupby(["opp", "game"], sort=False):
                state = self.cells[(opp, pos)]
                state.decay_to(day, self.half_life)
                state.update(rows.residual, rows.pid, day)


def build_position_features(frame, pregame_expectation, half_life=60.0, overall_prior=150.0, interaction_priors=(30.0, 100.0)):
    required = {"date", "opp", "game", "pid", "y_play", "y_fp", "fantasy_position"}
    if not required.issubset(frame.columns):
        raise ValueError("MISSING_RESIDUAL_COLUMNS")
    if len(frame) != len(pregame_expectation):
        raise ValueError("RESIDUAL_ALIGNMENT_MISMATCH")
    d = frame.reset_index(drop=True).copy()
    d["residual"] = d.y_fp.to_numpy(float) - np.asarray(pregame_expectation, float)
    engine = PositionalResidualEngine(half_life, overall_prior, interaction_priors)
    result = [None] * len(d)
    for day, daily in d.groupby("date", sort=True):
        for (opp, pos), rows in daily.groupby(["opp", "fantasy_position"], dropna=False, sort=False):
            values = engine.feature(opp, pos, day)
            for i in rows.index:
                result[i] = values.copy()
        engine.update_day(daily[(daily.y_play == 1) & daily.residual.notna()])
    return pd.DataFrame(result, index=frame.index), engine
