from __future__ import annotations

from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.loader import (
    DEFAULT_MARKET_HISTORY_PROCESSED_DIR,
    PROCESSED_WEEKLY_SCHEMA,
    ensure_processed_weekly_schema,
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
