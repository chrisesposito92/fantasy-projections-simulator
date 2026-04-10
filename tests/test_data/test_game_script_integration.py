"""Integration tests for GameScript wiring in GameContextBuilder."""

from unittest.mock import patch

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.game_script import GameScriptConfig


def test_builder_accepts_game_script_config_and_defers_engine_creation():
    config = GameScriptConfig(enabled=True)

    builder = GameContextBuilder(game_script_config=config)

    assert builder._game_script_config == config
    assert builder._game_script_engine is None


def test_dual_arm_builder_creation_threads_game_script_config_to_both_arms():
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
    for call in mock_builder.call_args_list:
        assert call.kwargs["game_script_config"] == config
