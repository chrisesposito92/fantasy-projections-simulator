"""Matchup engine — converts PFF defensive/OL data into per-game adjustment factors.

Uses z-score normalization to convert team-level PFF stats into factors
centered on 1.0 that shift simulation parameters (catch rate, sack rate, etc.).
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import MatchupConfig, MatchupContext, PffConfig

logger = logging.getLogger(__name__)


def compute_factor(
    team_value: float,
    league_avg: float,
    league_std: float,
    sensitivity: float,
    clamp: tuple[float, float],
) -> float:
    """Convert a team stat to a multiplicative factor via z-score.

    Args:
        team_value: The team's stat value.
        league_avg: League-wide mean of the stat (across teams).
        league_std: League-wide standard deviation of the stat.
        sensitivity: How much a 1-sigma deviation shifts the factor.
        clamp: (min, max) bounds for the returned factor.

    Returns:
        Factor centered on 1.0. Above 1.0 = above-average stat,
        below 1.0 = below-average stat.
    """
    if league_std <= 0:
        return 1.0
    z = (team_value - league_avg) / league_std
    factor = 1.0 + z * sensitivity
    return max(clamp[0], min(clamp[1], factor))


# ---------- Factor specification ----------

# Each entry maps a MatchupContext field to:
#   facet: PFF facet to load
#   primary_stat: preferred column for z-score
#   grade_fallback: backup column (PFF grade, 0-100 scale)
#   sensitivity_key: which MatchupConfig sensitivity to use
#   inverted: True if higher stat = worse for the opposing offense
#   team_col: "defense" or "offense" — which side the stat belongs to

_FACTOR_SPECS: list[dict] = [
    {
        "field": "catch_rate_factor",
        "facet": "defense_coverage",
        "primary_stat": "catch_rate",
        "grade_fallback": "grades_coverage_defense",
        "sensitivity_key": "pass_defense_sensitivity",
        "inverted": False,
        "team_side": "defense",
    },
    {
        "field": "pass_yards_factor",
        "facet": "defense_coverage",
        "primary_stat": "yards_per_reception",
        "grade_fallback": "grades_coverage_defense",
        "sensitivity_key": "pass_defense_sensitivity",
        "inverted": False,
        "team_side": "defense",
    },
    {
        "field": "sack_rate_factor",
        "facet": "defense_pass_rush",
        "primary_stat": "pass_rush_win_rate",
        "grade_fallback": "grades_pass_rush_defense",
        "sensitivity_key": "pass_rush_sensitivity",
        "inverted": False,
        "team_side": "defense",
    },
    {
        "field": "int_rate_factor",
        "facet": "defense_coverage",
        "primary_stat": "interceptions",
        "grade_fallback": "grades_coverage_defense",
        "sensitivity_key": "int_rate_sensitivity",
        "inverted": False,
        "team_side": "defense",
    },
    {
        "field": "rush_yards_factor",
        "facet": "defense_run",
        "primary_stat": "stop_percent",
        "grade_fallback": "grades_run_defense",
        "sensitivity_key": "run_defense_sensitivity",
        "inverted": True,
        "team_side": "defense",
    },
    {
        "field": "ol_pass_block_factor",
        "facet": "offense_pass_blocking",
        "primary_stat": "pbe",
        "grade_fallback": "grades_pass_block",
        "sensitivity_key": "ol_pass_sensitivity",
        "inverted": True,
        "team_side": "offense",
    },
    {
        "field": "ol_run_block_factor",
        "facet": "offense_run_blocking",
        "primary_stat": "grades_run_block",
        "grade_fallback": "run_block_percent",
        "sensitivity_key": "ol_run_sensitivity",
        "inverted": False,
        "team_side": "offense",
    },
]

# Grade sensitivity discount factor — grades are on a wider 0-100 scale
# so we reduce sensitivity to avoid oversized swings.
GRADE_SENSITIVITY_DISCOUNT = 0.5


class MatchupEngine:
    """Computes per-game matchup adjustment factors from PFF data.

    Uses defensive stats (coverage, pass rush, run defense) for the
    opposing defense, and OL stats (pass blocking, run blocking) for
    the offense's own line quality.
    """

    def __init__(self, config: PffConfig, pff_loader: PffLoader):
        self._config = config.matchup
        self._loader = pff_loader
        self._cache: dict[str, pl.DataFrame] = {}

    def _load_cached(self, facet: str, seasons: list[int]) -> pl.DataFrame:
        """Load a PFF facet with caching by facet + seasons."""
        key = f"{facet}_{'_'.join(str(s) for s in sorted(seasons))}"
        if key not in self._cache:
            self._cache[key] = self._loader.load_facet(facet, seasons)
        return self._cache[key]

    def _compute_league_stats(
        self, df: pl.DataFrame, stat_col: str
    ) -> tuple[float, float]:
        """Compute league mean and std for a stat, aggregating per-team first.

        Groups by team to get per-team averages, then computes mean/std
        across teams. This prevents teams with more players from dominating.

        Returns:
            (league_mean, league_std) across teams.
        """
        if df.is_empty() or stat_col not in df.columns:
            return 0.0, 0.0

        # Filter out nulls for the stat column
        valid = df.filter(pl.col(stat_col).is_not_null())
        if valid.is_empty():
            return 0.0, 0.0

        # Aggregate per team first
        team_stats = valid.group_by("team").agg(
            pl.col(stat_col).mean().alias("team_mean")
        )

        if team_stats.height < 2:
            # Need at least 2 teams for std
            mean_val = team_stats["team_mean"].mean()
            return float(mean_val) if mean_val is not None else 0.0, 0.0

        league_mean = team_stats["team_mean"].mean()
        league_std = team_stats["team_mean"].std()

        return (
            float(league_mean) if league_mean is not None else 0.0,
            float(league_std) if league_std is not None else 0.0,
        )

    def _get_team_stat(
        self, df: pl.DataFrame, team: str, stat_col: str
    ) -> tuple[float | None, int]:
        """Get a team's average stat value and game count.

        Returns:
            (team_avg, game_count). team_avg is None if team not found.
        """
        if df.is_empty() or stat_col not in df.columns:
            return None, 0

        team_rows = df.filter(pl.col("team") == team)
        if team_rows.is_empty():
            return None, 0

        # Count distinct games for this team
        if "game_id" in team_rows.columns:
            game_count = team_rows.select(pl.col("game_id").n_unique()).item()
        elif "week" in team_rows.columns:
            game_count = team_rows.select(pl.col("week").n_unique()).item()
        else:
            game_count = team_rows.height

        valid = team_rows.filter(pl.col(stat_col).is_not_null())
        if valid.is_empty():
            return None, game_count

        # Team average across all player-game rows
        team_avg = valid.select(pl.col(stat_col).mean()).item()
        return float(team_avg) if team_avg is not None else None, game_count

    def _compute_single_factor(
        self,
        df: pl.DataFrame,
        team: str,
        spec: dict,
        config: MatchupConfig,
    ) -> float:
        """Compute a single MatchupContext factor for a team.

        Tries the primary stat first. Falls back to grade-based factor
        when the primary stat column is missing or the team has fewer
        than min_games games.
        """
        sensitivity = getattr(config, spec["sensitivity_key"])
        clamp = config.factor_clamp

        # Try primary stat
        primary = spec["primary_stat"]
        team_val, game_count = self._get_team_stat(df, team, primary)

        use_fallback = (
            team_val is None
            or primary not in df.columns
            or game_count < config.min_games
        )

        if not use_fallback:
            assert team_val is not None  # guaranteed by use_fallback check
            league_avg, league_std = self._compute_league_stats(df, primary)
            factor = compute_factor(team_val, league_avg, league_std, sensitivity, clamp)
        else:
            # Fallback to grade column with reduced sensitivity
            grade_col = spec["grade_fallback"]
            grade_val, _ = self._get_team_stat(df, team, grade_col)
            if grade_val is None:
                return 1.0  # No data at all — neutral
            league_avg, league_std = self._compute_league_stats(df, grade_col)
            grade_sensitivity = sensitivity * GRADE_SENSITIVITY_DISCOUNT
            factor = compute_factor(
                grade_val, league_avg, league_std, grade_sensitivity, clamp
            )

        # Inverted factors: higher stat = better for that team = worse for opponent
        if spec["inverted"]:
            factor = 2.0 - factor

        return factor

    def compute(
        self,
        defense_team: str,
        offense_team: str,
        training_seasons: list[int],
        season_weights: dict[int, float] | None = None,
    ) -> MatchupContext:
        """Compute matchup adjustment factors for a game.

        Args:
            defense_team: Team abbreviation for the defense (opponent).
            offense_team: Team abbreviation for the offense (own team).
            training_seasons: Seasons to load PFF data from.
            season_weights: Optional season weighting (not used for factor
                computation, reserved for future recency weighting).

        Returns:
            MatchupContext with all factors populated.
        """
        _ = season_weights  # reserved for future recency weighting
        if not self._config.enabled:
            return MatchupContext()

        context = MatchupContext()

        for spec in _FACTOR_SPECS:
            facet = spec["facet"]
            team = defense_team if spec["team_side"] == "defense" else offense_team

            df = self._load_cached(facet, training_seasons)
            if df.is_empty():
                continue  # Factor stays at 1.0

            factor = self._compute_single_factor(df, team, spec, self._config)
            setattr(context, spec["field"], factor)

        logger.info(
            "Matchup factors: %s D vs %s O → catch=%.3f pass_yd=%.3f "
            "sack=%.3f int=%.3f rush_yd=%.3f ol_pass=%.3f ol_run=%.3f",
            defense_team,
            offense_team,
            context.catch_rate_factor,
            context.pass_yards_factor,
            context.sack_rate_factor,
            context.int_rate_factor,
            context.rush_yards_factor,
            context.ol_pass_block_factor,
            context.ol_run_block_factor,
        )

        return context
