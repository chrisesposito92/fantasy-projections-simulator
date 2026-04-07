"""Open-Meteo weather provider with local JSON cache."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from fantasy_sim.data.weather.models import GameWeather

logger = logging.getLogger(__name__)

_HISTORICAL_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HOURLY_PARAMS = "temperature_2m,wind_speed_10m,precipitation,snowfall"

# Unit conversions
_KMH_TO_MPH = 0.621371
_MM_TO_INCHES = 0.0393701


def _c_to_f(celsius: float) -> float:
    return celsius * 9.0 / 5.0 + 32.0


class WeatherProvider:
    """Fetches game-time weather from Open-Meteo with local JSON cache.

    Historical dates use the archive API; future dates use the forecast API.
    Results are cached as JSON files at ``cache_dir``, one per unique
    (latitude, longitude, date) lookup.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        forecast_ttl_hours: int = 6,
    ) -> None:
        self._cache_dir = cache_dir or Path.home() / ".fantasy-sim" / "weather"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._forecast_ttl_hours = forecast_ttl_hours

    def _cache_path(self, lat: float, lon: float, game_date: date) -> Path:
        """Deterministic cache filename from coordinates + date."""
        lat_s = f"{lat:.2f}".replace("-", "n")
        lon_s = f"{lon:.2f}".replace("-", "n")
        return self._cache_dir / f"{lat_s}_{lon_s}_{game_date.isoformat()}.json"

    def _read_cache(self, path: Path, game_date: date) -> GameWeather | None:
        """Read cached weather, respecting TTL for forecasts."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        # Stale forecast: game is now in the past but was cached from a forecast.
        # Refetch so the historical archive endpoint provides actual weather.
        source = data.get("source", "historical")
        if game_date < date.today() and source == "forecast":
            return None

        # Historical data is immutable — always valid
        if game_date < date.today():
            try:
                return GameWeather(**{k: data[k] for k in GameWeather.__dataclass_fields__})
            except (KeyError, TypeError):
                path.unlink(missing_ok=True)
                return None

        # Forecast data — check TTL
        fetched_at = data.get("fetched_at")
        if fetched_at:
            try:
                fetched = datetime.fromisoformat(fetched_at)
                if fetched.tzinfo is None:
                    fetched = fetched.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
                if age_hours < self._forecast_ttl_hours:
                    return GameWeather(**{k: data[k] for k in GameWeather.__dataclass_fields__})
            except (ValueError, KeyError, TypeError):
                path.unlink(missing_ok=True)
                return None
        return None

    def _write_cache(self, path: Path, gw: GameWeather, game_date: date) -> None:
        """Write weather result to cache with timestamp and source tag."""
        is_historical = game_date < date.today()
        data = {
            "wind_speed_mph": gw.wind_speed_mph,
            "temperature_f": gw.temperature_f,
            "precipitation_inches": gw.precipitation_inches,
            "precipitation_type": gw.precipitation_type,
            "source": "historical" if is_historical else "forecast",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(data, indent=2))

    def get_weather(
        self,
        latitude: float,
        longitude: float,
        game_date: date,
        game_hour: int,
    ) -> GameWeather | None:
        """Fetch weather for a location and date, using cache when available.

        Returns GameWeather with converted units, or None on error.
        """
        cache_path = self._cache_path(latitude, longitude, game_date)

        cached = self._read_cache(cache_path, game_date)
        if cached is not None:
            return cached

        try:
            gw = self._fetch(latitude, longitude, game_date, game_hour)
        except Exception:
            logger.warning(
                "Weather API error for (%.2f, %.2f) on %s", latitude, longitude, game_date,
                exc_info=True,
            )
            return None

        self._write_cache(cache_path, gw, game_date)
        return gw

    def _fetch(
        self,
        latitude: float,
        longitude: float,
        game_date: date,
        game_hour: int,
    ) -> GameWeather:
        """Call Open-Meteo API and parse response into GameWeather."""
        is_historical = game_date < date.today()
        base_url = _HISTORICAL_URL if is_historical else _FORECAST_URL

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": _HOURLY_PARAMS,
            "start_date": game_date.isoformat(),
            "end_date": game_date.isoformat(),
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timezone": "America/New_York",
        }

        resp = httpx.get(base_url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

        hourly = data["hourly"]
        # Extract 3-hour game window (kickoff to kickoff + 3h)
        start_idx = max(0, min(game_hour, 23))
        end_idx = min(start_idx + 3, len(hourly["time"]))

        temps = hourly["temperature_2m"][start_idx:end_idx]
        winds = hourly["wind_speed_10m"][start_idx:end_idx]
        precips = hourly["precipitation"][start_idx:end_idx]
        snows = hourly["snowfall"][start_idx:end_idx]

        avg_temp_c = sum(temps) / len(temps) if temps else 20.0
        avg_wind_kmh = sum(winds) / len(winds) if winds else 0.0
        total_precip_mm = sum(precips)
        total_snow_cm = sum(snows)

        # Determine precipitation type
        if total_precip_mm <= 0:
            precip_type = "none"
        elif total_snow_cm > 0:
            precip_type = "snow"
        else:
            precip_type = "rain"

        return GameWeather(
            wind_speed_mph=round(avg_wind_kmh * _KMH_TO_MPH, 1),
            temperature_f=round(_c_to_f(avg_temp_c), 1),
            precipitation_inches=round(total_precip_mm * _MM_TO_INCHES, 3),
            precipitation_type=precip_type,
        )
