import polars as pl

from fantasy_sim.data.market_history.importer import build_market_history_cache
from fantasy_sim.data.market_history.loader import (
    MarketHistoryLoader,
    PROCESSED_WEEKLY_SCHEMA,
)
from fantasy_sim.data.market_history.models import MarketHistoryConfig


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


def _raw_week_frame_with_duplicate_rows(season: int, week: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [season, season],
            "week": [week, week],
            "player_id": ["QB1", "QB1"],
            "full_name": ["QB One", "QB One"],
            "position": ["QB", "QB"],
            "team": ["KC", "KC"],
            "open_fpts": [18.0, 18.0],
            "close_fpts": [19.0, 20.0],
            "books": [3, 4],
            "line_stddev": [1.0, 1.1],
            "anytime_td_prob": [0.10, 0.20],
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


def test_build_market_history_cache_collapses_duplicate_rows(tmp_path):
    raw_root = tmp_path / "raw" / "2023"
    raw_root.mkdir(parents=True)
    _raw_week_frame_with_duplicate_rows(2023, 1).write_parquet(
        raw_root / "week01.parquet"
    )

    output_path = build_market_history_cache(
        2023,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert frame.height == 1
    assert frame["close_fpts"].to_list() == [20.0]
    assert frame["books"].to_list() == [4]


def test_build_market_history_cache_writes_schema_stable_empty_file(tmp_path):
    output_path = build_market_history_cache(
        2023,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )

    frame = pl.read_parquet(output_path)

    assert frame.is_empty()
    assert frame.schema == PROCESSED_WEEKLY_SCHEMA


def test_loader_returns_empty_processed_schema_when_file_is_missing(tmp_path):
    loader = MarketHistoryLoader(
        MarketHistoryConfig(enabled=True, data_dir=str(tmp_path))
    )

    frame = loader.load_weekly([2023])

    assert frame.schema == PROCESSED_WEEKLY_SCHEMA
    assert frame.is_empty()


def test_loader_reads_multiple_seasons_from_processed_store(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    _raw_week_frame(2023, 1).write_parquet(
        processed / "market_history_weekly_2023.parquet"
    )
    _raw_week_frame(2024, 1, player_id="QB2").write_parquet(
        processed / "market_history_weekly_2024.parquet"
    )

    loader = MarketHistoryLoader(
        MarketHistoryConfig(enabled=True, data_dir=str(processed))
    )
    frame = loader.load_weekly([2023, 2024]).sort(["season", "player_id"])

    assert frame["season"].to_list() == [2023, 2024]
    assert frame["player_id"].to_list() == ["QB1", "QB2"]
