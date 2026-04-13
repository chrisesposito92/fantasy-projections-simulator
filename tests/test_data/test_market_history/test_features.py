from __future__ import annotations

import polars as pl

from fantasy_sim.data.market_history.features import (
    PLAYER_WEEK_MARKET_HISTORY_SCHEMA,
    normalize_market_history,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig


def test_normalize_market_history_pivots_long_form_signals_to_player_week():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [1, 1, 1],
            "player_id": ["QB1", "QB1", "QB1"],
            "full_name": ["QB One", "QB One", "QB One"],
            "position": ["QB", "QB", "QB"],
            "team": ["KC", "KC", "KC"],
            "market_key": [
                "player_pass_yds",
                "player_pass_tds",
                "player_anytime_td",
            ],
            "bookmaker_count": [3, 2, 2],
            "line": [255.5, 1.5, None],
            "line_stddev": [0.0, 0.0, None],
            "implied_prob": [None, None, 0.40],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))
    row = normalized.row(0, named=True)

    assert normalized.schema == PLAYER_WEEK_MARKET_HISTORY_SCHEMA
    assert row["pass_yards_line"] == 255.5
    assert row["pass_tds_line"] == 1.5
    assert row["anytime_td_prob"] == 0.40
    assert row["covered_market_count"] == 3
    assert row["confidence_factor"] == 1.0


def test_normalize_market_history_reduces_confidence_for_high_dispersion_lines():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 1],
            "player_id": ["WR1", "WR1"],
            "full_name": ["WR One", "WR One"],
            "position": ["WR", "WR"],
            "team": ["MIN", "MIN"],
            "market_key": ["player_receptions", "player_reception_yds"],
            "bookmaker_count": [2, 2],
            "line": [5.5, 70.5],
            "line_stddev": [0.0, 1.5],
            "implied_prob": [None, None],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))
    row = normalized.row(0, named=True)

    assert row["covered_market_count"] == 2
    assert round(row["confidence_factor"], 4) == 0.75


def test_normalize_market_history_filters_positions_not_in_scope():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["K1"],
            "full_name": ["K One"],
            "position": ["K"],
            "team": ["KC"],
            "market_key": ["player_anytime_td"],
            "bookmaker_count": [2],
            "line": [None],
            "line_stddev": [None],
            "implied_prob": [0.10],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))

    assert normalized.is_empty()
