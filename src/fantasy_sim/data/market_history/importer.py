from __future__ import annotations

from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.loader import (
    DEFAULT_MARKET_HISTORY_PROCESSED_DIR,
    PROCESSED_WEEKLY_SCHEMA,
)

DEFAULT_MARKET_HISTORY_RAW_DIR = Path.home() / ".fantasy-sim" / "market-history" / "raw"


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
        frame = pl.read_parquet(path).select(list(PROCESSED_WEEKLY_SCHEMA))
        frame = frame.with_columns(
            [
                pl.col("season").cast(pl.Int64),
                pl.col("week").cast(pl.Int64),
                pl.col("player_id").cast(pl.Utf8),
                pl.col("full_name").cast(pl.Utf8),
                pl.col("position").cast(pl.Utf8),
                pl.col("team").cast(pl.Utf8),
                pl.col("open_fpts").cast(pl.Float64),
                pl.col("close_fpts").cast(pl.Float64),
                pl.col("books").cast(pl.Int64),
                pl.col("line_stddev").cast(pl.Float64),
                pl.col("anytime_td_prob").cast(pl.Float64),
            ]
        ).unique(subset=["season", "week", "player_id"], keep="last")
        frames.append(frame)

    processed_root.mkdir(parents=True, exist_ok=True)
    if frames:
        combined = pl.concat(frames, how="diagonal_relaxed").sort(
            ["season", "week", "player_id"]
        )
    else:
        combined = pl.DataFrame(schema=PROCESSED_WEEKLY_SCHEMA)
    combined.write_parquet(output_path)
    return output_path
