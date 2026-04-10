"""Integration tests for GameScript wiring in GameContextBuilder."""

from unittest.mock import MagicMock, patch

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.game_script import GameScriptConfig, GameScriptProfile


def test_builder_accepts_game_script_config_and_creates_engine_when_enabled():
    config = GameScriptConfig(enabled=True)

    builder = GameContextBuilder(game_script_config=config)

    assert builder._game_script_config == config
    assert builder._game_script_engine is not None


def test_dual_arm_builder_creation_only_threads_game_script_config_to_on_arm():
    config = GameScriptConfig(enabled=True)

    with patch("fantasy_sim.validation.parallel.GameContextBuilder") as mock_builder:
        from fantasy_sim.validation.parallel import _create_builders

        _create_builders(
            cache_dir="cache",
            pff_config=None,
            weather_config=None,
            vegas_config=None,
            props_config=None,
            usage_config=None,
            game_script_config=config,
            td_tendency_config=None,
            dual_arm=True,
        )

    assert mock_builder.call_count == 2
    assert "game_script_config" not in mock_builder.call_args_list[0].kwargs
    assert mock_builder.call_args_list[1].kwargs["game_script_config"] == config


def test_build_game_attaches_game_script_profiles(expanded_pbp, sample_rosters):
    config = GameScriptConfig(enabled=True)
    builder = GameContextBuilder(game_script_config=config)
    builder._game_script_engine = MagicMock()
    builder._game_script_engine.compute.side_effect = [
        GameScriptProfile(team="KC", trailing_late_pass_rate_factor=1.10),
        GameScriptProfile(team="BUF", trailing_late_pass_rate_factor=1.05),
    ]

    home_dists, away_dists, _, _ = builder.build_game(
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=3,
        pbp=expanded_pbp,
        rosters=sample_rosters,
        training_seasons=[2024],
    )

    assert home_dists.game_script_config is config
    assert away_dists.game_script_config is config
    assert home_dists.game_script_profile.team == "KC"
    assert away_dists.game_script_profile.team == "BUF"
