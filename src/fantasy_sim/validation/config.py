"""Config resolution for A/B validation.

Replaces the mode-based config system with defaults.yaml + dot-notation overrides.
"""

from __future__ import annotations

import copy

from fantasy_sim.data.market_history.config import load_market_history_config
from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config, load_props_config
from fantasy_sim.data.availability.config import load_availability_config
from fantasy_sim.data.role_trend.config import load_role_trend_config
from fantasy_sim.data.usage.config import load_usage_config
from fantasy_sim.data.tracking.config import load_tracking_config
from fantasy_sim.data.game_script import load_game_script_config
from fantasy_sim.data.goal_line_concentration import load_goal_line_concentration_config
from fantasy_sim.data.play_call_model import load_play_call_model_config
from fantasy_sim.data.target_selection import load_target_selection_config
from fantasy_sim.data.td_tendency import load_td_tendency_config


def _parse_value(s: str) -> bool | int | float | str | list:
    """Parse a CLI string value to its Python type.

    Handles: 'true'/'false' -> bool, [a,b,...] -> list of parsed values,
    integers, floats, else str.
    """
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # List syntax: [0.85,1.15] or [1,2,3]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(item.strip()) for item in inner.split(",")]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """Apply dot-notation overrides to a config dict.

    Each override is 'dotted.key.path=value'. Deep-copies config first
    so the original is never mutated.

    Raises KeyError if any key in the path doesn't exist (including the leaf).
    """
    config = copy.deepcopy(config)
    for override in overrides:
        key_path, raw_value = override.split("=", 1)
        keys = key_path.split(".")
        target = config
        for k in keys[:-1]:
            target = target[k]
        leaf = keys[-1]
        if leaf not in target:
            raise KeyError(
                f"Unknown config key '{key_path}': "
                f"'{leaf}' not found in {'.'.join(keys[:-1]) or 'root'}"
            )
        target[leaf] = _parse_value(raw_value)
    return config


def build_engine_configs(config: dict) -> dict:
    """Build all engine config dataclasses from a full config dict.

    Returns a dict with keys: pff_config, weather_config, vegas_config,
    props_config, usage_config, tracking_config, availability_config,
    role_trend_config, market_history_config, game_script_config,
    goal_line_concentration_config, td_tendency_config.
    Each value is the config dataclass if enabled, or None if disabled.
    """
    pff = load_pff_config(config)
    weather = load_weather_config(config)
    vegas = load_vegas_config(config)
    props = load_props_config(config)
    usage = load_usage_config(config)
    tracking = load_tracking_config(config)
    availability = load_availability_config(config)
    role_trend = load_role_trend_config(config)
    market_history = load_market_history_config(config)
    game_script = load_game_script_config(config)
    goal_line_concentration = load_goal_line_concentration_config(config)
    td_tendency = load_td_tendency_config(config)
    target_selection = load_target_selection_config(config)
    play_call_model = load_play_call_model_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
        "tracking_config": tracking if tracking.enabled else None,
        "availability_config": availability if availability.enabled else None,
        "role_trend_config": role_trend if role_trend.enabled else None,
        "market_history_config": market_history if market_history.enabled else None,
        "game_script_config": game_script if game_script.enabled else None,
        "goal_line_concentration_config": (
            goal_line_concentration if goal_line_concentration.enabled else None
        ),
        "td_tendency_config": td_tendency if td_tendency.enabled else None,
        "target_selection_config": target_selection if target_selection.enabled else None,
        "play_call_model_config": play_call_model if play_call_model.enabled else None,
    }


def build_bare_engine_configs() -> dict:
    """Return engine configs dict with all engines disabled (None)."""
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
        "tracking_config": None,
        "availability_config": None,
        "role_trend_config": None,
        "market_history_config": None,
        "game_script_config": None,
        "goal_line_concentration_config": None,
        "td_tendency_config": None,
        "target_selection_config": None,
        "play_call_model_config": None,
    }
