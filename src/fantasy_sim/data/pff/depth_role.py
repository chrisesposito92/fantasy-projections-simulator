from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import (
    DepthRoleConfig,
    DepthRoleFactors,
    DepthRolePositionConfig,
)
from fantasy_sim.models.player import TeamRoster

_BUCKETS = ("behind_los", "short", "medium", "deep")


def _bounded_ratio_factor(
    observed: float,
    baseline: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    lower, upper = clamp
    if baseline <= 0 or not np.isfinite(observed) or not np.isfinite(baseline):
        return 1.0
    factor = 1.0 + ((observed / baseline) - 1.0) * sensitivity
    return float(np.clip(factor, lower, upper))


def _safe_bucket_target(column: str) -> pl.Expr:
    return pl.coalesce([pl.col(column).cast(pl.Float64), pl.lit(0.0)])


def _air_proxy_expr() -> pl.Expr:
    expr = pl.lit(0.0)
    for bucket in _BUCKETS:
        expr = expr + (
            _safe_bucket_target(f"{bucket}_targets")
            * pl.coalesce(
                [pl.col(f"{bucket}_avg_depth_of_target").cast(pl.Float64), pl.lit(0.0)]
            )
        )
    return expr.alias("_air_proxy")


class DepthRoleEngine:
    """Compute bounded WR/TE role-volume factors from PFF receiving-depth data."""

    def __init__(self, loader: PffLoader, config: DepthRoleConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        key = f"receiving_depth_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet("receiving_depth", seasons)
        return self._cache[key]

    def _aggregate_team_roles(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
        pff_crosswalk: dict[int, str],
    ) -> pl.DataFrame:
        df = self._load_cached(seasons)
        if df.is_empty():
            return pl.DataFrame()

        reverse_crosswalk = pl.DataFrame(
            {
                "pff_player_id": list(pff_crosswalk.keys()),
                "player_id": list(pff_crosswalk.values()),
            }
        )
        if reverse_crosswalk.is_empty():
            return pl.DataFrame()

        df = (
            df.rename({"player_id": "pff_player_id"})
            .join(reverse_crosswalk, on="pff_player_id", how="inner")
            .filter(pl.col("position").is_in(list(self._config.positions)))
            .filter(pl.col("season").is_in(seasons))
            .filter(
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
            )
            .with_columns(
                pl.coalesce([pl.col("routes").cast(pl.Float64), pl.lit(0.0)]).alias("_routes"),
                pl.coalesce([pl.col("targets").cast(pl.Float64), pl.lit(0.0)]).alias("_targets"),
                _air_proxy_expr(),
            )
        )
        if df.is_empty():
            return pl.DataFrame()

        player_roles = (
            df.group_by(["season", "team", "player_id", "position"])
            .agg(
                pl.col("_routes").sum().alias("routes"),
                pl.col("_targets").sum().alias("targets"),
                pl.col("_air_proxy").sum().alias("air_proxy"),
                pl.col("game_id").n_unique().alias("games"),
            )
        )
        team_totals = (
            player_roles.group_by(["season", "team"])
            .agg(
                pl.col("targets").sum().alias("team_targets"),
                pl.col("air_proxy").sum().alias("team_air_proxy"),
            )
        )
        return player_roles.join(team_totals, on=["season", "team"], how="left").with_columns(
            pl.when(pl.col("team_targets") > 0)
            .then(pl.col("targets") / pl.col("team_targets"))
            .otherwise(pl.lit(0.0))
            .alias("target_role"),
            pl.when(pl.col("team_air_proxy") > 0)
            .then(pl.col("air_proxy") / pl.col("team_air_proxy"))
            .otherwise(pl.lit(0.0))
            .alias("air_role"),
        )

    def _position_config(self, position: str) -> DepthRolePositionConfig:
        return self._config.wr if position == "WR" else self._config.te

    def _blended_role_row(
        self,
        current_row: dict | None,
        previous_row: dict | None,
    ) -> dict | None:
        if current_row is None and previous_row is None:
            return None
        if current_row is None:
            return previous_row
        if (
            not self._config.early_season_blend
            or previous_row is None
            or current_row["games"] >= self._config.min_games
        ):
            return current_row

        weight = current_row["games"] / max(self._config.min_games, 1)
        return {
            "target_role": weight * current_row["target_role"]
            + (1.0 - weight) * previous_row["target_role"],
            "air_role": weight * current_row["air_role"]
            + (1.0 - weight) * previous_row["air_role"],
            "routes": current_row["routes"] + previous_row["routes"],
            "targets": current_row["targets"] + previous_row["targets"],
            "games": current_row["games"],
        }

    def apply(
        self,
        roster: TeamRoster,
        pff_crosswalk: dict[int, str],
        target_season: int,
        max_week: int,
    ) -> None:
        if not self._config.enabled or max_week is None or target_season is None:
            return

        role_rows = self._aggregate_team_roles(
            [target_season - 1, target_season],
            target_season,
            max_week,
            pff_crosswalk,
        )
        if role_rows.is_empty():
            return

        team_rows = role_rows.filter(pl.col("team") == roster.team)
        if team_rows.is_empty():
            return

        current_rows = {
            row["player_id"]: row
            for row in team_rows.filter(pl.col("season") == target_season).iter_rows(named=True)
        }
        previous_rows = {
            row["player_id"]: row
            for row in team_rows.filter(pl.col("season") == target_season - 1).iter_rows(named=True)
        }

        for player in roster.players:
            if player.position not in self._config.positions:
                continue

            row = self._blended_role_row(
                current_rows.get(player.player_id),
                previous_rows.get(player.player_id),
            )
            if row is None:
                continue
            if row["routes"] < self._config.min_routes or row["targets"] < self._config.min_targets:
                continue

            position_cfg = self._position_config(player.position)
            factors = DepthRoleFactors(
                target_share_factor=_bounded_ratio_factor(
                    row["target_role"],
                    player.usage.target_share,
                    position_cfg.target_share_sensitivity,
                    position_cfg.factor_clamp,
                ),
                air_yards_share_factor=_bounded_ratio_factor(
                    row["air_role"],
                    player.usage.air_yards_share,
                    position_cfg.air_yards_share_sensitivity,
                    position_cfg.factor_clamp,
                ),
            )
            player.usage.target_share *= factors.target_share_factor
            player.usage.air_yards_share *= factors.air_yards_share_factor
