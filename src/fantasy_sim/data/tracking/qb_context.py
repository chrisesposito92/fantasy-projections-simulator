from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.tracking.models import QbContextConfig
from fantasy_sim.engine.types import TeamDistributions
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


class QbContextEngine:
    def __init__(self, config: QbContextConfig):
        self.config = config

    def apply(
        self,
        roster: TeamRoster,
        team_dists: TeamDistributions,
        features: pl.DataFrame,
    ) -> None:
        if not self.config.enabled or features is None or features.is_empty():
            return

        required_columns = {
            "player_id",
            "dropbacks",
            "no_huddle_rate",
            "play_action_rate",
            "pressure_rate",
            "blitz_rate",
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

        try:
            starter = roster.get_starting_qb()
        except ValueError:
            return

        row = next(
            (
                feature_row
                for feature_row in team_features.select(
                    [
                        "player_id",
                        "dropbacks",
                        "no_huddle_rate",
                        "play_action_rate",
                        "pressure_rate",
                        "blitz_rate",
                    ]
                ).iter_rows(named=True)
                if feature_row["player_id"] == starter.player_id
            ),
            None,
        )
        if row is None:
            return

        dropbacks = row["dropbacks"]
        no_huddle_rate = row["no_huddle_rate"]
        play_action_rate = row["play_action_rate"]
        pressure_rate = row["pressure_rate"]
        blitz_rate = row["blitz_rate"]
        if (
            dropbacks is None
            or no_huddle_rate is None
            or play_action_rate is None
            or pressure_rate is None
            or blitz_rate is None
        ):
            return
        if dropbacks < self.config.min_dropbacks:
            return

        pace_factor = _bounded_factor(
            float(no_huddle_rate) + float(play_action_rate),
            baselines["pace_signal"],
            self.config.pace_sensitivity,
            self.config.factor_clamp,
        )
        pass_factor = _bounded_factor(
            float(play_action_rate),
            baselines["play_action_rate"],
            self.config.pass_rate_sensitivity,
            self.config.factor_clamp,
        )
        sack_factor = _bounded_factor(
            float(pressure_rate),
            baselines["pressure_rate"],
            self.config.sack_rate_sensitivity,
            self.config.factor_clamp,
        )
        scramble_factor = _bounded_factor(
            float(pressure_rate) + float(blitz_rate),
            baselines["scramble_signal"],
            self.config.scramble_sensitivity,
            self.config.factor_clamp,
        )

        team_dists.pace_factor *= pace_factor
        adjusted_pass_rate = float(np.clip(
            team_dists.play_calling.default["pass"] * pass_factor,
            0.0,
            1.0,
        ))
        team_dists.play_calling.default["pass"] = adjusted_pass_rate
        if "run" in team_dists.play_calling.default:
            team_dists.play_calling.default["run"] = float(
                np.clip(1.0 - adjusted_pass_rate, 0.0, 1.0)
            )
        team_dists.turnover_rates.sack_rate *= sack_factor
        starter.usage.scramble_rate *= scramble_factor

    def _feature_baselines(self, features: pl.DataFrame) -> dict[str, float] | None:
        if features.is_empty():
            return None

        means: dict[str, float] = {}
        for column in (
            "no_huddle_rate",
            "play_action_rate",
            "pressure_rate",
            "blitz_rate",
        ):
            value = features.select(pl.col(column).cast(pl.Float64).mean()).item()
            if value is None:
                return None
            means[column] = float(value)

        return {
            "pace_signal": means["no_huddle_rate"] + means["play_action_rate"],
            "play_action_rate": means["play_action_rate"],
            "pressure_rate": means["pressure_rate"],
            "scramble_signal": means["pressure_rate"] + means["blitz_rate"],
        }
