"""Tests for Open-Meteo weather provider with cache."""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fantasy_sim.data.weather.models import GameWeather
from fantasy_sim.data.weather.provider import WeatherProvider


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "weather"


@pytest.fixture
def provider(cache_dir):
    return WeatherProvider(cache_dir=cache_dir, forecast_ttl_hours=6)


def _mock_hourly_response(temp_c=25.0, wind_kmh=16.0, precip_mm=0.0, snowfall_cm=0.0):
    """Build a mock Open-Meteo hourly response dict."""
    return {
        "hourly": {
            "time": [f"2024-09-08T{h:02d}:00" for h in range(24)],
            "temperature_2m": [temp_c] * 24,
            "wind_speed_10m": [wind_kmh] * 24,
            "precipitation": [precip_mm] * 24,
            "snowfall": [snowfall_cm] * 24,
        }
    }


class TestWeatherProvider:
    def test_historical_endpoint(self, provider):
        """Past dates should use the archive API."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response()
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)

            url = mock_httpx.get.call_args[0][0]
            assert "archive-api.open-meteo.com" in url

    def test_forecast_endpoint(self, provider):
        """Future dates should use the forecast API."""
        future = date(2099, 1, 1)
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response()
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            provider.get_weather(39.0, -94.5, future, 17)

            url = mock_httpx.get.call_args[0][0]
            assert "api.open-meteo.com" in url

    def test_returns_game_weather(self, provider):
        """Should return a GameWeather with converted units."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response(
                temp_c=25.0, wind_kmh=16.0, precip_mm=2.5, snowfall_cm=0.0,
            )
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            gw = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)

            assert isinstance(gw, GameWeather)
            assert 76.0 <= gw.temperature_f <= 78.0
            assert 9.0 <= gw.wind_speed_mph <= 11.0
            assert gw.precipitation_type == "rain"

    def test_snow_detection(self, provider):
        """Snowfall > 0 should set precipitation_type to 'snow'."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response(
                temp_c=-5.0, precip_mm=3.0, snowfall_cm=2.0,
            )
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            gw = provider.get_weather(39.0, -94.5, date(2024, 12, 22), 17)
            assert gw.precipitation_type == "snow"

    def test_no_precipitation(self, provider):
        """Zero precipitation should be type 'none'."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response(
                precip_mm=0.0, snowfall_cm=0.0,
            )
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            gw = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)
            assert gw.precipitation_type == "none"


class TestWeatherCache:
    def test_cache_stores_result(self, provider, cache_dir):
        """First call stores JSON, second call reads from cache (no API)."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response()
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            gw1 = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)

        # Second call — httpx not patched, should use cache
        gw2 = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)
        assert gw2.wind_speed_mph == gw1.wind_speed_mph

    def test_cache_file_created(self, provider, cache_dir):
        """Cache file should exist after first call."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_resp = MagicMock()
            mock_resp.json.return_value = _mock_hourly_response()
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)

        json_files = list(cache_dir.glob("*.json"))
        assert len(json_files) == 1

    def test_api_error_returns_none(self, provider):
        """API errors should return None, not crash."""
        with patch("fantasy_sim.data.weather.provider.httpx") as mock_httpx:
            mock_httpx.get.side_effect = Exception("API timeout")

            result = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)
            assert result is None
