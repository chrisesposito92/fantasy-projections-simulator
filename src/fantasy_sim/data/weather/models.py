"""Data models for the weather engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WindConfig:
    """Configuration for wind-based adjustments."""
    threshold_mph: float = 10
    fg_sensitivity: float = 0.008
    fg_50_plus_multiplier: float = 2.5
    pass_yards_sensitivity: float = 0.004
    int_rate_sensitivity: float = 0.003
    xp_sensitivity: float = 0.002


@dataclass
class TemperatureConfig:
    """Configuration for temperature-based adjustments."""
    threshold_f: float = 35
    fumble_rate_sensitivity: float = 0.003


@dataclass
class PrecipitationConfig:
    """Configuration for precipitation-based adjustments."""
    catch_rate_sensitivity: float = 0.03
    fumble_rate_sensitivity: float = 0.02
    fg_sensitivity: float = 0.015
    pass_yards_sensitivity: float = 0.008


@dataclass
class WeatherConfig:
    """Top-level weather configuration."""
    enabled: bool = False
    wind: WindConfig = field(default_factory=WindConfig)
    temperature: TemperatureConfig = field(default_factory=TemperatureConfig)
    precipitation: PrecipitationConfig = field(default_factory=PrecipitationConfig)
    factor_clamp: tuple[float, float] = (0.80, 1.20)
    forecast_ttl_hours: int = 6


@dataclass(frozen=True)
class GameWeather:
    """Raw weather data for one game."""
    wind_speed_mph: float
    temperature_f: float
    precipitation_inches: float
    precipitation_type: str  # "none" | "rain" | "snow"


@dataclass
class WeatherContext:
    """Multiplicative factors derived from weather conditions.

    All factors centered on 1.0 (neutral). Values < 1.0 reduce the stat,
    values > 1.0 increase it. For "bad weather" stats like fumble_rate,
    > 1.0 means more fumbles.
    """
    fg_accuracy_factor: dict[str, float] = field(
        default_factory=lambda: {"0_39": 1.0, "40_49": 1.0, "50_plus": 1.0}
    )
    xp_accuracy_factor: float = 1.0
    catch_rate_factor: float = 1.0
    pass_yards_factor: float = 1.0
    fumble_rate_factor: float = 1.0
    int_rate_factor: float = 1.0
    raw: GameWeather | None = None
