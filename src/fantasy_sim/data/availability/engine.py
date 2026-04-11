from __future__ import annotations

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader
from fantasy_sim.data.availability.models import AvailabilityConfig, AvailabilityDecision
from fantasy_sim.models.player import PlayerModel, TeamRoster


class AvailabilityEngine:
    """Conservative explicit-signal-first availability adjustments."""

    def __init__(
        self,
        config: AvailabilityConfig,
        role_inputs_loader: WeeklyRoleInputLoader | None = None,
    ) -> None:
        self._config = config
        self._loader = role_inputs_loader or WeeklyRoleInputLoader()
        self._cache: dict[int, pl.DataFrame] = {}

    def apply(self, roster: TeamRoster, season: int, week: int) -> None:
        if not self._config.enabled:
            return

        for player in roster.players:
            if player.position not in self._config.positions:
                continue

            decision = self._decision_for_player(
                player_id=player.player_id,
                position=player.position,
                team=roster.team,
                season=season,
                week=week,
            )
            self._apply_decision(player, decision)

    def _season_inputs(self, season: int) -> pl.DataFrame:
        cached = self._cache.get(season)
        if cached is not None:
            return cached

        frame = self._loader.load_weekly([season])
        self._cache[season] = frame
        return frame

    def _decision_for_player(
        self,
        player_id: str,
        position: str,
        team: str,
        season: int,
        week: int,
    ) -> AvailabilityDecision:
        rows = self._season_inputs(season).filter(
            (pl.col("player_id") == player_id)
            & (pl.col("team") == team)
            & (pl.col("week") <= week)
        )
        current = rows.filter(pl.col("week") == week)

        explicit = self._explicit_decision(position=position, current=current)
        if explicit is not None:
            return explicit

        return self._usage_fallback_decision(position=position, history=rows.filter(pl.col("week") < week))

    def _explicit_decision(
        self,
        position: str,
        current: pl.DataFrame,
    ) -> AvailabilityDecision | None:
        if current.is_empty():
            return None

        row = current.row(0, named=True)

        if self._config.injuries.enabled:
            status = row.get("report_status")
            if status in self._config.injuries.hard_out_statuses:
                return AvailabilityDecision(
                    hard_inactive=True,
                    factor=0.0,
                    reason=f"injury:{status}",
                )
            if status in self._config.injuries.limited_statuses:
                return AvailabilityDecision(
                    factor=self._config.injuries.limited_factor,
                    reason=f"injury:{status}",
                )

        if position == "QB" and self._config.depth_charts.enabled:
            depth_position = row.get("depth_position")
            starter_slot = self._config.depth_charts.starter_slots.get("QB", "QB1")
            if depth_position == starter_slot:
                return AvailabilityDecision(reason="depth:starter")
            if isinstance(depth_position, str) and depth_position.startswith("QB"):
                return AvailabilityDecision(
                    hard_inactive=True,
                    factor=0.0,
                    reason=f"depth:{depth_position}",
                )

        return None

    def _usage_fallback_decision(
        self,
        position: str,
        history: pl.DataFrame,
    ) -> AvailabilityDecision:
        cfg = self._config.usage_fallback
        if not cfg.enabled or history.is_empty():
            return AvailabilityDecision()

        recent = history.tail(cfg.lookback_weeks)
        offense_pct = self._mean_or_zero(recent, "offense_pct")
        attempts = self._sum_or_zero(recent, "attempts")
        carries = self._sum_or_zero(recent, "carries")
        targets = self._sum_or_zero(recent, "targets")

        if position == "QB" and offense_pct < 0.75:
            return AvailabilityDecision(
                factor=cfg.qb_low_usage_factor,
                reason="usage:soft",
            )

        if position == "RB" and offense_pct < 0.40 and carries + targets <= 8:
            return AvailabilityDecision(
                factor=cfg.rb_low_usage_factor,
                reason="usage:soft",
            )

        if position == "WR" and offense_pct < 0.55 and targets <= 6:
            return AvailabilityDecision(
                factor=cfg.wr_low_usage_factor,
                reason="usage:soft",
            )

        if position == "TE" and offense_pct < 0.60 and targets <= 6:
            return AvailabilityDecision(
                factor=cfg.te_low_usage_factor,
                reason="usage:soft",
            )

        # Preserve a conservative fallback for low-volume QB history even when
        # offense_pct is missing from legacy inputs.
        if position == "QB" and offense_pct == 0.0 and attempts <= 24:
            return AvailabilityDecision(
                factor=cfg.qb_low_usage_factor,
                reason="usage:soft",
            )

        return AvailabilityDecision()

    @staticmethod
    def _sum_or_zero(frame: pl.DataFrame, column: str) -> float:
        if column not in frame.columns:
            return 0.0
        value = frame.select(pl.col(column).fill_null(0).sum()).item()
        return float(value or 0.0)

    @staticmethod
    def _mean_or_zero(frame: pl.DataFrame, column: str) -> float:
        if column not in frame.columns:
            return 0.0
        value = frame.select(pl.col(column).fill_null(0).mean()).item()
        return float(value or 0.0)

    @staticmethod
    def _apply_decision(player: PlayerModel, decision: AvailabilityDecision) -> None:
        if decision.hard_inactive:
            AvailabilityEngine._zero_usage(player)
            return

        factor = decision.factor
        for field in (
            "snap_share",
            "carry_share",
            "red_zone_carry_share",
            "outer_rz_carry_share",
            "goal_line_carry_share",
            "target_share",
            "red_zone_target_share",
            "outer_rz_target_share",
            "goal_line_target_share",
            "air_yards_share",
            "scramble_rate",
        ):
            setattr(player.usage, field, getattr(player.usage, field) * factor)

    @staticmethod
    def _zero_usage(player: PlayerModel) -> None:
        for field in (
            "snap_share",
            "carry_share",
            "red_zone_carry_share",
            "outer_rz_carry_share",
            "goal_line_carry_share",
            "target_share",
            "red_zone_target_share",
            "outer_rz_target_share",
            "goal_line_target_share",
            "air_yards_share",
            "scramble_rate",
        ):
            setattr(player.usage, field, 0.0)
