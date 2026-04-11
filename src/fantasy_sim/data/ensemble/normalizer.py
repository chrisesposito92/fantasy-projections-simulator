"""Normalize raw FF Opportunity weekly data into the ensemble schema."""

from __future__ import annotations

import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig

NORMALIZED_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "week": pl.Int64,
    "player_id": pl.Utf8,
    "name": pl.Utf8,
    "position": pl.Utf8,
    "team": pl.Utf8,
    "prior_fpts": pl.Float64,
}


def normalize_ff_opportunity(
    raw: pl.DataFrame,
    config: FfOpportunityConfig,
) -> pl.DataFrame:
    """Normalize raw FF Opportunity data into the ensemble input schema."""
    if raw.is_empty() or config.feature not in raw.columns:
        return pl.DataFrame(schema=NORMALIZED_SCHEMA)

    normalized = (
        raw.with_columns(
            pl.col("season").cast(pl.Int64, strict=False),
            pl.col("week").cast(pl.Int64, strict=False),
            pl.col("player_id").cast(pl.Utf8, strict=False),
            pl.col("full_name").cast(pl.Utf8, strict=False).alias("name"),
            pl.col("position").cast(pl.Utf8, strict=False),
            pl.col("posteam").cast(pl.Utf8, strict=False).alias("team"),
            pl.col(config.feature).cast(pl.Float64, strict=False).alias("prior_fpts"),
        )
        .filter(pl.col("position").is_in(config.positions))
        .filter(
            pl.col("player_id").is_not_null()
            & pl.col("prior_fpts").is_not_null()
        )
        .select(list(NORMALIZED_SCHEMA))
        .group_by(["season", "week", "player_id"])
        .agg(
            pl.col("name").sort().first().alias("name"),
            pl.col("position").sort().first().alias("position"),
            pl.col("team").sort().first().alias("team"),
            pl.col("prior_fpts").mean().alias("prior_fpts"),
        )
        .select(list(NORMALIZED_SCHEMA))
        .sort(["season", "week", "player_id"])
    )

    return normalized
