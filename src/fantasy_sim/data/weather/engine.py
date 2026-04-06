"""Weather engine — compute game-day adjustment factors from weather data."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fantasy_sim.data.weather.models import GameWeather, WeatherConfig, WeatherContext
from fantasy_sim.data.weather.provider import WeatherProvider
from fantasy_sim.data.weather.stadiums import get_stadium, is_indoor

logger = logging.getLogger(__name__)


def _compute_factor(
    value: float,
    threshold: float,
    sensitivity: float,
    clamp: tuple[float, float],
    *,
    direction: str = "above",
    effect: str = "negative",
) -> float:
    """Compute a single weather factor using threshold + linear scaling."""
    if direction == "above":
        excess = max(0.0, value - threshold)
    else:
        excess = max(0.0, threshold - value)

    if excess == 0.0:
        return 1.0

    shift = sensitivity * excess
    if effect == "negative":
        factor = 1.0 - shift
    else:
        factor = 1.0 + shift

    return max(clamp[0], min(clamp[1], factor))


def compute_weather_factors(
    weather: GameWeather,
    config: WeatherConfig,
) -> WeatherContext:
    """Compute all weather adjustment factors from raw weather data.

    Factors from different weather variables are multiplied together.
    """
    clamp = config.factor_clamp
    wind = config.wind
    temp = config.temperature
    precip = config.precipitation

    # --- Wind factors ---
    wind_excess = max(0.0, weather.wind_speed_mph - wind.threshold_mph)
    if wind_excess > 0:
        wind_fg_base = _compute_factor(
            weather.wind_speed_mph, wind.threshold_mph,
            wind.fg_sensitivity, clamp, effect="negative",
        )
        wind_fg_50 = _compute_factor(
            weather.wind_speed_mph, wind.threshold_mph,
            wind.fg_sensitivity * wind.fg_50_plus_multiplier, clamp, effect="negative",
        )
        wind_xp = _compute_factor(
            weather.wind_speed_mph, wind.threshold_mph,
            wind.xp_sensitivity, clamp, effect="negative",
        )
        wind_pass_yards = _compute_factor(
            weather.wind_speed_mph, wind.threshold_mph,
            wind.pass_yards_sensitivity, clamp, effect="negative",
        )
        wind_int_rate = _compute_factor(
            weather.wind_speed_mph, wind.threshold_mph,
            wind.int_rate_sensitivity, clamp, effect="positive",
        )
    else:
        wind_fg_base = wind_fg_50 = wind_xp = wind_pass_yards = wind_int_rate = 1.0

    # --- Temperature factors ---
    temp_fumble = _compute_factor(
        weather.temperature_f, temp.threshold_f,
        temp.fumble_rate_sensitivity, clamp,
        direction="below", effect="positive",
    )

    # --- Precipitation factors ---
    pi = weather.precipitation_inches
    if pi > 0:
        precip_catch = _compute_factor(
            pi, 0.0, precip.catch_rate_sensitivity, clamp, effect="negative",
        )
        precip_fumble = _compute_factor(
            pi, 0.0, precip.fumble_rate_sensitivity, clamp, effect="positive",
        )
        precip_fg = _compute_factor(
            pi, 0.0, precip.fg_sensitivity, clamp, effect="negative",
        )
        precip_pass_yards = _compute_factor(
            pi, 0.0, precip.pass_yards_sensitivity, clamp, effect="negative",
        )
    else:
        precip_catch = precip_fumble = precip_fg = precip_pass_yards = 1.0

    # --- Combine multiplicatively ---
    def _clamp(v: float) -> float:
        return max(clamp[0], min(clamp[1], v))

    return WeatherContext(
        fg_accuracy_factor={
            "0_39": _clamp(wind_fg_base * precip_fg),
            "40_49": _clamp(wind_fg_base * precip_fg),
            "50_plus": _clamp(wind_fg_50 * precip_fg),
        },
        xp_accuracy_factor=_clamp(wind_xp),
        catch_rate_factor=_clamp(precip_catch),
        pass_yards_factor=_clamp(wind_pass_yards * precip_pass_yards),
        fumble_rate_factor=_clamp(temp_fumble * precip_fumble),
        int_rate_factor=_clamp(wind_int_rate),
        raw=weather,
    )


class WeatherEngine:
    """Orchestrates weather data fetching + factor computation for a game."""

    def __init__(
        self,
        config: WeatherConfig,
        cache_dir: Path | None = None,
    ) -> None:
        self._config = config
        self._provider = WeatherProvider(
            cache_dir=cache_dir,
            forecast_ttl_hours=config.forecast_ttl_hours,
        )
        self._schedule_cache: dict[int, dict] = {}

    def _load_schedule(self, season: int) -> dict[tuple[int, str, str], tuple[date, int]]:
        """Load nflverse schedule and build lookup: (week, home, away) -> (date, hour_utc)."""
        if season in self._schedule_cache:
            return self._schedule_cache[season]

        try:
            import nflreadpy
            sched = nflreadpy.import_schedules([season])
        except Exception:
            logger.warning("Could not load schedule for season %d", season)
            self._schedule_cache[season] = {}
            return {}

        lookup: dict[tuple[int, str, str], tuple[date, int]] = {}
        for row in sched.iter_rows(named=True):
            week = row.get("week")
            home = row.get("home_team")
            away = row.get("away_team")
            gameday = row.get("gameday")
            gametime = row.get("gametime")

            if not all((week, home, away, gameday)):
                continue

            if isinstance(gameday, str):
                game_date = date.fromisoformat(gameday)
            else:
                game_date = gameday

            hour_utc = 17  # default: 1pm ET = 17 UTC
            if gametime:
                try:
                    parts = str(gametime).split(":")
                    et_hour = int(parts[0])
                    hour_utc = et_hour + 4
                except (ValueError, IndexError):
                    pass

            lookup[(int(week), str(home), str(away))] = (game_date, hour_utc)

        self._schedule_cache[season] = lookup
        return lookup

    def get_context(
        self,
        home_team: str,
        away_team: str,
        target_season: int,
        week: int,
    ) -> WeatherContext | None:
        """Get weather factors for a specific game."""
        if is_indoor(home_team):
            logger.debug("Indoor game %s vs %s — weather neutral", home_team, away_team)
            return WeatherContext()

        schedule = self._load_schedule(target_season)
        key = (week, home_team, away_team)
        if key not in schedule:
            logger.warning(
                "No schedule entry for week %d %s vs %s (season %d)",
                week, home_team, away_team, target_season,
            )
            return None

        game_date, hour_utc = schedule[key]

        stadium = get_stadium(home_team)
        if stadium is None:
            logger.warning("No stadium for %s", home_team)
            return None

        weather = self._provider.get_weather(
            stadium.latitude, stadium.longitude, game_date, hour_utc,
        )
        if weather is None:
            return None

        ctx = compute_weather_factors(weather, self._config)
        logger.debug(
            "Weather %s vs %s week %d: wind=%.1f mph, temp=%.1f°F, "
            "precip=%.3f in (%s) → fg_50=%+.3f catch=%+.3f",
            home_team, away_team, week,
            weather.wind_speed_mph, weather.temperature_f,
            weather.precipitation_inches, weather.precipitation_type,
            ctx.fg_accuracy_factor["50_plus"] - 1.0,
            ctx.catch_rate_factor - 1.0,
        )
        return ctx
