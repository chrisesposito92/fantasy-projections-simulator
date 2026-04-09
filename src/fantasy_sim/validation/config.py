"""Config resolution for A/B validation.

Replaces the mode-based config system with defaults.yaml + dot-notation overrides.
"""

from __future__ import annotations

import copy

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.weather.config import load_weather_config
from fantasy_sim.data.vegas.config import load_vegas_config, load_props_config
from fantasy_sim.data.usage.config import load_usage_config


def _parse_value(s: str) -> bool | int | float | str:
    """Parse a CLI string value to its Python type.

    Handles: 'true'/'false' -> bool, integers, floats, else str.
    """
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
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
    props_config, usage_config. Each value is the config dataclass if
    enabled, or None if disabled.
    """
    pff = load_pff_config(config)
    weather = load_weather_config(config)
    vegas = load_vegas_config(config)
    props = load_props_config(config)
    usage = load_usage_config(config)
    return {
        "pff_config": pff if pff.enabled else None,
        "weather_config": weather if weather.enabled else None,
        "vegas_config": vegas if vegas.enabled else None,
        "props_config": props if props.enabled else None,
        "usage_config": usage if usage.enabled else None,
    }


def build_bare_engine_configs() -> dict:
    """Return engine configs dict with all engines disabled (None)."""
    return {
        "pff_config": None,
        "weather_config": None,
        "vegas_config": None,
        "props_config": None,
        "usage_config": None,
    }
