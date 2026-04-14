from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.pff.models import RbSchemeFitConfig
from fantasy_sim.data.pff.rb_scheme_fit import RbSchemeFitEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster(team: str, rb_id: str = "RB1") -> TeamRoster:
    return TeamRoster(
        team=team,
        players=[
            PlayerModel(
                "QB1",
                "QB One",
                "QB",
                team,
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                rb_id,
                "RB One",
                "RB",
                team,
                PlayerUsage(carry_share=0.55),
                PlayerOutcomes(rushing_yards_dist=np.array([3.0, 4.0, 5.0, 6.0])),
            ),
        ],
    )


def _rushing_direction_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2023, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "player_id": [101, 101, 101, 101],
            "position": ["RB", "RB", "RB", "RB"],
            "game_id": [1, 2, 3, 4],
            "directions": [
                [
                    {"direction": "ML", "attempts": 4, "yards": 20, "ypa": 5.0},
                    {"direction": "MR", "attempts": 2, "yards": 10, "ypa": 5.0},
                    {"direction": "LE", "attempts": 1, "yards": 2, "ypa": 2.0},
                ],
                [
                    {"direction": "ML", "attempts": 3, "yards": 15, "ypa": 5.0},
                    {"direction": "MR", "attempts": 3, "yards": 12, "ypa": 4.0},
                    {"direction": "RE", "attempts": 1, "yards": 3, "ypa": 3.0},
                ],
                [
                    {"direction": "ML", "attempts": 2, "yards": 8, "ypa": 4.0},
                    {"direction": "MR", "attempts": 2, "yards": 8, "ypa": 4.0},
                    {"direction": "LE", "attempts": 1, "yards": 2, "ypa": 2.0},
                ],
                [
                    {"direction": "ML", "attempts": 6, "yards": 27, "ypa": 4.5},
                    {"direction": "MR", "attempts": 5, "yards": 20, "ypa": 4.0},
                ],
            ],
        }
    )


def _offense_run_blocking_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2023, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "game_id": [1, 2, 3, 4],
            "gap_snap_counts_run_play": [30, 29, 28, 27],
            "zone_snap_counts_run_play": [2, 3, 2, 2],
            "gap_snap_counts_run_block": [30, 29, 28, 27],
            "zone_snap_counts_run_block": [2, 3, 2, 2],
            "gap_grades_run_block": [67.0, 66.0, 68.0, 66.0],
            "zone_grades_run_block": [56.0, 55.0, 57.0, 55.0],
        }
    )


def _historical_window_rushing_direction_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2022, 2022, 2022, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "player_id": [101, 101, 101, 101],
            "position": ["RB", "RB", "RB", "RB"],
            "game_id": [11, 12, 13, 14],
            "directions": [
                [
                    {"direction": "ML", "attempts": 8, "yards": 64, "ypa": 8.0},
                    {"direction": "MR", "attempts": 6, "yards": 36, "ypa": 6.0},
                    {"direction": "LE", "attempts": 4, "yards": 12, "ypa": 3.0},
                ],
                [
                    {"direction": "ML", "attempts": 6, "yards": 42, "ypa": 7.0},
                    {"direction": "MR", "attempts": 4, "yards": 20, "ypa": 5.0},
                    {"direction": "RE", "attempts": 3, "yards": 9, "ypa": 3.0},
                ],
                [
                    {"direction": "ML", "attempts": 5, "yards": 35, "ypa": 7.0},
                    {"direction": "MR", "attempts": 3, "yards": 18, "ypa": 6.0},
                    {"direction": "LE", "attempts": 2, "yards": 6, "ypa": 3.0},
                ],
                [
                    {"direction": "LE", "attempts": 1, "yards": 3, "ypa": 3.0},
                ],
            ],
        }
    )


def _historical_window_blocking_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2022, 2022, 2022, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "game_id": [11, 12, 13, 14],
            "gap_snap_counts_run_play": [40, 39, 38, 2],
            "zone_snap_counts_run_play": [1, 1, 1, 5],
            "gap_snap_counts_run_block": [40, 39, 38, 2],
            "zone_snap_counts_run_block": [1, 1, 1, 5],
            "gap_grades_run_block": [68.0, 67.0, 69.0, 58.0],
            "zone_grades_run_block": [58.0, 57.0, 59.0, 62.0],
        }
    )


def _team_blend_rushing_direction_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2023, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "player_id": [101, 101, 101, 101],
            "position": ["RB", "RB", "RB", "RB"],
            "game_id": [21, 22, 23, 24],
            "directions": [
                [
                    {"direction": "ML", "attempts": 7, "yards": 42, "ypa": 6.0},
                    {"direction": "MR", "attempts": 5, "yards": 25, "ypa": 5.0},
                ],
                [
                    {"direction": "ML", "attempts": 6, "yards": 30, "ypa": 5.0},
                    {"direction": "MR", "attempts": 4, "yards": 18, "ypa": 4.5},
                ],
                [
                    {"direction": "ML", "attempts": 5, "yards": 20, "ypa": 4.0},
                    {"direction": "MR", "attempts": 3, "yards": 12, "ypa": 4.0},
                ],
                [
                    {"direction": "ML", "attempts": 6, "yards": 24, "ypa": 4.0},
                    {"direction": "MR", "attempts": 4, "yards": 16, "ypa": 4.0},
                ],
            ],
        }
    )


def _team_blend_blocking_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2023, 2024],
            "week": [7, 8, 9, 3],
            "team": ["TEN", "TEN", "TEN", "TEN"],
            "game_id": [21, 22, 23, 24],
            "gap_snap_counts_run_play": [28, 27, 26, 28],
            "zone_snap_counts_run_play": [4, 5, 4, 4],
            "gap_snap_counts_run_block": [28, 27, 26, 28],
            "zone_snap_counts_run_block": [4, 5, 4, 4],
            "gap_grades_run_block": [72.0, 71.0, 73.0, 40.0],
            "zone_grades_run_block": [55.0, 54.0, 56.0, 80.0],
        }
    )


def _non_immediate_prior_rushing_direction_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2021, 2021, 2022, 2022, 2024],
            "week": [7, 8, 7, 8, 3],
            "team": ["TEN", "TEN", "TEN", "TEN", "TEN"],
            "player_id": [101, 101, 101, 101, 101],
            "position": ["RB", "RB", "RB", "RB", "RB"],
            "game_id": [31, 32, 41, 42, 51],
            "directions": [
                [
                    {"direction": "LE", "attempts": 8, "yards": 48, "ypa": 6.0},
                    {"direction": "RE", "attempts": 6, "yards": 30, "ypa": 5.0},
                ],
                [
                    {"direction": "LE", "attempts": 7, "yards": 35, "ypa": 5.0},
                    {"direction": "RE", "attempts": 5, "yards": 20, "ypa": 4.0},
                ],
                [
                    {"direction": "ML", "attempts": 8, "yards": 64, "ypa": 8.0},
                    {"direction": "MR", "attempts": 6, "yards": 36, "ypa": 6.0},
                ],
                [
                    {"direction": "ML", "attempts": 6, "yards": 42, "ypa": 7.0},
                    {"direction": "MR", "attempts": 4, "yards": 20, "ypa": 5.0},
                ],
                [
                    {"direction": "LE", "attempts": 1, "yards": 3, "ypa": 3.0},
                ],
            ],
        }
    )


def _non_immediate_prior_blocking_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2021, 2021, 2022, 2022, 2024],
            "week": [7, 8, 7, 8, 3],
            "team": ["TEN", "TEN", "TEN", "TEN", "TEN"],
            "game_id": [31, 32, 41, 42, 51],
            "gap_snap_counts_run_play": [1, 1, 40, 39, 2],
            "zone_snap_counts_run_play": [18, 17, 1, 1, 5],
            "gap_snap_counts_run_block": [1, 1, 40, 39, 2],
            "zone_snap_counts_run_block": [18, 17, 1, 1, 5],
            "gap_grades_run_block": [55.0, 56.0, 68.0, 67.0, 58.0],
            "zone_grades_run_block": [66.0, 65.0, 58.0, 57.0, 62.0],
        }
    )


def test_compute_returns_empty_when_crosswalk_is_missing():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(loader, RbSchemeFitConfig(enabled=True))

    factors = engine.compute(
        roster=_make_roster("TEN"),
        pff_crosswalk={},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert factors == {}


def test_compute_rewards_interior_back_on_gap_heavy_team():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.50,
            min_attempts=10,
            min_games=2,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert "ten_rb" in factors
    assert factors["ten_rb"].rushing_yards_factor > 1.0


def test_compute_ignores_rare_buckets_and_returns_neutral_when_no_classified_attempts():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        pl.DataFrame(
            {
                "season": [2024],
                "week": [3],
                "team": ["TEN"],
                "player_id": [101],
                "position": ["RB"],
                "game_id": [2],
                "directions": [[
                    {"direction": "JS-L", "attempts": 4, "yards": 20, "ypa": 5.0},
                    {"direction": "EA-R", "attempts": 3, "yards": 12, "ypa": 4.0},
                ]],
            }
        )
        if facet == "rushing_direction"
        else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(enabled=True, min_attempts=5, min_games=1),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2024],
        target_season=2024,
        max_week=4,
    )

    assert factors == {}


def test_compute_uses_previous_season_for_early_blend():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _rushing_direction_df() if facet == "rushing_direction" else _offense_run_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.50,
            min_attempts=20,
            min_games=4,
            early_season_blend=True,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert factors["ten_rb"].rushing_yards_factor > 1.0


def test_compute_falls_back_to_full_historical_window_when_current_and_immediate_previous_are_insufficient():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _historical_window_rushing_direction_df()
        if facet == "rushing_direction"
        else _historical_window_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.80,
            min_attempts=20,
            min_games=3,
            early_season_blend=True,
            scheme_usage_weight=1.0,
            blocking_alignment_weight=0.0,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2022, 2024],
        target_season=2024,
        max_week=4,
    )

    assert "ten_rb" in factors
    assert factors["ten_rb"].rushing_yards_factor > 1.0


def test_compute_blends_previous_team_blocking_grades_when_current_season_is_early():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _team_blend_rushing_direction_df()
        if facet == "rushing_direction"
        else _team_blend_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.50,
            min_attempts=10,
            min_games=4,
            scheme_usage_weight=0.0,
            blocking_alignment_weight=1.0,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2023, 2024],
        target_season=2024,
        max_week=4,
    )

    assert "ten_rb" in factors
    assert factors["ten_rb"].rushing_yards_factor > 1.0


def test_compute_does_not_blend_with_non_immediate_prior_season():
    loader = MagicMock()
    loader.load_facet.side_effect = lambda facet, seasons: (
        _non_immediate_prior_rushing_direction_df()
        if facet == "rushing_direction"
        else _non_immediate_prior_blocking_df()
    )
    engine = RbSchemeFitEngine(
        loader,
        RbSchemeFitConfig(
            enabled=True,
            rush_yards_sensitivity=0.80,
            min_attempts=20,
            min_games=3,
            early_season_blend=True,
            scheme_usage_weight=1.0,
            blocking_alignment_weight=0.0,
            factor_clamp=(0.90, 1.10),
        ),
    )

    factors = engine.compute(
        roster=_make_roster("TEN", rb_id="ten_rb"),
        pff_crosswalk={101: "ten_rb"},
        training_seasons=[2021, 2022, 2024],
        target_season=2024,
        max_week=4,
    )

    assert "ten_rb" in factors
    assert factors["ten_rb"].rushing_yards_factor == pytest.approx(1.0453601789709173)


def test_previous_season_rows_requires_immediate_prior_season():
    loader = MagicMock()
    engine = RbSchemeFitEngine(loader, RbSchemeFitConfig(enabled=True))

    rows = pl.DataFrame(
        {
            "season": [2021, 2022, 2024],
            "game_id": [1, 2, 3],
        }
    )

    previous_rows = engine._previous_season_rows(rows, target_season=2024)

    assert previous_rows.is_empty()
