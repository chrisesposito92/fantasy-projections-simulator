"""Tests for FF Opportunity weekly data loading."""

from unittest.mock import patch

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader


@patch("fantasy_sim.data.ensemble.loader.nflreadpy.load_ff_opportunity")
def test_load_weekly_caches_by_season(mock_load_ff_opportunity, tmp_path):
    cache_dir = tmp_path / "ff-opportunity-cache"
    loader = FfOpportunityLoader(cache_dir=cache_dir)
    mock_load_ff_opportunity.return_value = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "player_id": ["00-0000001"],
            "full_name": ["Patrick Mahomes"],
            "position": ["QB"],
            "posteam": ["KC"],
            "total_fantasy_points_exp": [24.5],
        }
    )

    first = loader.load_weekly([2024])
    second = loader.load_weekly([2024])

    assert first.shape == (1, 7)
    assert second.shape == (1, 7)
    mock_load_ff_opportunity.assert_called_once_with(
        seasons=[2024],
        stat_type="weekly",
    )
    assert (cache_dir / "ff_opportunity_weekly_2024.parquet").exists()
