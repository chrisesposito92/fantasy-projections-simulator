"""Load weather configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.weather.models import (
    PrecipitationConfig,
    TemperatureConfig,
    WeatherConfig,
    WindConfig,
)


def load_weather_config(config: dict) -> WeatherConfig:
    """Extract weather config from the full defaults config dict."""
    raw = config.get("weather", {})
    if not raw:
        return WeatherConfig()

    wind_raw = raw.get("wind", {})
    wind = WindConfig(
        threshold_mph=wind_raw.get("threshold_mph", 10),
        fg_sensitivity=wind_raw.get("fg_sensitivity", 0.008),
        fg_50_plus_multiplier=wind_raw.get("fg_50_plus_multiplier", 2.5),
        pass_yards_sensitivity=wind_raw.get("pass_yards_sensitivity", 0.004),
        int_rate_sensitivity=wind_raw.get("int_rate_sensitivity", 0.003),
        xp_sensitivity=wind_raw.get("xp_sensitivity", 0.002),
    )

    temp_raw = raw.get("temperature", {})
    temperature = TemperatureConfig(
        threshold_f=temp_raw.get("threshold_f", 35),
        fumble_rate_sensitivity=temp_raw.get("fumble_rate_sensitivity", 0.003),
    )

    precip_raw = raw.get("precipitation", {})
    precipitation = PrecipitationConfig(
        catch_rate_sensitivity=precip_raw.get("catch_rate_sensitivity", 0.03),
        fumble_rate_sensitivity=precip_raw.get("fumble_rate_sensitivity", 0.02),
        fg_sensitivity=precip_raw.get("fg_sensitivity", 0.015),
        pass_yards_sensitivity=precip_raw.get("pass_yards_sensitivity", 0.008),
    )

    clamp = raw.get("factor_clamp", [0.80, 1.20])

    return WeatherConfig(
        enabled=raw.get("enabled", False),
        wind=wind,
        temperature=temperature,
        precipitation=precipitation,
        factor_clamp=tuple(clamp),
        forecast_ttl_hours=raw.get("forecast_ttl_hours", 6),
    )
