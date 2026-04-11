"""Loader for cached Fantasy Football Opportunity weekly data."""

from __future__ import annotations

from pathlib import Path

import nflreadpy
import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig
from fantasy_sim.data.loader import DEFAULT_CACHE_DIR


class FfOpportunityLoader:
    """Load FF Opportunity weekly data with per-season parquet caching."""

    def __init__(
        self,
        config: FfOpportunityConfig | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.config = config or FfOpportunityConfig()

        if cache_dir is not None:
            self.cache_dir = Path(cache_dir)
        elif self.config.cache_dir:
            self.cache_dir = Path(self.config.cache_dir)
        else:
            self.cache_dir = DEFAULT_CACHE_DIR

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        """Load FF Opportunity weekly data for the requested seasons."""
        frames: list[pl.DataFrame] = []

        for season in seasons:
            cache_path = self.cache_dir / f"ff_opportunity_weekly_{season}.parquet"
            if cache_path.exists():
                frames.append(pl.read_parquet(cache_path))
                continue

            frame = nflreadpy.load_ff_opportunity(
                seasons=[season],
                stat_type="weekly",
            )
            frame.write_parquet(cache_path)
            frames.append(frame)

        if not frames:
            return pl.DataFrame()

        return pl.concat(frames, how="diagonal_relaxed")
