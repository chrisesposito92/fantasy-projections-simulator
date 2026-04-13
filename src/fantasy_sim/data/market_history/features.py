from __future__ import annotations

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.market_history.loader import (
    MARKET_HISTORY_SIGNAL_SCHEMA,
    ensure_market_history_signal_schema,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig

_LINE_MARKETS: dict[str, str] = {
    "player_pass_attempts": "pass_attempts",
    "player_pass_yds": "pass_yards",
    "player_pass_tds": "pass_tds",
    "player_rush_attempts": "rush_attempts",
    "player_rush_yds": "rush_yards",
    "player_receptions": "receptions",
    "player_reception_yds": "receiving_yards",
}

PLAYER_WEEK_MARKET_HISTORY_SCHEMA: SchemaDict = {
    "season": pl.Int64,
    "week": pl.Int64,
    "player_id": pl.Utf8,
    "full_name": pl.Utf8,
    "position": pl.Utf8,
    "team": pl.Utf8,
    "pass_attempts_line": pl.Float64,
    "pass_attempts_bookmaker_count": pl.Int64,
    "pass_attempts_line_stddev": pl.Float64,
    "pass_yards_line": pl.Float64,
    "pass_yards_bookmaker_count": pl.Int64,
    "pass_yards_line_stddev": pl.Float64,
    "pass_tds_line": pl.Float64,
    "pass_tds_bookmaker_count": pl.Int64,
    "pass_tds_line_stddev": pl.Float64,
    "rush_attempts_line": pl.Float64,
    "rush_attempts_bookmaker_count": pl.Int64,
    "rush_attempts_line_stddev": pl.Float64,
    "rush_yards_line": pl.Float64,
    "rush_yards_bookmaker_count": pl.Int64,
    "rush_yards_line_stddev": pl.Float64,
    "receptions_line": pl.Float64,
    "receptions_bookmaker_count": pl.Int64,
    "receptions_line_stddev": pl.Float64,
    "receiving_yards_line": pl.Float64,
    "receiving_yards_bookmaker_count": pl.Int64,
    "receiving_yards_line_stddev": pl.Float64,
    "anytime_td_prob": pl.Float64,
    "anytime_td_bookmaker_count": pl.Int64,
    "covered_market_count": pl.Int64,
    "confidence_factor": pl.Float64,
}


def normalize_market_history(
    frame: pl.DataFrame,
    config: MarketHistoryConfig,
) -> pl.DataFrame:
    """Pivot long-form market rows into player-week signals with aggregate confidence."""
    if frame.is_empty():
        return pl.DataFrame(schema=PLAYER_WEEK_MARKET_HISTORY_SCHEMA)
    frame = ensure_market_history_signal_schema(frame)

    min_books = max(config.min_books, 1)
    dispersion_scale = max(config.dispersion_scale, 1e-9)
    filtered = frame.filter(pl.col("position").is_in(list(config.positions)))
    if filtered.is_empty():
        return pl.DataFrame(schema=PLAYER_WEEK_MARKET_HISTORY_SCHEMA)

    aggregations: list[pl.Expr] = []
    for market_key, prefix in _LINE_MARKETS.items():
        aggregations.extend(
            [
                pl.when(pl.col("market_key") == market_key)
                .then(pl.col("line"))
                .otherwise(None)
                .max()
                .alias(f"{prefix}_line"),
                pl.when(pl.col("market_key") == market_key)
                .then(pl.col("bookmaker_count"))
                .otherwise(None)
                .max()
                .alias(f"{prefix}_bookmaker_count"),
                pl.when(pl.col("market_key") == market_key)
                .then(pl.col("line_stddev"))
                .otherwise(None)
                .max()
                .alias(f"{prefix}_line_stddev"),
            ]
        )

    aggregations.extend(
        [
            pl.when(pl.col("market_key") == "player_anytime_td")
            .then(pl.col("implied_prob"))
            .otherwise(None)
            .max()
            .alias("anytime_td_prob"),
            pl.when(pl.col("market_key") == "player_anytime_td")
            .then(pl.col("bookmaker_count"))
            .otherwise(None)
            .max()
            .alias("anytime_td_bookmaker_count"),
        ]
    )

    pivoted = filtered.group_by(
        ["season", "week", "player_id", "full_name", "position", "team"]
    ).agg(aggregations)

    confidence_columns: list[str] = []
    confidence_exprs: list[pl.Expr] = []
    for prefix in _LINE_MARKETS.values():
        confidence_name = f"{prefix}_confidence"
        confidence_columns.append(confidence_name)
        line_col = f"{prefix}_line"
        books_col = f"{prefix}_bookmaker_count"
        std_col = f"{prefix}_line_stddev"
        confidence_exprs.append(
            pl.when(pl.col(line_col).is_not_null())
            .then(
                ((pl.col(books_col).fill_null(0) / min_books).clip(0.0, 1.0))
                * (
                    pl.when(
                        pl.lit(config.features.dispersion)
                        & pl.col(std_col).is_not_null()
                    )
                    .then((1.0 - (pl.col(std_col) / dispersion_scale)).clip(0.0, 1.0))
                    .otherwise(1.0)
                )
            )
            .otherwise(None)
            .alias(confidence_name)
        )

    confidence_columns.append("anytime_td_confidence")
    confidence_exprs.append(
        pl.when(
            pl.lit(config.features.anytime_td) & pl.col("anytime_td_prob").is_not_null()
        )
        .then((pl.col("anytime_td_bookmaker_count").fill_null(0) / min_books).clip(0.0, 1.0))
        .otherwise(None)
        .alias("anytime_td_confidence")
    )

    normalized = pivoted.with_columns(confidence_exprs)

    covered_count_expr = pl.sum_horizontal(
        [
            pl.when(pl.col(column).is_not_null()).then(1).otherwise(0)
            for column in confidence_columns
        ]
    ).cast(pl.Int64)
    confidence_sum_expr = pl.sum_horizontal(
        [pl.col(column).fill_null(0.0) for column in confidence_columns]
    )

    normalized = normalized.with_columns(
        [
            covered_count_expr.alias("covered_market_count"),
            pl.when(covered_count_expr > 0)
            .then(confidence_sum_expr / covered_count_expr.cast(pl.Float64))
            .otherwise(0.0)
            .alias("confidence_factor"),
        ]
    ).drop(confidence_columns)

    return normalized.select(list(PLAYER_WEEK_MARKET_HISTORY_SCHEMA))
