"""Load Vegas configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig


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


def load_props_config(defaults: dict) -> PropsConfig:
    """Extract PropsConfig from the full defaults config dict.

    Reads from defaults["vegas"]["props"]. Returns PropsConfig(enabled=False)
    if the key is missing (graceful fallback).

    Args:
        defaults: The full defaults.yaml dict (or subset with "vegas" key).

    Returns:
        PropsConfig populated from YAML, or PropsConfig(enabled=False) if
        the "vegas.props" section is absent.
    """
    vegas = defaults.get("vegas", {})
    props = vegas.get("props")
    if not props:
        return PropsConfig(enabled=False)

    markets_raw = props.get("markets")
    if markets_raw is None:
        from fantasy_sim.data.vegas.models import PropsConfig as _PC
        markets_raw = _PC.__dataclass_fields__["markets"].default_factory()

    return PropsConfig(
        enabled=props.get("enabled", False),
        prior_strength=float(props.get("prior_strength", 10.0)),
        min_divergence=float(props.get("min_divergence", 0.005)),
        cache_dir=props.get("cache_dir"),
        api_key_env=props.get("api_key_env", "ODDS_API_KEY"),
        fuzzy_threshold=float(props.get("fuzzy_threshold", 0.85)),
        markets=list(markets_raw),
    )
