from __future__ import annotations

from unittest.mock import patch

import polars as pl

from fantasy_sim.data.loader import DataLoader


def test_load_participation_caches_to_parquet(tmp_path):
    mock_df = pl.DataFrame({"player_id": ["p1"], "season": [2024]})

    with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
        mock_nfl.load_participation.return_value = mock_df
        first_loader = DataLoader(cache_dir=tmp_path)
        first_result = first_loader.load_participation([2024])

    with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
        second_loader = DataLoader(cache_dir=tmp_path)
        second_result = second_loader.load_participation([2024])
        mock_nfl.load_participation.assert_not_called()

    assert first_result.shape == mock_df.shape
    assert second_result.shape == mock_df.shape
    assert second_result.to_dict(as_series=False) == first_result.to_dict(as_series=False)
    assert (tmp_path / "participation_2024.parquet").exists()


def test_load_ftn_charting_caches_to_parquet(tmp_path):
    mock_df = pl.DataFrame({"player_id": ["p1"], "season": [2024]})

    with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
        mock_nfl.load_ftn_charting.return_value = mock_df
        first_loader = DataLoader(cache_dir=tmp_path)
        first_result = first_loader.load_ftn_charting([2024])

    with patch("fantasy_sim.data.loader.nflreadpy") as mock_nfl:
        second_loader = DataLoader(cache_dir=tmp_path)
        second_result = second_loader.load_ftn_charting([2024])
        mock_nfl.load_ftn_charting.assert_not_called()

    assert first_result.shape == mock_df.shape
    assert second_result.shape == mock_df.shape
    assert second_result.to_dict(as_series=False) == first_result.to_dict(as_series=False)
    assert (tmp_path / "ftn_charting_2024.parquet").exists()
