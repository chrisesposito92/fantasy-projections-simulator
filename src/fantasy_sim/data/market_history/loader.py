from __future__ import annotations

from pathlib import Path

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.crosswalk import OddsPlayerCrosswalk
from fantasy_sim.data.market_history.models import MarketHistoryConfig

DEFAULT_MARKET_HISTORY_PROCESSED_DIR = (
    Path.home() / ".fantasy-sim" / "market-history" / "processed"
)

PLAYER_MARKET_SOURCE_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "event_id": pl.Utf8,
    "schedule_game_id": pl.Utf8,
    "snapshot_label": pl.Utf8,
    "snapshot_timestamp": pl.Utf8,
    "market_key": pl.Utf8,
    "player_name": pl.Utf8,
    "player_name_normalized": pl.Utf8,
    "home_team": pl.Utf8,
    "away_team": pl.Utf8,
    "bookmaker_count": pl.Int64,
    "line": pl.Float64,
    "line_stddev": pl.Float64,
    "over_price": pl.Float64,
    "under_price": pl.Float64,
    "yes_price": pl.Float64,
    "implied_prob": pl.Float64,
}

MARKET_HISTORY_SIGNAL_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "player_id": pl.Utf8,
    "full_name": pl.Utf8,
    "position": pl.Utf8,
    "team": pl.Utf8,
    "event_id": pl.Utf8,
    "schedule_game_id": pl.Utf8,
    "snapshot_label": pl.Utf8,
    "snapshot_timestamp": pl.Utf8,
    "market_key": pl.Utf8,
    "player_name": pl.Utf8,
    "player_name_normalized": pl.Utf8,
    "home_team": pl.Utf8,
    "away_team": pl.Utf8,
    "bookmaker_count": pl.Int64,
    "line": pl.Float64,
    "line_stddev": pl.Float64,
    "over_price": pl.Float64,
    "under_price": pl.Float64,
    "yes_price": pl.Float64,
    "implied_prob": pl.Float64,
}

REQUIRED_MARKET_SIGNAL_COLUMNS: tuple[str, ...] = (
    *PLAYER_MARKET_SOURCE_SCHEMA.keys(),
)

ESSENTIAL_RESOLVED_SIGNAL_COLUMNS: tuple[str, ...] = (
    "season",
    "week",
    "player_id",
    "full_name",
    "position",
    "team",
    "market_key",
    "bookmaker_count",
    "line",
    "line_stddev",
    "implied_prob",
)


class MarketHistoryLoader:
    """Load resolved historical market signals from per-season player-market parquet."""

    def __init__(
        self,
        config: MarketHistoryConfig | None = None,
        data_dir: Path | None = None,
        roster_loader: DataLoader | None = None,
        crosswalk: OddsPlayerCrosswalk | None = None,
    ) -> None:
        self.config = config or MarketHistoryConfig()
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        elif self.config.data_dir:
            self.data_dir = Path(self.config.data_dir)
        else:
            self.data_dir = DEFAULT_MARKET_HISTORY_PROCESSED_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._roster_loader = roster_loader or DataLoader()
        self._crosswalk = crosswalk or OddsPlayerCrosswalk(loader=self._roster_loader)

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for season in seasons:
            path = self.data_dir / f"player_markets_{season}_{self.config.snapshot_label}.parquet"
            if path.exists():
                raw = ensure_market_history_source_schema(pl.read_parquet(path))
                crosswalk = self._crosswalk.build_for_season(raw, season)
                if crosswalk.is_empty():
                    continue
                frames.append(
                    raw.join(
                        crosswalk,
                        on=[
                            "season",
                            "week",
                            "schedule_game_id",
                            "player_name",
                            "player_name_normalized",
                        ],
                        how="inner",
                    ).select(
                        [
                            pl.col(column).cast(dtype).alias(column)
                            for column, dtype in MARKET_HISTORY_SIGNAL_SCHEMA.items()
                        ]
                    )
                )
        if not frames:
            return pl.DataFrame(schema=MARKET_HISTORY_SIGNAL_SCHEMA)
        return pl.concat(frames, how="diagonal_relaxed")


def ensure_market_history_source_schema(frame: pl.DataFrame) -> pl.DataFrame:
    """Cast player-market source parquet to the canonical raw market schema."""
    missing_required = [
        column
        for column in REQUIRED_MARKET_SIGNAL_COLUMNS
        if column not in frame.columns
    ]
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(
            f"Processed market history is missing required columns: {missing}"
        )

    return frame.select(
        [
            pl.col(column).cast(dtype).alias(column)
            for column, dtype in PLAYER_MARKET_SOURCE_SCHEMA.items()
        ]
    )


def ensure_market_history_signal_schema(frame: pl.DataFrame) -> pl.DataFrame:
    """Backfill optional resolved-signal columns and cast to the canonical schema."""
    missing_required = [
        column
        for column in ESSENTIAL_RESOLVED_SIGNAL_COLUMNS
        if column not in frame.columns
    ]
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(
            f"Resolved market history is missing required columns: {missing}"
        )

    missing_optional = [
        pl.lit(None, dtype=dtype).alias(column)
        for column, dtype in MARKET_HISTORY_SIGNAL_SCHEMA.items()
        if column not in frame.columns
    ]
    if missing_optional:
        frame = frame.with_columns(missing_optional)

    return frame.select(
        [
            pl.col(column).cast(dtype).alias(column)
            for column, dtype in MARKET_HISTORY_SIGNAL_SCHEMA.items()
        ]
    )
