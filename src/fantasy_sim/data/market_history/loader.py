from __future__ import annotations

from pathlib import Path

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.market_history.models import MarketHistoryConfig

DEFAULT_MARKET_HISTORY_PROCESSED_DIR = (
    Path.home() / ".fantasy-sim" / "market-history" / "processed"
)

PROCESSED_WEEKLY_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "player_id": pl.Utf8,
    "full_name": pl.Utf8,
    "position": pl.Utf8,
    "team": pl.Utf8,
    "open_fpts": pl.Float64,
    "close_fpts": pl.Float64,
    "books": pl.Int64,
    "line_stddev": pl.Float64,
    "anytime_td_prob": pl.Float64,
}

REQUIRED_PROCESSED_WEEKLY_COLUMNS: tuple[str, ...] = (
    "season",
    "week",
    "player_id",
    "full_name",
    "position",
    "team",
    "open_fpts",
    "close_fpts",
    "books",
)


class MarketHistoryLoader:
    """Load processed historical market snapshots from per-season parquet."""

    def __init__(
        self,
        config: MarketHistoryConfig | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.config = config or MarketHistoryConfig()
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        elif self.config.data_dir:
            self.data_dir = Path(self.config.data_dir)
        else:
            self.data_dir = DEFAULT_MARKET_HISTORY_PROCESSED_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = self.data_dir / f"market_history_weekly_{season}.parquet"
            if path.exists():
                frames.append(ensure_processed_weekly_schema(pl.read_parquet(path)))
        if not frames:
            return pl.DataFrame(schema=PROCESSED_WEEKLY_SCHEMA)
        return pl.concat(frames, how="diagonal_relaxed")


def ensure_processed_weekly_schema(frame: pl.DataFrame) -> pl.DataFrame:
    """Backfill optional columns and cast processed weekly frames to the canonical schema."""
    missing_required = [
        column
        for column in REQUIRED_PROCESSED_WEEKLY_COLUMNS
        if column not in frame.columns
    ]
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(
            f"Processed market history is missing required columns: {missing}"
        )

    missing_optional = [
        pl.lit(None, dtype=dtype).alias(column)
        for column, dtype in PROCESSED_WEEKLY_SCHEMA.items()
        if column not in frame.columns
    ]
    if missing_optional:
        frame = frame.with_columns(missing_optional)

    return frame.select(
        [
            pl.col(column).cast(dtype).alias(column)
            for column, dtype in PROCESSED_WEEKLY_SCHEMA.items()
        ]
    )
