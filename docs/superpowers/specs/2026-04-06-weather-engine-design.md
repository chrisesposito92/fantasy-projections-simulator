# Weather Engine Design

**Date:** 2026-04-06
**Status:** Draft

## Overview

Add game-day weather conditions (wind, temperature, precipitation) as an adjustment layer in the simulation pipeline. Weather factors modify kicking accuracy, catch rates, passing yards, and turnover rates before simulation. Supports both backtesting (historical weather by game date) and forward projection (weather forecast by game date) through a single API source.

## Data Source

**Open-Meteo** (free, no API key required):
- Historical Weather API for past games
- Forecast API for upcoming games (7-day window)
- Hourly resolution — pick the game-time window using nflverse schedule `gametime`
- Rate limit: 10,000 requests/day (a full season is ~272 games)

## Architecture

Three components in a new `data/weather/` package, following the PFF adjustment layer pattern.

### StadiumRegistry (`stadiums.py`)

Static mapping of team abbreviation to stadium metadata.

```python
@dataclass(frozen=True)
class StadiumInfo:
    name: str
    latitude: float
    longitude: float
    venue_type: str  # "outdoor" | "dome" | "retractable"
```

- 32 NFL teams, ~30 unique stadiums (LAR/LAC share SoFi, NYG/NYJ share MetLife)
- `venue_type` of `"dome"` or `"retractable"` → indoor game, weather factors are all 1.0
- `is_indoor(team: str) -> bool` helper

### WeatherProvider (`provider.py`)

API client with local cache.

```python
@dataclass(frozen=True)
class GameWeather:
    wind_speed_mph: float
    temperature_f: float
    precipitation_inches: float       # total from kickoff to kickoff + 3 hours
    precipitation_type: str           # "none" | "rain" | "snow"
```

- `get_weather(latitude, longitude, game_date, game_hour_utc) -> GameWeather`
- `game_hour_utc` is the kickoff hour (derived from nflverse schedule `gametime` field)
- Routes to Open-Meteo historical API if `game_date < today`, forecast API if `game_date >= today`
- Uses httpx (already a project dependency for PFF scraper)

**Cache:** JSON files at `~/.fantasy-sim/weather/`, one per game.
- Filename: `{season}_week{week:02d}_{home}_{away}.json`
- Historical data: cached permanently (immutable — weather that already happened doesn't change)
- Forecast data: refetched if `fetched_at` > `forecast_ttl_hours` (default 6) and game date is still in the future
- A full season is ~272 files, trivially small

**Schedule resolution:** Uses nflverse `import_schedules()` (already available via the data pipeline) to map `(season, week, home_team, away_team)` to `game_date` + `game_hour_utc`. No new parameters needed on `build_game()`.

### WeatherEngine (`engine.py`)

Computes multiplicative factors from raw weather data.

```python
@dataclass(frozen=True)
class WeatherContext:
    fg_accuracy_factor: dict[str, float]  # per distance bucket: "0_39", "40_49", "50_plus"
    xp_accuracy_factor: float
    catch_rate_factor: float
    pass_yards_factor: float
    fumble_rate_factor: float
    int_rate_factor: float
    raw: GameWeather                       # for logging/debugging
```

**Factor model — threshold + linear scaling:**

Unlike PFF layers which use z-scores (relative strength matters), weather effects have absolute thresholds. 5 mph wind is irrelevant; 25 mph matters. 65F vs 75F is negligible; 20F vs 35F is significant.

```
Below threshold: factor = 1.0 (no effect)
Above threshold: factor = 1.0 + sensitivity * (value - threshold)
Clamped to [min_clamp, max_clamp]
```

For temperature, the direction is inverted (cold is bad):
```
Above threshold: factor = 1.0 (no effect)
Below threshold: factor = 1.0 + sensitivity * (threshold - value)
```

**Factor mapping:**

| Factor | Wind | Temperature | Precipitation |
|--------|------|-------------|---------------|
| `fg_accuracy_factor["0_39"]` | sensitivity | | sensitivity |
| `fg_accuracy_factor["40_49"]` | sensitivity | | sensitivity |
| `fg_accuracy_factor["50_plus"]` | sensitivity * `fg_50_plus_multiplier` | | sensitivity |
| `xp_accuracy_factor` | sensitivity | | |
| `catch_rate_factor` | | | sensitivity |
| `pass_yards_factor` | sensitivity | | sensitivity |
| `fumble_rate_factor` | | sensitivity | sensitivity |
| `int_rate_factor` | sensitivity | | |

Factors from multiple weather variables are **multiplied** (e.g., wind + rain compounds the kicking penalty).

**Dome short-circuit:** If `is_indoor(home_team)` is `True`, `compute()` returns all factors at 1.0 without making an API call.

## Configuration

In `defaults.yaml`:

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

Sensitivities are initial estimates. Tuned via A/B testing against the backtester.

## Integration into `build_game()`

### Layer Ordering

Weather is applied **last**, after all PFF layers:

1. Base distributions (play calling, outcomes, turnovers, kicking, drive start)
2. PFF Matchup Engine
3. PFF Tier Engine + Team Context
4. PFF Coverage Engine
5. PFF DST Baseline
6. PFF Kicker Engine
7. **Weather Engine** (new)

**Rationale:** PFF layers establish player/team quality. Weather is an environment modifier applied on top of the calibrated distributions. Applying it last ensures weather factors are never overwritten by PFF layers.

### Application

`_apply_weather(home_dists, away_dists, home_roster, away_roster, weather_ctx)`:

- Modifies `TurnoverRates.fumble_rate` and `TurnoverRates.int_rate` — multiplicative
- Modifies `KickingModel.fg_make_rate` per distance bucket and `KickingModel.xp_rate` — multiplicative
- Modifies player-level `catch_rate` on both rosters — multiplicative (same pattern as coverage engine)
- Modifies player-level `receiving_yards_dist` on both rosters — additive shift: `shift = (factor - 1.0) * np.mean(player.receiving_yards_dist)` (same pattern as matchup engine)
- **Symmetric:** Both teams receive identical adjustments (weather affects both sides equally)

### `GameContextBuilder` Changes

- `__init__()` receives `WeatherConfig` alongside `PffConfig`
- Conditionally instantiates `WeatherEngine` if `weather.enabled` is `True`
- `build_game()` calls `weather_engine.get_context(home, away, target_season, week)` then `_apply_weather()` at the end of the pipeline
- If schedule data unavailable (season not yet released), logs a warning and skips weather (graceful no-op)

## CLI Integration

- New `--weather/--no-weather` flag on `week`, `season`, `game`, `player`, `backtest` commands
- Defaults to `weather.enabled` in config
- `demo` command: flag not available (synthetic data, no real dates/stadiums)
- `game --demo`: flag not available (same reason)
- Pattern mirrors existing `--pff/--no-pff` flag

## What Weather Does NOT Affect

- **Play calling distributions** — teams don't systematically run more in bad weather at the per-play granularity captured by our bucketed distributions. Coaches adapt, but this is already implicit in PBP data.
- **Rushing yards** — research shows minimal weather effect on run efficiency.
- **Sack rate** — no meaningful signal in the literature.

## A/B Testing

Extend `validate_pff_signal.py` and `validate_weekly_signal.py`:

- New modes: `--mode weather`, `--mode weather+tier`, `--mode weather+tier+matchup`
- `--config-override` supports `weather` key for sensitivity sweeps
- Same ledger pattern — compare weather-on vs weather-off across backtested seasons
- Primary metrics: rank_corr, weekly_mae, season_mae, kicker_mae (new — weather should notably improve kicker projections in outdoor games)

## Testing Strategy

Unit tests in `tests/test_data/test_weather/`:

- `test_stadiums.py` — all 32 teams have entries, dome flags correct, lat/lon within continental US bounds, shared-stadium teams have same coordinates
- `test_provider.py` — mock httpx responses from Open-Meteo, verify historical vs forecast endpoint routing, cache hit/miss/TTL behavior, graceful error handling (API timeout, malformed response)
- `test_engine.py` — factor computation: wind above/below threshold, temperature below freezing, precipitation scaling, dome short-circuit (all factors 1.0), factor clamping at bounds, combined multi-variable effects (wind + rain compounds), edge cases (0 wind, 0 precip, exactly-at-threshold)
- `test_integration.py` — `build_game()` with weather enabled produces modified kicking/turnover/catch distributions, weather disabled is identity (distributions unchanged), dome game distributions unchanged

No network in unit tests — mock all Open-Meteo calls via `unittest.mock.patch` (same pattern as nflreadpy mocking throughout the codebase).

## Out of Scope (v1)

- **Altitude** (Denver thin-air effect) — add later as a `StadiumInfo.altitude_ft` field; architectural change is trivial (one more factor)
- **Snow vs rain factor distinction** — v1 treats all precipitation uniformly; adding a `snow_multiplier` to config is a one-line change later
- **Wind direction** (headwind vs crosswind for kicking) — requires stadium orientation data and kick direction modeling; significant complexity for marginal gain
- **In-game weather changes** — NFL games are ~3 hours; weather is effectively constant for simulation purposes
