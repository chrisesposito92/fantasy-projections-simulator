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

# KS-13 Path A: optional lo/hi quantile columns passed through when present in
# the raw frame. These are absent from nflverse FF Opportunity data (probe
# confirmed 2026-04-27, path=B selected) but supported for future data sources.
# Mapping: raw column name -> (normalized column name, dtype)
_OPTIONAL_QUANTILE_SOURCES: dict[str, str] = {
    "total_fantasy_points_exp_lo": "prior_fpts_lo",
    "total_fantasy_points_exp_hi": "prior_fpts_hi",
}


def normalize_ff_opportunity(
    raw: pl.DataFrame,
    config: FfOpportunityConfig,
) -> pl.DataFrame:
    """Normalize raw FF Opportunity data into the ensemble input schema.

    KS-13 Path A: if `total_fantasy_points_exp_lo` / `total_fantasy_points_exp_hi`
    columns are present in the raw frame, they are passed through as
    `prior_fpts_lo` / `prior_fpts_hi` in the output so that
    `FfOpportunityProjectionEnsembler.blend_week` can use them for Gaussian
    sampling. These columns are optional — nflverse FF Opportunity data does NOT
    include them (probe confirmed 2026-04-27, path=B selected).
    """
    if raw.is_empty() or config.feature not in raw.columns:
        return pl.DataFrame(schema=NORMALIZED_SCHEMA)

    # Build optional quantile column renames/selects
    extra_with_cols: list = []
    extra_agg_exprs: list = []
    extra_select_cols: list[str] = []

    for src_col, dst_col in _OPTIONAL_QUANTILE_SOURCES.items():
        if src_col in raw.columns:
            extra_with_cols.append(
                pl.col(src_col).cast(pl.Float64, strict=False).alias(dst_col)
            )
            extra_agg_exprs.append(pl.col(dst_col).mean().alias(dst_col))
            extra_select_cols.append(dst_col)

    normalized = (
        raw.with_columns(
            [
                pl.col("season").cast(pl.Int64, strict=False),
                pl.col("week").cast(pl.Int64, strict=False),
                pl.col("player_id").cast(pl.Utf8, strict=False),
                pl.col("full_name").cast(pl.Utf8, strict=False).alias("name"),
                pl.col("position").cast(pl.Utf8, strict=False),
                pl.col("posteam").cast(pl.Utf8, strict=False).alias("team"),
                pl.col(config.feature).cast(pl.Float64, strict=False).alias("prior_fpts"),
            ]
            + extra_with_cols
        )
        .filter(pl.col("position").is_in(config.positions))
        .filter(
            pl.col("player_id").is_not_null()
            & pl.col("prior_fpts").is_not_null()
        )
        .select(list(NORMALIZED_SCHEMA) + extra_select_cols)
        .group_by(["season", "week", "player_id"])
        .agg(
            [
                pl.col("name").sort().first().alias("name"),
                pl.col("position").sort().first().alias("position"),
                pl.col("team").sort().first().alias("team"),
                pl.col("prior_fpts").mean().alias("prior_fpts"),
            ]
            + extra_agg_exprs
        )
        .select(list(NORMALIZED_SCHEMA) + extra_select_cols)
        .sort(["season", "week", "player_id"])
    )

    return normalized
