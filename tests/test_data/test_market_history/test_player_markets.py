from __future__ import annotations

import json

import polars as pl

from fantasy_sim.data.market_history.player_markets import (
    PLAYER_MARKET_SIGNAL_SCHEMA,
    aggregate_props_snapshot,
    build_player_market_signals_for_season,
    decimal_price_to_implied_prob,
)


def test_decimal_price_to_implied_prob():
    assert decimal_price_to_implied_prob(2.0) == 0.5
    assert decimal_price_to_implied_prob(None) is None
    assert decimal_price_to_implied_prob(0.0) is None


def _raw_record() -> dict:
    return {
        "season": 2024,
        "week": 1,
        "event_id": "event-1",
        "schedule_game_id": "2024_01_ARI_BUF",
        "snapshot_label": "close_core8",
        "snapshot_timestamp": "2024-09-08T17:00:00Z",
        "payload": {
            "data": {
                "id": "event-1",
                "home_team": "Buffalo Bills",
                "away_team": "Arizona Cardinals",
                "bookmakers": [
                    {
                        "key": "draftkings",
                        "markets": [
                            {
                                "key": "player_pass_yds",
                                "outcomes": [
                                    {
                                        "description": "Josh Allen",
                                        "name": "Over",
                                        "point": 255.5,
                                        "price": 1.90,
                                    },
                                    {
                                        "description": "Josh Allen",
                                        "name": "Under",
                                        "point": 255.5,
                                        "price": 1.90,
                                    },
                                ],
                            },
                            {
                                "key": "player_anytime_td",
                                "outcomes": [
                                    {
                                        "description": "Josh Allen",
                                        "name": "Yes",
                                        "price": 2.50,
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "key": "fanduel",
                        "markets": [
                            {
                                "key": "player_pass_yds",
                                "outcomes": [
                                    {
                                        "description": "Josh Allen",
                                        "name": "Over",
                                        "point": 256.5,
                                        "price": 1.91,
                                    },
                                    {
                                        "description": "Josh Allen",
                                        "name": "Under",
                                        "point": 256.5,
                                        "price": 1.87,
                                    },
                                ],
                            },
                            {
                                "key": "player_anytime_td",
                                "outcomes": [
                                    {
                                        "description": "Josh Allen",
                                        "name": "Yes",
                                        "price": 2.40,
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        },
    }


def test_aggregate_props_snapshot_builds_market_native_rows():
    frame = aggregate_props_snapshot(_raw_record()).sort("market_key")

    assert frame.schema == PLAYER_MARKET_SIGNAL_SCHEMA
    assert frame["market_key"].to_list() == [
        "player_anytime_td",
        "player_pass_yds",
    ]

    anytime = frame.filter(pl.col("market_key") == "player_anytime_td").row(0, named=True)
    passing = frame.filter(pl.col("market_key") == "player_pass_yds").row(0, named=True)

    assert anytime["bookmaker_count"] == 2
    assert anytime["line"] is None
    assert anytime["yes_price"] == 2.45
    assert round(anytime["implied_prob"], 6) == round(1.0 / 2.45, 6)

    assert passing["bookmaker_count"] == 2
    assert passing["line"] == 256.0
    assert round(passing["line_stddev"], 6) == round(0.5773502691896257, 6)
    assert round(passing["over_price"], 6) == round(1.905, 6)
    assert round(passing["under_price"], 6) == round(1.885, 6)
    assert passing["yes_price"] is None
    assert passing["implied_prob"] is None
    assert passing["player_name_normalized"] == "josh allen"


def test_build_player_market_signals_for_season_reads_raw_json(tmp_path):
    raw_dir = tmp_path / "raw" / "props" / "2024" / "close_core8"
    raw_dir.mkdir(parents=True)
    (raw_dir / "event-1.json").write_text(json.dumps(_raw_record()))

    output_path = build_player_market_signals_for_season(
        2024,
        snapshot_label="close_core8",
        raw_props_dir=tmp_path / "raw" / "props",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert output_path.name == "player_markets_2024_close_core8.parquet"
    assert frame.schema == PLAYER_MARKET_SIGNAL_SCHEMA
    assert frame.height == 2
