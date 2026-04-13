from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl

from fantasy_sim.data.loader import DataLoader
from fantasy_sim.data.market_history.crosswalk import (
    ODDS_PLAYER_CROSSWALK_SCHEMA,
    OddsPlayerCrosswalk,
)


def _market_players() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [1, 1, 1],
            "schedule_game_id": [
                "2024_01_ARI_BUF",
                "2024_01_CAR_NO",
                "2024_01_BUF_MIN",
            ],
            "player_name": ["Josh Allen", "Chris Olavee", "Alex Smith"],
            "player_name_normalized": ["josh allen", "chris olavee", "alex smith"],
            "home_team": ["Buffalo Bills", "New Orleans Saints", "Buffalo Bills"],
            "away_team": ["Arizona Cardinals", "Carolina Panthers", "Minnesota Vikings"],
        }
    )


def _rosters() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1],
            "player_id": ["BUF-QB1", "JAX-QB1", "NO-WR1", "BUF-WR2", "MIN-WR2"],
            "player_name": [
                "Josh Allen",
                "Josh Allen",
                "Chris Olave",
                "Alex Smith",
                "Alex Smith",
            ],
            "position": ["QB", "QB", "WR", "WR", "WR"],
            "team": ["BUF", "JAX", "NO", "BUF", "MIN"],
        }
    )


def test_build_for_season_scopes_exact_name_matching_to_the_game_teams():
    loader = MagicMock(spec=DataLoader)
    loader.load_rosters.return_value = _rosters()
    crosswalk = OddsPlayerCrosswalk(loader=loader)

    frame = crosswalk.build_for_season(_market_players(), 2024).sort("player_name")

    assert frame.schema == ODDS_PLAYER_CROSSWALK_SCHEMA
    assert frame["player_name"].to_list() == ["Chris Olavee", "Josh Allen"]
    assert frame["player_id"].to_list() == ["NO-WR1", "BUF-QB1"]
    assert frame["match_source"].to_list() == ["fuzzy", "exact"]


def test_build_for_season_skips_ambiguous_same_name_on_both_teams():
    loader = MagicMock(spec=DataLoader)
    loader.load_rosters.return_value = _rosters()
    crosswalk = OddsPlayerCrosswalk(loader=loader)

    frame = crosswalk.build_for_season(_market_players(), 2024)

    assert "Alex Smith" not in frame["player_name"].to_list()


def test_build_for_season_preserves_null_schedule_game_id_when_matching_by_teams():
    loader = MagicMock(spec=DataLoader)
    loader.load_rosters.return_value = _rosters().filter(pl.col("player_id") == "BUF-QB1")
    crosswalk = OddsPlayerCrosswalk(loader=loader)

    frame = crosswalk.build_for_season(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "schedule_game_id": [None],
                "player_name": ["Josh Allen"],
                "player_name_normalized": ["josh allen"],
                "home_team": ["Buffalo Bills"],
                "away_team": ["Arizona Cardinals"],
            }
        ),
        2024,
    )

    row = frame.row(0, named=True)
    assert row["player_id"] == "BUF-QB1"
    assert row["schedule_game_id"] is None
