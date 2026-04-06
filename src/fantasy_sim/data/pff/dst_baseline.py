"""DST Baseline Engine — fumble rate and defensive TD rate adjustments."""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.matchup import compute_factor
from fantasy_sim.data.pff.models import DstBaselineConfig, DstBaselineContext

logger = logging.getLogger(__name__)

DEFAULT_INT_RETURN_TD_RATE = 0.20
DEFAULT_FUMBLE_RETURN_TD_RATE = 0.10


class DstBaselineEngine:
    """Computes per-team DST baseline adjustments from PFF defense_summary data.

    Three adjustments:
    - fumble_rate_factor: z-score multiplier on opposing offense's fumble_rate
      (team forced-fumble quality).
    - int_return_td_rate: team-specific pick-six rate (Bayesian shrinkage
      from the 0.20 league constant).
    - fumble_return_td_rate: team-specific fumble return TD rate (Bayesian
      shrinkage from the 0.10 league constant).

    These complement the MatchupEngine, which handles sack/INT/yards factors
    but not DST-specific scoring components.
    """

    def __init__(
        self,
        config: DstBaselineConfig,
        pff_loader: PffLoader,
        seasons: list[int],
    ) -> None:
        self._config = config
        self._loader = pff_loader
        self._seasons = seasons
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, seasons: list[int]) -> pl.DataFrame:
        """Load defense_summary for the given seasons, with caching."""
        key = "_".join(str(s) for s in sorted(seasons))
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet("defense_summary", seasons)
        return self._cache[key]

    def _filter_season_week(
        self,
        df: pl.DataFrame,
        target_season: int,
        max_week: int | None,
    ) -> pl.DataFrame:
        """Filter df to a single season with optional week < max_week."""
        filtered = df.filter(pl.col("season") == target_season)
        if max_week is not None:
            filtered = filtered.filter(pl.col("week") < max_week)
        return filtered

    def _get_team_game_stats(
        self,
        df: pl.DataFrame,
        team: str,
        target_season: int,
        max_week: int | None,
    ) -> pl.DataFrame:
        """Aggregate player-level rows to per-game team totals for one team."""
        filtered = self._filter_season_week(df, target_season, max_week)
        filtered = filtered.filter(pl.col("team") == team)
        if filtered.is_empty():
            return pl.DataFrame()

        return filtered.group_by(["team", "season", "week"]).agg([
            pl.col("forced_fumbles").fill_null(0).sum(),
            pl.col("fumble_recoveries").fill_null(0).sum(),
            pl.col("fumble_recovery_touchdowns").fill_null(0).sum(),
            pl.col("interceptions").fill_null(0).sum(),
            pl.col("interception_touchdowns").fill_null(0).sum(),
            pl.col("snap_counts_defense").fill_null(0).sum(),
        ])

    def _compute_all_team_fumble_rates(
        self,
        df: pl.DataFrame,
        target_season: int,
        max_week: int | None,
    ) -> dict[str, float]:
        """Compute forced-fumble rate per defensive snap for every team."""
        filtered = self._filter_season_week(df, target_season, max_week)
        if filtered.is_empty():
            return {}

        team_stats = filtered.group_by("team").agg([
            pl.col("forced_fumbles").fill_null(0).sum().alias("total_ff"),
            pl.col("snap_counts_defense").fill_null(0).sum().alias("total_snaps"),
        ])

        result: dict[str, float] = {}
        for row in team_stats.iter_rows(named=True):
            if row["total_snaps"] > 0:
                result[row["team"]] = row["total_ff"] / row["total_snaps"]
        return result

    def _count_team_games(
        self,
        df: pl.DataFrame,
        team: str,
        target_season: int,
        max_week: int | None,
    ) -> int:
        """Count distinct games a team appears in after filtering."""
        filtered = self._filter_season_week(df, target_season, max_week)
        team_rows = filtered.filter(pl.col("team") == team)
        if team_rows.is_empty():
            return 0
        if "week" in team_rows.columns:
            return team_rows.select(pl.col("week").n_unique()).item()
        return team_rows.height

    def compute(
        self,
        defense_team: str,
        target_season: int,
        max_week: int | None = None,
    ) -> DstBaselineContext:
        """Compute DST baseline adjustments for a team in a given week.

        Uses same-season rolling window (week < max_week). When the team has
        fewer than min_games in the current season, blends with the previous
        season via a linear ramp.

        Args:
            defense_team: Team abbreviation (e.g. "KC").
            target_season: The season being simulated.
            max_week: Exclude data from this week and later (rolling window).
                      None means use all available data for the season.

        Returns:
            DstBaselineContext with fumble_rate_factor, int_return_td_rate,
            and fumble_return_td_rate. Falls back to neutral defaults when
            no data is available.
        """
        if not self._config.enabled:
            return DstBaselineContext()

        df = self._load_cached(self._seasons)
        if df.is_empty():
            return DstBaselineContext()

        # --- Current-season team stats ---
        n_games = self._count_team_games(df, defense_team, target_season, max_week)
        team_games = self._get_team_game_stats(df, defense_team, target_season, max_week)

        # --- Previous-season blend (early-season only) ---
        prev_games_df: pl.DataFrame | None = None
        prev_season = target_season - 1
        if n_games < self._config.min_games and prev_season in self._seasons:
            prev_games_df = self._get_team_game_stats(df, defense_team, prev_season, None)
            if prev_games_df.is_empty():
                prev_games_df = None

        # ---------------------------------------------------------------
        # Fumble rate factor (z-score across all teams)
        # ---------------------------------------------------------------
        all_rates = self._compute_all_team_fumble_rates(df, target_season, max_week)
        fumble_factor = 1.0

        if all_rates and defense_team in all_rates and len(all_rates) >= 2:
            league_rates = list(all_rates.values())
            league_mean = float(np.mean(league_rates))
            league_std = float(np.std(league_rates, ddof=1))
            sensitivity = self._config.sensitivities.get("fumble_rate", 0.06)
            clamp = tuple(self._config.clamp)
            fumble_factor = compute_factor(
                all_rates[defense_team],
                league_mean,
                league_std,
                sensitivity,
                clamp,
            )

        # ---------------------------------------------------------------
        # Defensive TD rates (Bayesian shrinkage toward league priors)
        # ---------------------------------------------------------------
        prior = self._config.prior_strength

        if not team_games.is_empty():
            team_ints = int(team_games["interceptions"].sum())
            team_int_tds = int(team_games["interception_touchdowns"].sum())
            team_fum_recs = int(team_games["fumble_recoveries"].sum())
            team_fum_tds = int(team_games["fumble_recovery_touchdowns"].sum())
        else:
            team_ints = team_int_tds = team_fum_recs = team_fum_tds = 0

        # Blend with previous season when current season is early
        if prev_games_df is not None and n_games < self._config.min_games:
            blend_w = n_games / self._config.min_games
            prev_ints = int(prev_games_df["interceptions"].sum())
            prev_int_tds = int(prev_games_df["interception_touchdowns"].sum())
            prev_fum_recs = int(prev_games_df["fumble_recoveries"].sum())
            prev_fum_tds = int(prev_games_df["fumble_recovery_touchdowns"].sum())

            team_ints = round(team_ints * blend_w + prev_ints * (1 - blend_w))
            team_int_tds = round(team_int_tds * blend_w + prev_int_tds * (1 - blend_w))
            team_fum_recs = round(team_fum_recs * blend_w + prev_fum_recs * (1 - blend_w))
            team_fum_tds = round(team_fum_tds * blend_w + prev_fum_tds * (1 - blend_w))

        denom_int = team_ints + prior
        int_td_rate = (
            (team_int_tds + prior * DEFAULT_INT_RETURN_TD_RATE) / denom_int
            if denom_int > 0
            else DEFAULT_INT_RETURN_TD_RATE
        )

        denom_fum = team_fum_recs + prior
        fum_td_rate = (
            (team_fum_tds + prior * DEFAULT_FUMBLE_RETURN_TD_RATE) / denom_fum
            if denom_fum > 0
            else DEFAULT_FUMBLE_RETURN_TD_RATE
        )

        logger.debug(
            "DstBaseline %s (season=%d, week<%s): ff_factor=%.3f "
            "int_td_rate=%.3f fum_td_rate=%.3f",
            defense_team,
            target_season,
            max_week,
            fumble_factor,
            float(int_td_rate),
            float(fum_td_rate),
        )

        return DstBaselineContext(
            fumble_rate_factor=fumble_factor,
            int_return_td_rate=float(int_td_rate),
            fumble_return_td_rate=float(fum_td_rate),
        )
