from __future__ import annotations

import polars as pl

from fantasy_sim.data.market_history.loader import PROCESSED_WEEKLY_SCHEMA
from fantasy_sim.data.market_history.models import MarketHistoryConfig

_MOVEMENT_WEIGHT = 0.25
_MIN_ANYTIME_CONFIDENCE = 0.85
_MAX_ANYTIME_CONFIDENCE = 1.15

NORMALIZED_MARKET_HISTORY_SCHEMA: dict[str, pl.DataType] = {
    **PROCESSED_WEEKLY_SCHEMA,
    "line_move": pl.Float64,
    "prior_fpts": pl.Float64,
    "adjusted_prior_fpts": pl.Float64,
    "confidence_factor": pl.Float64,
}


def normalize_market_history(
    frame: pl.DataFrame,
    config: MarketHistoryConfig,
) -> pl.DataFrame:
    """Build normalized per-player market priors and confidence signals."""
    if frame.is_empty():
        return pl.DataFrame(schema=NORMALIZED_MARKET_HISTORY_SCHEMA)

    min_books = max(config.min_books, 1)
    dispersion_scale = max(config.dispersion_scale, 1e-9)

    normalized = (
        frame.filter(pl.col("position").is_in(list(config.positions)))
        .with_columns(
            [
                (
                    (pl.col("close_fpts") - pl.col("open_fpts"))
                    .fill_null(0.0)
                    .cast(pl.Float64)
                ).alias("line_move"),
                pl.coalesce([pl.col("close_fpts"), pl.col("open_fpts")])
                .cast(pl.Float64)
                .alias("prior_fpts"),
                (
                    (pl.col("books").fill_null(0) / min_books)
                    .clip(0.0, 1.0)
                ).alias("book_confidence"),
                pl.when(
                    pl.lit(config.features.dispersion) & pl.col("line_stddev").is_not_null()
                )
                .then(
                    (1.0 - (pl.col("line_stddev") / dispersion_scale)).clip(0.0, 1.0)
                )
                .otherwise(1.0)
                .alias("dispersion_confidence"),
                pl.when(
                    pl.lit(config.features.anytime_td) & pl.col("anytime_td_prob").is_not_null()
                )
                .then(
                    (0.85 + pl.col("anytime_td_prob")).clip(
                        _MIN_ANYTIME_CONFIDENCE,
                        _MAX_ANYTIME_CONFIDENCE,
                    )
                )
                .otherwise(1.0)
                .alias("anytime_confidence"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.lit(config.features.movement))
                .then(pl.col("line_move") * _MOVEMENT_WEIGHT)
                .otherwise(0.0)
                .alias("movement_adjustment"),
                (
                    pl.col("book_confidence")
                    * pl.col("dispersion_confidence")
                    * pl.col("anytime_confidence")
                )
                .clip(0.0, 1.0)
                .alias("confidence_factor"),
            ]
        )
        .with_columns(
            [
                (pl.col("prior_fpts") + pl.col("movement_adjustment"))
                .cast(pl.Float64)
                .alias("adjusted_prior_fpts")
            ]
        )
        .drop(
            [
                "book_confidence",
                "dispersion_confidence",
                "anytime_confidence",
                "movement_adjustment",
            ]
        )
    )

    return normalized.select(list(NORMALIZED_MARKET_HISTORY_SCHEMA))
