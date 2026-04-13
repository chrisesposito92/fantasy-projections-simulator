from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import RbEfficiencyConfig
from fantasy_sim.models.player import TeamRoster

RB_POSITIONS = {"RB"}


def _bounded_factor(
    value: float,
    center: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    """Return a bounded multiplicative factor centered on 1.0."""
    lower, upper = clamp
    if not np.isfinite(value) or not np.isfinite(center):
        return 1.0
    factor = 1.0 + (value - center) * sensitivity
    return float(np.clip(factor, lower, upper))


class RbEfficiencyEngine:
    def __init__(self, config: RbEfficiencyConfig):
        self.config = config

    def apply(self, roster: TeamRoster, features: pl.DataFrame) -> None:
        if not self.config.enabled or features is None or features.is_empty():
            return

        required_columns = {"player_id", "attempts", "rush_yoe_per_att"}
        if not required_columns.issubset(features.columns):
            return

        team_features = features
        if "team" in features.columns:
            team_features = features.filter(pl.col("team") == roster.team)
            if team_features.is_empty():
                return

        feature_rows = {
            row["player_id"]: row
            for row in team_features.select(
                ["player_id", "attempts", "rush_yoe_per_att"]
            ).iter_rows(named=True)
            if row["player_id"] is not None
        }

        for player in roster.players:
            if player.position not in RB_POSITIONS:
                continue

            row = feature_rows.get(player.player_id)
            if row is None:
                continue

            attempts = row["attempts"]
            rush_yoe_per_att = row["rush_yoe_per_att"]
            if attempts is None or rush_yoe_per_att is None:
                continue
            if attempts < self.config.min_attempts:
                continue

            carry_factor = _bounded_factor(
                float(rush_yoe_per_att),
                0.0,
                self.config.carry_share_sensitivity,
                self.config.factor_clamp,
            )
            rush_yards_factor = _bounded_factor(
                float(rush_yoe_per_att),
                0.0,
                self.config.rush_yards_sensitivity,
                self.config.factor_clamp,
            )

            player.usage.carry_share *= carry_factor
            if player.outcomes.rushing_yards_dist is not None:
                adjusted = np.asarray(player.outcomes.rushing_yards_dist, dtype=float) * rush_yards_factor
                player.outcomes.rushing_yards_dist = np.rint(adjusted).astype(np.int64)
