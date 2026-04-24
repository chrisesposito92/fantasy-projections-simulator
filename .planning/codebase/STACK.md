# Technology Stack

**Analysis Date:** 2026-04-24

## Languages

**Primary:**
- Python 3.12+ - Package source in `src/fantasy_sim/`, standalone tooling in `scripts/`, tests in `tests/`. Declared by `pyproject.toml` as `requires-python = ">=3.12"`.

**Secondary:**
- YAML - Runtime configuration in `config/defaults.yaml`, examples in `config/season.example.yaml`, `config/season.2025.yaml`, and `config/custom_scoring.example.yaml`.
- JSON - Validation ledgers and model artifacts in `results/`, bundled learned artifacts in `src/fantasy_sim/data/ensemble/artifacts/`, and raw external data caches managed by scripts.
- Markdown - Operational docs in `README.md`, `docs/AB-TESTING.md`, `docs/CLI-COMMANDS.md`, `docs/CONFIG.md`, and `docs/pff-setup.md`.

## Runtime

**Environment:**
- CPython 3.12+ is the supported runtime from `pyproject.toml`.
- Local workspace venv reports Python 3.13.11 at `.venv/bin/python`.
- CI runs Python 3.12, 3.13, and 3.14 in `.github/workflows/ci.yml`.

**Package Manager:**
- uv 0.10.12 in the local environment.
- Lockfile: `uv.lock` present.
- Package manifest: `pyproject.toml`.
- Local virtual environment: `.venv/` present and ignored by `.gitignore`.

## Frameworks

**Core:**
- Click 8.3.1 - CLI command framework used by `src/fantasy_sim/cli.py` and `scripts/scrape_pff_props.py`.
- Rich 14.3.3 - Terminal tables/progress output in `src/fantasy_sim/output/tables.py`, `src/fantasy_sim/validation/report.py`, and several `scripts/*.py`.
- Polars 1.39.3 - DataFrame engine throughout `src/fantasy_sim/data/`, `src/fantasy_sim/validation/`, and `scripts/`. Use polars for new data work, not pandas.
- NumPy 2.4.4 - Simulation arrays, random sampling, and numeric calculations in `src/fantasy_sim/engine/`, `src/fantasy_sim/models/`, and `src/fantasy_sim/scoring/`.

**Testing:**
- pytest 9.0.2 - Test runner configured in `pyproject.toml`.
- pytest-xdist 3.8.0 - Parallel test support declared in `pyproject.toml` and used by CI-capable test runs.
- Hypothesis 6.151.10 - Property-testing dependency declared in `pyproject.toml` and pinned in `uv.lock`.

**Build/Dev:**
- hatchling - Build backend declared in `pyproject.toml`.
- GitHub Actions - CI pipeline in `.github/workflows/ci.yml`.
- argparse - Standalone script CLIs in `scripts/validate.py`, `scripts/scrape_pff.py`, market-history scripts, and artifact-fitting scripts.

## Key Dependencies

**Critical:**
- `nflreadpy` 0.1.5 - nflverse data access in `src/fantasy_sim/data/loader.py` and FF Opportunity loading in `src/fantasy_sim/data/ensemble/loader.py`.
- `polars` 1.39.3 - Parquet IO, joins, aggregation, and schema casting in `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/data/market_history/loader.py`, and validation code.
- `numpy` 2.4.4 - Outcome distributions, Monte Carlo simulation, and learned-node math in `src/fantasy_sim/engine/monte_carlo.py`, `src/fantasy_sim/engine/play_resolver.py`, and `src/fantasy_sim/data/target_selection/training.py`.
- `scipy` 1.17.1 - Spearman/KS validation metrics in `src/fantasy_sim/validation/metrics.py` and L-BFGS fitting in `src/fantasy_sim/data/target_selection/training.py`.
- `pyyaml` 6.0.3 - YAML configuration loading in `src/fantasy_sim/config/loader.py` and CLI config resolution in `src/fantasy_sim/cli.py`.
- `httpx` 0.28.1 - External HTTP clients in `scripts/scrape_pff.py`, `scripts/scrape_pff_props.py`, `src/fantasy_sim/data/weather/provider.py`, and `src/fantasy_sim/data/market_history/events_inventory.py`.
- `thefuzz` 0.22.1 with `rapidfuzz` 3.14.3 - Fuzzy player-name resolution in `src/fantasy_sim/overrides/resolver.py` and market/props crosswalk code.

**Infrastructure:**
- `click` 8.3.1 - Installed package command `fantasy-sim = "fantasy_sim.cli:main"` in `pyproject.toml`.
- `rich` 14.3.3 - Human-readable CLI and validation output.
- `requests` 2.33.0 - Transitive/runtime support package present in the local environment.
- `pydantic` 2.12.5 and `pydantic-settings` 2.13.1 - Present in the local environment through dependencies.

## Configuration

**Environment:**
- Main runtime config lives in `config/defaults.yaml`.
- Scoring presets live under `scoring:` in `config/defaults.yaml`; `_inherit` chains are resolved by `src/fantasy_sim/config/loader.py`.
- Season overrides use `config/season.yaml` when present, or an explicit `--config` path. Example shape is in `config/season.example.yaml`.
- Custom scoring uses `config/custom_scoring.example.yaml` as the template and is loaded with `--scoring-config`.
- Repo root `.env` is present and ignored by `.gitignore`; secret contents were not inspected.
- External credential files are outside the repo at `~/.fantasy-sim/pff/.env` and `~/.fantasy-sim/market-history/.env`; do not inspect or commit their contents.

**Build:**
- `pyproject.toml` declares package metadata, runtime dependencies, dev dependencies, console script, build backend, and pytest config.
- `uv.lock` pins resolved dependency versions.
- `.github/workflows/ci.yml` installs uv, installs `.[dev]`, and runs pytest on Python 3.12/3.13/3.14.
- `.gitignore` excludes `.venv/`, caches, `.env`, `.planning/`, and most of `results/`.

## CLI And Scripts

**Installed CLI:**
- `fantasy-sim` is declared in `pyproject.toml` and implemented by `src/fantasy_sim/cli.py`.
- Subcommands in `src/fantasy_sim/cli.py`: `demo`, `week`, `season`, `game`, `player`, and `backtest`.
- Common output formats are Rich terminal tables, CSV, and JSON through `src/fantasy_sim/output/export.py`.

**Validation:**
- Primary A/B harness: `scripts/validate.py`.
- Bare-baseline cache helpers: `src/fantasy_sim/validation/cache.py`.
- Unified ledger helpers: `src/fantasy_sim/validation/ledger.py`.
- Historical validation scripts: `scripts/validate_pff_signal.py` and `scripts/validate_weekly_signal.py`.
- Sanity scripts: `scripts/validate_data.py`, `scripts/validate_players.py`, `scripts/validate_sim.py`, `scripts/validate_passing.py`, and `scripts/validate_tier_spotcheck.py`.

**Data Acquisition:**
- PFF game/fantasy scraper: `scripts/scrape_pff.py`.
- PFF props scraper: `scripts/scrape_pff_props.py`.
- The Odds API event inventory: `scripts/fetch_market_history_events.py`.
- The Odds API props snapshots: `scripts/fetch_market_history_props.py`.
- Market-history aggregation: `scripts/build_market_history_player_markets.py`.
- Legacy market-history importer: `scripts/import_market_history.py`.
- Tracking/nflverse backfill: `scripts/backfill_tracking_data.py`.

**Model Artifact Fitting:**
- Dynamic blend weights: `scripts/fit_dynamic_blend_weights.py`.
- Residual calibration buckets: `scripts/fit_residual_calibration.py`.
- Receiver target-selection artifacts: `scripts/fit_target_selection.py`.
- PFF coefficient/talent sweeps: `scripts/fit_talent_coefficients.py` and `scripts/sweep_talent_params.py`.

## Data And Artifact Formats

**Parquet:**
- nflverse cache files are written by `src/fantasy_sim/data/loader.py` under `~/.fantasy-sim/cache/`.
- PFF processed facets are read from `~/.fantasy-sim/pff/processed/nfl/` by `src/fantasy_sim/data/pff/loader.py`.
- Market-history processed player markets are read from `~/.fantasy-sim/market-history/processed/` by `src/fantasy_sim/data/market_history/loader.py`.

**JSON:**
- A/B validation ledger: `results/ab_ledger.json`.
- Bare-baseline validation caches: `results/cache/bare_<season>_<sims>_<scoring>_<training_years>.json`.
- Bundled dynamic-blend artifacts: `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json` and `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json`.
- Bundled residual-calibration artifacts: `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json` and `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json`.
- Experimental artifacts exist under `results/dynamic_blend/`, `results/residual_calibration/`, and `results/target_selection/`.

## Platform Requirements

**Development:**
- Python 3.12+.
- uv with `uv.lock`.
- Network access for first-run nflverse data pulls, Open-Meteo weather, PFF scraping, and The Odds API market-history fetching.
- PFF Premium credentials for `scripts/scrape_pff.py`; PFF API key for `scripts/scrape_pff_props.py`.
- The Odds API key for `scripts/fetch_market_history_events.py` and `scripts/fetch_market_history_props.py`.

**Production:**
- No web server or hosted app target is defined.
- Runtime is a local/package CLI that reads YAML config, local parquet/JSON caches, bundled artifacts, and optional external data caches.
- CI target is GitHub Actions via `.github/workflows/ci.yml`.

---

*Stack analysis: 2026-04-24*
