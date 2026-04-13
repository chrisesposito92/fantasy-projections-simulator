from __future__ import annotations

from pathlib import Path

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.market_history.loader import DEFAULT_MARKET_HISTORY_PROCESSED_DIR

DEFAULT_MARKET_HISTORY_RAW_DIR = Path.home() / ".fantasy-sim" / "market-history" / "raw"

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


def ensure_processed_weekly_schema(frame: pl.DataFrame) -> pl.DataFrame:
    """Backfill optional columns and cast legacy processed weekly frames."""
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


def build_market_history_cache(
    season: int,
    *,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
) -> Path:
    """Combine week-level raw snapshots into one processed season parquet."""
    raw_root = Path(raw_dir or DEFAULT_MARKET_HISTORY_RAW_DIR) / str(season)
    processed_root = Path(processed_dir or DEFAULT_MARKET_HISTORY_PROCESSED_DIR)
    output_path = processed_root / f"market_history_weekly_{season}.parquet"

    frames: list[pl.DataFrame] = []
    for path in sorted(raw_root.glob("week*.parquet")):
        frame = ensure_processed_weekly_schema(pl.read_parquet(path))
        frames.append(frame)

    processed_root.mkdir(parents=True, exist_ok=True)
    if frames:
        combined = (
            pl.concat(frames, how="diagonal_relaxed")
            .unique(subset=["season", "week", "player_id"], keep="last")
            .sort(["season", "week", "player_id"])
        )
    else:
        combined = pl.DataFrame(schema=PROCESSED_WEEKLY_SCHEMA)
    combined.write_parquet(output_path)
    return output_path
