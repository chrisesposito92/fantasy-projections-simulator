"""Team context engine — computes season-level team environment factors.

Uses PBP pass rate and PFF OL/QB data to produce TeamContext factors
that adjust tier distribution blending based on team-level characteristics.
"""

from __future__ import annotations

import logging

import numpy as np
import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.matchup import compute_factor
from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig

logger = logging.getLogger(__name__)


class TeamContextEngine:
    """Computes season-level team context factors from PBP and PFF data.

    Three factors:
    - pass_rate_factor: how pass-heavy a team is vs league average
    - ol_run_block_factor: offensive line run blocking quality
    - qb_quality_factor: starting QB grade quality

    All factors are centered on 1.0 (neutral). Returns TeamContext.
    """

    def __init__(self, config: TeamContextConfig, pff_loader: PffLoader):
        self._config = config
        self._loader = pff_loader
        self._cache: dict[str, pl.DataFrame] = {}

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cached(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        """Load a PFF facet with caching by facet + seasons."""
        key = f"{facet}_{'_'.join(str(s) for s in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(facet, seasons)
        return self._cache[key]

    # ------------------------------------------------------------------
    # Shared utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def _count_team_games(df: pl.DataFrame, team: str) -> int:
        """Count distinct games for a team in a DataFrame."""
        if df.is_empty():
            return 0
        if "team" not in df.columns:
            return 0
        team_rows = df.filter(pl.col("team") == team)
        if team_rows.is_empty():
            return 0
        if "game_id" in team_rows.columns:
            return team_rows.select(pl.col("game_id").n_unique()).item()
        elif "week" in team_rows.columns:
            return team_rows.select(pl.col("week").n_unique()).item()
        return team_rows.height

    @staticmethod
    def _snap_weighted_factor(
        df: pl.DataFrame,
        team: str,
        grade_col: str,
        snap_col: str,
        sensitivity: float,
        clamp: tuple[float, float],
    ) -> float | None:
        """Compute snap-weighted team average → league z-score → factor.

        Returns None if there is no data to compute from.
        """
        required = {"team", grade_col, snap_col}
        if df.is_empty() or not required.issubset(df.columns):
            return None

        valid = df.filter(
            pl.col(grade_col).is_not_null() & pl.col(snap_col).is_not_null()
        )
        if valid.is_empty():
            return None

        # Snap-weighted average per team
        team_avgs = (
            valid.group_by("team")
            .agg(
                (
                    (pl.col(grade_col) * pl.col(snap_col)).sum()
                    / pl.col(snap_col).sum()
                ).alias("snap_weighted_avg")
            )
        )

        if team_avgs.is_empty():
            return None

        # League mean/std across teams
        avgs = team_avgs["snap_weighted_avg"].to_list()
        if len(avgs) < 2:
            return None

        league_avg = float(np.mean(avgs))
        league_std = float(np.std(avgs, ddof=1))

        # Look up this team
        team_row = team_avgs.filter(pl.col("team") == team)
        if team_row.is_empty():
            return None

        team_val = team_row["snap_weighted_avg"].item()
        if team_val is None:
            return None

        return compute_factor(float(team_val), league_avg, league_std, sensitivity, clamp)

    # ------------------------------------------------------------------
    # Pass rate factor
    # ------------------------------------------------------------------

    def _pass_rate_from_pbp(self, plays: pl.DataFrame, team: str) -> float | None:
        """Compute per-team pass rate z-score factor from filtered PBP plays.

        Returns None when data is insufficient.
        """
        if plays.is_empty():
            return None

        required = {"play_type", "posteam"}
        if not required.issubset(plays.columns):
            return None

        relevant = plays.filter(pl.col("play_type").is_in(["pass", "run"]))
        if relevant.is_empty():
            return None

        # Per-team pass rate
        team_rates = (
            relevant.group_by("posteam")
            .agg(
                (
                    (pl.col("play_type") == "pass").sum().cast(pl.Float64)
                    / pl.len()
                ).alias("pass_rate")
            )
        )

        if team_rates.is_empty():
            return None

        rates = team_rates["pass_rate"].to_list()
        if len(rates) < 2:
            return None

        league_avg = float(np.mean(rates))
        league_std = float(np.std(rates, ddof=1))

        team_row = team_rates.filter(pl.col("posteam") == team)
        if team_row.is_empty():
            return None

        team_val = team_row["pass_rate"].item()
        if team_val is None:
            return None

        return compute_factor(
            float(team_val),
            league_avg,
            league_std,
            self._config.pass_rate_sensitivity,
            self._config.factor_clamp,
        )

    def _count_pbp_games(self, pbp: pl.DataFrame, team: str, season: int) -> int:
        """Count distinct games for a team in a specific season of PBP data.

        Uses week as the primary uniqueness key (PBP data is already pre-filtered
        to a season window, and game_id may collide across separate concat frames).
        """
        if pbp.is_empty():
            return 0
        cols = pbp.columns
        if "posteam" not in cols or "season" not in cols:
            return 0
        team_rows = pbp.filter(
            (pl.col("posteam") == team) & (pl.col("season") == season)
        )
        if team_rows.is_empty():
            return 0
        # Prefer week (always distinct across games in PBP) over game_id
        # which may collide when frames are concatenated from separate _make_pbp calls.
        if "week" in cols:
            return team_rows.select(pl.col("week").n_unique()).item()
        elif "game_id" in cols:
            return team_rows.select(pl.col("game_id").n_unique()).item()
        return team_rows.height

    def _compute_pass_rate_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
        pbp: pl.DataFrame | None,
    ) -> float:
        """Compute the pass rate factor for a team from PBP data.

        Uses same-season rolling window (week < max_week). Blends with
        previous season when the team has fewer than min_games games.

        Returns 1.0 for missing/empty data or team not found.
        """
        if pbp is None or pbp.is_empty():
            return 1.0

        # Current season: filter to target_season and week < max_week
        cols = pbp.columns
        if "season" in cols and "week" in cols:
            current_plays = pbp.filter(
                (pl.col("season") == target_season) & (pl.col("week") < max_week)
            )
        elif "season" in cols:
            current_plays = pbp.filter(pl.col("season") == target_season)
        else:
            # No season column — treat the whole frame as current
            current_plays = pbp

        current_factor = self._pass_rate_from_pbp(current_plays, team)

        # Count current season games for this team
        current_games = self._count_pbp_games(current_plays, team, target_season) if "season" in cols else 0

        if current_games >= self._config.min_games:
            return current_factor if current_factor is not None else 1.0

        # Early-season blend: look for previous season data in the same pbp frame
        if "season" in cols:
            prev_plays = pbp.filter(pl.col("season") == target_season - 1)
        else:
            prev_plays = pl.DataFrame()

        prev_factor = self._pass_rate_from_pbp(prev_plays, team)
        if prev_factor is None:
            # No previous season data — return what we have from current
            return current_factor if current_factor is not None else 1.0

        # Linear ramp blend: weight = current_games / min_games
        blend_weight = current_games / self._config.min_games
        curr = current_factor if current_factor is not None else 1.0
        return blend_weight * curr + (1.0 - blend_weight) * prev_factor

    # ------------------------------------------------------------------
    # OL run blocking factor
    # ------------------------------------------------------------------

    def _compute_ol_run_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
    ) -> float:
        """Compute the OL run blocking factor from PFF offense_run_blocking data.

        Returns 1.0 for missing data or team not found.
        """
        current_df = self._load_cached("offense_run_blocking", [target_season])
        if not current_df.is_empty() and "week" in current_df.columns:
            current_df = current_df.filter(pl.col("week") < max_week)

        current_games = self._count_team_games(current_df, team)
        current_factor = self._snap_weighted_factor(
            current_df,
            team,
            "grades_run_block",
            "snap_counts_run_block",
            self._config.ol_run_sensitivity,
            self._config.factor_clamp,
        )

        if current_games >= self._config.min_games:
            return current_factor if current_factor is not None else 1.0

        # Early-season blend with previous season
        prev_df = self._load_cached("offense_run_blocking", [target_season - 1])
        prev_factor = self._snap_weighted_factor(
            prev_df,
            team,
            "grades_run_block",
            "snap_counts_run_block",
            self._config.ol_run_sensitivity,
            self._config.factor_clamp,
        )

        if prev_factor is None:
            return current_factor if current_factor is not None else 1.0

        blend_weight = current_games / self._config.min_games
        curr = current_factor if current_factor is not None else 1.0
        return blend_weight * curr + (1.0 - blend_weight) * prev_factor

    # ------------------------------------------------------------------
    # QB quality factor
    # ------------------------------------------------------------------

    def _compute_qb_quality_factor(
        self,
        team: str,
        target_season: int,
        max_week: int,
    ) -> float:
        """Compute the QB quality factor from PFF passing_summary data.

        Returns 1.0 for missing data or team not found.
        """
        current_df = self._load_cached("passing_summary", [target_season])
        if not current_df.is_empty() and "week" in current_df.columns:
            current_df = current_df.filter(pl.col("week") < max_week)

        current_games = self._count_team_games(current_df, team)
        current_factor = self._snap_weighted_factor(
            current_df,
            team,
            "grades_pass",
            "passing_snaps",
            self._config.qb_quality_sensitivity,
            self._config.factor_clamp,
        )

        if current_games >= self._config.min_games:
            return current_factor if current_factor is not None else 1.0

        # Early-season blend with previous season
        prev_df = self._load_cached("passing_summary", [target_season - 1])
        prev_factor = self._snap_weighted_factor(
            prev_df,
            team,
            "grades_pass",
            "passing_snaps",
            self._config.qb_quality_sensitivity,
            self._config.factor_clamp,
        )

        if prev_factor is None:
            return current_factor if current_factor is not None else 1.0

        blend_weight = current_games / self._config.min_games
        curr = current_factor if current_factor is not None else 1.0
        return blend_weight * curr + (1.0 - blend_weight) * prev_factor

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def compute(
        self,
        team: str,
        target_season: int,
        max_week: int,
        pbp: pl.DataFrame | None = None,
    ) -> TeamContext:
        """Compute all team context factors and return a TeamContext.

        Args:
            team: Team abbreviation (e.g. "KC").
            target_season: The season being simulated.
            max_week: Data is filtered to week < max_week.
            pbp: Play-by-play DataFrame (needed for pass rate factor).

        Returns:
            TeamContext with all factors populated (neutral 1.0 when disabled).
        """
        if not self._config.enabled:
            return TeamContext(ol_run_yards_scale=self._config.ol_run_yards_scale)

        pass_rate = self._compute_pass_rate_factor(team, target_season, max_week, pbp)
        ol_run = self._compute_ol_run_factor(team, target_season, max_week)
        qb_quality = self._compute_qb_quality_factor(team, target_season, max_week)

        logger.info(
            "TeamContext factors: %s (season=%d, week<%d) → "
            "pass_rate=%.3f ol_run=%.3f qb_quality=%.3f",
            team,
            target_season,
            max_week,
            pass_rate,
            ol_run,
            qb_quality,
        )

        return TeamContext(
            pass_rate_factor=pass_rate,
            ol_run_block_factor=ol_run,
            qb_quality_factor=qb_quality,
            ol_run_yards_scale=self._config.ol_run_yards_scale,
        )
