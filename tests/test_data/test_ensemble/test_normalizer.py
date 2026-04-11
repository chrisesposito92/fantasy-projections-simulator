"""Tests for FF Opportunity data normalization."""

import polars as pl

from fantasy_sim.data.ensemble.models import FfOpportunityConfig
from fantasy_sim.data.ensemble.normalizer import normalize_ff_opportunity


def test_normalize_ff_opportunity_filters_and_selects_columns():
    raw = pl.DataFrame(
        {
            "season": ["2024", "2024", "2024"],
            "week": ["1", "1", "1"],
            "player_id": ["00-0000001", "00-0000002", "00-0000003"],
            "full_name": ["Patrick Mahomes", "Justin Jefferson", "Christian McCaffrey"],
            "position": ["QB", "WR", "RB"],
            "posteam": ["KC", "MIN", "SF"],
            "total_fantasy_points_exp": [24.5, 18.2, 20.0],
        }
    )
    config = FfOpportunityConfig(
        positions=("QB", "WR"),
        feature="total_fantasy_points_exp",
    )

    normalized = normalize_ff_opportunity(raw, config)

    assert normalized.columns == [
        "season",
        "week",
        "player_id",
        "name",
        "position",
        "team",
        "prior_fpts",
    ]
    assert normalized["season"].to_list() == [2024, 2024]
    assert normalized["week"].to_list() == [1, 1]
    assert normalized["name"].to_list() == ["Patrick Mahomes", "Justin Jefferson"]
    assert normalized["team"].to_list() == ["KC", "MIN"]
    assert normalized["position"].to_list() == ["QB", "WR"]
    assert normalized["prior_fpts"].to_list() == [24.5, 18.2]


def test_normalize_ff_opportunity_drops_missing_player_id_and_prior_feature():
    raw = pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [1, 1, 1],
            "player_id": ["00-0000001", None, "00-0000003"],
            "full_name": ["Patrick Mahomes", "Justin Jefferson", "CeeDee Lamb"],
            "position": ["QB", "WR", "WR"],
            "posteam": ["KC", "MIN", "DAL"],
            "total_fantasy_points_exp": [24.5, 18.2, None],
        }
    )
    config = FfOpportunityConfig(
        positions=("QB", "WR"),
        feature="total_fantasy_points_exp",
    )

    normalized = normalize_ff_opportunity(raw, config)

    assert normalized.shape == (1, 7)
    assert normalized["player_id"].to_list() == ["00-0000001"]
    assert normalized["prior_fpts"].to_list() == [24.5]
