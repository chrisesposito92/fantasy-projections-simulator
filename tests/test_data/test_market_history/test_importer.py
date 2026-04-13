from __future__ import annotations

import polars as pl

from fantasy_sim.data.market_history.importer import (
    PROCESSED_WEEKLY_SCHEMA,
    build_market_history_cache,
)


def _raw_week_frame(season: int, week: int, *, player_id: str = "QB1") -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [season],
            "week": [week],
            "player_id": [player_id],
            "full_name": ["QB One"],
            "position": ["QB"],
            "team": ["KC"],
            "open_fpts": [18.0],
            "close_fpts": [19.0],
            "books": [3],
            "line_stddev": [1.0],
            "anytime_td_prob": [0.10],
        }
    )


def test_build_market_history_cache_combines_weeks_into_one_season_file(tmp_path):
    raw_root = tmp_path / "raw" / "2023"
    raw_root.mkdir(parents=True)
    _raw_week_frame(2023, 1).write_parquet(raw_root / "week01.parquet")
    _raw_week_frame(2023, 2).write_parquet(raw_root / "week02.parquet")

    output_path = build_market_history_cache(
        2023,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert output_path.name == "market_history_weekly_2023.parquet"
    assert frame["week"].to_list() == [1, 2]
    assert frame["player_id"].to_list() == ["QB1", "QB1"]


def test_build_market_history_cache_writes_schema_stable_empty_file(tmp_path):
    output_path = build_market_history_cache(
        2023,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert frame.is_empty()
    assert frame.schema == PROCESSED_WEEKLY_SCHEMA
