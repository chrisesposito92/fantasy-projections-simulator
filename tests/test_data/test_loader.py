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
    def test_clear_cache(self, mock_nfl, loader, cache_dir):
        mock_df = pl.DataFrame({"play_type": ["pass"], "yards_gained": [10]})
        mock_nfl.load_pbp.return_value = mock_df
        loader.load_pbp(seasons=[2024])
        assert any(cache_dir.iterdir())
        loader.clear_cache()
        assert not any(cache_dir.iterdir())
