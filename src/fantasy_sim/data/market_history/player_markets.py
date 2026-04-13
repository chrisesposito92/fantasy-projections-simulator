from __future__ import annotations

import json
from pathlib import Path

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.market_history.events_inventory import DEFAULT_MARKET_HISTORY_DIR
from fantasy_sim.data.vegas.crosswalk import standardize_name

DEFAULT_MARKET_HISTORY_RAW_PROPS_DIR = DEFAULT_MARKET_HISTORY_DIR / "raw" / "props"
DEFAULT_PLAYER_MARKETS_PROCESSED_DIR = DEFAULT_MARKET_HISTORY_DIR / "processed"

PLAYER_MARKET_SIGNAL_SCHEMA: SchemaDict = {
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


def decimal_price_to_implied_prob(price: float | None) -> float | None:
    """Convert decimal odds to implied probability."""
    if price is None or price <= 0:
        return None
    return 1.0 / price


def raw_signal_path(
    season: int,
    snapshot_label: str,
    *,
    processed_dir: Path | None = None,
) -> Path:
    base_dir = Path(processed_dir or DEFAULT_PLAYER_MARKETS_PROCESSED_DIR)
    return base_dir / f"player_markets_{season}_{snapshot_label}.parquet"


def _empty_player_markets() -> pl.DataFrame:
    return pl.DataFrame(schema=PLAYER_MARKET_SIGNAL_SCHEMA)


def flatten_props_snapshot(record: dict) -> pl.DataFrame:
    """Flatten one cached event props snapshot into bookmaker-level rows."""
    payload_data = record.get("payload", {}).get("data", {})
    rows: list[dict[str, object]] = []

    for bookmaker in payload_data.get("bookmakers", []):
        bookmaker_key = bookmaker.get("key")
        for market in bookmaker.get("markets", []):
            market_key = market.get("key")
            for outcome in market.get("outcomes", []):
                player_name = str(outcome.get("description") or "")
                rows.append(
                    {
                        "season": int(record["season"]),
                        "week": int(record["week"]),
                        "event_id": str(record["event_id"]),
                        "schedule_game_id": (
                            str(record["schedule_game_id"])
                            if record.get("schedule_game_id") is not None
                            else None
                        ),
                        "snapshot_label": str(record["snapshot_label"]),
                        "snapshot_timestamp": str(record["snapshot_timestamp"]),
                        "market_key": str(market_key),
                        "player_name": player_name,
                        "player_name_normalized": standardize_name(player_name),
                        "home_team": payload_data.get("home_team"),
                        "away_team": payload_data.get("away_team"),
                        "bookmaker_key": bookmaker_key,
                        "outcome_name": outcome.get("name"),
                        "point": outcome.get("point"),
                        "price": outcome.get("price"),
                    }
                )

    if not rows:
        return pl.DataFrame(
            schema={
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
                "bookmaker_key": pl.Utf8,
                "outcome_name": pl.Utf8,
                "point": pl.Float64,
                "price": pl.Float64,
            }
        )

    return pl.DataFrame(rows).with_columns(
        [
            pl.col("season").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            pl.col("event_id").cast(pl.Utf8),
            pl.col("schedule_game_id").cast(pl.Utf8),
            pl.col("snapshot_label").cast(pl.Utf8),
            pl.col("snapshot_timestamp").cast(pl.Utf8),
            pl.col("market_key").cast(pl.Utf8),
            pl.col("player_name").cast(pl.Utf8),
            pl.col("player_name_normalized").cast(pl.Utf8),
            pl.col("home_team").cast(pl.Utf8),
            pl.col("away_team").cast(pl.Utf8),
            pl.col("bookmaker_key").cast(pl.Utf8),
            pl.col("outcome_name").cast(pl.Utf8),
            pl.col("point").cast(pl.Float64),
            pl.col("price").cast(pl.Float64),
        ]
    )


def aggregate_props_snapshot(record: dict) -> pl.DataFrame:
    """Aggregate bookmaker-level outcomes into player-week market-native signals."""
    flat = flatten_props_snapshot(record)
    if flat.is_empty():
        return _empty_player_markets()

    grouping = [
        "season",
        "week",
        "event_id",
        "schedule_game_id",
        "snapshot_label",
        "snapshot_timestamp",
        "market_key",
        "player_name",
        "player_name_normalized",
        "home_team",
        "away_team",
    ]

    grouped = flat.group_by(grouping).agg(
        [
            pl.col("bookmaker_key").n_unique().alias("bookmaker_count"),
            pl.col("point").median().alias("line"),
            pl.col("point").std().alias("line_stddev"),
            pl.when(pl.col("outcome_name") == "Over")
            .then(pl.col("price"))
            .otherwise(None)
            .median()
            .alias("over_price"),
            pl.when(pl.col("outcome_name") == "Under")
            .then(pl.col("price"))
            .otherwise(None)
            .median()
            .alias("under_price"),
            pl.when(pl.col("outcome_name") == "Yes")
            .then(pl.col("price"))
            .otherwise(None)
            .median()
            .alias("yes_price"),
        ]
    )

    return grouped.with_columns(
        pl.col("yes_price")
        .map_elements(decimal_price_to_implied_prob, return_dtype=pl.Float64)
        .alias("implied_prob")
    ).select(
        [
            pl.col(column).cast(dtype).alias(column)
            for column, dtype in PLAYER_MARKET_SIGNAL_SCHEMA.items()
        ]
    )


def build_player_market_signals_for_season(
    season: int,
    *,
    snapshot_label: str,
    raw_props_dir: Path | None = None,
    processed_dir: Path | None = None,
) -> Path:
    """Build one season parquet of market-native player-week signals from raw props JSON."""
    base_dir = Path(raw_props_dir or DEFAULT_MARKET_HISTORY_RAW_PROPS_DIR) / str(season) / snapshot_label
    frames: list[pl.DataFrame] = []

    for path in sorted(base_dir.glob("*.json")):
        record = json.loads(path.read_text())
        frames.append(aggregate_props_snapshot(record))

    if frames:
        combined = (
            pl.concat(frames, how="diagonal_relaxed")
            .unique(
                subset=[
                    "season",
                    "week",
                    "event_id",
                    "snapshot_label",
                    "market_key",
                    "player_name_normalized",
                ],
                keep="first",
            )
            .sort(
                [
                    "week",
                    "event_id",
                    "market_key",
                    "player_name_normalized",
                ]
            )
        )
    else:
        combined = _empty_player_markets()

    output_path = raw_signal_path(season, snapshot_label, processed_dir=processed_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.write_parquet(output_path)
    return output_path
