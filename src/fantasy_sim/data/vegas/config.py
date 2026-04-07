"""Load Vegas configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.vegas.models import VegasConfig


def load_vegas_config(defaults: dict) -> VegasConfig:
    """Extract Vegas config from the full defaults config dict.

    Args:
        defaults: The full defaults.yaml dict (or a subset with a "vegas" key).

    Returns:
        VegasConfig populated from the YAML, or VegasConfig(enabled=False) if
        the "vegas" key is missing.
    """
    vegas = defaults.get("vegas")
    if not vegas:
        return VegasConfig(enabled=False)

    itt_raw = vegas.get("itt", {})
    spread_raw = vegas.get("spread", {})

    itt_clamp_raw = itt_raw.get("factor_clamp", [0.88, 1.12])
    spread_clamp_raw = spread_raw.get("factor_clamp", [0.92, 1.08])

    return VegasConfig(
        enabled=vegas.get("enabled", False),
        itt_sensitivity=itt_raw.get("sensitivity", 0.06),
        itt_clamp=tuple(itt_clamp_raw),
        spread_sensitivity=spread_raw.get("sensitivity", 0.04),
        spread_clamp=tuple(spread_clamp_raw),
    )
