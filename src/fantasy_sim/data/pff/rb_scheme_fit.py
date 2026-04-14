from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import RbSchemeFitConfig, RbSchemeFitFactors
from fantasy_sim.models.player import TeamRoster

_INTERIOR_DIRECTIONS = {"ML", "MR", "LG", "RG"}
_EDGE_DIRECTIONS = {"LE", "RE", "LT", "RT"}


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return 0.0
    return float(numerator / denominator)


class RbSchemeFitEngine:
    def __init__(self, loader: PffLoader, config: RbSchemeFitConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        key = f"{facet}_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(facet, seasons)
        return self._cache[key]

    def _flatten_direction_rows(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
        pff_crosswalk: Mapping[int, str],
    ) -> pl.DataFrame:
        df = self._load_cached("rushing_direction", seasons)
        if df.is_empty() or "directions" not in df.columns:
            return pl.DataFrame()

        filtered = (
            df.filter(pl.col("position") == "RB")
            .filter(pl.col("season").is_in(seasons))
            .filter(
                (pl.col("season") < target_season)
                | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
            )
        )
        if filtered.is_empty():
            return pl.DataFrame()

        reverse_crosswalk = pl.DataFrame(
            {
                "pff_player_id": list(pff_crosswalk.keys()),
                "player_id": list(pff_crosswalk.values()),
            }
        )
        if reverse_crosswalk.is_empty():
            return pl.DataFrame()

        exploded = (
            filtered.explode("directions")
            .drop_nulls("directions")
            .unnest("directions")
            .with_columns(
                pl.when(pl.col("direction").is_in(list(_INTERIOR_DIRECTIONS)))
                .then(pl.lit("interior"))
                .when(pl.col("direction").is_in(list(_EDGE_DIRECTIONS)))
                .then(pl.lit("edge"))
                .otherwise(pl.lit(None))
                .alias("family")
            )
            .filter(pl.col("family").is_not_null())
            .rename({"player_id": "pff_player_id"})
            .join(reverse_crosswalk, on="pff_player_id", how="inner")
        )
        if exploded.is_empty():
            return pl.DataFrame()

        return exploded.select(
            [
                "season",
                "team",
                "player_id",
                "game_id",
                "family",
                pl.col("attempts").cast(pl.Float64),
                pl.col("yards").cast(pl.Float64),
            ]
        )

    def _aggregate_team_blocking(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> pl.DataFrame:
        df = self._load_cached("offense_run_blocking", seasons)
        if df.is_empty():
            return pl.DataFrame()

        filtered = df.filter(pl.col("season").is_in(seasons)).filter(
            (pl.col("season") < target_season)
            | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
        )
        if filtered.is_empty():
            return pl.DataFrame()

        return filtered.with_columns(
            (
                pl.col("gap_grades_run_block").cast(pl.Float64)
                * pl.col("gap_snap_counts_run_block").cast(pl.Float64)
            ).alias("gap_grade_weight"),
            (
                pl.col("zone_grades_run_block").cast(pl.Float64)
                * pl.col("zone_snap_counts_run_block").cast(pl.Float64)
            ).alias("zone_grade_weight"),
        ).group_by(["season", "team"]).agg(
            pl.col("game_id").n_unique().alias("games"),
            pl.col("gap_snap_counts_run_play").sum().cast(pl.Float64).alias("gap_run_play"),
            pl.col("zone_snap_counts_run_play").sum().cast(pl.Float64).alias("zone_run_play"),
            pl.col("gap_snap_counts_run_block").sum().cast(pl.Float64).alias("gap_run_block_snaps"),
            pl.col("zone_snap_counts_run_block").sum().cast(pl.Float64).alias("zone_run_block_snaps"),
            pl.col("gap_grade_weight").sum().cast(pl.Float64),
            pl.col("zone_grade_weight").sum().cast(pl.Float64),
        )

    def _player_profile(self, rows: pl.DataFrame) -> dict[str, float] | None:
        if rows.is_empty():
            return None

        interior = rows.filter(pl.col("family") == "interior")
        edge = rows.filter(pl.col("family") == "edge")
        total_attempts = float(rows["attempts"].sum())
        if total_attempts <= 0:
            return None

        interior_attempts = float(interior["attempts"].sum()) if not interior.is_empty() else 0.0
        edge_attempts = float(edge["attempts"].sum()) if not edge.is_empty() else 0.0
        interior_yards = float(interior["yards"].sum()) if not interior.is_empty() else 0.0
        edge_yards = float(edge["yards"].sum()) if not edge.is_empty() else 0.0

        return {
            "games": float(rows.select(pl.col("game_id").n_unique()).item()),
            "classified_attempts": total_attempts,
            "interior_attempt_share": _safe_ratio(interior_attempts, total_attempts),
            "edge_attempt_share": _safe_ratio(edge_attempts, total_attempts),
            "interior_ypa": _safe_ratio(interior_yards, interior_attempts),
            "edge_ypa": _safe_ratio(edge_yards, edge_attempts),
            "overall_ypa": _safe_ratio(float(rows["yards"].sum()), total_attempts),
        }

    def _team_profile(self, rows: pl.DataFrame) -> dict[str, float] | None:
        if rows.is_empty():
            return None

        gap_run_play = float(rows["gap_run_play"].sum())
        zone_run_play = float(rows["zone_run_play"].sum())
        gap_run_block_snaps = float(rows["gap_run_block_snaps"].sum())
        zone_run_block_snaps = float(rows["zone_run_block_snaps"].sum())
        total_run_play = gap_run_play + zone_run_play
        if total_run_play <= 0:
            return None

        return {
            "games": float(rows["games"].sum()),
            "gap_share": _safe_ratio(gap_run_play, total_run_play),
            "zone_share": _safe_ratio(zone_run_play, total_run_play),
            "gap_grade": _safe_ratio(
                float(rows["gap_grade_weight"].sum()),
                gap_run_block_snaps,
            ),
            "zone_grade": _safe_ratio(
                float(rows["zone_grade_weight"].sum()),
                zone_run_block_snaps,
            ),
        }

    def _passes_player_gates(self, profile: dict[str, float] | None) -> bool:
        if profile is None:
            return False
        return (
            profile["classified_attempts"] >= self._config.min_attempts
            and profile["games"] >= self._config.min_games
        )

    def _passes_team_gates(self, profile: dict[str, float] | None) -> bool:
        if profile is None:
            return False
        return profile["games"] >= self._config.min_games

    def _normalized_weights(self) -> tuple[float, float]:
        usage_weight = max(float(self._config.scheme_usage_weight), 0.0)
        blocking_weight = max(float(self._config.blocking_alignment_weight), 0.0)
        total = usage_weight + blocking_weight
        if total <= 0:
            return 0.0, 0.0
        return usage_weight / total, blocking_weight / total

    def _blended_rows(
        self,
        current_rows: pl.DataFrame,
        previous_rows: pl.DataFrame,
    ) -> pl.DataFrame:
        if current_rows.is_empty():
            return previous_rows
        if previous_rows.is_empty():
            return current_rows
        return pl.concat([current_rows, previous_rows], how="vertical_relaxed")

    def _previous_season_rows(self, rows: pl.DataFrame, target_season: int) -> pl.DataFrame:
        if rows.is_empty():
            return pl.DataFrame()
        immediate_previous = target_season - 1
        return rows.filter(pl.col("season") == immediate_previous)

    def _select_player_profile(
        self,
        rows: pl.DataFrame,
        target_season: int,
    ) -> dict[str, float] | None:
        current_rows = rows.filter(pl.col("season") == target_season)
        current_profile = self._player_profile(current_rows)
        if self._passes_player_gates(current_profile):
            return current_profile

        previous_rows = self._previous_season_rows(rows, target_season)
        if self._config.early_season_blend and not current_rows.is_empty() and not previous_rows.is_empty():
            blended_profile = self._player_profile(
                self._blended_rows(current_rows, previous_rows)
            )
            if self._passes_player_gates(blended_profile):
                return blended_profile

        historical_profile = self._player_profile(rows)
        if self._passes_player_gates(historical_profile):
            return historical_profile
        return None

    def _select_team_profile(
        self,
        rows: pl.DataFrame,
        target_season: int,
    ) -> dict[str, float] | None:
        current_rows = rows.filter(pl.col("season") == target_season)
        current_profile = self._team_profile(current_rows)
        if self._passes_team_gates(current_profile):
            return current_profile

        previous_rows = self._previous_season_rows(rows, target_season)
        if self._config.early_season_blend and not current_rows.is_empty() and not previous_rows.is_empty():
            blended_profile = self._team_profile(
                self._blended_rows(current_rows, previous_rows)
            )
            if self._passes_team_gates(blended_profile):
                return blended_profile

        historical_profile = self._team_profile(rows)
        if self._passes_team_gates(historical_profile):
            return historical_profile
        return None

    def compute(
        self,
        roster: TeamRoster,
        pff_crosswalk: Mapping[int, str] | None,
        training_seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> dict[str, RbSchemeFitFactors]:
        if not self._config.enabled or not pff_crosswalk:
            return {}

        direction_rows = self._flatten_direction_rows(
            training_seasons,
            target_season,
            max_week,
            pff_crosswalk,
        )
        if direction_rows.is_empty():
            return {}

        blocking_rows = self._aggregate_team_blocking(training_seasons, target_season, max_week)
        if blocking_rows.is_empty():
            return {}

        usage_weight, blocking_weight = self._normalized_weights()
        if usage_weight == 0.0 and blocking_weight == 0.0:
            return {}

        team_rows = blocking_rows.filter(pl.col("team") == roster.team)
        team_profile = self._select_team_profile(team_rows, target_season)
        if team_profile is None:
            return {}

        results: dict[str, RbSchemeFitFactors] = {}
        for player in roster.players:
            if (
                player.position != "RB"
                or player.usage.carry_share <= 0
                or player.outcomes.rushing_yards_dist is None
                or len(player.outcomes.rushing_yards_dist) == 0
            ):
                continue

            player_rows = direction_rows.filter(pl.col("player_id") == player.player_id)
            player_profile = self._select_player_profile(player_rows, target_season)
            if player_profile is None:
                continue

            runner_usage_score = (
                (team_profile["gap_share"] * player_profile["interior_ypa"])
                + (team_profile["zone_share"] * player_profile["edge_ypa"])
            )
            runner_baseline_score = player_profile["overall_ypa"]
            usage_delta = _safe_ratio(runner_usage_score, runner_baseline_score) - 1.0

            family_preference = (
                player_profile["interior_attempt_share"] - player_profile["edge_attempt_share"]
            )
            blocking_delta = family_preference * (
                (team_profile["gap_grade"] - team_profile["zone_grade"]) / 100.0
            )

            combined_delta = (usage_weight * usage_delta) + (blocking_weight * blocking_delta)
            factor = 1.0 + (combined_delta * self._config.rush_yards_sensitivity)
            factor = float(np.clip(factor, *self._config.factor_clamp))

            results[player.player_id] = RbSchemeFitFactors(rushing_yards_factor=factor)

        return results
