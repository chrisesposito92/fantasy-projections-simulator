"""Configuration loader for the Usage intelligence layer."""

from __future__ import annotations

from fantasy_sim.data.usage.models import (
    UsageConfig, SnapConfig, CpoeConfig, NgsConfig, RouteRateConfig,
)


def load_usage_config(defaults: dict) -> UsageConfig:
    """Extract UsageConfig from the full defaults config dict.

    Reads from defaults["usage"]. Returns UsageConfig(enabled=False)
    if the key is missing.

    Args:
        defaults: The full defaults.yaml dict (or a subset with a "usage" key).

    Returns:
        UsageConfig populated from the YAML, or UsageConfig(enabled=False) if
        the "usage" key is missing.
    """
    usage = defaults.get("usage")
    if not usage:
        return UsageConfig(enabled=False)

    snap_d = usage.get("snap", {})
    cpoe_d = usage.get("cpoe", {})
    ngs_d = usage.get("ngs", {})
    rr_d = usage.get("route_rate", {})

    return UsageConfig(
        enabled=usage.get("enabled", True),
        snap=SnapConfig(
            prior_strength=snap_d.get("prior_strength", 8.0),
            min_games=snap_d.get("min_games", 4),
            factor_clamp=tuple(snap_d.get("factor_clamp", [0.70, 1.30])),
            manual_crosswalk=snap_d.get("manual_crosswalk", {}),
        ),
        cpoe=CpoeConfig(
            enabled=cpoe_d.get("enabled", True),
            sensitivity=cpoe_d.get("sensitivity", 0.30),
            min_plays=cpoe_d.get("min_plays", 20),
            cpoe_league_avg=cpoe_d.get("cpoe_league_avg", 1.0),
            cpoe_league_std=cpoe_d.get("cpoe_league_std", 4.0),
        ),
        ngs=NgsConfig(
            enabled=ngs_d.get("enabled", True),
            separation_sensitivity=ngs_d.get("separation_sensitivity", 0.04),
            cushion_sensitivity=ngs_d.get("cushion_sensitivity", -0.03),
            factor_clamp=tuple(ngs_d.get("factor_clamp", [0.95, 1.05])),
            min_targets=ngs_d.get("min_targets", 10),
        ),
        route_rate=RouteRateConfig(
            enabled=rr_d.get("enabled", True),
            sensitivity=rr_d.get("sensitivity", 0.5),
            min_routes=rr_d.get("min_routes", 10),
        ),
    )
