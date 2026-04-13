from __future__ import annotations

import polars as pl
from polars._typing import SchemaDict

from fantasy_sim.data.loader import DataLoader

RECEIVER_FEATURE_SCHEMA: SchemaDict = {
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "targets": pl.Int64,
    "catchable_rate": pl.Float64,
    "contested_rate": pl.Float64,
    "mean_air_yards": pl.Float64,
}

RB_FEATURE_SCHEMA: SchemaDict = {
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "attempts": pl.Int64,
    "no_huddle_rate": pl.Float64,
    "play_action_rate": pl.Float64,
    "rush_yoe_per_att": pl.Float64,
}

QB_FEATURE_SCHEMA: SchemaDict = {
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "dropbacks": pl.Int64,
    "pressure_rate": pl.Float64,
    "no_huddle_rate": pl.Float64,
    "play_action_rate": pl.Float64,
    "blitz_rate": pl.Float64,
    "avg_time_to_throw": pl.Float64,
    "aggressiveness": pl.Float64,
    "cpoe": pl.Float64,
}

FTN_JOIN_SCHEMA: SchemaDict = {
    "is_catchable_ball": pl.Float64,
    "is_contested_ball": pl.Float64,
    "is_no_huddle": pl.Float64,
    "is_play_action": pl.Float64,
    "n_blitzers": pl.Float64,
}

RB_OPTIONAL_SCHEMA: SchemaDict = {
    "is_no_huddle": pl.Float64,
    "is_play_action": pl.Float64,
    "rush_yoe_per_att": pl.Float64,
}

QB_OPTIONAL_SCHEMA: SchemaDict = {
    "was_pressure": pl.Float64,
    "is_no_huddle": pl.Float64,
    "is_play_action": pl.Float64,
    "n_blitzers": pl.Float64,
    "avg_time_to_throw": pl.Float64,
    "aggressiveness": pl.Float64,
    "cpoe": pl.Float64,
}

SCHEMA_COLUMN_NAMES: dict[str, list[str]] = {
    "receiver": list(RECEIVER_FEATURE_SCHEMA),
    "rb": list(RB_FEATURE_SCHEMA),
    "qb": list(QB_FEATURE_SCHEMA),
}


class TrackingInputLoader:
    def __init__(self, loader: DataLoader | None = None, window_weeks: int = 4):
        self._loader = loader or DataLoader()
        self._window_weeks = window_weeks

    def _empty_frame(self, schema: SchemaDict) -> pl.DataFrame:
        return pl.DataFrame(schema=schema)

    def _rename_columns(self, df: pl.DataFrame, mapping: dict[str, str]) -> pl.DataFrame:
        rename_map = {
            source: target
            for source, target in mapping.items()
            if source in df.columns and target not in df.columns
        }
        if rename_map:
            return df.rename(rename_map)
        return df

    def _ensure_columns(self, df: pl.DataFrame, columns: SchemaDict) -> pl.DataFrame:
        missing = [
            pl.lit(None, dtype=dtype).alias(name)
            for name, dtype in columns.items()
            if name not in df.columns
        ]
        if missing:
            return df.with_columns(missing)
        return df

    def _cast_to_schema(self, df: pl.DataFrame, schema: SchemaDict) -> pl.DataFrame:
        return (
            df.with_columns(
                [pl.col(name).cast(dtype).alias(name) for name, dtype in schema.items()]
            )
            .select(list(schema))
        )

    def _window_filter(self, df: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
        if df.is_empty() or week <= 1:
            return df.clear()
        if "season" not in df.columns or "week" not in df.columns:
            return df.clear()
        min_week = max(1, week - self._window_weeks)
        return df.filter(
            (pl.col("season") == season)
            & (pl.col("week") >= min_week)
            & (pl.col("week") < week)
        )

    def _join_keys(self, left: pl.DataFrame, right: pl.DataFrame) -> list[str]:
        preferred = ["season", "week", "player_id"]
        available = [key for key in preferred if key in left.columns and key in right.columns]
        if available:
            return available
        if "player_id" in left.columns and "player_id" in right.columns:
            return ["player_id"]
        return []

    def _rate(self, column: str) -> pl.Expr:
        return pl.col(column).cast(pl.Float64).mean()

    def _joined_pbp_ftn(self, season: int) -> pl.DataFrame:
        pbp = self._loader.load_pbp([season])
        if pbp is None or pbp.is_empty():
            return pl.DataFrame()

        ftn = self._loader.load_ftn_charting([season])
        if ftn is None or ftn.is_empty():
            return self._ensure_columns(pbp, FTN_JOIN_SCHEMA)

        ftn = self._rename_columns(
            ftn,
            {
                "nflverse_game_id": "game_id",
                "nflverse_play_id": "play_id",
            },
        )
        join_keys = ["game_id", "play_id"]
        if not set(join_keys).issubset(pbp.columns) or not set(join_keys).issubset(ftn.columns):
            return self._ensure_columns(pbp, FTN_JOIN_SCHEMA)

        joined = pbp.join(
            self._ensure_columns(ftn, FTN_JOIN_SCHEMA)
            .select([*join_keys, *FTN_JOIN_SCHEMA.keys()])
            .unique(subset=join_keys, keep="first"),
            on=join_keys,
            how="left",
        )
        return self._ensure_columns(joined, FTN_JOIN_SCHEMA)

    def load_receiver_features(self, season: int, week: int) -> pl.DataFrame:
        ftn = self._loader.load_ftn_charting([season])
        if ftn is None or ftn.is_empty():
            return self._empty_frame(RECEIVER_FEATURE_SCHEMA)

        ftn = self._rename_columns(
            ftn,
            {
                "nflverse_game_id": "game_id",
                "nflverse_play_id": "play_id",
            },
        )
        receiver_ftn_required = {"game_id", "play_id", "is_catchable_ball", "is_contested_ball"}
        if not receiver_ftn_required.issubset(ftn.columns):
            return self._empty_frame(RECEIVER_FEATURE_SCHEMA)

        joined = self._joined_pbp_ftn(season)
        if joined.is_empty():
            return self._empty_frame(RECEIVER_FEATURE_SCHEMA)

        required = {
            "posteam",
            "receiver_player_id",
            "air_yards",
            "pass_attempt",
            "is_catchable_ball",
            "is_contested_ball",
        }
        if not required.issubset(joined.columns):
            return self._empty_frame(RECEIVER_FEATURE_SCHEMA)

        windowed = self._window_filter(joined, season, week).filter(
            (pl.col("pass_attempt") == 1) & pl.col("receiver_player_id").is_not_null()
        )
        if windowed.is_empty():
            return self._empty_frame(RECEIVER_FEATURE_SCHEMA)

        result = (
            windowed
            .group_by(["posteam", "receiver_player_id"])
            .agg(
                [
                    pl.len().alias("targets"),
                    self._rate("is_catchable_ball").alias("catchable_rate"),
                    self._rate("is_contested_ball").alias("contested_rate"),
                    pl.col("air_yards").cast(pl.Float64).mean().alias("mean_air_yards"),
                ]
            )
            .rename({"posteam": "team", "receiver_player_id": "player_id"})
            .select(SCHEMA_COLUMN_NAMES["receiver"])
        )
        return self._cast_to_schema(result, RECEIVER_FEATURE_SCHEMA)

    def load_rb_features(self, season: int, week: int) -> pl.DataFrame:
        joined = self._joined_pbp_ftn(season)
        if joined.is_empty():
            return self._empty_frame(RB_FEATURE_SCHEMA)

        required = {"posteam", "rusher_player_id", "rush_attempt"}
        if not required.issubset(joined.columns):
            return self._empty_frame(RB_FEATURE_SCHEMA)

        rushes = (
            self._window_filter(joined, season, week)
            .filter((pl.col("rush_attempt") == 1) & pl.col("rusher_player_id").is_not_null())
            .rename({"posteam": "team", "rusher_player_id": "player_id"})
        )
        if rushes.is_empty():
            return self._empty_frame(RB_FEATURE_SCHEMA)

        ngs = self._loader.load_nextgen_stats([season], stat_type="rushing")
        if ngs is not None and not ngs.is_empty():
            ngs = self._rename_columns(
                ngs,
                {
                    "player_gsis_id": "player_id",
                    "rush_yards_over_expected_per_att": "rush_yoe_per_att",
                },
            )
            ngs = self._window_filter(ngs, season, week)
            join_keys = self._join_keys(rushes, ngs)
            if join_keys and "rush_yoe_per_att" in ngs.columns:
                rushes = rushes.join(
                    ngs.select([*join_keys, "rush_yoe_per_att"])
                    .unique(subset=join_keys, keep="first"),
                    on=join_keys,
                    how="left",
                )

        rushes = self._ensure_columns(rushes, RB_OPTIONAL_SCHEMA)

        result = (
            rushes
            .group_by(["team", "player_id"])
            .agg(
                [
                    pl.len().alias("attempts"),
                    self._rate("is_no_huddle").alias("no_huddle_rate"),
                    self._rate("is_play_action").alias("play_action_rate"),
                    pl.col("rush_yoe_per_att").cast(pl.Float64).mean().alias("rush_yoe_per_att"),
                ]
            )
            .select(SCHEMA_COLUMN_NAMES["rb"])
        )
        return self._cast_to_schema(result, RB_FEATURE_SCHEMA)

    def load_qb_features(self, season: int, week: int) -> pl.DataFrame:
        pbp = self._loader.load_pbp([season])
        if pbp is None or pbp.is_empty():
            return self._empty_frame(QB_FEATURE_SCHEMA)

        required_pbp = {"game_id", "play_id", "season", "week", "posteam", "passer_player_id", "pass_attempt"}
        if not required_pbp.issubset(pbp.columns):
            return self._empty_frame(QB_FEATURE_SCHEMA)

        qbs = (
            self._window_filter(pbp, season, week)
            .filter((pl.col("pass_attempt") == 1) & pl.col("passer_player_id").is_not_null())
            .rename({"posteam": "team", "passer_player_id": "player_id"})
        )
        if qbs.is_empty():
            return self._empty_frame(QB_FEATURE_SCHEMA)

        participation = self._loader.load_participation([season])
        if participation is None or participation.is_empty():
            return self._empty_frame(QB_FEATURE_SCHEMA)

        participation = self._rename_columns(
            participation,
            {
                "nflverse_game_id": "game_id",
            },
        )
        required_participation = {"game_id", "play_id", "was_pressure"}
        if not required_participation.issubset(participation.columns):
            return self._empty_frame(QB_FEATURE_SCHEMA)

        participation = (
            self._window_filter(participation, season, week)
            .select(["game_id", "play_id", "was_pressure"])
            .unique(subset=["game_id", "play_id"], keep="first")
        )
        qbs = qbs.join(participation, on=["game_id", "play_id"], how="left")

        ftn = self._loader.load_ftn_charting([season])
        if ftn is not None and not ftn.is_empty():
            ftn = self._rename_columns(
                ftn,
                {
                    "nflverse_game_id": "game_id",
                    "nflverse_play_id": "play_id",
                },
            )
            if {"game_id", "play_id"}.issubset(ftn.columns):
                qbs = qbs.join(
                    self._ensure_columns(ftn, FTN_JOIN_SCHEMA)
                    .select(["game_id", "play_id", "is_no_huddle", "is_play_action", "n_blitzers"])
                    .unique(subset=["game_id", "play_id"], keep="first"),
                    on=["game_id", "play_id"],
                    how="left",
                )

        ngs = self._loader.load_nextgen_stats([season], stat_type="passing")
        if ngs is not None and not ngs.is_empty():
            ngs = self._rename_columns(
                ngs,
                {
                    "player_gsis_id": "player_id",
                    "completion_percentage_above_expectation": "cpoe",
                },
            )
            ngs = self._window_filter(ngs, season, week)
            join_keys = self._join_keys(qbs, ngs)
            ngs_columns = [name for name in ["avg_time_to_throw", "aggressiveness", "cpoe"] if name in ngs.columns]
            if join_keys and ngs_columns:
                qbs = qbs.join(
                    ngs.select([*join_keys, *ngs_columns]).unique(subset=join_keys, keep="first"),
                    on=join_keys,
                    how="left",
                )

        qbs = self._ensure_columns(qbs, QB_OPTIONAL_SCHEMA)

        result = (
            qbs
            .group_by(["team", "player_id"])
            .agg(
                [
                    pl.len().alias("dropbacks"),
                    self._rate("was_pressure").alias("pressure_rate"),
                    self._rate("is_no_huddle").alias("no_huddle_rate"),
                    self._rate("is_play_action").alias("play_action_rate"),
                    pl.col("n_blitzers").fill_null(0).gt(0).cast(pl.Float64).mean().alias("blitz_rate"),
                    pl.col("avg_time_to_throw").cast(pl.Float64).mean().alias("avg_time_to_throw"),
                    pl.col("aggressiveness").cast(pl.Float64).mean().alias("aggressiveness"),
                    pl.col("cpoe").cast(pl.Float64).mean().alias("cpoe"),
                ]
            )
            .select(SCHEMA_COLUMN_NAMES["qb"])
        )
        return self._cast_to_schema(result, QB_FEATURE_SCHEMA)
