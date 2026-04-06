"""Tests for weather factor computation engine."""

import pytest

from fantasy_sim.data.weather.engine import compute_weather_factors
from fantasy_sim.data.weather.models import (
    GameWeather,
    WeatherConfig,
    WeatherContext,
)


class TestComputeWeatherFactors:
    def test_calm_conditions_neutral(self):
        """No wind, warm, dry -> all factors 1.0."""
        gw = GameWeather(wind_speed_mph=5.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())
        assert ctx.fg_accuracy_factor == {"0_39": 1.0, "40_49": 1.0, "50_plus": 1.0}
        assert ctx.xp_accuracy_factor == 1.0
        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.fumble_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0

    def test_wind_above_threshold(self):
        """20 mph wind with threshold=10 -> 10 mph excess."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.92, abs=0.001)
        assert ctx.fg_accuracy_factor["40_49"] == pytest.approx(0.92, abs=0.001)
        assert ctx.fg_accuracy_factor["50_plus"] == pytest.approx(0.80, abs=0.001)
        assert ctx.xp_accuracy_factor == pytest.approx(0.98, abs=0.001)
        assert ctx.pass_yards_factor == pytest.approx(0.96, abs=0.001)
        assert ctx.int_rate_factor == pytest.approx(1.03, abs=0.001)

    def test_wind_below_threshold_no_effect(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=10.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["0_39"] == 1.0

    def test_cold_temperature_fumbles(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=20.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fumble_rate_factor == pytest.approx(1.045, abs=0.001)

    def test_warm_temperature_no_effect(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=50.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fumble_rate_factor == 1.0

    def test_precipitation_effects(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.catch_rate_factor == pytest.approx(0.985, abs=0.001)
        assert ctx.fumble_rate_factor == pytest.approx(1.01, abs=0.001)
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.9925, abs=0.001)
        assert ctx.pass_yards_factor == pytest.approx(0.996, abs=0.001)

    def test_combined_wind_and_rain(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=72.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.92 * 0.9925, abs=0.001)
        assert ctx.pass_yards_factor == pytest.approx(0.96 * 0.996, abs=0.001)

    def test_combined_cold_and_rain_fumbles(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=20.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fumble_rate_factor == pytest.approx(1.045 * 1.01, abs=0.001)

    def test_factor_clamping(self):
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=50.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["50_plus"] == 0.80

    def test_raw_weather_attached(self):
        gw = GameWeather(wind_speed_mph=15.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())
        assert ctx.raw is gw

    def test_zero_everything_neutral(self):
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())
        assert ctx.catch_rate_factor == 1.0
        assert ctx.fumble_rate_factor == 1.0

    def test_custom_clamp(self):
        cfg = WeatherConfig(factor_clamp=(0.90, 1.10))
        gw = GameWeather(wind_speed_mph=50.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["50_plus"] >= 0.90
