"""Post-simulation weekly projection nudges from same-season role trends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, cast, Protocol

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader
from fantasy_sim.data.role_trend.models import RoleTrendConfig


@dataclass
class TrendStats:
    total_rows: int
    adjusted_rows: int
    neutral_rows: int


ProjectionValue: TypeAlias = str | float | int | bool | None
ProjectionRow: TypeAlias = dict[str, ProjectionValue]


class RoleTrendInputsLoader(Protocol):
    def load_weekly(self, seasons: list[int]) -> pl.DataFrame: ...


class RoleTrendProjectionAdjuster:
    """Apply bounded post-sim role trend adjustments to weekly projections."""

    def __init__(
        self,
        config: RoleTrendConfig,
        role_inputs_loader: RoleTrendInputsLoader | None = None,
    ) -> None:
        self.config: RoleTrendConfig = config
        self.loader: RoleTrendInputsLoader = role_inputs_loader or WeeklyRoleInputLoader()
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
        value = cast(float | int | None, frame.select(expr.mean()).item())
        return float(value or 0.0)

    @staticmethod
    def _string_value(row: ProjectionRow, key: str) -> str | None:
        value = row.get(key)
        return value if isinstance(value, str) else None

    @staticmethod
    def _fpts_value(row: ProjectionRow) -> float:
        value = row.get("fpts")
        if isinstance(value, bool):
            raise TypeError("projection row has invalid boolean fpts")
        if isinstance(value, (int, float)):
            return float(value)
        raise TypeError("projection row is missing numeric fpts")

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
        history_inputs = season_inputs.filter(pl.col("week") < week)
        empty_history = history_inputs.head(0)
        history_by_key: dict[tuple[str, str], pl.DataFrame] = {}
        if not history_inputs.is_empty():
            for history_frame in history_inputs.partition_by(
                ["player_id", "team"],
                maintain_order=False,
            ):
                first_row = history_frame.row(0, named=True)
                history_by_key[(str(first_row["player_id"]), str(first_row["team"]))] = (
                    history_frame
                )
        adjusted_rows = 0
        output: list[ProjectionRow] = []

        for projection in projections:
            row = dict(projection)
            position = self._string_value(row, "position")
            player_id = self._string_value(row, "player_id")
            team = self._string_value(row, "team")

            if (
                position is None
                or position not in self.config.positions
                or player_id is None
                or team is None
            ):
                output.append(self._mark_neutral(row))
                continue

            player_history = history_by_key.get((player_id, team), empty_history)
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

            row["fpts"] = round(self._fpts_value(row) * factor, 1)
            row["role_trend_factor"] = round(factor, 4)
            row["role_trend_applied"] = factor != 1.0
            if row["role_trend_applied"]:
                adjusted_rows += 1
            output.append(row)

        output.sort(key=self._fpts_value, reverse=True)
        for rank, row in enumerate(output, start=1):
            row["rank"] = rank

        return output, TrendStats(
            total_rows=total_rows,
            adjusted_rows=adjusted_rows,
            neutral_rows=total_rows - adjusted_rows,
        )
