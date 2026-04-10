"""Test that goal-line concentration config flows through validation pipeline."""

from fantasy_sim.validation.config import build_bare_engine_configs, build_engine_configs


class TestGoalLineConcentrationConfigResolution:

    def test_build_engine_configs_includes_goal_line_concentration(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "game_script": {"enabled": False},
            "td_tendency": {"enabled": False},
            "goal_line_concentration": {"enabled": True},
        }

        result = build_engine_configs(config)

        assert "goal_line_concentration_config" in result
        assert result["goal_line_concentration_config"] is not None
        assert result["goal_line_concentration_config"].enabled is True

    def test_disabled_goal_line_concentration_returns_none(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "game_script": {"enabled": False},
            "td_tendency": {"enabled": False},
            "goal_line_concentration": {"enabled": False},
        }

        result = build_engine_configs(config)

        assert result["goal_line_concentration_config"] is None

    def test_build_bare_engine_configs_includes_goal_line_concentration_none(self):
        result = build_bare_engine_configs()

        assert "goal_line_concentration_config" in result
        assert result["goal_line_concentration_config"] is None
