from __future__ import annotations

from unittest.mock import Mock

import polars as pl
import pytest

from fantasy_sim.data.tracking.loader import TrackingInputLoader


def _receiver_schema() -> list[str]:
    return [
        "team",
        "player_id",
        "targets",
        "catchable_rate",
        "contested_rate",
        "mean_air_yards",
    ]


def _rb_schema() -> list[str]:
    return [
        "team",
        "player_id",
        "attempts",
        "no_huddle_rate",
        "play_action_rate",
        "rush_yoe_per_att",
    ]


def _qb_schema() -> list[str]:
    return [
        "team",
        "player_id",
        "dropbacks",
        "pressure_rate",
        "no_huddle_rate",
        "play_action_rate",
        "blitz_rate",
        "avg_time_to_throw",
        "aggressiveness",
        "cpoe",
    ]


def test_load_receiver_features_joins_ftn_flags_to_targeted_receiver():
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "game_id": ["2024_01_KC_BUF", "2024_02_KC_BAL", "2024_02_KC_BAL", "2024_03_KC_LV"],
            "play_id": [11, 21, 22, 31],
            "season": [2024, 2024, 2024, 2024],
            "week": [1, 2, 2, 3],
            "posteam": ["KC", "KC", "KC", "KC"],
            "receiver_player_id": ["gsis-wr1", "gsis-wr1", "gsis-wr2", "gsis-wr1"],
            "air_yards": [10.0, 20.0, 5.0, 40.0],
            "pass_attempt": [1, 1, 1, 1],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["2024_01_KC_BUF", "2024_02_KC_BAL", "2024_02_KC_BAL", "2024_03_KC_LV"],
            "nflverse_play_id": [11, 21, 22, 31],
            "is_catchable_ball": [1, 0, 1, 0],
            "is_contested_ball": [0, 1, 0, 1],
            "is_no_huddle": [0, 1, 0, 1],
            "is_play_action": [0, 1, 0, 1],
            "n_blitzers": [0, 1, 0, 2],
        }
    )

    feature_loader = TrackingInputLoader(loader=loader, window_weeks=4)

    result = feature_loader.load_receiver_features(season=2024, week=3)

    assert result.columns == _receiver_schema()
    assert result.sort(["team", "player_id"]).to_dicts() == [
        {
            "team": "KC",
            "player_id": "gsis-wr1",
            "targets": 2,
            "catchable_rate": 0.5,
            "contested_rate": 0.5,
            "mean_air_yards": 15.0,
        },
        {
            "team": "KC",
            "player_id": "gsis-wr2",
            "targets": 1,
            "catchable_rate": 1.0,
            "contested_rate": 0.0,
            "mean_air_yards": 5.0,
        },
    ]


def test_load_receiver_features_uses_only_prior_weeks():
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "game_id": ["2024_02_KC_BAL", "2024_03_KC_LV"],
            "play_id": [21, 31],
            "season": [2024, 2024],
            "week": [2, 3],
            "posteam": ["KC", "KC"],
            "receiver_player_id": ["gsis-wr1", "gsis-wr1"],
            "air_yards": [12.0, 40.0],
            "pass_attempt": [1, 1],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["2024_02_KC_BAL", "2024_03_KC_LV"],
            "nflverse_play_id": [21, 31],
            "is_catchable_ball": [1, 0],
            "is_contested_ball": [0, 1],
        }
    )

    result = TrackingInputLoader(loader=loader, window_weeks=4).load_receiver_features(
        season=2024,
        week=3,
    )

    assert result.to_dicts() == [
        {
            "team": "KC",
            "player_id": "gsis-wr1",
            "targets": 1,
            "catchable_rate": 1.0,
            "contested_rate": 0.0,
            "mean_air_yards": 12.0,
        }
    ]


@pytest.mark.parametrize(
    ("ftn_df", "label"),
    [
        (pl.DataFrame(), "empty_ftn"),
        (
            pl.DataFrame(
                {
                    "nflverse_game_id": ["2024_02_KC_BAL"],
                    "nflverse_play_id": [21],
                    "is_no_huddle": [1],
                }
            ),
            "missing_receiver_flags",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_load_receiver_features_returns_empty_schema_when_ftn_unusable(ftn_df, label):
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "game_id": ["2024_02_KC_BAL"],
            "play_id": [21],
            "season": [2024],
            "week": [2],
            "posteam": ["KC"],
            "receiver_player_id": ["gsis-wr1"],
            "air_yards": [12.0],
            "pass_attempt": [1],
        }
    )
    loader.load_ftn_charting.return_value = ftn_df

    result = TrackingInputLoader(loader=loader, window_weeks=4).load_receiver_features(
        season=2024,
        week=3,
    )

    assert result.columns == _receiver_schema()
    assert result.is_empty()


def test_load_rb_features_aggregates_and_uses_only_prior_weeks():
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "game_id": ["2024_04_KC_DEN", "2024_04_KC_DEN", "2024_05_KC_LV"],
            "play_id": [41, 42, 51],
            "season": [2024, 2024, 2024],
            "week": [4, 4, 5],
            "posteam": ["KC", "KC", "KC"],
            "rusher_player_id": ["gsis-rb1", "gsis-rb1", "gsis-rb1"],
            "rush_attempt": [1, 1, 1],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["2024_04_KC_DEN", "2024_04_KC_DEN", "2024_05_KC_LV"],
            "nflverse_play_id": [41, 42, 51],
            "is_no_huddle": [1, 0, 1],
            "is_play_action": [0, 1, 1],
        }
    )
    loader.load_nextgen_stats.return_value = pl.DataFrame(
        {
            "player_gsis_id": ["gsis-rb1", "gsis-rb1"],
            "season": [2024, 2024],
            "week": [4, 5],
            "rush_yards_over_expected_per_att": [0.8, 9.9],
        }
    )

    result = TrackingInputLoader(loader=loader, window_weeks=4).load_rb_features(
        season=2024,
        week=5,
    )

    assert result.columns == _rb_schema()
    assert result.to_dicts() == [
        {
            "team": "KC",
            "player_id": "gsis-rb1",
            "attempts": 2,
            "no_huddle_rate": 0.5,
            "play_action_rate": 0.5,
            "rush_yoe_per_att": 0.8,
        }
    ]
    loader.load_nextgen_stats.assert_called_once_with([2024], stat_type="rushing")


def test_load_qb_features_uses_only_prior_weeks():
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame(
        {
            "game_id": [
                "2024_04_KC_DEN",
                "2024_04_KC_DEN",
                "2024_05_KC_LV",
            ],
            "play_id": [41, 42, 51],
            "season": [2024, 2024, 2024],
            "week": [4, 4, 5],
            "posteam": ["KC", "KC", "KC"],
            "passer_player_id": ["gsis-qb1", "gsis-qb1", "gsis-qb1"],
            "pass_attempt": [1, 1, 1],
        }
    )
    loader.load_participation.return_value = pl.DataFrame(
        {
            "nflverse_game_id": [
                "2024_04_KC_DEN",
                "2024_04_KC_DEN",
                "2024_04_KC_DEN",
                "2024_05_KC_LV",
            ],
            "play_id": [41, 42, 99, 51],
            "season": [2024, 2024, 2024, 2024],
            "week": [4, 4, 4, 5],
            "team": ["KC", "KC", "KC", "KC"],
            "player_id": ["gsis-qb1", "gsis-qb1", "gsis-qb1", "gsis-qb1"],
            "was_pressure": [1, 0, 1, 1],
            "number_of_pass_rushers": [4, 4, 6, 5],
        }
    )
    loader.load_ftn_charting.return_value = pl.DataFrame(
        {
            "nflverse_game_id": ["2024_04_KC_DEN", "2024_04_KC_DEN", "2024_05_KC_LV"],
            "nflverse_play_id": [41, 42, 51],
            "is_no_huddle": [1, 0, 1],
            "is_play_action": [0, 1, 1],
            "n_blitzers": [1, 0, 3],
        }
    )
    loader.load_nextgen_stats.return_value = pl.DataFrame(
        {
            "player_gsis_id": ["gsis-qb1", "gsis-qb1"],
            "season": [2024, 2024],
            "week": [4, 5],
            "avg_time_to_throw": [2.8, 4.6],
            "aggressiveness": [0.17, 0.45],
            "completion_percentage_above_expectation": [6.0, -3.0],
        }
    )

    result = TrackingInputLoader(loader=loader, window_weeks=4).load_qb_features(
        season=2024,
        week=5,
    )

    assert result.columns == _qb_schema()
    assert result.to_dicts() == [
        {
            "team": "KC",
            "player_id": "gsis-qb1",
            "dropbacks": 2,
            "pressure_rate": 0.5,
            "no_huddle_rate": 0.5,
            "play_action_rate": 0.5,
            "blitz_rate": 0.5,
            "avg_time_to_throw": 2.8,
            "aggressiveness": 0.17,
            "cpoe": 6.0,
        }
    ]
    loader.load_pbp.assert_called_once_with([2024])
    loader.load_nextgen_stats.assert_called_once_with([2024], stat_type="passing")


@pytest.mark.parametrize(
    ("method_name", "schema"),
    [
        ("load_receiver_features", _receiver_schema()),
        ("load_rb_features", _rb_schema()),
        ("load_qb_features", _qb_schema()),
    ],
)
def test_public_loaders_return_empty_schema_on_empty_inputs(method_name, schema):
    loader = Mock()
    loader.load_pbp.return_value = pl.DataFrame()
    loader.load_ftn_charting.return_value = pl.DataFrame()
    loader.load_nextgen_stats.return_value = pl.DataFrame()
    loader.load_participation.return_value = pl.DataFrame()

    result = getattr(TrackingInputLoader(loader=loader, window_weeks=4), method_name)(
        season=2024,
        week=3,
    )

    assert result.columns == schema
    assert result.is_empty()
