from pathlib import Path
import polars as pl
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.preprocessor import Preprocessor


class DataPipeline:
    """Orchestrates data loading and preprocessing into distributions."""

    def __init__(self, cache_dir: Path, seasons: list[int]):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.seasons = seasons
        self.loader = DataLoader(cache_dir=self.cache_dir)
        self.preprocessor = Preprocessor()

    def build(
        self,
        pbp: pl.DataFrame | None = None,
        fg_data: pl.DataFrame | None = None,
        kickoff_data: pl.DataFrame | None = None,
        season_weights: dict[int, float] | None = None,
    ) -> dict:
        """Build all distributions from raw data.

        Pass dataframes directly for testing, or leave None to load from nflreadpy.
        Pass season_weights to give more influence to recent seasons, e.g.
        {2022: 0.2, 2023: 0.3, 2024: 0.5}.
        """
        if pbp is None:
            pbp = self.loader.load_pbp(self.seasons)
        if fg_data is None:
            fg_data = pbp.filter(pl.col("play_type") == "field_goal")
        if kickoff_data is None:
            kickoff_data = pbp.filter(pl.col("play_type") == "kickoff")
        xp_data = pbp.filter(pl.col("play_type") == "extra_point")

        return {
            "play_calling": self.preprocessor.compute_play_calling(pbp, season_weights=season_weights),
            "play_outcomes": self.preprocessor.compute_play_outcomes(pbp, season_weights=season_weights),
            "turnover_rates": self.preprocessor.compute_turnover_rates(pbp, season_weights=season_weights),
            "kicking": self.preprocessor.compute_kicking_model(fg_data, xp_data=xp_data),
            "drive_start": self.preprocessor.compute_drive_start_model(kickoff_data),
            "penalty_rates": self.preprocessor.compute_penalty_rates(pbp),
        }
