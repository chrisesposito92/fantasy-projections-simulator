"""Integration test for TdTendencyEngine in GameContextBuilder."""

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.td_tendency import TdTendencyConfig


class TestTdTendencyInGameContext:

    def test_builder_accepts_td_tendency_config(self):
        config = TdTendencyConfig(enabled=False)
        builder = GameContextBuilder(td_tendency_config=config)
        assert builder._td_tendency_engine is None

    def test_builder_creates_engine_when_enabled(self):
        config = TdTendencyConfig(enabled=True)
        builder = GameContextBuilder(td_tendency_config=config)
        assert builder._td_tendency_engine is not None
