"""Tests for weather data models and config loading."""

import pytest

from fantasy_sim.data.weather.models import (
    GameWeather,
    PrecipitationConfig,
    TemperatureConfig,
    WeatherConfig,
    WeatherContext,
    WindConfig,
)


class TestWeatherConfig:
    def test_default_disabled(self):
        cfg = WeatherConfig()
        assert cfg.enabled is False

    def test_default_wind(self):
        cfg = WindConfig()
        assert cfg.threshold_mph == 10
        assert cfg.fg_sensitivity == 0.008
        assert cfg.fg_50_plus_multiplier == 2.5
        assert cfg.pass_yards_sensitivity == 0.004
        assert cfg.int_rate_sensitivity == 0.003
        assert cfg.xp_sensitivity == 0.002

    def test_default_temperature(self):
        cfg = TemperatureConfig()
        assert cfg.threshold_f == 35
        assert cfg.fumble_rate_sensitivity == 0.003

    def test_default_precipitation(self):
        cfg = PrecipitationConfig()
        assert cfg.catch_rate_sensitivity == 0.03
        assert cfg.fumble_rate_sensitivity == 0.02
        assert cfg.fg_sensitivity == 0.015
        assert cfg.pass_yards_sensitivity == 0.008

    def test_factor_clamp_default(self):
        cfg = WeatherConfig()
        assert cfg.factor_clamp == (0.80, 1.20)

    def test_forecast_ttl_default(self):
        cfg = WeatherConfig()
        assert cfg.forecast_ttl_hours == 6


class TestGameWeather:
    def test_create(self):
        gw = GameWeather(
            wind_speed_mph=15.0,
            temperature_f=28.0,
            precipitation_inches=0.3,
            precipitation_type="rain",
        )
        assert gw.wind_speed_mph == 15.0
        assert gw.temperature_f == 28.0
        assert gw.precipitation_inches == 0.3
        assert gw.precipitation_type == "rain"

    def test_frozen(self):
        gw = GameWeather(wind_speed_mph=10.0, temperature_f=50.0,
                         precipitation_inches=0.0, precipitation_type="none")
        with pytest.raises(AttributeError):
            gw.wind_speed_mph = 20.0


class TestWeatherContext:
    def test_neutral_default(self):
        ctx = WeatherContext()
        assert ctx.fg_accuracy_factor == {"0_39": 1.0, "40_49": 1.0, "50_plus": 1.0}
        assert ctx.xp_accuracy_factor == 1.0
        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0
        assert ctx.raw is None


from fantasy_sim.data.weather.config import load_weather_config


class TestLoadWeatherConfig:
    def test_empty_config(self):
        cfg = load_weather_config({})
        assert cfg.enabled is False
        assert cfg.wind.threshold_mph == 10

    def test_enabled_from_yaml(self):
        cfg = load_weather_config({"weather": {"enabled": True}})
        assert cfg.enabled is True

    def test_wind_overrides(self):
        cfg = load_weather_config({
            "weather": {
                "wind": {"threshold_mph": 15, "fg_sensitivity": 0.01},
            }
        })
        assert cfg.wind.threshold_mph == 15
        assert cfg.wind.fg_sensitivity == 0.01
        assert cfg.wind.fg_50_plus_multiplier == 2.5

    def test_temperature_overrides(self):
        cfg = load_weather_config({
            "weather": {
                "temperature": {"threshold_f": 40, "fumble_rate_sensitivity": 0.005},
            }
        })
        assert cfg.temperature.threshold_f == 40
        assert cfg.temperature.fumble_rate_sensitivity == 0.005

    def test_precipitation_overrides(self):
        cfg = load_weather_config({
            "weather": {
                "precipitation": {"catch_rate_sensitivity": 0.05},
            }
        })
        assert cfg.precipitation.catch_rate_sensitivity == 0.05

    def test_factor_clamp(self):
        cfg = load_weather_config({
            "weather": {"factor_clamp": [0.85, 1.15]},
        })
        assert cfg.factor_clamp == (0.85, 1.15)

    def test_forecast_ttl(self):
        cfg = load_weather_config({
            "weather": {"forecast_ttl_hours": 12},
        })
        assert cfg.forecast_ttl_hours == 12
