# External Integrations

**Analysis Date:** 2026-04-26

## APIs & External Services

**NFL Data (nflverse):**
- nflreadpy library wraps nflverse public data endpoints
- What it's used for: Play-by-play data, rosters, schedules, player stats, snap counts, injuries, depth charts, draft picks
  - SDK/Client: `nflreadpy>=0.1.0` (imported in `src/fantasy_sim/data/loader.py`)
  - Auth: None (public)
  - Implementation: `DataLoader` class in `src/fantasy_sim/data/loader.py` caches responses as parquet

**PFF Premium (via httpx):**
- PFF REST API at `https://premium.pff.com`
- What it's used for: 21 game-level player facets (21 stat columns per position), player grades, advanced metrics
  - SDK/Client: httpx client built in `scripts/scrape_pff.py` with cookie-based auth
  - Auth: PFF cookie (session auth) stored at `~/.fantasy-sim/pff/.env` (never read this file)
  - Implementation: `src/fantasy_sim/data/pff/loader.py` reads pre-processed parquet files created by `scripts/scrape_pff.py`
  - Facets: offense (summary, blocking, pass_blocking, run_blocking), passing (summary, CPOE, turbocharged), receiving (summary, routes, yards after catch, catch rate), rushing (summary, yards after contact, break tackles), defense (summary, pass rush, tackling) — 21 total across NFL and NCAA
  - Data location: Raw JSON at `~/.fantasy-sim/pff/raw/`, processed parquet at `~/.fantasy-sim/pff/processed/nfl/` and `~/.fantasy-sim/pff/processed/ncaa/`
  - Usage: PFF Intelligence Layer runs 8 active engines (tier, team_context, matchup, coverage, rb_scheme_fit, qb_split, kicker, dst_baseline)

**PFF Props (via httpx):**
- PFF Consumer API at `https://consumer-api.pff.com/football/v3/betting/nfl`
- What it's used for: Consensus betting lines (receiving yards, receptions, rushing yards, passing yards, passing TDs, anytime TD)
  - SDK/Client: httpx client in `scripts/scrape_pff_props.py` with `Api-Key` header auth
  - Auth: PFF_API_KEY env var (precedence: env var > `~/.fantasy-sim/pff/.env`)
  - Implementation: `src/fantasy_sim/data/vegas/props_loader.py` reads cached parquet (no HTTP calls during runtime)
  - Data location: Parquet cache at `~/.fantasy-sim/pff/props/props_{season}_week{week:02d}.parquet` (current season only, keyed by season+week)
  - Usage: PlayerPropsEngine (VEG-03) blends prop consensus via PFF player ID crosswalk (no fuzzy name matching)

**Open-Meteo (Weather):**
- Historical archive API: `https://archive-api.open-meteo.com/v1/archive`
- Forecast API: `https://api.open-meteo.com/v1/forecast`
- What it's used for: Game-day weather (wind, temperature, precipitation) for adjustment factors
  - SDK/Client: httpx in `src/fantasy_sim/data/weather/provider.py`
  - Auth: None (free, no API key required)
  - Implementation: `WeatherProvider` class fetches hourly data, caches as JSON with 6-hour TTL for forecasts
  - Data location: JSON cache at `~/.fantasy-sim/weather/{lat}_{lon}_{date}.json`
  - Parameters: latitude, longitude, game_date, game_hour; returns 3-hour window (kickoff to kickoff+3h)
  - Unit conversions: km/h → mph (0.621371), mm → inches (0.0393701), celsius → fahrenheit

**The Odds API (Player Props):**
- Base URL: https://theoddsapi.com/v4/sports/{sport}/betting/
- What it's used for: Alternate player props source (receiving yards, receptions, rushing yards, passing yards, passing TDs, anytime TD)
  - SDK/Client: httpx (used when Vegas props engine enabled)
  - Auth: API key in `~/.fantasy-sim/props/.env` (env var `ODDS_API_KEY`)
  - Implementation: Referenced in config but primary props source is PFF (via scrape_pff_props.py)
  - Note: Secondary/experimental integration; PFF props is primary

## Data Storage

**Databases:**
- None (all data is file-based)

**File Storage:**
- **Local filesystem only** - Parquet and JSON cache files
  - nflverse cache: `~/.fantasy-sim/cache/pbp_{seasons}.parquet`, `player_stats_{summary}_{seasons}.parquet`, etc.
  - PFF data: `~/.fantasy-sim/pff/processed/nfl/{facet}_{season}.parquet` and `~/.fantasy-sim/pff/processed/ncaa/{facet}_{season}.parquet`
  - PFF props: `~/.fantasy-sim/pff/props/props_{season}_week{week:02d}.parquet`
  - Weather: `~/.fantasy-sim/weather/{lat}_{lon}_{date}.json`
  - Dynamic blend artifacts: bundled in repo at `src/fantasy_sim/data/ensemble/artifacts/` for 2023-2024
  - Residual calibration artifacts: bundled in repo at `src/fantasy_sim/data/ensemble/artifacts/` for 2023-2024

**Caching:**
- Three-layer cache strategy in `src/fantasy_sim/data/pipeline.py`:
  1. Pipeline output (parquet, keyed by training_seasons)
  2. PBP stats (parquet, keyed by training_seasons)
  3. Player models (parquet, keyed by training_seasons + target_season + week + props_enabled)
- Cache invalidation: Manual via `DataLoader.clear_cache()` or filesystem deletion
- TTL: Weather forecasts only (6-hour TTL); other caches are immutable (historical data) or manual-refresh

## Authentication & Identity

**Auth Provider:**
- Custom (no centralized auth)

**Implementation Approach:**
1. **nflreadpy**: Public data, no auth required
2. **PFF Premium**: Cookie-based session auth
   - Extraction: Manual browser cookie copy → `~/.fantasy-sim/pff/.env` (per `docs/pff-setup.md`)
   - Validation: `scripts/scrape_pff.py` checks cookie validity before scraping
3. **PFF Props (API Key)**: Header-based API key
   - Source: Environment variable `PFF_API_KEY` (precedence) or `~/.fantasy-sim/pff/.env`
   - Validation: HTTP 401/403 raises `AuthError` if invalid
4. **Open-Meteo**: No auth (public API)
5. **The Odds API**: Environment variable or file-based API key (not actively integrated)

## Monitoring & Observability

**Error Tracking:**
- Not detected (no Sentry, Rollbar, etc.)

**Logs:**
- Python logging module throughout codebase
- `logger = logging.getLogger(__name__)` pattern in all modules
- Key loggers:
  - `src/fantasy_sim/data/pff/loader.py` - Logs PFF file not found warnings
  - `src/fantasy_sim/data/weather/provider.py` - Logs API errors and cache misses
  - `scripts/scrape_pff.py` - Rich progress bars + console logging for scraping status

## CI/CD & Deployment

**Hosting:**
- Not detected (no cloud platform specified)

**CI Pipeline:**
- Not detected (GitHub Actions workflows not committed, or not present)

**Testing:**
- Local: `uv run pytest tests/ -v` (1200+ tests)
- Markers: `@pytest.mark.integration` (network), `@pytest.mark.statistical` (slow, bulk sim)
- Coverage: Implicit (no explicit coverage config detected)

## Environment Configuration

**Required env vars:**
- `PFF_API_KEY` (if using PFF props) - API key for PFF Consumer API
- `ODDS_API_KEY` (if using The Odds API props) - Not actively integrated; backup

**Secrets location:**
- PFF cookie: `~/.fantasy-sim/pff/.env` (read by `scripts/scrape_pff.py`, never by runtime code)
- PFF API key: Env var or `~/.fantasy-sim/pff/.env`
- The Odds API key: Env var or `~/.fantasy-sim/props/.env`

**Cache directories** (auto-created):
- `~/.fantasy-sim/cache/` - nflverse parquet cache
- `~/.fantasy-sim/pff/processed/` - PFF processed parquet (NFL and NCAA)
- `~/.fantasy-sim/pff/props/` - PFF player props parquet
- `~/.fantasy-sim/weather/` - Weather JSON cache
- `~/.fantasy-sim/pff/raw/` - PFF raw JSON (from scrape_pff.py)
- `~/.fantasy-sim/pff/state/` - PFF scraper progress tracking

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Data Sources Summary

| Source | Access | Used For | Type |
|--------|--------|----------|------|
| nflverse (via nflreadpy) | Public, no auth | PBP, rosters, schedules, player stats, draft picks | HTTP REST |
| PFF Premium | Premium subscription, cookie auth | 21 game-level facets (NFL + NCAA) | HTTP REST + scrape |
| PFF Props (API) | Paid subscription, API key | Consensus betting lines (receiving, rushing, passing, TD) | HTTP REST API |
| Open-Meteo | Free, no API key | Hourly weather (historical + forecast) | HTTP REST API |
| The Odds API | Paid subscription, API key | Player props (backup) | HTTP REST API |

## API Patterns

**httpx Configuration:**
- `httpx.Client()` with base_url, headers, timeout
- Examples:
  - PFF Props: `Api-Key` header auth (scripts/scrape_pff_props.py line 80)
  - Weather: No auth, timeout=15.0 seconds (src/fantasy_sim/data/weather/provider.py line 155)
- Error handling: `resp.raise_for_status()` for HTTP errors; `Exception` catching logs and returns None

**Caching Pattern:**
- Path-based deterministic cache keys (e.g., `{lat}_{lon}_{date}.json` for weather)
- Graceful fallback: Missing cache → fetch → return None on error (no hard failures)
- TTL enforcement: JSON metadata (`fetched_at`, `source` field) for forecast staleness

---

*Integration audit: 2026-04-26*
