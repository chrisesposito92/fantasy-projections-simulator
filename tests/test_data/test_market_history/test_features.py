import polars as pl

from fantasy_sim.data.market_history.features import normalize_market_history
from fantasy_sim.data.market_history.models import MarketHistoryConfig


def test_normalize_market_history_builds_adjusted_prior_and_confidence():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [16.0],
            "close_fpts": [18.0],
            "books": [4],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.50],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))
    row = normalized.row(0, named=True)

    assert row["prior_fpts"] == 18.0
    assert row["line_move"] == 2.0
    assert round(row["adjusted_prior_fpts"], 2) == 18.5
    assert round(row["confidence_factor"], 4) == 0.7667


def test_normalize_market_history_uses_open_fpts_when_close_is_disabled():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [16.0],
            "close_fpts": [18.0],
            "books": [4],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.50],
        }
    )
    config = MarketHistoryConfig(enabled=True)
    config.features.close_fpts = False

    normalized = normalize_market_history(frame, config)
    row = normalized.row(0, named=True)

    assert row["prior_fpts"] == 16.0
    assert row["line_move"] == -16.0


def test_normalize_market_history_uses_close_fpts_when_open_is_disabled():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [16.0],
            "close_fpts": [18.0],
            "books": [4],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.50],
        }
    )
    config = MarketHistoryConfig(enabled=True)
    config.features.open_fpts = False

    normalized = normalize_market_history(frame, config)
    row = normalized.row(0, named=True)

    assert row["prior_fpts"] == 18.0
    assert row["line_move"] == 18.0


def test_normalize_market_history_uses_zero_prior_when_both_price_flags_are_disabled():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["QB1"],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [16.0],
            "close_fpts": [18.0],
            "books": [4],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.50],
        }
    )
    config = MarketHistoryConfig(enabled=True)
    config.features.open_fpts = False
    config.features.close_fpts = False

    normalized = normalize_market_history(frame, config)
    row = normalized.row(0, named=True)

    assert row["prior_fpts"] == 0.0
    assert row["line_move"] == 0.0


def test_normalize_market_history_filters_positions_not_in_scope():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["K1"],
            "full_name": ["K One"],
            "position": ["K"],
            "team": ["KC"],
            "open_fpts": [8.0],
            "close_fpts": [8.5],
            "books": [3],
            "line_stddev": [0.2],
            "anytime_td_prob": [None],
        }
    )

    normalized = normalize_market_history(frame, MarketHistoryConfig(enabled=True))

    assert normalized.is_empty()
