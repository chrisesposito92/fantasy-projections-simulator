from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import MatchupContext, QbSplitConfig, QbSplitFactors
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {
    "season",
    "week",
    "team",
    "player_id",
    "game_id",
    "pressure_dropbacks",
    "no_pressure_dropbacks",
    "pressure_completion_percent",
    "no_pressure_completion_percent",
    "pressure_ypa",
    "no_pressure_ypa",
}


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0 or not np.isfinite(numerator) or not np.isfinite(denominator):
        return 1.0
    return float(numerator / denominator)


class QbSplitEngine:
    """Derive QB pressure-response factors from PFF passing-detail splits."""

    def __init__(self, loader: PffLoader, config: QbSplitConfig):
        self._loader = loader
        self._config = config
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        key = f"passing_detail_{'_'.join(str(season) for season in sorted(seasons))}"
        if key not in self._cache:
            df = self._loader.load_facet("passing_detail", seasons)
            if df.is_empty() or not _REQUIRED_COLUMNS.issubset(df.columns):
                missing_columns = sorted(_REQUIRED_COLUMNS.difference(df.columns))
                if missing_columns:
                    logger.debug(
                        "QbSplitEngine missing required passing_detail columns: %s",
                        ", ".join(missing_columns),
                    )
                self._cache[key] = pl.DataFrame()
            else:
                self._cache[key] = df
        return self._cache[key]

    def _aggregate_rows(
        self,
        seasons: list[int],
        target_season: int,
        max_week: int,
    ) -> pl.DataFrame:
        df = self._load_cached(seasons)
        if df.is_empty():
            return pl.DataFrame()

        filtered = df.filter(pl.col("season").is_in(seasons)).filter(
            (pl.col("season") < target_season)
            | ((pl.col("season") == target_season) & (pl.col("week") < max_week))
        )
        if filtered.is_empty():
            return pl.DataFrame()

        return (
            filtered.with_columns(
                (
                    pl.col("pressure_dropbacks").cast(pl.Float64)
                    * pl.col("pressure_completion_percent").cast(pl.Float64)
                ).alias("_pressure_completion_weight"),
                (
                    pl.col("no_pressure_dropbacks").cast(pl.Float64)
                    * pl.col("no_pressure_completion_percent").cast(pl.Float64)
                ).alias("_clean_completion_weight"),
                (
                    pl.col("pressure_dropbacks").cast(pl.Float64)
                    * pl.col("pressure_ypa").cast(pl.Float64)
                ).alias("_pressure_ypa_weight"),
                (
                    pl.col("no_pressure_dropbacks").cast(pl.Float64)
                    * pl.col("no_pressure_ypa").cast(pl.Float64)
                ).alias("_clean_ypa_weight"),
            )
            .group_by(["season", "player_id"])
            .agg(
                pl.col("pressure_dropbacks").sum().cast(pl.Float64),
                pl.col("no_pressure_dropbacks").sum().cast(pl.Float64),
                pl.col("_pressure_completion_weight").sum(),
                pl.col("_clean_completion_weight").sum(),
                pl.col("_pressure_ypa_weight").sum(),
                pl.col("_clean_ypa_weight").sum(),
                pl.col("game_id").n_unique().alias("games"),
            )
        )

    def _summary(self, rows: pl.DataFrame) -> dict[str, float] | None:
        if rows.is_empty():
            return None

        pressure_dropbacks = float(rows["pressure_dropbacks"].sum())
        clean_dropbacks = float(rows["no_pressure_dropbacks"].sum())
        games = int(rows["games"].sum())
        pressure_completion_weight = float(rows["_pressure_completion_weight"].sum())
        clean_completion_weight = float(rows["_clean_completion_weight"].sum())
        pressure_ypa_weight = float(rows["_pressure_ypa_weight"].sum())
        clean_ypa_weight = float(rows["_clean_ypa_weight"].sum())

        return {
            "pressure_dropbacks": pressure_dropbacks,
            "no_pressure_dropbacks": clean_dropbacks,
            "games": games,
            "_pressure_completion_weight": pressure_completion_weight,
            "_clean_completion_weight": clean_completion_weight,
            "_pressure_ypa_weight": pressure_ypa_weight,
            "_clean_ypa_weight": clean_ypa_weight,
        }

    def _passes_sample_gates(self, row: dict[str, float] | None) -> bool:
        if row is None:
            return False
        return (
            row["pressure_dropbacks"] >= self._config.min_pressure_dropbacks
            and row["no_pressure_dropbacks"] >= self._config.min_clean_dropbacks
            and row["games"] >= self._config.min_games
        )

    def _blend_rows(
        self,
        current_row: dict[str, float] | None,
        previous_row: dict[str, float] | None,
    ) -> dict[str, float] | None:
        if current_row is None and previous_row is None:
            return None
        if current_row is None:
            return previous_row
        if previous_row is None:
            return current_row

        if not self._config.early_season_blend or current_row["games"] >= self._config.min_games:
            return current_row

        blend_weight = current_row["games"] / max(self._config.min_games, 1)
        return {
            key: blend_weight * current_row[key] + (1.0 - blend_weight) * previous_row[key]
            for key in current_row
        }

    def _blended_row(
        self,
        qb_rows: pl.DataFrame,
        target_season: int,
    ) -> dict[str, float] | None:
        current_row = self._summary(qb_rows.filter(pl.col("season") == target_season))
        previous_seasons = [
            int(season)
            for season in qb_rows["season"].unique().to_list()
            if int(season) < target_season
        ]
        previous_row = None
        if previous_seasons:
            previous_season = max(previous_seasons)
            previous_row = self._summary(
                qb_rows.filter(pl.col("season") == previous_season)
            )

        if self._passes_sample_gates(current_row):
            return current_row
        if self._config.early_season_blend and current_row is not None and previous_row is not None:
            blended = self._blend_rows(current_row, previous_row)
            if blended is not None and self._passes_sample_gates(previous_row):
                return blended
        if self._passes_sample_gates(previous_row):
            return previous_row
        return None

    def _trait_pair(self, row: dict[str, float] | None) -> tuple[float, float] | None:
        if row is None:
            return None

        pressure_completion = _safe_ratio(
            row["_pressure_completion_weight"],
            row["pressure_dropbacks"],
        )
        clean_completion = _safe_ratio(
            row["_clean_completion_weight"],
            row["no_pressure_dropbacks"],
        )
        pressure_ypa = _safe_ratio(
            row["_pressure_ypa_weight"],
            row["pressure_dropbacks"],
        )
        clean_ypa = _safe_ratio(
            row["_clean_ypa_weight"],
            row["no_pressure_dropbacks"],
        )

        return (
            _safe_ratio(pressure_completion, clean_completion),
            _safe_ratio(pressure_ypa, clean_ypa),
        )

    def compute(
        self,
        roster: TeamRoster,
        pff_crosswalk: dict[int, str],
        training_seasons: list[int],
        target_season: int,
        max_week: int,
        matchup_context: MatchupContext,
    ) -> QbSplitFactors:
        if not self._config.enabled:
            return QbSplitFactors()

        pressure_environment = (
            matchup_context.sack_rate_factor * matchup_context.ol_pass_block_factor
        )
        if np.isclose(pressure_environment, 1.0):
            return QbSplitFactors()

        starter_qb = roster.get_starting_qb()
        reverse_crosswalk = {nflverse_id: pff_id for pff_id, nflverse_id in pff_crosswalk.items()}
        qb_pff_id = reverse_crosswalk.get(starter_qb.player_id)
        if qb_pff_id is None:
            return QbSplitFactors()

        aggregated = self._aggregate_rows(training_seasons, target_season, max_week)
        if aggregated.is_empty():
            return QbSplitFactors()

        qb_row = self._blended_row(
            aggregated.filter(pl.col("player_id") == qb_pff_id),
            target_season,
        )
        qb_traits = self._trait_pair(qb_row)
        if qb_traits is None:
            return QbSplitFactors()

        league_traits = self._trait_pair(self._summary(aggregated))
        if league_traits is None:
            return QbSplitFactors()

        completion_trait = _safe_ratio(qb_traits[0], league_traits[0])
        yards_trait = _safe_ratio(qb_traits[1], league_traits[1])

        completion_factor = 1.0 + (
            (completion_trait - 1.0)
            * (pressure_environment - 1.0)
            * self._config.completion_sensitivity
        )
        yards_factor = 1.0 + (
            (yards_trait - 1.0)
            * (pressure_environment - 1.0)
            * self._config.yards_sensitivity
        )

        return QbSplitFactors(
            catch_rate_factor=float(
                np.clip(
                    completion_factor,
                    self._config.catch_rate_clamp[0],
                    self._config.catch_rate_clamp[1],
                )
            ),
            yards_scale_factor=float(
                np.clip(
                    yards_factor,
                    self._config.yards_scale_clamp[0],
                    self._config.yards_scale_clamp[1],
                )
            ),
        )
