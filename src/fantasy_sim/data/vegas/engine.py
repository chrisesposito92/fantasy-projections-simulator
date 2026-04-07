"""VegasEngine — converts Vegas lines into per-team adjustment factors.

VEG-01: Implied team total (ITT) -> volume_factor -> TeamDistributions.pace_factor
VEG-02: Spread -> pass_rate_factor -> PlayCallingDist.default

Sign convention (nflverse): positive spread_line = home team favored.
  home_itt = total_line / 2 + spread_line / 2
  away_itt = total_line / 2 - spread_line / 2

League stats verified on 854 games 2022-2024:
  ITT_LEAGUE_AVG = 21.97
  ITT_LEAGUE_STD = 3.67
  SPREAD_STD     = 5.72
"""

from __future__ import annotations

import logging

import polars as pl

from fantasy_sim.data.pff.matchup import compute_factor
from fantasy_sim.data.vegas.models import VegasConfig, VegasContext

logger = logging.getLogger(__name__)

# Verified league constants (854 games, 2022-2024)
ITT_LEAGUE_AVG: float = 21.97
ITT_LEAGUE_STD: float = 3.67
SPREAD_STD: float = 5.72


def compute_itt(spread_line: float, total_line: float) -> tuple[float, float]:
    """Compute per-team implied totals from Vegas lines.

    Args:
        spread_line: Vegas spread from home team perspective. Positive = home
            favored (nflverse convention).
        total_line: Over/under total for the game.

    Returns:
        (home_itt, away_itt) — implied team totals in points.
    """
    home_itt = total_line / 2.0 + spread_line / 2.0
    away_itt = total_line / 2.0 - spread_line / 2.0
    return home_itt, away_itt


class VegasEngine:
    """Computes per-team Vegas-derived adjustment factors.

    Uses schedule data (spread_line, total_line) to produce VegasContext
    objects for both the home and away team in a game.
    """

    def __init__(self, config: VegasConfig, loader) -> None:
        """Initialise VegasEngine.

        Args:
            config: VegasConfig with sensitivity and clamp parameters.
            loader: DataLoader (or compatible) with load_schedules() method.
        """
        self._config = config
        self._loader = loader

    def compute(
        self,
        home_team: str,
        away_team: str,
        target_season: int,
        week: int,
    ) -> tuple[VegasContext, VegasContext]:
        """Compute Vegas adjustment factors for one game.

        Returns neutral contexts (all factors 1.0) if the game is not found
        in the schedule or if spread/total data is missing.

        Args:
            home_team: Home team abbreviation.
            away_team: Away team abbreviation.
            target_season: NFL season year.
            week: NFL week number.

        Returns:
            (home_ctx, away_ctx) VegasContext objects.
        """
        neutral_home = VegasContext(team=home_team)
        neutral_away = VegasContext(team=away_team)

        # Load schedules for the target season
        schedule_df = self._loader.load_schedules([target_season])

        if schedule_df is None or schedule_df.is_empty():
            logger.debug("Vegas: empty schedule for season %d", target_season)
            return neutral_home, neutral_away

        # Filter to the specific game
        game_rows = schedule_df.filter(
            (pl.col("home_team") == home_team)
            & (pl.col("away_team") == away_team)
            & (pl.col("week") == week)
            & (pl.col("season") == target_season)
        )

        if game_rows.is_empty():
            logger.debug(
                "Vegas: no game found for %s vs %s (season=%d, week=%d)",
                home_team, away_team, target_season, week,
            )
            return neutral_home, neutral_away

        row = game_rows.row(0, named=True)
        spread_line = row.get("spread_line")
        total_line = row.get("total_line")

        if spread_line is None or total_line is None:
            logger.debug(
                "Vegas: missing spread/total for %s vs %s (season=%d, week=%d)",
                home_team, away_team, target_season, week,
            )
            return neutral_home, neutral_away

        config = self._config

        # VEG-01: Compute per-team implied totals -> volume factors
        home_itt, away_itt = compute_itt(float(spread_line), float(total_line))

        home_volume = compute_factor(
            home_itt, ITT_LEAGUE_AVG, ITT_LEAGUE_STD,
            config.itt_sensitivity, config.itt_clamp,
        )
        away_volume = compute_factor(
            away_itt, ITT_LEAGUE_AVG, ITT_LEAGUE_STD,
            config.itt_sensitivity, config.itt_clamp,
        )

        # VEG-02: Spread-derived pass rate factors — inverted z-score (favorites run more)
        # Positive spread_line = home favored -> home_pass uses -spread_line (runs more)
        # Away is underdog  -> away_pass uses +spread_line (passes more)
        home_pass = compute_factor(
            -float(spread_line), 0.0, SPREAD_STD,
            config.spread_sensitivity, config.spread_clamp,
        )
        away_pass = compute_factor(
            float(spread_line), 0.0, SPREAD_STD,
            config.spread_sensitivity, config.spread_clamp,
        )

        home_ctx = VegasContext(
            team=home_team,
            volume_factor=home_volume,
            pass_rate_factor=home_pass,
        )
        away_ctx = VegasContext(
            team=away_team,
            volume_factor=away_volume,
            pass_rate_factor=away_pass,
        )

        logger.info(
            "Vegas factors: %s (home) vs %s (away) spread=%.1f total=%.1f "
            "-> home(vol=%.3f prf=%.3f) away(vol=%.3f prf=%.3f)",
            home_team, away_team, float(spread_line), float(total_line),
            home_volume, home_pass, away_volume, away_pass,
        )

        return home_ctx, away_ctx
