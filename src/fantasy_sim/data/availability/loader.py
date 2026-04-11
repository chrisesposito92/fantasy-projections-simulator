from __future__ import annotations

from dataclasses import InitVar, dataclass, field

import polars as pl

from fantasy_sim.data.loader import DataLoader

ROLE_SNAP_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "week": pl.Int64,
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "offense_pct": pl.Float64,
}

ROLE_INJURY_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "week": pl.Int64,
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "report_status": pl.Utf8,
    "practice_status": pl.Utf8,
}

ROLE_DEPTH_SCHEMA: dict[str, pl.DataType] = {
    "season": pl.Int64,
    "week": pl.Int64,
    "team": pl.Utf8,
    "player_id": pl.Utf8,
    "depth_position": pl.Utf8,
}


@dataclass
class WeeklyRoleInputLoader:
    loader_input: InitVar[DataLoader | None] = None
    loader: DataLoader = field(init=False)
    _cache: dict[tuple[int, ...], pl.DataFrame] = field(default_factory=dict, init=False)

    def __post_init__(self, loader_input: DataLoader | None) -> None:
        self.loader = loader_input or DataLoader()

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        key = tuple(sorted(seasons))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        rosters = self.loader.load_rosters(seasons).select(
            [
                "season",
                "week",
                "team",
                "position",
                "player_id",
                "player_name",
                "pfr_id",
                "depth_chart_position",
                "status_description_abbr",
            ]
        )

        stats = self.loader.load_player_stats(seasons).select(
            [
                "season",
                "week",
                "team",
                "player_id",
                "player_name",
                "position",
                "attempts",
                "carries",
                "targets",
                "receptions",
                "target_share",
            ]
        )

        frame = (
            rosters.join(
                stats,
                on=["season", "week", "team", "player_id"],
                how="left",
                suffix="_stats",
            )
            .with_columns(
                pl.coalesce("player_name", "player_name_stats").alias("player_name"),
                pl.coalesce("position", "position_stats").alias("position"),
            )
            .drop(["player_name_stats", "position_stats"])
            .join(self._load_snap_inputs(seasons, rosters), on=["season", "week", "team", "player_id"], how="left")
            .join(self._load_injury_inputs(seasons), on=["season", "week", "team", "player_id"], how="left")
            .join(self._load_depth_inputs(seasons, rosters), on=["season", "week", "team", "player_id"], how="left")
        )

        self._cache[key] = frame
        return frame

    def _load_snap_inputs(self, seasons: list[int], rosters: pl.DataFrame) -> pl.DataFrame:
        snap = self.loader.load_snap_counts(seasons)
        if snap.is_empty():
            return pl.DataFrame(schema=ROLE_SNAP_SCHEMA)

        roster_ids = rosters
        if roster_ids.schema.get("pfr_id") == pl.Null:
            roster_ids = roster_ids.with_columns(pl.col("pfr_id").cast(pl.Utf8))

        return (
            snap.select(["season", "week", "team", "pfr_player_id", "offense_pct"])
            .join(
                roster_ids.select(["season", "week", "team", "pfr_id", "player_id"])
                .unique(subset=["season", "week", "team", "pfr_id"], keep="first"),
                left_on=["season", "week", "team", "pfr_player_id"],
                right_on=["season", "week", "team", "pfr_id"],
                how="left",
            )
            .select(["season", "week", "team", "player_id", "offense_pct"])
        )

    def _load_injury_inputs(self, seasons: list[int]) -> pl.DataFrame:
        injuries = self.loader.load_injuries(seasons)
        if injuries.is_empty():
            return pl.DataFrame(schema=ROLE_INJURY_SCHEMA)

        return injuries.select(
            [
                "season",
                "week",
                "team",
                "player_id",
                "report_status",
                "practice_status",
            ]
        )

    def _load_depth_inputs(self, seasons: list[int], rosters: pl.DataFrame) -> pl.DataFrame:
        depth = self.loader.load_depth_charts(seasons)
        if depth.is_empty():
            return pl.DataFrame(schema=ROLE_DEPTH_SCHEMA)

        roster_keys = rosters.select(
            ["season", "week", "team", "player_id", "position"]
        ).unique(subset=["season", "week", "team", "player_id"], keep="first")

        return (
            depth.rename({"club_code": "team", "gsis_id": "player_id"})
            .join(
                roster_keys,
                on=["season", "week", "team", "player_id"],
                how="inner",
                suffix="_roster",
            )
            .filter(pl.col("position") == pl.col("position_roster"))
            .select(["season", "week", "team", "player_id", "depth_position"])
            .unique(subset=["season", "week", "team", "player_id"], keep="first")
        )
