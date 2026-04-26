# Technology Stack

**Analysis Date:** 2026-04-26

## Languages

**Primary:**
- Python 3.12+ - Core application language, enforced via `requires-python >= 3.12`

## Runtime

**Environment:**
- Python 3.12 (uv-managed via `pyproject.toml`)

**Package Manager:**
- uv (for reproducible builds, specified in `pyproject.toml`)
- Lockfile: `uv.lock` present (132.5K)

## Frameworks

**Core:**
- nflreadpy 0.1.0+ - Fetches NFL play-by-play, rosters, schedules, player stats, draft picks from nflverse
- polars 1.0.0+ - DataFrame operations (NOT pandas); replaces traditional data manipulation
- numpy 2.0.0+ - Numerical arrays and Monte Carlo random sampling; random number generation via `np.random.Generator`

**Data Processing:**
- scipy 1.14.0+ - Statistical functions (distributions, empirical analysis)
- PyYAML 6.0+ - Configuration parsing for defaults.yaml, season configs, scoring presets

**CLI & Output:**
- Click 8.0+ - Command-line interface (`fantasy-sim` entry point at `src/fantasy_sim/cli.py`)
- Rich 13.0+ - Terminal output (tables, progress, console output)

**HTTP & APIs:**
- httpx 0.27.0+ - HTTP client for PFF (premium), Open-Meteo (weather), The Odds API (props)

**Testing:**
- pytest 8.0+ (primary test runner, 1200+ tests)
- pytest-xdist 3.0+ - Parallel test execution
- hypothesis 6.0+ - Property-based testing for validation

**Utilities:**
- thefuzz 0.22.0+ - Fuzzy string matching (player name crosswalk, Levenshtein distance ≥0.85 for props)

## Key Dependencies

**Critical:**
- nflreadpy - Public NFL data source (no auth); blocks entire pipeline if unavailable
- polars - DataFrame operations throughout data layer and analysis
- httpx - Required for API integrations (PFF, Open-Meteo, The Odds API)

**Infrastructure:**
- numpy - Non-parametric distribution sampling (core to play-by-play resolution)
- scipy - Statistical calculations for validation metrics (Spearman, MAE, KS distribution)
- PyYAML - Configuration inheritance chain (defaults → season → CLI overrides)

## Configuration

**Environment:**
- YAML-based configuration with inheritance chain
  - `config/defaults.yaml` - Base configuration (simulation, scoring, PFF engines, weather, vegas, ensemble settings)
  - `config/season.{year}.yaml` - Season-specific overrides (e.g., `season.2025.yaml`)
  - `config/custom_scoring.example.yaml` - User-definable scoring systems
  - CLI flags override config file values

**Key Configuration Files:**
- `config/defaults.yaml` (10.8K) - Master config with 50+ config sections:
  - `simulation:` (num_sims, training_years, historical_seasons)
  - `scoring:` (PPR/half-PPR/standard with `_inherit` chains)
  - `positions:` (min_snaps/targets per position)
  - `pff:` (tier_engine, team_context, matchup, coverage, rb_scheme_fit, qb_split, kicker, dst_baseline)
  - `weather:` (wind, temperature, precipitation sensitivities)
  - `vegas:` (ITT pace, spread conditioning, player props)
  - `usage:` (snap counts, CPOE, NGS, route rate)
  - `ensemble:` (ff_opportunity, dynamic_blend, residual_calibration)
  - `market_history:` (market consensus blend)
  - `availability:` (injuries, depth charts)
  - `role_trend, game_script, td_tendency:` (conditional adjustment layers)

## Build

**Build System:**
- hatchling (specified in `pyproject.toml` `build-system`)
- CLI entry point: `fantasy-sim = "fantasy_sim.cli:main"` at `src/fantasy_sim/cli.py`

**Output Artifacts:**
- Parquet files (nflverse cache at `~/.fantasy-sim/cache/`)
- JSON cache (weather at `~/.fantasy-sim/weather/`)
- Parquet cache (PFF processed at `~/.fantasy-sim/pff/processed/`)
- Parquet cache (player props at `~/.fantasy-sim/pff/props/`)
- CSV/JSON export via `--format csv|json --output path`

## Platform Requirements

**Development:**
- Python 3.12+
- uv package manager
- Unix-like shell (scripts use bash/zsh)
- Network access to nflverse (public), Open-Meteo (free), PFF (premium subscription), The Odds API (paid)

**Production:**
- Python 3.12+ runtime
- File write permissions for `~/.fantasy-sim/` cache directories
- Optional: PFF premium subscription (if using PFF intelligence layers)
- Optional: The Odds API key (if using player props engine)

**Testing:**
- pytest 8.0+, pytest-xdist, hypothesis
- Network isolation (unit tests mock nflreadpy via `unittest.mock.patch`)
- Markers: `@pytest.mark.integration` (network-required), `@pytest.mark.statistical` (slow, bulk sim)

---

*Stack analysis: 2026-04-26*
