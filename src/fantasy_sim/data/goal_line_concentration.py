"""Configuration loader for goal-line concentration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoalLineConcentrationConfig:
    """Configuration for goal-line concentration selection behavior."""

    enabled: bool = False


def load_goal_line_concentration_config(defaults: dict) -> GoalLineConcentrationConfig:
    """Extract GoalLineConcentrationConfig from the full defaults config dict."""
    raw = defaults.get("goal_line_concentration")
    if not raw:
        return GoalLineConcentrationConfig(enabled=False)
    return GoalLineConcentrationConfig(enabled=raw.get("enabled", False))
