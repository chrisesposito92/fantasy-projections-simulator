"""PropsLoader: reads PFF player props from pre-cached parquet files.

VEG-03 implementation (D-11/D-12). Cache files are created by
scripts/scrape_pff_props.py. This loader never makes HTTP calls --
it only reads from the local filesystem.

Gracefully returns empty DataFrame when cache file is missing (D-00/D-15),
enabling safe backtest operation without props data.
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from fantasy_sim.data.vegas.models import PropsConfig

logger = logging.getLogger(__name__)

# Mapping from PFF prop_key values to PlayerPropsEngine market keys.
# Used by PlayerPropsEngine to translate PFF-format props into the
# existing market dispatch methods.
PFF_TO_ENGINE_MARKET: dict[str, str] = {
    "recv_yd": "player_reception_yds",
    "recv_rec": "player_receptions",
    "rush_yd": "player_rush_yds",
    "rush_td": "player_rush_tds",
    "pass_yd": "player_pass_yds",
    "pass_td": "player_pass_tds",
    "pass_att": "player_pass_attempts",
    "rush_att": "player_rush_attempts",
    "anytime_td": "player_anytime_td",
}


class PropsLoader:
    """Read PFF player props from pre-cached parquet files.

    Cache files are created by scripts/scrape_pff_props.py. This loader
    never makes HTTP calls -- it only reads from the local filesystem.
    Gracefully returns empty DataFrame when cache file is missing (D-00/D-15).

    Args:
        config: PropsConfig with enabled flag, prior_strength, etc.
        cache_dir: Override cache directory (for testing). If None, uses
            config.cache_dir or ~/.fantasy-sim/pff/props/.
    """

    def __init__(
        self,
        config: PropsConfig,
        cache_dir: Path | None = None,
    ) -> None:
        self.config = config

        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        elif config.cache_dir:
            self.cache_dir = Path(config.cache_dir)
        else:
            self.cache_dir = Path.home() / ".fantasy-sim" / "pff" / "props"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_props(self, season: int, week: int) -> pl.DataFrame:
        """Load props for (season, week) from PFF parquet cache.

        Returns DataFrame with columns: player_id, prop_key, consensus_line,
        first_name, last_name, team_id, position, season, week.
        Returns empty DataFrame if cache file missing or config disabled.

        Args:
            season: NFL season year (e.g. 2024).
            week: NFL week number (1-18).

        Returns:
            DataFrame with PFF props data, or empty DataFrame on any failure.
        """
        if not self.config.enabled:
            return self._empty_df()

        cache_path = self.cache_dir / f"props_{season}_week{week:02d}.parquet"
        if not cache_path.exists():
            logger.debug(
                "No PFF props cache for %d week %d at %s", season, week, cache_path
            )
            return self._empty_df()

        logger.debug("PFF props cache hit: %s", cache_path)
        return pl.read_parquet(cache_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_df() -> pl.DataFrame:
        """Return an empty DataFrame with the expected PFF parquet schema."""
        return pl.DataFrame(schema={
            "player_id": pl.Int64,
            "first_name": pl.Utf8,
            "last_name": pl.Utf8,
            "team_id": pl.Int64,
            "position": pl.Utf8,
            "prop_key": pl.Utf8,
            "consensus_line": pl.Float64,
            "season": pl.Int64,
            "week": pl.Int64,
            "projections_json": pl.Utf8,
            "averages_json": pl.Utf8,
            "matchup_json": pl.Utf8,
            "last_ten_json": pl.Utf8,
            "option_json": pl.Utf8,
        })
