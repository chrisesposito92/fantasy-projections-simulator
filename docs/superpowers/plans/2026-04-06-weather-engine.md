# Weather Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add game-day weather (wind, temperature, precipitation) as an adjustment layer that modifies kicking accuracy, catch rates, passing yards, and turnover rates before simulation.

**Architecture:** New `data/weather/` package with three components — StadiumRegistry (team → location + dome flag), WeatherProvider (Open-Meteo API client + JSON cache), and WeatherEngine (threshold + linear factor model). Applied as the final layer in `build_game()` after all PFF engines. Config-driven sensitivities in `defaults.yaml`, CLI `--weather/--no-weather` flag.

**Tech Stack:** Python, httpx (existing dependency), Open-Meteo API (free, no key), nflverse schedules (existing)

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/fantasy_sim/data/weather/__init__.py` | Package init |
| Create | `src/fantasy_sim/data/weather/models.py` | `WeatherConfig`, `WindConfig`, `TemperatureConfig`, `PrecipitationConfig`, `GameWeather`, `WeatherContext` dataclasses |
| Create | `src/fantasy_sim/data/weather/config.py` | `load_weather_config(defaults)` — YAML → dataclasses |
| Create | `src/fantasy_sim/data/weather/stadiums.py` | `StadiumInfo`, `STADIUMS` dict, `is_indoor()`, `get_stadium()` |
| Create | `src/fantasy_sim/data/weather/provider.py` | `WeatherProvider` — Open-Meteo client + JSON cache |
| Create | `src/fantasy_sim/data/weather/engine.py` | `WeatherEngine` — factor computation + orchestration |
| Modify | `config/defaults.yaml` | Add `weather:` section |
| Modify | `src/fantasy_sim/data/game_context.py:38-116` | Add `weather_config` param, instantiate `WeatherEngine` |
| Modify | `src/fantasy_sim/data/game_context.py:557` | Call `_apply_weather()` after kicker engine |
| Modify | `src/fantasy_sim/cli.py:97-105` | Wire `weather_config` into `_make_builder()` |
| Modify | `src/fantasy_sim/cli.py` (5 commands) | Add `--weather/--no-weather` flag |
| Create | `tests/test_data/test_weather/__init__.py` | Test package init |
| Create | `tests/test_data/test_weather/test_models.py` | Config + dataclass tests |
| Create | `tests/test_data/test_weather/test_stadiums.py` | Stadium registry tests |
| Create | `tests/test_data/test_weather/test_provider.py` | API client + cache tests |
| Create | `tests/test_data/test_weather/test_engine.py` | Factor computation tests |
| Create | `tests/test_data/test_weather/test_integration.py` | `build_game()` integration tests |

---

### Task 1: Weather Data Models and Config

**Files:**
- Create: `src/fantasy_sim/data/weather/__init__.py`
- Create: `src/fantasy_sim/data/weather/models.py`
- Create: `src/fantasy_sim/data/weather/config.py`
- Modify: `config/defaults.yaml`
- Create: `tests/test_data/test_weather/__init__.py`
- Create: `tests/test_data/test_weather/test_models.py`

- [ ] **Step 1: Write tests for weather config dataclasses**

Create `tests/test_data/test_weather/__init__.py` (empty) and `tests/test_data/test_weather/test_models.py`:

```python
"""Tests for weather data models and config loading."""

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
        import pytest
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_weather/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fantasy_sim.data.weather'`

- [ ] **Step 3: Implement weather data models**

Create `src/fantasy_sim/data/weather/__init__.py`:

```python
"""Weather engine — game-day weather adjustments for simulation."""
```

Create `src/fantasy_sim/data/weather/models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_models.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Write tests for config loading**

Append to `tests/test_data/test_weather/test_models.py`:

```python
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
        # Non-overridden fields keep defaults
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
```

- [ ] **Step 6: Implement config loading**

Create `src/fantasy_sim/data/weather/config.py`:

```python
"""Load weather configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.weather.models import (
    PrecipitationConfig,
    TemperatureConfig,
    WeatherConfig,
    WindConfig,
)


def load_weather_config(config: dict) -> WeatherConfig:
    """Extract weather config from the full defaults config dict.

    Args:
        config: The full defaults.yaml dict (or a subset with a "weather" key).

    Returns:
        WeatherConfig with all sub-configs populated.
    """
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_models.py -v`
Expected: All 15 tests PASS

- [ ] **Step 8: Add weather section to defaults.yaml**

Append to `config/defaults.yaml` after the `pff:` section (after line 178):

```yaml

weather:
  enabled: false  # opt-in for v1, flip to true once A/B validated
  wind:
    threshold_mph: 10
    fg_sensitivity: 0.008         # per mph above threshold
    fg_50_plus_multiplier: 2.5    # 50+ yarders hit harder than short FGs
    pass_yards_sensitivity: 0.004
    int_rate_sensitivity: 0.003
    xp_sensitivity: 0.002
  temperature:
    threshold_f: 35
    fumble_rate_sensitivity: 0.003  # per degree below threshold
  precipitation:
    catch_rate_sensitivity: 0.03    # per inch in 3-hour game window
    fumble_rate_sensitivity: 0.02
    fg_sensitivity: 0.015
    pass_yards_sensitivity: 0.008
  factor_clamp: [0.80, 1.20]
  forecast_ttl_hours: 6
```

- [ ] **Step 9: Commit**

```bash
git add src/fantasy_sim/data/weather/__init__.py src/fantasy_sim/data/weather/models.py \
    src/fantasy_sim/data/weather/config.py config/defaults.yaml \
    tests/test_data/test_weather/__init__.py tests/test_data/test_weather/test_models.py
git commit -m "feat(weather): add data models, config loading, and defaults.yaml section"
```

---

### Task 2: Stadium Registry

**Files:**
- Create: `src/fantasy_sim/data/weather/stadiums.py`
- Create: `tests/test_data/test_weather/test_stadiums.py`

- [ ] **Step 1: Write tests for stadium registry**

Create `tests/test_data/test_weather/test_stadiums.py`:

```python
"""Tests for NFL stadium registry."""

import pytest

from fantasy_sim.data.weather.stadiums import (
    STADIUMS,
    StadiumInfo,
    get_stadium,
    is_indoor,
)

# All 32 NFL team abbreviations
ALL_TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
]

DOME_TEAMS = {"ARI", "ATL", "DAL", "DET", "HOU", "IND", "LA", "LAC", "LV", "MIN", "NO"}


class TestStadiumInfo:
    def test_frozen(self):
        info = StadiumInfo(name="Test", latitude=40.0, longitude=-74.0, venue_type="outdoor")
        with pytest.raises(AttributeError):
            info.latitude = 50.0


class TestStadiumRegistry:
    def test_all_32_teams_present(self):
        for team in ALL_TEAMS:
            assert team in STADIUMS, f"Missing stadium for {team}"

    def test_no_extra_teams(self):
        for team in STADIUMS:
            assert team in ALL_TEAMS, f"Unexpected team {team} in registry"

    def test_latitude_bounds(self):
        """All NFL stadiums are in the continental US (lat 25-48)."""
        for team, info in STADIUMS.items():
            assert 25.0 <= info.latitude <= 48.5, (
                f"{team}: latitude {info.latitude} out of continental US bounds"
            )

    def test_longitude_bounds(self):
        """All NFL stadiums are in the continental US (lon -125 to -70)."""
        for team, info in STADIUMS.items():
            assert -125.0 <= info.longitude <= -70.0, (
                f"{team}: longitude {info.longitude} out of continental US bounds"
            )

    def test_shared_stadiums_same_coords(self):
        """LAR/LAC share SoFi, NYG/NYJ share MetLife."""
        assert STADIUMS["LA"].latitude == STADIUMS["LAC"].latitude
        assert STADIUMS["LA"].longitude == STADIUMS["LAC"].longitude
        assert STADIUMS["NYG"].latitude == STADIUMS["NYJ"].latitude
        assert STADIUMS["NYG"].longitude == STADIUMS["NYJ"].longitude

    def test_venue_types_valid(self):
        for team, info in STADIUMS.items():
            assert info.venue_type in ("outdoor", "dome", "retractable"), (
                f"{team}: invalid venue_type '{info.venue_type}'"
            )


class TestIsIndoor:
    def test_dome_teams(self):
        for team in DOME_TEAMS:
            assert is_indoor(team) is True, f"{team} should be indoor"

    def test_outdoor_teams(self):
        outdoor = set(ALL_TEAMS) - DOME_TEAMS
        for team in outdoor:
            assert is_indoor(team) is False, f"{team} should be outdoor"

    def test_unknown_team(self):
        assert is_indoor("ZZZ") is False


class TestGetStadium:
    def test_known_team(self):
        info = get_stadium("KC")
        assert info is not None
        assert info.name == "GEHA Field at Arrowhead Stadium"
        assert info.venue_type == "outdoor"

    def test_unknown_team(self):
        assert get_stadium("ZZZ") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_weather/test_stadiums.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement stadium registry**

Create `src/fantasy_sim/data/weather/stadiums.py`:

```python
"""NFL stadium registry — team to location and venue type mapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StadiumInfo:
    """Stadium metadata for weather lookups."""
    name: str
    latitude: float
    longitude: float
    venue_type: str  # "outdoor" | "dome" | "retractable"


STADIUMS: dict[str, StadiumInfo] = {
    "ARI": StadiumInfo("State Farm Stadium", 33.5276, -112.2626, "retractable"),
    "ATL": StadiumInfo("Mercedes-Benz Stadium", 33.7554, -84.4010, "retractable"),
    "BAL": StadiumInfo("M&T Bank Stadium", 39.2780, -76.6227, "outdoor"),
    "BUF": StadiumInfo("Highmark Stadium", 42.7738, -78.7870, "outdoor"),
    "CAR": StadiumInfo("Bank of America Stadium", 35.2258, -80.8528, "outdoor"),
    "CHI": StadiumInfo("Soldier Field", 41.8623, -87.6167, "outdoor"),
    "CIN": StadiumInfo("Paycor Stadium", 39.0955, -84.5161, "outdoor"),
    "CLE": StadiumInfo("Cleveland Browns Stadium", 41.5061, -81.6995, "outdoor"),
    "DAL": StadiumInfo("AT&T Stadium", 32.7473, -97.0945, "retractable"),
    "DEN": StadiumInfo("Empower Field at Mile High", 39.7439, -105.0201, "outdoor"),
    "DET": StadiumInfo("Ford Field", 42.3400, -83.0456, "dome"),
    "GB": StadiumInfo("Lambeau Field", 44.5013, -88.0622, "outdoor"),
    "HOU": StadiumInfo("NRG Stadium", 29.6847, -95.4107, "retractable"),
    "IND": StadiumInfo("Lucas Oil Stadium", 39.7601, -86.1639, "retractable"),
    "JAX": StadiumInfo("EverBank Stadium", 30.3239, -81.6373, "outdoor"),
    "KC": StadiumInfo("GEHA Field at Arrowhead Stadium", 39.0489, -94.4839, "outdoor"),
    "LA": StadiumInfo("SoFi Stadium", 33.9534, -118.3390, "dome"),
    "LAC": StadiumInfo("SoFi Stadium", 33.9534, -118.3390, "dome"),
    "LV": StadiumInfo("Allegiant Stadium", 36.0909, -115.1833, "dome"),
    "MIA": StadiumInfo("Hard Rock Stadium", 25.9580, -80.2389, "outdoor"),
    "MIN": StadiumInfo("U.S. Bank Stadium", 44.9736, -93.2575, "dome"),
    "NE": StadiumInfo("Gillette Stadium", 42.0909, -71.2643, "outdoor"),
    "NO": StadiumInfo("Caesars Superdome", 29.9511, -90.0812, "dome"),
    "NYG": StadiumInfo("MetLife Stadium", 40.8128, -74.0742, "outdoor"),
    "NYJ": StadiumInfo("MetLife Stadium", 40.8128, -74.0742, "outdoor"),
    "PHI": StadiumInfo("Lincoln Financial Field", 39.9008, -75.1675, "outdoor"),
    "PIT": StadiumInfo("Acrisure Stadium", 40.4468, -80.0158, "outdoor"),
    "SEA": StadiumInfo("Lumen Field", 47.5952, -122.3316, "outdoor"),
    "SF": StadiumInfo("Levi's Stadium", 37.4033, -121.9694, "outdoor"),
    "TB": StadiumInfo("Raymond James Stadium", 27.9759, -82.5033, "outdoor"),
    "TEN": StadiumInfo("Nissan Stadium", 36.1665, -86.7713, "outdoor"),
    "WAS": StadiumInfo("Northwest Stadium", 38.9076, -76.8645, "outdoor"),
}


def get_stadium(team: str) -> StadiumInfo | None:
    """Get stadium info for a team abbreviation. Returns None if unknown."""
    return STADIUMS.get(team)


def is_indoor(team: str) -> bool:
    """Return True if the team plays in a dome or retractable-roof stadium."""
    info = STADIUMS.get(team)
    if info is None:
        return False
    return info.venue_type in ("dome", "retractable")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_stadiums.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/weather/stadiums.py tests/test_data/test_weather/test_stadiums.py
git commit -m "feat(weather): add NFL stadium registry with dome/outdoor flags"
```

---

### Task 3: Weather Provider (Open-Meteo API Client + Cache)

**Files:**
- Create: `src/fantasy_sim/data/weather/provider.py`
- Create: `tests/test_data/test_weather/test_provider.py`

- [ ] **Step 1: Write tests for weather provider**

Create `tests/test_data/test_weather/test_provider.py`:

```python
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
            # 25°C ≈ 77°F, 16 km/h ≈ 9.94 mph
            mock_resp.json.return_value = _mock_hourly_response(
                temp_c=25.0, wind_kmh=16.0, precip_mm=2.5, snowfall_cm=0.0,
            )
            mock_resp.raise_for_status = MagicMock()
            mock_httpx.get.return_value = mock_resp

            gw = provider.get_weather(39.0, -94.5, date(2024, 9, 8), 17)

            assert isinstance(gw, GameWeather)
            assert 76.0 <= gw.temperature_f <= 78.0  # 25°C = 77°F
            assert 9.0 <= gw.wind_speed_mph <= 11.0  # 16 km/h ≈ 9.94 mph
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_weather/test_provider.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement weather provider**

Create `src/fantasy_sim/data/weather/provider.py`:

```python
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

    def _read_cache(
        self, path: Path, game_date: date
    ) -> GameWeather | None:
        """Read cached weather, respecting TTL for forecasts."""
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        # Historical data is immutable — always valid
        if game_date < date.today():
            return GameWeather(**{k: data[k] for k in GameWeather.__dataclass_fields__})

        # Forecast data — check TTL
        fetched_at = data.get("fetched_at")
        if fetched_at:
            fetched = datetime.fromisoformat(fetched_at)
            age_hours = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
            if age_hours < self._forecast_ttl_hours:
                return GameWeather(
                    **{k: data[k] for k in GameWeather.__dataclass_fields__}
                )
        return None

    def _write_cache(
        self, path: Path, gw: GameWeather
    ) -> None:
        """Write weather result to cache with timestamp."""
        data = {
            "wind_speed_mph": gw.wind_speed_mph,
            "temperature_f": gw.temperature_f,
            "precipitation_inches": gw.precipitation_inches,
            "precipitation_type": gw.precipitation_type,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(data, indent=2))

    def get_weather(
        self,
        latitude: float,
        longitude: float,
        game_date: date,
        game_hour_utc: int,
    ) -> GameWeather | None:
        """Fetch weather for a location and date, using cache when available.

        Args:
            latitude: Stadium latitude.
            longitude: Stadium longitude.
            game_date: Date of the game.
            game_hour_utc: Kickoff hour in UTC (0-23).

        Returns:
            GameWeather with converted units, or None on error.
        """
        cache_path = self._cache_path(latitude, longitude, game_date)

        cached = self._read_cache(cache_path, game_date)
        if cached is not None:
            return cached

        try:
            gw = self._fetch(latitude, longitude, game_date, game_hour_utc)
        except Exception:
            logger.warning(
                "Weather API error for (%.2f, %.2f) on %s", latitude, longitude, game_date,
                exc_info=True,
            )
            return None

        self._write_cache(cache_path, gw)
        return gw

    def _fetch(
        self,
        latitude: float,
        longitude: float,
        game_date: date,
        game_hour_utc: int,
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
        }

        resp = httpx.get(base_url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()

        hourly = data["hourly"]
        # Extract 3-hour game window (kickoff to kickoff + 3h)
        start_idx = max(0, min(game_hour_utc, 23))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_provider.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/weather/provider.py tests/test_data/test_weather/test_provider.py
git commit -m "feat(weather): add Open-Meteo provider with JSON cache and unit conversion"
```

---

### Task 4: Weather Engine (Factor Computation)

**Files:**
- Create: `src/fantasy_sim/data/weather/engine.py`
- Create: `tests/test_data/test_weather/test_engine.py`

- [ ] **Step 1: Write tests for factor computation**

Create `tests/test_data/test_weather/test_engine.py`:

```python
"""Tests for weather factor computation engine."""

import pytest

from fantasy_sim.data.weather.engine import compute_weather_factors
from fantasy_sim.data.weather.models import (
    GameWeather,
    WeatherConfig,
    WeatherContext,
    WindConfig,
)


class TestComputeWeatherFactors:
    def test_calm_conditions_neutral(self):
        """No wind, warm, dry → all factors 1.0."""
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
        """20 mph wind with threshold=10 → 10 mph excess, factors shift."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        # fg: 1.0 - 0.008 * 10 = 0.92 for 0_39 and 40_49
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.92, abs=0.001)
        assert ctx.fg_accuracy_factor["40_49"] == pytest.approx(0.92, abs=0.001)
        # 50_plus: 1.0 - 0.008 * 2.5 * 10 = 0.80
        assert ctx.fg_accuracy_factor["50_plus"] == pytest.approx(0.80, abs=0.001)
        # xp: 1.0 - 0.002 * 10 = 0.98
        assert ctx.xp_accuracy_factor == pytest.approx(0.98, abs=0.001)
        # pass_yards: 1.0 - 0.004 * 10 = 0.96
        assert ctx.pass_yards_factor == pytest.approx(0.96, abs=0.001)
        # int_rate: 1.0 + 0.003 * 10 = 1.03
        assert ctx.int_rate_factor == pytest.approx(1.03, abs=0.001)

    def test_wind_below_threshold_no_effect(self):
        """Wind at exactly the threshold has zero excess → neutral."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=10.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["0_39"] == 1.0

    def test_cold_temperature_fumbles(self):
        """20°F with threshold=35 → 15 degree excess → fumble_rate up."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=20.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        # 1.0 + 0.003 * (35 - 20) = 1.045
        assert ctx.fumble_rate_factor == pytest.approx(1.045, abs=0.001)

    def test_warm_temperature_no_effect(self):
        """50°F is above threshold → no fumble adjustment."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=50.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fumble_rate_factor == 1.0

    def test_precipitation_effects(self):
        """0.5 inches of rain → catch_rate, fumble, fg, pass_yards affected."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        # catch_rate: 1.0 - 0.03 * 0.5 = 0.985
        assert ctx.catch_rate_factor == pytest.approx(0.985, abs=0.001)
        # fumble: 1.0 + 0.02 * 0.5 = 1.01
        assert ctx.fumble_rate_factor == pytest.approx(1.01, abs=0.001)
        # fg: 1.0 - 0.015 * 0.5 = 0.9925
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.9925, abs=0.001)
        # pass_yards: 1.0 - 0.008 * 0.5 = 0.996
        assert ctx.pass_yards_factor == pytest.approx(0.996, abs=0.001)

    def test_combined_wind_and_rain(self):
        """Wind + rain compound multiplicatively."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=72.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        # fg 0_39: wind gives 0.92, rain gives 0.9925 → 0.92 * 0.9925 ≈ 0.9131
        assert ctx.fg_accuracy_factor["0_39"] == pytest.approx(0.92 * 0.9925, abs=0.001)
        # pass_yards: wind 0.96, rain 0.996 → 0.96 * 0.996 ≈ 0.9562
        assert ctx.pass_yards_factor == pytest.approx(0.96 * 0.996, abs=0.001)

    def test_combined_cold_and_rain_fumbles(self):
        """Cold + rain both increase fumble_rate multiplicatively."""
        cfg = WeatherConfig()
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=20.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, cfg)
        # cold: 1.045, rain: 1.01 → 1.045 * 1.01 ≈ 1.05545
        assert ctx.fumble_rate_factor == pytest.approx(1.045 * 1.01, abs=0.001)

    def test_factor_clamping(self):
        """Extreme conditions should be clamped to [0.80, 1.20]."""
        cfg = WeatherConfig()
        # 50 mph wind → extreme factor for 50_plus:
        # 1.0 - 0.008 * 2.5 * 40 = 0.20 → clamped to 0.80
        gw = GameWeather(wind_speed_mph=50.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["50_plus"] == 0.80

    def test_raw_weather_attached(self):
        """WeatherContext should carry the raw GameWeather for logging."""
        gw = GameWeather(wind_speed_mph=15.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())
        assert ctx.raw is gw

    def test_zero_everything_neutral(self):
        """0 wind, warm, 0 precip → perfectly neutral."""
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())
        assert ctx.catch_rate_factor == 1.0
        assert ctx.fumble_rate_factor == 1.0

    def test_custom_clamp(self):
        """Custom factor_clamp should be respected."""
        cfg = WeatherConfig(factor_clamp=(0.90, 1.10))
        gw = GameWeather(wind_speed_mph=50.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, cfg)
        assert ctx.fg_accuracy_factor["50_plus"] >= 0.90
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_weather/test_engine.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement weather engine**

Create `src/fantasy_sim/data/weather/engine.py`:

```python
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
    """Compute a single weather factor using threshold + linear scaling.

    Args:
        value: Raw weather value (e.g., wind mph).
        threshold: Below this value, no effect.
        sensitivity: Factor change per unit above/below threshold.
        clamp: (min, max) for the final factor.
        direction: "above" (wind/precip: higher is worse) or
                   "below" (temp: lower is worse).
        effect: "negative" (reduces accuracy/yards) or
                "positive" (increases rate like fumbles/INTs).

    Returns:
        Multiplicative factor centered on 1.0.
    """
    if direction == "above":
        excess = max(0.0, value - threshold)
    else:  # "below" — temperature
        excess = max(0.0, threshold - value)

    if excess == 0.0:
        return 1.0

    shift = sensitivity * excess
    if effect == "negative":
        factor = 1.0 - shift
    else:  # "positive" — increases the rate
        factor = 1.0 + shift

    return max(clamp[0], min(clamp[1], factor))


def compute_weather_factors(
    weather: GameWeather,
    config: WeatherConfig,
) -> WeatherContext:
    """Compute all weather adjustment factors from raw weather data.

    Factors from different weather variables (wind, temp, precipitation)
    are multiplied together — compound effects.

    Args:
        weather: Raw weather data for the game.
        config: Weather configuration with thresholds and sensitivities.

    Returns:
        WeatherContext with multiplicative factors centered on 1.0.
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
    """Orchestrates weather data fetching + factor computation for a game.

    Handles schedule resolution, dome detection, and provider calls.
    """

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
        """Load nflverse schedule and build lookup: (week, home, away) → (date, hour_utc)."""
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

            # Parse gametime (e.g., "13:00" ET → approximate UTC)
            hour_utc = 17  # default: 1pm ET = 17 UTC
            if gametime:
                try:
                    parts = str(gametime).split(":")
                    et_hour = int(parts[0])
                    hour_utc = et_hour + 4  # ET → UTC (approximate)
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
        """Get weather factors for a specific game.

        Returns None if weather data is unavailable (dome → returns neutral
        WeatherContext, not None).
        """
        # Dome games → neutral factors, no API call
        if is_indoor(home_team):
            logger.debug("Indoor game %s vs %s — weather neutral", home_team, away_team)
            return WeatherContext()

        # Look up game date from schedule
        schedule = self._load_schedule(target_season)
        key = (week, home_team, away_team)
        if key not in schedule:
            logger.warning(
                "No schedule entry for week %d %s vs %s (season %d)",
                week, home_team, away_team, target_season,
            )
            return None

        game_date, hour_utc = schedule[key]

        # Get stadium location
        stadium = get_stadium(home_team)
        if stadium is None:
            logger.warning("No stadium for %s", home_team)
            return None

        # Fetch weather
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_engine.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/data/weather/engine.py tests/test_data/test_weather/test_engine.py
git commit -m "feat(weather): add factor computation engine with threshold+linear model"
```

---

### Task 5: Integration into GameContextBuilder

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py`
- Create: `tests/test_data/test_weather/test_integration.py`

- [ ] **Step 1: Write integration tests**

Create `tests/test_data/test_weather/test_integration.py`:

```python
"""Integration tests — weather engine applied via build_game() pipeline."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from datetime import date

from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.weather.models import GameWeather, WeatherConfig, WeatherContext
from fantasy_sim.data.weather.engine import compute_weather_factors
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes


def _make_test_dists(team: str) -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.5, "run": 0.5}),
        play_outcomes=PlayOutcomeDist(distributions={}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.84, "50_plus": 0.67}, xp_rate=0.95),
        drive_start=DriveStartModel(touchback_rate=0.6, touchback_yardline=75, return_yardlines=np.array([75])),
    )


def _make_test_roster(team: str) -> TeamRoster:
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB1", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([5, 8, 12, 15, 20]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(
                        rushing_yards_dist=np.array([2, 3, 4, 5, 6]),
                        catch_rate=0.70, receiving_yards_dist=np.array([3, 5, 7]),
                        fumble_rate=0.008)),
    ])


class TestApplyWeather:
    def test_weather_modifies_kicking(self):
        """Weather with wind should reduce FG accuracy."""
        from fantasy_sim.data.game_context import GameContextBuilder
        dists = _make_test_dists("KC")
        roster = _make_test_roster("KC")
        gw = GameWeather(wind_speed_mph=25.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())

        original_fg_50 = dists.kicking.fg_make_rate["50_plus"]
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.kicking.fg_make_rate["50_plus"] < original_fg_50

    def test_weather_modifies_turnover_rates(self):
        """Cold + rain should increase fumble rate."""
        dists = _make_test_dists("GB")
        roster = _make_test_roster("GB")
        gw = GameWeather(wind_speed_mph=15.0, temperature_f=20.0,
                         precipitation_inches=0.3, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        original_fumble = dists.turnover_rates.fumble_rate
        original_int = dists.turnover_rates.int_rate
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.turnover_rates.fumble_rate > original_fumble
        assert dists.turnover_rates.int_rate > original_int

    def test_weather_modifies_catch_rate(self):
        """Rain should reduce catch rate on receivers."""
        dists = _make_test_dists("BUF")
        roster = _make_test_roster("BUF")
        gw = GameWeather(wind_speed_mph=0.0, temperature_f=72.0,
                         precipitation_inches=0.8, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        wr = next(p for p in roster.players if p.position == "WR")
        original_cr = wr.outcomes.catch_rate
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert wr.outcomes.catch_rate < original_cr

    def test_weather_modifies_receiving_yards(self):
        """Wind should shift receiving yards distributions down."""
        dists = _make_test_dists("CHI")
        roster = _make_test_roster("CHI")
        gw = GameWeather(wind_speed_mph=25.0, temperature_f=72.0,
                         precipitation_inches=0.0, precipitation_type="none")
        ctx = compute_weather_factors(gw, WeatherConfig())

        wr = next(p for p in roster.players if p.position == "WR")
        original_mean = np.mean(wr.outcomes.receiving_yards_dist)
        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert np.mean(wr.outcomes.receiving_yards_dist) < original_mean

    def test_neutral_weather_no_change(self):
        """Calm/warm/dry weather should not modify any distributions."""
        dists = _make_test_dists("MIA")
        roster = _make_test_roster("MIA")
        ctx = WeatherContext()  # all 1.0

        original_fg = dict(dists.kicking.fg_make_rate)
        original_fumble = dists.turnover_rates.fumble_rate
        wr = next(p for p in roster.players if p.position == "WR")
        original_cr = wr.outcomes.catch_rate

        GameContextBuilder._apply_weather(dists, roster, ctx)
        assert dists.kicking.fg_make_rate == original_fg
        assert dists.turnover_rates.fumble_rate == original_fumble
        assert wr.outcomes.catch_rate == original_cr

    def test_symmetric_application(self):
        """Both teams should get identical weather adjustments."""
        gw = GameWeather(wind_speed_mph=20.0, temperature_f=30.0,
                         precipitation_inches=0.5, precipitation_type="rain")
        ctx = compute_weather_factors(gw, WeatherConfig())

        home_dists = _make_test_dists("KC")
        away_dists = _make_test_dists("BUF")
        home_roster = _make_test_roster("KC")
        away_roster = _make_test_roster("BUF")

        GameContextBuilder._apply_weather(home_dists, home_roster, ctx)
        GameContextBuilder._apply_weather(away_dists, away_roster, ctx)

        assert home_dists.kicking.fg_make_rate == away_dists.kicking.fg_make_rate
        assert home_dists.turnover_rates.fumble_rate == pytest.approx(
            away_dists.turnover_rates.fumble_rate
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_data/test_weather/test_integration.py -v`
Expected: FAIL with `AttributeError: type object 'GameContextBuilder' has no attribute '_apply_weather'`

- [ ] **Step 3: Add `_apply_weather` static method to GameContextBuilder**

Add to `src/fantasy_sim/data/game_context.py` after `_apply_coverage()` (around line 355), before `_ensure_pff_crosswalk()`:

```python
    @staticmethod
    def _apply_weather(
        dists: TeamDistributions,
        roster: TeamRoster,
        ctx: "WeatherContext",
    ) -> None:
        """Apply weather factors to TeamDistributions and TeamRoster in-place.

        Factors centered on 1.0 (neutral). Only non-neutral factors are applied.
        Weather affects both teams identically — call once per team.
        """
        import numpy as np

        # --- Kicking ---
        for bucket in ("0_39", "40_49", "50_plus"):
            factor = ctx.fg_accuracy_factor.get(bucket, 1.0)
            if factor != 1.0:
                dists.kicking.fg_make_rate[bucket] = max(
                    0.0, min(1.0, dists.kicking.fg_make_rate[bucket] * factor)
                )
        if ctx.xp_accuracy_factor != 1.0:
            dists.kicking.xp_rate = max(
                0.0, min(1.0, dists.kicking.xp_rate * ctx.xp_accuracy_factor)
            )

        # --- Turnovers ---
        if ctx.fumble_rate_factor != 1.0:
            dists.turnover_rates.fumble_rate *= ctx.fumble_rate_factor
        if ctx.int_rate_factor != 1.0:
            dists.turnover_rates.int_rate *= ctx.int_rate_factor

        # --- Receivers: catch_rate and receiving_yards_dist ---
        if ctx.catch_rate_factor != 1.0:
            for player in roster.players:
                if player.usage.target_share > 0 and player.outcomes.catch_rate > 0:
                    player.outcomes.catch_rate = max(
                        0.0, min(1.0, player.outcomes.catch_rate * ctx.catch_rate_factor)
                    )
                    player.outcomes.red_zone_catch_rate = max(
                        0.0,
                        min(1.0, player.outcomes.red_zone_catch_rate * ctx.catch_rate_factor),
                    )

        if ctx.pass_yards_factor != 1.0:
            for player in roster.players:
                if (
                    player.usage.target_share > 0
                    and player.outcomes.receiving_yards_dist is not None
                    and len(player.outcomes.receiving_yards_dist) > 0
                ):
                    mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
                    shift = (ctx.pass_yards_factor - 1.0) * mean_yards
                    player.outcomes.receiving_yards_dist = (
                        player.outcomes.receiving_yards_dist + shift
                    )
```

- [ ] **Step 4: Add `WeatherContext` import to game_context.py**

Add to the imports at the top of `src/fantasy_sim/data/game_context.py`:

```python
from fantasy_sim.data.weather.models import WeatherContext
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_data/test_weather/test_integration.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Wire WeatherEngine into `GameContextBuilder.__init__()`**

In `src/fantasy_sim/data/game_context.py`, add `weather_config` parameter to `__init__()` (after `pff_config`):

```python
    def __init__(
        self,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        pff_config: PffConfig | None = None,
        weather_config: "WeatherConfig | None" = None,
    ):
```

Add engine initialization at the end of `__init__()` (after the dst_baseline block, around line 115):

```python
        # Weather engine setup
        self._weather_engine = None
        if weather_config is not None and weather_config.enabled:
            from fantasy_sim.data.weather.engine import WeatherEngine
            self._weather_engine = WeatherEngine(
                config=weather_config,
                cache_dir=self.cache_dir.parent / "weather",
            )
            logger.info("Weather engine enabled")
        self._weather_config = weather_config
```

Add the `WeatherConfig` import (use string annotation to avoid circular import if needed — already handled by the `from __future__ import annotations` if present, otherwise use a TYPE_CHECKING guard):

At the top of `game_context.py`, add:

```python
from fantasy_sim.data.weather.models import WeatherConfig, WeatherContext
```

- [ ] **Step 7: Call weather engine at the end of `build_game()`**

In `src/fantasy_sim/data/game_context.py`, add weather application after the kicker engine block (around line 556, before the `return` statement):

```python
        # Weather adjustments (final layer — game-condition modifier)
        if self._weather_engine is not None and target_season and week:
            weather_ctx = self._weather_engine.get_context(
                home_team, away_team, target_season, week,
            )
            if weather_ctx is not None:
                self._apply_weather(home_dists, home_roster, weather_ctx)
                self._apply_weather(away_dists, away_roster, weather_ctx)

        return home_dists, away_dists, home_roster, away_roster
```

- [ ] **Step 8: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All existing tests PASS, all new weather tests PASS

- [ ] **Step 9: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_data/test_weather/test_integration.py
git commit -m "feat(weather): integrate WeatherEngine into build_game() as final adjustment layer"
```

---

### Task 6: CLI Integration

**Files:**
- Modify: `src/fantasy_sim/cli.py`

- [ ] **Step 1: Add `load_weather_config` import and update `_make_builder()`**

In `src/fantasy_sim/cli.py`, add import (after the `load_pff_config` import on line 9):

```python
from fantasy_sim.data.weather.config import load_weather_config
```

Update `_make_builder()` (currently lines 97-105) to accept and wire weather config:

```python
def _make_builder(pff_flag: bool | None = None, weather_flag: bool | None = None) -> GameContextBuilder:
    """Create GameContextBuilder, optionally with PFF and weather enabled."""
    defaults = load_defaults()
    pff_config = load_pff_config(defaults)
    if pff_flag is True:
        pff_config.enabled = True
    elif pff_flag is False:
        pff_config.enabled = False
    weather_config = load_weather_config(defaults)
    if weather_flag is True:
        weather_config.enabled = True
    elif weather_flag is False:
        weather_config.enabled = False
    loader = DataLoader()
    return GameContextBuilder(
        cache_dir=loader.cache_dir, pff_config=pff_config, weather_config=weather_config,
    )
```

- [ ] **Step 2: Add `--weather/--no-weather` flag to `week` command**

Add after the `--pff/--no-pff` option (around line 512):

```python
@click.option("--weather/--no-weather", default=None, help="Enable/disable weather adjustments")
```

Update the function signature and `_make_builder` call:

```python
def week(ctx, week_num, season, sims, scoring, output_format, output_path, overrides, config_path, scoring_config_path, detail, pff, weather, training_years):
```

Update the builder call inside `week()`:

```python
    builder = _make_builder(pff, weather)
```

- [ ] **Step 3: Add `--weather/--no-weather` to `season`, `game`, `player`, `backtest` commands**

Apply the same pattern to each:

For `season` (around line 637): add option, update signature to include `weather`, update `_make_builder(pff, weather)`.

For `game` (around line 819): add option, update signature to include `weather`, update `_make_builder(pff, weather)`.

For `player` (around line 954): add option, update signature to include `weather`, update `_make_builder(pff, weather)`.

For `backtest` (find the command): add option, update signature, update builder call. Note: `backtest` creates its own `Backtester` which internally uses `GameContextBuilder` — check if it uses `_make_builder()` or constructs directly. Update accordingly.

- [ ] **Step 4: Verify CLI help shows the new flag**

Run: `uv run fantasy-sim week --help`
Expected: Output includes `--weather / --no-weather  Enable/disable weather adjustments`

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/cli.py
git commit -m "feat(weather): add --weather/--no-weather CLI flag to week/season/game/player/backtest"
```

---

### Task 7: A/B Harness Support and Final Validation

**Files:**
- Modify: `scripts/validate_pff_signal.py` (add `weather` to config-override keys)
- Modify: `scripts/validate_weekly_signal.py` (add `weather` mode)

- [ ] **Step 1: Add `weather` to `--config-override` support in `validate_pff_signal.py`**

In `scripts/validate_pff_signal.py`, find the config-override handling block (where it checks for `tier_engine`, `talent`, `matchup`, `team_context`, `ncaa_rookie` keys). Add `weather` to the accepted keys:

```python
if "weather" in override_dict:
    from fantasy_sim.data.weather.config import load_weather_config
    weather_config = load_weather_config(defaults)
    weather_raw = override_dict["weather"]
    if "enabled" in weather_raw:
        weather_config.enabled = weather_raw["enabled"]
    # Allow overriding any nested weather config
    for section in ("wind", "temperature", "precipitation"):
        if section in weather_raw:
            sub_config = getattr(weather_config, section)
            for k, v in weather_raw[section].items():
                setattr(sub_config, k, v)
```

- [ ] **Step 2: Add `--mode weather` support to validate scripts**

In both `validate_pff_signal.py` and `validate_weekly_signal.py`, add weather-inclusive modes:

```python
# In the mode routing logic:
if "weather" in mode:
    weather_config.enabled = True
else:
    weather_config.enabled = False
```

Add the weather_config to the builder construction in the validation harness.

- [ ] **Step 3: Run the existing test suite**

Run: `uv run pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 4: Run a quick smoke test**

Run: `uv run fantasy-sim week 1 --season 2024 --sims 10 --weather`
Expected: Completes without error (weather data fetched from Open-Meteo for outdoor games, dome games skipped).

Note: This requires network access. If offline, verify with:
Run: `uv run fantasy-sim demo --sims 10`
Expected: Completes without error (demo has no weather flag — baseline still works).

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_pff_signal.py scripts/validate_weekly_signal.py
git commit -m "feat(weather): add weather mode to A/B validation harness"
```

- [ ] **Step 6: Run final full test count**

Run: `uv run pytest tests/ -v --timeout=60 | tail -1`
Expected: Output shows all tests passed with new weather tests included.

- [ ] **Step 7: Final commit with any remaining cleanup**

```bash
git add -A
git status  # verify no unintended files
git commit -m "chore(weather): final cleanup and test count verification"
```
