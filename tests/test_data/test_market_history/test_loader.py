from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.loader import (
    MARKET_HISTORY_SIGNAL_SCHEMA,
    MarketHistoryLoader,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig


def _raw_player_markets(season: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [season, season, season],
            "week": [1, 1, 1],
            "event_id": ["event-1", "event-1", "event-1"],
            "schedule_game_id": [
                "2024_01_ARI_BUF",
                "2024_01_ARI_BUF",
                "2024_01_ARI_BUF",
            ],
            "snapshot_label": ["close_core8", "close_core8", "close_core8"],
            "snapshot_timestamp": [
                "2024-09-08T17:00:00Z",
                "2024-09-08T17:00:00Z",
                "2024-09-08T17:00:00Z",
            ],
            "market_key": [
                "player_pass_yds",
                "player_rush_yds",
                "player_pass_yds",
            ],
            "player_name": ["Josh Allen", "James Cook", "Unknown Player"],
            "player_name_normalized": ["josh allen", "james cook", "unknown player"],
            "home_team": ["Buffalo Bills", "Buffalo Bills", "Buffalo Bills"],
            "away_team": ["Arizona Cardinals", "Arizona Cardinals", "Arizona Cardinals"],
            "bookmaker_count": [3, 3, 2],
            "line": [255.5, 65.5, 199.5],
            "line_stddev": [0.0, 0.5, 0.0],
            "over_price": [1.90, 1.88, 1.95],
            "under_price": [1.90, 1.92, 1.85],
            "yes_price": [None, None, None],
            "implied_prob": [None, None, None],
        }
    )


def _rosters() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 1],
            "player_id": ["BUF-QB1", "BUF-RB1"],
            "player_name": ["Josh Allen", "James Cook"],
            "position": ["QB", "RB"],
            "team": ["BUF", "BUF"],
        }
    )


def test_loader_resolves_market_players_to_nflverse_ids(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _raw_player_markets(2024).write_parquet(
        processed / "player_markets_2024_close_core8.parquet"
    )
    roster_loader = MagicMock(spec=DataLoader)
    roster_loader.load_rosters.return_value = _rosters()

    loader = MarketHistoryLoader(
        MarketHistoryConfig(
            enabled=True,
            data_dir=str(processed),
            snapshot_label="close_core8",
        ),
        roster_loader=roster_loader,
    )

    frame = loader.load_weekly([2024]).sort(["player_id", "market_key"])

    assert frame.schema == MARKET_HISTORY_SIGNAL_SCHEMA
    assert frame["player_id"].to_list() == ["BUF-QB1", "BUF-RB1"]
    assert frame["full_name"].to_list() == ["Josh Allen", "James Cook"]
    assert frame["position"].to_list() == ["QB", "RB"]
    assert frame["team"].to_list() == ["BUF", "BUF"]
    assert "Unknown Player" not in frame["player_name"].to_list()


def test_loader_returns_empty_signal_schema_when_season_file_is_missing(tmp_path):
    loader = MarketHistoryLoader(
        MarketHistoryConfig(
            enabled=True,
            data_dir=str(tmp_path),
            snapshot_label="close_core8",
        ),
        roster_loader=MagicMock(spec=DataLoader),
    )

    frame = loader.load_weekly([2024])

    assert frame.schema == MARKET_HISTORY_SIGNAL_SCHEMA
    assert frame.is_empty()


def test_loader_reads_multiple_seasons_from_player_market_store(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _raw_player_markets(2023).with_columns(
        pl.lit("2023_01_ARI_BUF").alias("schedule_game_id")
    ).write_parquet(processed / "player_markets_2023_close_core8.parquet")
    _raw_player_markets(2024).write_parquet(
        processed / "player_markets_2024_close_core8.parquet"
    )
    roster_loader = MagicMock(spec=DataLoader)
    roster_loader.load_rosters.side_effect = [
        _rosters().with_columns(pl.lit(2023).alias("season")),
        _rosters(),
    ]

    loader = MarketHistoryLoader(
        MarketHistoryConfig(
            enabled=True,
            data_dir=str(processed),
            snapshot_label="close_core8",
        ),
        roster_loader=roster_loader,
    )
    frame = loader.load_weekly([2023, 2024]).sort(["season", "player_id", "market_key"])

    assert frame["season"].unique().to_list() == [2023, 2024]
    assert frame.height == 4
