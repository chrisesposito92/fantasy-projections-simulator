"""Post-simulation weekly projection nudges from same-season role trends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader
from fantasy_sim.data.role_trend.models import RoleTrendConfig


@dataclass
class TrendStats:
    total_rows: int
    adjusted_rows: int
    neutral_rows: int


ProjectionRow = dict[str, Any]


class RoleTrendProjectionAdjuster:
    """Apply bounded post-sim role trend adjustments to weekly projections."""

    def __init__(
        self,
        config: RoleTrendConfig,
        role_inputs_loader: WeeklyRoleInputLoader | None = None,
    ) -> None:
        self.config = config
        self.loader = role_inputs_loader or WeeklyRoleInputLoader()
        self._cache: dict[int, pl.DataFrame] = {}

    def _season_inputs(self, season: int) -> pl.DataFrame:
        cached = self._cache.get(season)
        if cached is not None:
            return cached

        frame = self.loader.load_weekly([season])
        self._cache[season] = frame
        return frame

    def _position_sensitivity(self, position: str) -> float:
        if position == "QB":
            return self.config.qb.sensitivity
        if position == "RB":
            return self.config.rb.sensitivity
        if position == "WR":
            return self.config.wr.sensitivity
        return self.config.te.sensitivity

    @staticmethod
    def _mean_expr(frame: pl.DataFrame, expr: pl.Expr) -> float:
        if frame.is_empty():
            return 0.0
        value = frame.select(expr.mean()).item()
        return float(value or 0.0)

    def _opportunity(self, frame: pl.DataFrame, position: str) -> float:
        if frame.is_empty():
            return 0.0

        attempts = pl.col("attempts").fill_null(0)
        carries = pl.col("carries").fill_null(0)
        targets = pl.col("targets").fill_null(0)

        if position == "QB":
            return self._mean_expr(frame, attempts + (carries * 0.5))
        if position == "RB":
            return self._mean_expr(frame, carries + (targets * 1.5))
        return self._mean_expr(frame, targets)

    def _participation(self, frame: pl.DataFrame) -> float:
        if "offense_pct" not in frame.columns:
            return 1.0

        non_null = frame.filter(pl.col("offense_pct").is_not_null())
        if non_null.is_empty():
            return 1.0

        return self._mean_expr(non_null, pl.col("offense_pct").clip(0.0, 1.0))

    def _trend_signal(self, frame: pl.DataFrame, position: str) -> float:
        if frame.is_empty():
            return 0.0
        return self._opportunity(frame, position) * self._participation(frame)

    @staticmethod
    def _mark_neutral(row: ProjectionRow) -> ProjectionRow:
        row["role_trend_applied"] = False
        row["role_trend_factor"] = 1.0
        return row

    def adjust_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], TrendStats]:
        total_rows = len(projections)
        if not projections:
            return [], TrendStats(total_rows=0, adjusted_rows=0, neutral_rows=0)

        if not self.config.enabled or week <= 1:
            rows = [self._mark_neutral(dict(projection)) for projection in projections]
            return rows, TrendStats(
                total_rows=total_rows,
                adjusted_rows=0,
                neutral_rows=total_rows,
            )

        season_inputs = self._season_inputs(season)
        adjusted_rows = 0
        output: list[ProjectionRow] = []

        for projection in projections:
            row = dict(projection)
            position = row.get("position", "")
            player_id = row.get("player_id")
            team = row.get("team")

            if (
                position not in self.config.positions
                or player_id is None
                or team is None
            ):
                output.append(self._mark_neutral(row))
                continue

            player_history = season_inputs.filter(
                (pl.col("player_id") == player_id)
                & (pl.col("team") == team)
                & (pl.col("week") < week)
            )
            recent = player_history.tail(self.config.window_weeks)
            baseline = player_history.head(
                max(0, player_history.height - self.config.window_weeks)
            )

            if recent.is_empty():
                output.append(self._mark_neutral(row))
                continue

            recent_signal = self._trend_signal(recent, position)
            baseline_signal = self._trend_signal(baseline, position)
            if baseline_signal <= 0:
                baseline_signal = recent_signal
            if baseline_signal <= 0:
                output.append(self._mark_neutral(row))
                continue

            ratio = recent_signal / baseline_signal
            sensitivity = self._position_sensitivity(position)
            raw_factor = 1.0 + ((ratio - 1.0) * sensitivity)
            factor = min(
                self.config.factor_clamp[1],
                max(self.config.factor_clamp[0], raw_factor),
            )

            row["fpts"] = round(float(row["fpts"]) * factor, 1)
            row["role_trend_factor"] = round(factor, 4)
            row["role_trend_applied"] = factor != 1.0
            if row["role_trend_applied"]:
                adjusted_rows += 1
            output.append(row)

        output.sort(key=lambda projection: projection["fpts"], reverse=True)
        for rank, row in enumerate(output, start=1):
            row["rank"] = rank

        return output, TrendStats(
            total_rows=total_rows,
            adjusted_rows=adjusted_rows,
            neutral_rows=total_rows - adjusted_rows,
        )
