# External Integrations

**Analysis Date:** 2026-04-24

## APIs & External Services

**nflverse Data via nflreadpy:**
- nflverse - Core public NFL data used for historical play-by-play, rosters, schedules, actuals, injuries, snap counts, Next Gen Stats, participation, FTN charting, depth charts, draft picks, and FF Opportunity.
  - SDK/Client: `nflreadpy` in `src/fantasy_sim/data/loader.py` and `src/fantasy_sim/data/ensemble/loader.py`.
  - Auth: None detected.
  - Cache: `~/.fantasy-sim/cache/*.parquet` through `DataLoader._cache_key()` in `src/fantasy_sim/data/loader.py`.
  - Runtime consumers: `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/validation/backtester.py`, `scripts/validate.py`, and `src/fantasy_sim/cli.py`.

**PFF Premium Game And Fantasy Data:**
- PFF Premium REST API - Game-level player facets for PFF intelligence engines.
  - SDK/Client: `httpx.Client` in `scripts/scrape_pff.py`.
  - Auth: `PFF_COOKIE` in `~/.fantasy-sim/pff/.env`; do not inspect or commit this file.
  - Base URL: `https://premium.pff.com`.
  - Raw cache: `~/.fantasy-sim/pff/raw/<league>/facets/<season>/week_<week>/`.
  - Processed cache: `~/.fantasy-sim/pff/processed/nfl/{facet}_{season}.parquet` and `~/.fantasy-sim/pff/processed/ncaa/{facet}_{season}.parquet`.
  - Runtime loader: `src/fantasy_sim/data/pff/loader.py`.
- PFF fantasy stats endpoints - Aggregate receiving and passing stats used by PFF-derived TD tendency/fantasy feature workflows.
  - SDK/Client: `httpx.Client` in `scripts/scrape_pff.py`.
  - Auth: same PFF cookie path as game facets.
  - Endpoint family: `https://www.pff.com/api/fantasy/stats/...`.
  - Output: `~/.fantasy-sim/pff/processed/nfl/fantasy_receiving_<season>.parquet` and `~/.fantasy-sim/pff/processed/nfl/fantasy_passing_<season>.parquet`.

**PFF Consumer Player Props:**
- PFF consumer betting API - Consensus player props used by the Vegas props engine.
  - SDK/Client: `httpx.Client` in `scripts/scrape_pff_props.py`.
  - Auth: `PFF_API_KEY` from shell environment or `~/.fantasy-sim/pff/.env`; do not inspect or commit this file.
  - Base URL: `https://consumer-api.pff.com/football/v3/betting/nfl`.
  - Raw/processed cache: `~/.fantasy-sim/pff/props/props_<season>_week<week>.parquet`.
  - Runtime loader: `src/fantasy_sim/data/vegas/props_loader.py`.
  - Runtime engine: `src/fantasy_sim/data/vegas/props_engine.py`.

**The Odds API Market History:**
- The Odds API v4 historical events - Event-id inventory used before fetching historical player props.
  - SDK/Client: `httpx.Client` in `src/fantasy_sim/data/market_history/events_inventory.py`.
  - Auth: `THE_ODDS_API_KEY` or legacy `THE_ODDS_API` from shell environment or `~/.fantasy-sim/market-history/.env`; do not inspect or commit this file.
  - Base URL: `https://api.the-odds-api.com`.
  - Sport key: `americanfootball_nfl`.
  - Raw cache: `~/.fantasy-sim/market-history/raw/events/<season>/<gameday>.json`.
  - Processed inventory: `~/.fantasy-sim/market-history/processed/events_inventory_<season>.parquet`.
  - Fetch script: `scripts/fetch_market_history_events.py`.
- The Odds API v4 historical event odds - Historical player prop snapshots for market-history priors.
  - SDK/Client: `httpx.Client` in `src/fantasy_sim/data/market_history/props_backfill.py`.
  - Auth: same The Odds API env/file source as event inventory.
  - Raw cache: `~/.fantasy-sim/market-history/raw/props/<season>/<snapshot_label>/<event_id>.json`.
  - Aggregated player markets: `~/.fantasy-sim/market-history/processed/player_markets_<season>_<snapshot_label>.parquet`.
  - Fetch script: `scripts/fetch_market_history_props.py`.
  - Build script: `scripts/build_market_history_player_markets.py`.
  - Runtime loader: `src/fantasy_sim/data/market_history/loader.py`.
  - Runtime scorer: `src/fantasy_sim/scoring/market_history.py`.

**Open-Meteo Weather:**
- Open-Meteo archive/forecast APIs - Game-day weather adjustments.
  - SDK/Client: `httpx.get` in `src/fantasy_sim/data/weather/provider.py`.
  - Auth: None.
  - Historical URL: `https://archive-api.open-meteo.com/v1/archive`.
  - Forecast URL: `https://api.open-meteo.com/v1/forecast`.
  - Cache: `~/.fantasy-sim/weather/<lat>_<lon>_<date>.json`.
  - Engine: `src/fantasy_sim/data/weather/engine.py`.
  - Stadium registry: `src/fantasy_sim/data/weather/stadiums.py`.

**Vegas Lines From nflverse Schedules:**
- nflverse schedule lines - Spread and total fields used as Vegas pace/pass-rate signals.
  - SDK/Client: `DataLoader.load_schedules()` in `src/fantasy_sim/data/loader.py`.
  - Auth: None.
  - Engine: `src/fantasy_sim/data/vegas/engine.py`.
  - Config: `vegas:` and `vegas.props:` in `config/defaults.yaml`.

## Data Storage

**Databases:**
- Not detected.
  - Connection: Not applicable.
  - Client: Not applicable.

**File Storage:**
- Local filesystem only.
- Repo-local generated outputs include `results/ab_ledger.json`, `results/cache/`, `results/dynamic_blend/`, `results/residual_calibration/`, and `results/target_selection/`.
- User-home data caches live under `~/.fantasy-sim/cache/`, `~/.fantasy-sim/pff/`, `~/.fantasy-sim/weather/`, and `~/.fantasy-sim/market-history/`.

**Caching:**
- nflverse parquet cache: `src/fantasy_sim/data/loader.py`.
- PFF raw JSON, processed parquet, and scrape progress cache: `scripts/scrape_pff.py`.
- PFF props parquet cache: `scripts/scrape_pff_props.py` and `src/fantasy_sim/data/vegas/props_loader.py`.
- Weather JSON cache with forecast TTL: `src/fantasy_sim/data/weather/provider.py`.
- Market-history raw JSON and processed parquet caches: `src/fantasy_sim/data/market_history/events_inventory.py`, `src/fantasy_sim/data/market_history/props_backfill.py`, and `src/fantasy_sim/data/market_history/player_markets.py`.
- Bare validation cache: `src/fantasy_sim/validation/cache.py`.
- In-process caches exist in `DataLoader._memory_cache` in `src/fantasy_sim/data/loader.py`, `PffLoader._crosswalk_cache` in `src/fantasy_sim/data/pff/loader.py`, and projection-adjuster artifact caches in `src/fantasy_sim/scoring/dynamic_blend.py` and `src/fantasy_sim/scoring/residual_calibration.py`.

## Authentication & Identity

**Auth Provider:**
- No application login/auth provider is implemented.
  - Implementation: Local CLI only; external service credentials are read by scripts when acquiring data.

**External Auth Inputs:**
- `PFF_COOKIE` - Read from `~/.fantasy-sim/pff/.env` by `scripts/scrape_pff.py`.
- `PFF_API_KEY` - Read from shell environment or `~/.fantasy-sim/pff/.env` by `scripts/scrape_pff_props.py`.
- `THE_ODDS_API_KEY` or `THE_ODDS_API` - Read from shell environment or `~/.fantasy-sim/market-history/.env` by `src/fantasy_sim/data/market_history/events_inventory.py`.
- `FANTASY_SIM_BUILD_MODE=process` - Optional validation parallelism mode in `src/fantasy_sim/validation/parallel.py`.

**Identity Crosswalks:**
- PFF player IDs map to nflverse `player_id` through roster `pff_id` and exact name/team fallback in `src/fantasy_sim/data/pff/loader.py`.
- PFF props use PFF `player_id` and the PFF crosswalk in `src/fantasy_sim/data/vegas/props_engine.py`.
- The Odds API player names are normalized and matched through `src/fantasy_sim/data/market_history/crosswalk.py` and `src/fantasy_sim/data/market_history/loader.py`.
- User override names are resolved through exact id/name, underscore conversion, and fuzzy matching in `src/fantasy_sim/overrides/resolver.py`.

## Monitoring & Observability

**Error Tracking:**
- None detected.

**Logs:**
- Python `logging` is used by runtime loaders and engines in `src/fantasy_sim/data/`, `src/fantasy_sim/scoring/`, and `src/fantasy_sim/validation/`.
- Rich console/progress output is used by acquisition and validation scripts such as `scripts/scrape_pff.py`, `scripts/fetch_market_history_events.py`, and `scripts/validate.py`.
- Persistent validation history is stored in `results/ab_ledger.json` through `src/fantasy_sim/validation/ledger.py`.

## CI/CD & Deployment

**Hosting:**
- Not detected. The project is a local/package CLI, not a deployed service.

**CI Pipeline:**
- GitHub Actions in `.github/workflows/ci.yml`.
- Main test job installs uv through `astral-sh/setup-uv@v4`, sets up Python 3.12/3.13/3.14, installs `.[dev]`, and runs non-integration/non-statistical pytest tests.
- Statistical test job runs only when a pull request has the `run-statistical-tests` label and uses Python 3.14.

## Environment Configuration

**Required env vars:**
- None required for `fantasy-sim demo` and local simulations that can use cached/public data.
- `PFF_COOKIE` is required in `~/.fantasy-sim/pff/.env` for `scripts/scrape_pff.py`.
- `PFF_API_KEY` is required in shell environment or `~/.fantasy-sim/pff/.env` for `scripts/scrape_pff_props.py`.
- `THE_ODDS_API_KEY` or `THE_ODDS_API` is required in shell environment or `~/.fantasy-sim/market-history/.env` for `scripts/fetch_market_history_events.py` and `scripts/fetch_market_history_props.py`.
- `FANTASY_SIM_BUILD_MODE` is optional and only changes validation build parallelism in `src/fantasy_sim/validation/parallel.py`.

**Secrets location:**
- Repo root `.env` exists and is ignored by `.gitignore`; contents were not inspected.
- PFF secrets are stored outside the repo in `~/.fantasy-sim/pff/.env`; contents must not be inspected or committed.
- The Odds API secrets are stored outside the repo in `~/.fantasy-sim/market-history/.env`; contents must not be inspected or committed.

## Webhooks & Callbacks

**Incoming:**
- None detected.

**Outgoing:**
- `nflreadpy` requests/downloads nflverse data from its configured upstream sources through `src/fantasy_sim/data/loader.py`.
- `httpx` calls PFF Premium and PFF consumer APIs in `scripts/scrape_pff.py` and `scripts/scrape_pff_props.py`.
- `httpx` calls The Odds API in `src/fantasy_sim/data/market_history/events_inventory.py` and `src/fantasy_sim/data/market_history/props_backfill.py`.
- `httpx` calls Open-Meteo in `src/fantasy_sim/data/weather/provider.py`.

## Integration Workflows

**PFF Data Workflow:**
- Acquire raw PFF game facets with `scripts/scrape_pff.py`.
- Process raw PFF JSON into parquet with `scripts/scrape_pff.py --process-only`.
- Runtime PFF engines read processed parquet through `src/fantasy_sim/data/pff/loader.py`.

**PFF Props Workflow:**
- Acquire weekly props with `scripts/scrape_pff_props.py`.
- Runtime props integration reads cached parquet through `src/fantasy_sim/data/vegas/props_loader.py`.
- Missing props cache returns an empty polars DataFrame from `PropsLoader.load_props()` in `src/fantasy_sim/data/vegas/props_loader.py`.

**Market-History Workflow:**
- Fetch event inventory with `scripts/fetch_market_history_events.py`.
- Fetch event prop snapshots with `scripts/fetch_market_history_props.py`.
- Build player-market parquet with `scripts/build_market_history_player_markets.py`.
- Runtime market-history projection adjustment reads `player_markets_<season>_<snapshot_label>.parquet` through `src/fantasy_sim/data/market_history/loader.py` and `src/fantasy_sim/scoring/market_history.py`.

**Validation And Artifact Workflow:**
- Run A/B validation with `scripts/validate.py`.
- Refit dynamic blend artifacts with `scripts/fit_dynamic_blend_weights.py`.
- Refit residual calibration artifacts with `scripts/fit_residual_calibration.py`.
- Refit target-selection artifacts with `scripts/fit_target_selection.py`.
- Bundled dynamic-blend and residual-calibration artifacts are read by `src/fantasy_sim/scoring/dynamic_blend.py` and `src/fantasy_sim/scoring/residual_calibration.py`.

---

*Integration audit: 2026-04-24*
