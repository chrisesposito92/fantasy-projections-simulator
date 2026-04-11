import polars as pl
import pytest
from pathlib import Path
from unittest.mock import patch
from fantasy_sim.data.loader import DataLoader


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def loader(cache_dir):
    return DataLoader(cache_dir=cache_dir)


class TestDataLoaderCaching:
    def test_cache_dir_created(self, loader, cache_dir):
        assert cache_dir.exists()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_caches_to_parquet(self, mock_nfl, loader, cache_dir):
        mock_df = pl.DataFrame({"play_type": ["pass", "run"], "yards_gained": [10, 5]})
        mock_nfl.load_pbp.return_value = mock_df
        result = loader.load_pbp(seasons=[2024])
        assert result.shape == mock_df.shape
        cache_file = cache_dir / "pbp_2024.parquet"
        assert cache_file.exists()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_uses_cache_on_second_call(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        loader.load_pbp(seasons=[2024])
        mock_nfl.load_pbp.assert_called_once()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_pbp_multiple_seasons(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10], "season": [2024]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2023, 2024])
        mock_nfl.load_pbp.assert_called_once_with([2023, 2024])


class TestDataLoaderMethods:
    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_schedules(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"game_id": ["g1"], "home_team": ["KC"]})
        mock_nfl.load_schedules.return_value = mock_df
        result = loader.load_schedules(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_rosters(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"player_id": ["p1"], "position": ["QB"]})
        mock_nfl.load_rosters_weekly.return_value = mock_df
        result = loader.load_rosters(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_player_stats(self, mock_nfl, loader):
        mock_df = pl.DataFrame({"player_id": ["p1"], "passing_yards": [300]})
        mock_nfl.load_player_stats.return_value = mock_df
        result = loader.load_player_stats(seasons=[2024])
        assert result.shape[0] == 1

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_load_injuries_normalizes_player_identity_columns(self, mock_nfl, loader):
        mock_df = pl.DataFrame(
            {
                "gsis_id": ["00-001"],
                "full_name": ["Player One"],
                "report_status": ["Questionable"],
            }
        )
        mock_nfl.load_injuries.return_value = mock_df

        result = loader.load_injuries(seasons=[2024])

        assert "player_id" in result.columns
        assert "player_name" in result.columns
        assert "gsis_id" not in result.columns
        assert "full_name" not in result.columns
        assert result["player_id"].to_list() == ["00-001"]
        assert result["player_name"].to_list() == ["Player One"]

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_clear_cache(self, mock_nfl, loader, cache_dir):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        assert any(cache_dir.iterdir())
        loader.clear_cache()
        assert not any(cache_dir.iterdir())


class TestDataLoaderMemoryCache:
    """Tests for in-memory DataFrame caching to avoid redundant parquet reads."""

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_memory_cache_returns_same_object(self, mock_nfl, loader):
        """Second call returns the exact same DataFrame object (no parquet re-read)."""
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df
        first = loader.load_pbp(seasons=[2024])
        second = loader.load_pbp(seasons=[2024])
        assert first is second

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_memory_cache_different_seasons_separate_entries(self, mock_nfl, loader):
        """Different season lists produce separate cache entries."""
        df_2023 = pl.DataFrame({"season": [2023]})
        df_2024 = pl.DataFrame({"season": [2024]})
        mock_nfl.load_pbp.side_effect = [df_2023, df_2024]
        r1 = loader.load_pbp(seasons=[2023])
        r2 = loader.load_pbp(seasons=[2024])
        assert r1 is not r2
        assert r1["season"][0] == 2023
        assert r2["season"][0] == 2024

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_memory_cache_survives_parquet_read(self, mock_nfl, loader):
        """After initial load, parquet file exists but memory cache is used (no disk read)."""
        mock_df = pl.DataFrame({"x": [1]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        # Verify memory cache populated
        assert len(loader._memory_cache) == 1
        # Third call should still use memory cache
        result = loader.load_pbp(seasons=[2024])
        assert result is mock_df  # exact same object from _save_cache

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_clear_cache_clears_memory(self, mock_nfl, loader):
        """clear_cache() removes both parquet files and memory cache."""
        mock_df = pl.DataFrame({"x": [1]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        assert len(loader._memory_cache) == 1
        loader.clear_cache()
        assert len(loader._memory_cache) == 0

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_memory_cache_works_for_rosters(self, mock_nfl, loader):
        """Memory cache works across different load methods."""
        mock_df = pl.DataFrame({"player_id": ["p1"], "position": ["QB"]})
        mock_nfl.load_rosters_weekly.return_value = mock_df
        first = loader.load_rosters(seasons=[2024])
        second = loader.load_rosters(seasons=[2024])
        assert first is second
        mock_nfl.load_rosters_weekly.assert_called_once()

    @patch("fantasy_sim.data.loader.nflreadpy")
    def test_memory_cache_works_for_injuries(self, mock_nfl, loader):
        """Repeated injury loads reuse the in-memory cache."""
        mock_df = pl.DataFrame({"player_id": ["p1"], "report_status": ["Out"]})
        mock_nfl.load_injuries.return_value = mock_df

        first = loader.load_injuries(seasons=[2024])
        second = loader.load_injuries(seasons=[2024])

        assert first is second
        mock_nfl.load_injuries.assert_called_once()
