"""Tests for goal-line concentration config loading."""

from fantasy_sim.data.goal_line_concentration import (
    GoalLineConcentrationConfig,
    load_goal_line_concentration_config,
)


class TestGoalLineConcentrationConfig:

    def test_default_config_is_disabled(self):
        config = GoalLineConcentrationConfig()
        assert config.enabled is False

    def test_load_enabled_from_dict(self):
        raw = {"goal_line_concentration": {"enabled": True}}
        config = load_goal_line_concentration_config(raw)
        assert config.enabled is True

    def test_missing_section_returns_disabled_config(self):
        config = load_goal_line_concentration_config({})
        assert config.enabled is False

    def test_empty_section_uses_disabled_default(self):
        config = load_goal_line_concentration_config({"goal_line_concentration": {}})
        assert config.enabled is False
