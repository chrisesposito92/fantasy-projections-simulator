from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import ReceiverParticipationConfig
from fantasy_sim.models.player import TeamRoster


def _bounded_factor(
    value: float,
    baseline: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    """Return a bounded multiplicative factor centered on 1.0."""
    lower, upper = clamp
    if baseline <= 0 or not np.isfinite(value) or not np.isfinite(baseline):
        return 1.0
    delta = (value - baseline) / baseline
    factor = 1.0 + delta * sensitivity
    return float(np.clip(factor, lower, upper))


class ReceiverParticipationEngine:
    def __init__(self, config: ReceiverParticipationConfig):
        self.config = config

    def apply(self, roster: TeamRoster, features: pl.DataFrame) -> None:
        if not self.config.enabled or features is None or features.is_empty():
            return

        required_columns = {
            "player_id",
            "targets",
            "catchable_rate",
            "contested_rate",
            "mean_air_yards",
        }
        if not required_columns.issubset(features.columns):
            return

        baselines = self._feature_baselines(features)
        if baselines is None:
            return

        team_features = features
        if "team" in features.columns:
            team_features = features.filter(pl.col("team") == roster.team)
            if team_features.is_empty():
                return

        feature_rows = {
            row["player_id"]: row
            for row in team_features.select(
                ["player_id", "targets", "catchable_rate", "contested_rate", "mean_air_yards"]
            ).iter_rows(named=True)
            if row["player_id"] is not None
        }

        for player in roster.players:
            if player.position not in self.config.positions:
                continue

            row = feature_rows.get(player.player_id)
            if row is None:
                continue

            targets = row["targets"]
            if targets is None or targets < self.config.min_targets:
                continue

            target_factor = _bounded_factor(
                float(row["catchable_rate"]),
                baselines["catchable_rate"],
                self.config.target_share_sensitivity,
                self.config.factor_clamp,
            )
            air_factor = _bounded_factor(
                float(row["mean_air_yards"]),
                baselines["mean_air_yards"],
                self.config.air_yards_sensitivity,
                self.config.factor_clamp,
            )
            catchable_factor = _bounded_factor(
                float(row["catchable_rate"]),
                baselines["catchable_rate"],
                self.config.catchable_target_sensitivity,
                self.config.factor_clamp,
            )
            contested_factor = _bounded_factor(
                float(row["contested_rate"]),
                baselines["contested_rate"],
                self.config.contested_target_sensitivity,
                self.config.factor_clamp,
            )
            catch_factor = float(
                np.clip(
                    catchable_factor * contested_factor,
                    self.config.factor_clamp[0],
                    self.config.factor_clamp[1],
                )
            )

            player.usage.target_share *= target_factor
            player.usage.air_yards_share *= air_factor
            player.outcomes.catch_rate *= catch_factor

            if player.outcomes.receiving_yards_dist is not None:
                player.outcomes.receiving_yards_dist = (
                    np.asarray(player.outcomes.receiving_yards_dist, dtype=float) * air_factor
                )

    def _feature_baselines(self, features: pl.DataFrame) -> dict[str, float] | None:
        if features.is_empty():
            return None

        baselines: dict[str, float] = {}
        for column in ("catchable_rate", "contested_rate", "mean_air_yards"):
            if column not in features.columns:
                return None
            value = features.select(pl.col(column).cast(pl.Float64).mean()).item()
            if value is None:
                return None
            baselines[column] = float(value)
        return baselines
