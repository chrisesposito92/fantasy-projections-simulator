# Coding Conventions

**Analysis Date:** 2026-04-24

## Naming Patterns

**Files:**
- Use lowercase snake_case Python modules under `src/fantasy_sim/`: examples include `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/engine/play_resolver.py`, `src/fantasy_sim/scoring/residual_calibration.py`, and `src/fantasy_sim/validation/parallel.py`.
- Keep subsystem-specific implementations in matching package directories: PFF code goes in `src/fantasy_sim/data/pff/`, Vegas code in `src/fantasy_sim/data/vegas/`, weather code in `src/fantasy_sim/data/weather/`, scoring layers in `src/fantasy_sim/scoring/`, and validation utilities in `src/fantasy_sim/validation/`.
- Use `models.py` for subsystem dataclasses such as `src/fantasy_sim/data/pff/models.py`, `src/fantasy_sim/data/vegas/models.py`, `src/fantasy_sim/data/weather/models.py`, and `src/fantasy_sim/data/market_history/models.py`.
- Use `config.py` for typed config loaders and dataclass resolution, such as `src/fantasy_sim/data/pff/config.py`, `src/fantasy_sim/data/weather/config.py`, `src/fantasy_sim/data/vegas/config.py`, and `src/fantasy_sim/validation/config.py`.

**Functions:**
- Use snake_case for functions and methods: `bucket_play()` in `src/fantasy_sim/models/game_state.py`, `run_simulations()` in `src/fantasy_sim/engine/monte_carlo.py`, `build_player_projections()` in `src/fantasy_sim/scoring/projections.py`, and `ks_distribution_summary()` in `src/fantasy_sim/validation/metrics.py`.
- Use a leading underscore for private helpers scoped to a module or class: `_parse_value()` in `src/fantasy_sim/validation/config.py`, `_red_zone_td_gate()` in `src/fantasy_sim/engine/play_resolver.py`, `_filter_available()` in `src/fantasy_sim/engine/player_selector.py`, and `_normalize_weekly_fpts_ks()` in `src/fantasy_sim/validation/ledger.py`.
- Loader functions follow `load_*` names when reading config/data: `load_defaults()` in `src/fantasy_sim/config/loader.py`, `load_pff_config()` in `src/fantasy_sim/data/pff/config.py`, `load_weather_config()` in `src/fantasy_sim/data/weather/config.py`, and `load_weekly()` in `src/fantasy_sim/data/market_history/loader.py`.
- Builder/aggregation functions follow `build_*` or `compute_*`: `DataPipeline.build()` in `src/fantasy_sim/data/pipeline.py`, `Preprocessor.compute_play_outcomes()` in `src/fantasy_sim/data/preprocessor.py`, `build_engine_configs()` in `src/fantasy_sim/validation/config.py`, and `build_detailed_projections()` in `src/fantasy_sim/scoring/projections.py`.

**Variables:**
- Use descriptive snake_case for local values and dict keys: `training_seasons`, `target_season`, `season_weights`, `cache_path`, `weekly_fpts_ks`, and `stat_ks` appear in `src/fantasy_sim/data/preprocessor.py`, `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/validation/ledger.py`, and `scripts/validate.py`.
- Use domain abbreviations only where they are established: `pbp` in `src/fantasy_sim/data/preprocessor.py`, `pff_config` in `src/fantasy_sim/data/game_context.py`, `rng` in `src/fantasy_sim/engine/game_sim.py`, and `fpts` in `src/fantasy_sim/scoring/projections.py`.
- Use all-caps module constants for calibrated values and schemas: `MIN_BUCKET_PLAYS` in `src/fantasy_sim/data/preprocessor.py`, `PASS_TD_GATE` in `src/fantasy_sim/engine/play_resolver.py`, `PLAYER_MARKET_SOURCE_SCHEMA` in `src/fantasy_sim/data/market_history/loader.py`, and `CURRENT_LEDGER_SCHEMA_VERSION` in `src/fantasy_sim/validation/ledger.py`.

**Types:**
- Use PascalCase for dataclasses and protocol types: `GameStateBucket` in `src/fantasy_sim/models/game_state.py`, `TeamDistributions` in `src/fantasy_sim/engine/types.py`, `PffConfig` in `src/fantasy_sim/data/pff/models.py`, and `TargetSelectionContextProtocol` in `src/fantasy_sim/engine/types.py`.
- Use `Config`, `Context`, `Factors`, `Model`, and `Result` suffixes consistently: `WeatherConfig`, `WeatherContext`, and `GameWeather` in `src/fantasy_sim/data/weather/models.py`; `VegasConfig` and `VegasContext` in `src/fantasy_sim/data/vegas/models.py`; `GameSpec` and `GameSimResult` in `src/fantasy_sim/validation/parallel.py`.
- Use `@dataclass(frozen=True)` for hashable value objects used as dict keys or immutable raw records: `GameStateBucket` in `src/fantasy_sim/models/game_state.py` and `GameWeather` in `src/fantasy_sim/data/weather/models.py`.

## Code Style

**Formatting:**
- No formatter config is detected in `pyproject.toml`; follow the existing 4-space Python style used across `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/data/preprocessor.py`, and `src/fantasy_sim/validation/metrics.py`.
- Keep function signatures typed and explicit. Most production modules use Python 3.12 union syntax such as `TeamRoster | None`, `dict[str, float]`, and `tuple[list[PlayerModel], np.ndarray]` in `src/fantasy_sim/engine/player_selector.py`, `src/fantasy_sim/models/player.py`, and `src/fantasy_sim/validation/config.py`.
- Prefer `from __future__ import annotations` in newer modules that use forward references or heavy type imports, as in `src/fantasy_sim/engine/types.py`, `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/data/pff/config.py`, `src/fantasy_sim/data/weather/provider.py`, and `scripts/validate.py`.
- Use `TYPE_CHECKING` blocks to avoid runtime circular imports or expensive imports, as in `src/fantasy_sim/engine/types.py`, `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/engine/play_resolver.py`, and `src/fantasy_sim/validation/parallel.py`.

**Linting:**
- Not detected. `pyproject.toml` defines pytest settings and dependencies but has no `[tool.ruff]`, `[tool.black]`, or `[tool.mypy]` sections.
- Keep style aligned with existing code instead of introducing new lint-only churn in `src/fantasy_sim/` or `tests/`.

## Import Organization

**Order:**
1. Standard library imports first: examples include `json`, `logging`, `Path`, `dataclass`, `field`, and `TYPE_CHECKING` in `src/fantasy_sim/validation/ledger.py`, `src/fantasy_sim/data/weather/provider.py`, and `src/fantasy_sim/validation/parallel.py`.
2. Third-party imports next: `numpy as np`, `polars as pl`, `httpx`, `yaml`, and `scipy.stats` appear in `src/fantasy_sim/data/preprocessor.py`, `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/data/weather/provider.py`, `src/fantasy_sim/config/loader.py`, and `src/fantasy_sim/validation/metrics.py`.
3. Local `fantasy_sim.*` imports last: examples include `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/data/pipeline.py`, `src/fantasy_sim/scoring/projections.py`, and `src/fantasy_sim/validation/config.py`.
- Deferred local imports are acceptable to avoid cycles or subprocess import issues, such as `from fantasy_sim.engine.player_selector import select_passer, select_receiver` inside `src/fantasy_sim/engine/play_resolver.py` and deferred `GameContextBuilder` imports in `src/fantasy_sim/validation/parallel.py`.

**Path Aliases:**
- Use package imports rooted at `fantasy_sim`, not relative imports, throughout `src/fantasy_sim/`.
- `pyproject.toml` sets `pythonpath = ["src"]` for tests, so tests import `fantasy_sim.*` directly, as in `tests/test_engine/test_player_selector.py`, `tests/test_data/test_loader.py`, and `tests/test_validation/test_metrics.py`.
- Script tests that target files in `scripts/` add the script directory to `sys.path`, as in `tests/test_scripts/test_scrape_pff.py` and `tests/test_scripts/test_scrape_pff_props.py`.

## Type Hints And Data Models

**Dataclasses:**
- Use dataclasses for domain records, simulation state, config, and validation ledger entries. Examples: `PlayerModel`, `PlayerUsage`, and `TeamRoster` in `src/fantasy_sim/models/player.py`; `GameState`, `PlayResult`, and `GameResult` in `src/fantasy_sim/engine/types.py`; `SeasonMetrics` and `LedgerEntry` in `src/fantasy_sim/validation/ledger.py`.
- Use `field(default_factory=...)` for mutable defaults such as lists, dicts, and nested config objects. Examples: `weeks_missed` in `src/fantasy_sim/models/player.py`, `defensive_td_rates` in `src/fantasy_sim/engine/types.py`, config dict defaults in `src/fantasy_sim/data/pff/models.py`, and `stat_ks` in `src/fantasy_sim/validation/ledger.py`.
- Avoid mutable literal defaults in dataclasses. Use factories like `field(default_factory=dict)` and `field(default_factory=WeatherConfig)` patterns shown in `src/fantasy_sim/data/pff/models.py`, `src/fantasy_sim/data/weather/models.py`, and `src/fantasy_sim/validation/parallel.py`.

**Type Hints:**
- Use precise container types on public functions and dataclass fields: `dict[str, PlayCallingDist]` in `src/fantasy_sim/data/preprocessor.py`, `list[GameSpec]` in `src/fantasy_sim/validation/parallel.py`, `Mapping[str, object]` in `scripts/validate.py`, and `Sequence[float]` in `src/fantasy_sim/validation/metrics.py`.
- Use `object` or `dict` only at boundaries where config, JSON, or projection row shapes are intentionally dynamic: `apply_overrides()` in `src/fantasy_sim/validation/config.py`, `LedgerEntry.config_snapshot` in `src/fantasy_sim/validation/ledger.py`, and projection rows in `src/fantasy_sim/scoring/projections.py`.
- Use protocols for optional extension surfaces instead of concrete imports when the engine consumes a narrow interface. `TargetSelectionContextProtocol` in `src/fantasy_sim/engine/types.py` defines the learned target-selection hook used by `src/fantasy_sim/engine/player_selector.py`.

## DataFrame And Numeric Conventions

**Polars:**
- Use `polars as pl` for all DataFrame work. Examples include `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/data/preprocessor.py`, `src/fantasy_sim/data/market_history/loader.py`, `src/fantasy_sim/data/pff/tier_engine.py`, `scripts/validate.py`, and tests under `tests/test_data/`.
- Do not introduce pandas. No `import pandas` usage is detected in `src/`, `scripts/`, or `tests/`; keep all DataFrame fixtures and transformations in polars.
- Use polars expressions for filtering, casting, joining, schema stabilization, and parquet IO: `pl.col(...).is_in(...)` in `src/fantasy_sim/data/preprocessor.py`, `pl.read_parquet()` and `write_parquet()` in `src/fantasy_sim/data/loader.py`, `pl.concat(..., how="diagonal_relaxed")` in `src/fantasy_sim/data/loader.py`, and schema casts in `src/fantasy_sim/data/market_history/loader.py`.
- Return typed empty `pl.DataFrame(schema=...)` from data loaders when data is missing but the pipeline can continue. Examples: `PropsLoader._empty_df()` in `src/fantasy_sim/data/vegas/props_loader.py` and `MarketHistoryLoader.load_weekly()` in `src/fantasy_sim/data/market_history/loader.py`.

**Numpy:**
- Use `numpy as np` for numerical arrays, random sampling, percentiles, correlations, and simulation summaries. Examples include `src/fantasy_sim/models/distributions.py`, `src/fantasy_sim/engine/monte_carlo.py`, `src/fantasy_sim/scoring/projections.py`, and `src/fantasy_sim/validation/metrics.py`.
- Empirical distributions are stored as `np.ndarray` fields and sampled with `rng.choice(...)`, as in `PlayOutcomeDist.sample_yards()` in `src/fantasy_sim/models/distributions.py`, `PlayerOutcomes` in `src/fantasy_sim/models/player.py`, and `src/fantasy_sim/engine/play_resolver.py`.
- Convert numpy scalar outputs to plain Python floats before writing projection rows or JSON-facing metrics, as in `src/fantasy_sim/scoring/projections.py` and `src/fantasy_sim/validation/metrics.py`.

**RNG Handling:**
- Pass `np.random.Generator` explicitly through simulation code. `run_simulations()` in `src/fantasy_sim/engine/monte_carlo.py` creates `rng = np.random.default_rng(seed)` and passes it into `simulate_game()` in `src/fantasy_sim/engine/game_sim.py`.
- Public play-level functions accept `rng: np.random.Generator` rather than using global random state: `resolve_play()` in `src/fantasy_sim/engine/play_resolver.py`, `select_receiver()` and `select_rusher()` in `src/fantasy_sim/engine/player_selector.py`, and `DriveStartModel.sample_start_yardline()` in `src/fantasy_sim/models/distributions.py`.
- Use deterministic seeds in tests and validation harnesses. Examples: `np.random.default_rng(42)` in `tests/test_engine/test_player_selector.py`, `run_simulations(..., seed=42)` in `tests/test_engine/test_statistical_validation.py`, and CRC32 game seeds in `scripts/validate.py`.
- Avoid `np.random.RandomState` in production. It appears in fixture generation in `tests/conftest.py` for legacy deterministic sample data; new production code should use `np.random.default_rng()`.

## Config And Loader Patterns

**YAML Config Loading:**
- Load raw YAML through `load_config()` and `load_defaults()` in `src/fantasy_sim/config/loader.py`; raise `ConfigError` for missing files, invalid mappings, unknown scoring formats, and circular scoring inheritance.
- Resolve feature-specific dataclasses from the full defaults dict through subsystem loaders: `load_pff_config()` in `src/fantasy_sim/data/pff/config.py`, `load_weather_config()` in `src/fantasy_sim/data/weather/config.py`, `load_vegas_config()` and `load_props_config()` in `src/fantasy_sim/data/vegas/config.py`, and `build_engine_configs()` in `src/fantasy_sim/validation/config.py`.
- Treat disabled or missing config sections as neutral config dataclasses or `None` engine kwargs. `build_engine_configs()` in `src/fantasy_sim/validation/config.py` returns `None` for disabled engines; `build_bare_engine_configs()` returns all engine configs disabled.

**Override Parsing:**
- Use dot-notation overrides for validation configs through `apply_overrides()` in `src/fantasy_sim/validation/config.py`.
- Validate override keys by requiring every path segment and leaf to already exist. Unknown keys raise `KeyError` with the full dotted path in `src/fantasy_sim/validation/config.py`.
- Parse CLI override values into bool, int, float, list, or string via `_parse_value()` in `src/fantasy_sim/validation/config.py`.

**Cache And IO:**
- Use `Path` for filesystem paths, create cache directories in constructors, and keep cache roots configurable for tests. Examples: `DataLoader` in `src/fantasy_sim/data/loader.py`, `WeatherProvider` in `src/fantasy_sim/data/weather/provider.py`, and `MarketHistoryLoader` in `src/fantasy_sim/data/market_history/loader.py`.
- Do not read secret files during normal mapping or documentation. Secret-bearing runtime paths such as `~/.fantasy-sim/pff/.env` and `~/.fantasy-sim/props/.env` are external configuration, not codebase documentation inputs.

## Error Handling

**Patterns:**
- Raise specific exceptions for invalid inputs that should fail fast: `ConfigError` in `src/fantasy_sim/config/loader.py`, `ValueError` for invalid `n_sims` in `src/fantasy_sim/engine/monte_carlo.py`, `ValueError` for bad `play_type` in `src/fantasy_sim/engine/play_resolver.py`, and `KeyError` for unknown override paths in `src/fantasy_sim/validation/config.py`.
- Include the offending value in exception messages. Examples: `n_sims must be positive` in `src/fantasy_sim/engine/monte_carlo.py`, `Unexpected play_type` in `src/fantasy_sim/engine/play_resolver.py`, and `Invalid projection fpts` in `scripts/validate.py`.
- Use safe fallback returns for optional external data paths where absence is allowed: `WeatherProvider.get_weather()` returns `None` on API error in `src/fantasy_sim/data/weather/provider.py`; `PropsLoader.load_props()` returns an empty schema DataFrame when disabled or missing cache in `src/fantasy_sim/data/vegas/props_loader.py`.
- Use worker-level exception capture in validation parallelism so one bad game can be skipped with diagnostic metadata while the run continues. Examples: `_do_build_single()` and `_do_build_dual()` in `src/fantasy_sim/validation/parallel.py`.
- Re-raise process-pool infrastructure failures as actionable runtime errors. `simulate_games_parallel()` and build helpers in `src/fantasy_sim/validation/parallel.py` raise `RuntimeError("Worker process crashed. Try --workers 1 for sequential mode.")` on `BrokenExecutor`.

## Logging

**Framework:** `logging`

**Patterns:**
- Use module loggers with `logger = logging.getLogger(__name__)`, as in `src/fantasy_sim/validation/parallel.py`, `src/fantasy_sim/validation/coverage.py`, `src/fantasy_sim/data/weather/provider.py`, `src/fantasy_sim/data/vegas/engine.py`, and `src/fantasy_sim/data/vegas/props_loader.py`.
- Use `logger.warning(..., exc_info=True)` when swallowing exceptions that should be visible during diagnostics, as in `src/fantasy_sim/validation/parallel.py` and `src/fantasy_sim/data/weather/provider.py`.
- Use `logger.debug()` for cache miss/hit messages and low-noise diagnostics, such as PFF props cache messages in `src/fantasy_sim/data/vegas/props_loader.py` and Vegas schedule diagnostics in `src/fantasy_sim/data/vegas/engine.py`.
- Avoid `print()` in library modules under `src/fantasy_sim/`; reserve console output for CLI and scripts such as `scripts/validate.py`, `scripts/validate_sim.py`, and `scripts/validate_players.py`.

## Comments

**When to Comment:**
- Use comments for domain calibration constants and physics assumptions that are not self-evident, such as `PASS_TD_GATE`, `RUN_TD_GATE`, `CATCH_YARDS_BOOST`, and `RZ_CATCH_RATE_MODIFIER` in `src/fantasy_sim/engine/play_resolver.py`.
- Use comments to explain compatibility and fallback behavior, such as schema migration in `src/fantasy_sim/validation/ledger.py`, worker initialization in `src/fantasy_sim/validation/parallel.py`, and PFF props cache behavior in `src/fantasy_sim/data/vegas/props_loader.py`.
- Keep inline comments targeted to domain rules and avoid restating simple assignments. Existing comments in `src/fantasy_sim/models/player.py`, `src/fantasy_sim/engine/types.py`, and `src/fantasy_sim/data/preprocessor.py` are domain-oriented.

**JSDoc/TSDoc:**
- Not applicable. This is a Python codebase.
- Use Python docstrings on public classes, dataclasses, and public functions. Examples: `TeamRoster` in `src/fantasy_sim/models/player.py`, `WeatherProvider` in `src/fantasy_sim/data/weather/provider.py`, `DataPipeline.build()` in `src/fantasy_sim/data/pipeline.py`, and `run_season()` in `scripts/validate.py`.
- Keep docstrings short for simple helpers and expand them for public interfaces with non-obvious fallback or side-effect behavior, such as `MarketHistoryLoader` in `src/fantasy_sim/data/market_history/loader.py` and `PropsLoader` in `src/fantasy_sim/data/vegas/props_loader.py`.

## Function Design

**Size:** Use small helpers for single concerns when logic is domain-specific, and keep orchestration functions explicit when they document pipeline order.
- Small helpers: `_numeric_value()` and `_compute_distribution_ks()` in `scripts/validate.py`, `_scale_clock_runoff()` and `_apply_home_field()` in `src/fantasy_sim/engine/play_resolver.py`, `_receiver_usage_weight()` in `src/fantasy_sim/engine/player_selector.py`.
- Orchestrators: `simulate_game()` in `src/fantasy_sim/engine/game_sim.py`, `run_season()` in `scripts/validate.py`, and `GameContextBuilder.build_game()` in `src/fantasy_sim/data/game_context.py`.

**Parameters:** Prefer explicit typed dependencies over hidden globals.
- Pass dataframes directly for testability in `DataPipeline.build()` in `src/fantasy_sim/data/pipeline.py`.
- Pass `cache_dir`, `config`, loaders, crosswalks, and providers into constructors for testability in `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/data/market_history/loader.py`, and `src/fantasy_sim/data/weather/provider.py`.
- Pass all simulation randomness through `rng` parameters in `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/engine/play_resolver.py`, and `src/fantasy_sim/engine/player_selector.py`.

**Return Values:** Prefer typed dataclasses for domain results and plain dict/list rows for projection/report outputs.
- Dataclass returns: `SimulationSummary` from `src/fantasy_sim/engine/monte_carlo.py`, `GameWeather` from `src/fantasy_sim/data/weather/provider.py`, and `LedgerEntry` from `src/fantasy_sim/validation/ledger.py`.
- Dict/list projection rows: `build_player_projections()` and `build_detailed_projections()` in `src/fantasy_sim/scoring/projections.py`, `run_season()` in `scripts/validate.py`, and `format_ledger_table()` in `src/fantasy_sim/validation/ledger.py`.

## Module Design

**Exports:**
- Package `__init__.py` files are light and used only when a subsystem intentionally exposes a public surface, such as `src/fantasy_sim/data/ensemble/__init__.py`, `src/fantasy_sim/data/target_selection/__init__.py`, and `src/fantasy_sim/scoring/__init__.py`.
- Keep most imports direct from implementation modules in tests and production. Examples: `from fantasy_sim.engine.player_selector import select_receiver` in `tests/test_engine/test_player_selector.py` and `from fantasy_sim.validation.metrics import ks_distribution_summary` in `tests/test_validation/test_metrics.py`.

**Barrel Files:**
- Limited use. Prefer direct module imports unless an existing subsystem `__init__.py` already exports the object.
- Do not add broad barrel exports across unrelated subsystems; keep module boundaries aligned with `src/fantasy_sim/data/`, `src/fantasy_sim/engine/`, `src/fantasy_sim/scoring/`, and `src/fantasy_sim/validation/`.

---

*Convention analysis: 2026-04-24*
