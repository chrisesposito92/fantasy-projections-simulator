"""Integration tests for GameScript wiring in GameContextBuilder."""

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.game_script import GameScriptConfig


def test_builder_accepts_game_script_config_and_defers_engine_creation():
    config = GameScriptConfig(enabled=True)

    builder = GameContextBuilder(game_script_config=config)

    assert builder._game_script_config == config
    assert builder._game_script_engine is None
