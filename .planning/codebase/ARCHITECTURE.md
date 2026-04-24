# Architecture

**Analysis Date:** 2026-04-24

## Pattern Overview

**Overall:** Layered simulation pipeline with feature-gated intelligence engines and post-simulation projection layers.

**Key Characteristics:**
- Use `src/fantasy_sim/data/game_context.py` as the main composition root for simulation inputs. New pre-simulation signals should feed `GameContextBuilder` instead of calling the engine directly.
- Keep play simulation in `src/fantasy_sim/engine/` independent of data loading. Engine functions consume `TeamDistributions`, `TeamRoster`, and `np.random.Generator` objects.
- Keep fantasy scoring and post-simulation calibration in `src/fantasy_sim/scoring/`. Projection layers operate on projection row dictionaries after Monte Carlo results exist.
- Resolve feature flags from `config/defaults.yaml` into dataclasses via `src/fantasy_sim/data/*/config.py` loaders and `src/fantasy_sim/validation/config.py`.
- Run promotion evidence through `scripts/validate.py` and `src/fantasy_sim/validation/`, not through ad-hoc CLI runs.

## Layers

**Command Orchestration:**
- Purpose: Parse user intent, resolve config, build game contexts, run simulations, and format/export results.
- Location: `src/fantasy_sim/cli.py`, `scripts/`
- Contains: Click commands in `src/fantasy_sim/cli.py`; standalone validation, fitting, scraping, and import scripts in `scripts/validate.py`, `scripts/fit_dynamic_blend_weights.py`, `scripts/fit_residual_calibration.py`, `scripts/fit_target_selection.py`, `scripts/scrape_pff.py`, `scripts/import_market_history.py`.
- Depends on: `src/fantasy_sim/config/loader.py`, `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/engine/monte_carlo.py`, `src/fantasy_sim/scoring/`, `src/fantasy_sim/output/`, `src/fantasy_sim/validation/`.
- Used by: Console entry point `fantasy-sim` from `pyproject.toml`; direct `uv run python scripts/*.py` commands.

**Configuration:**
- Purpose: Load YAML defaults, resolve scoring inheritance, and translate nested config sections into typed config dataclasses.
- Location: `config/`, `src/fantasy_sim/config/`, `src/fantasy_sim/data/*/config.py`, `src/fantasy_sim/validation/config.py`
- Contains: Project defaults in `config/defaults.yaml`; examples in `config/season.example.yaml`, `config/custom_scoring.example.yaml`, `config/season.2025.yaml`; generic config helpers in `src/fantasy_sim/config/loader.py`; signal loaders such as `src/fantasy_sim/data/pff/config.py`, `src/fantasy_sim/data/weather/config.py`, `src/fantasy_sim/data/vegas/config.py`, `src/fantasy_sim/data/usage/config.py`; A/B override resolution in `src/fantasy_sim/validation/config.py`.
- Depends on: YAML mappings and data-layer config dataclasses in `src/fantasy_sim/data/*/models.py`.
- Used by: `src/fantasy_sim/cli.py`, `scripts/validate.py`, `src/fantasy_sim/validation/backtester.py`, fitting scripts in `scripts/`.

**Data Loading And Preprocessing:**
- Purpose: Fetch/cache raw NFL data and transform it into empirical distributions and player model ingredients.
- Location: `src/fantasy_sim/data/`
- Contains: `DataLoader` in `src/fantasy_sim/data/loader.py`, `DataPipeline` in `src/fantasy_sim/data/pipeline.py`, `Preprocessor` in `src/fantasy_sim/data/preprocessor.py`, player model assembly in `src/fantasy_sim/data/player_builder.py`, actual-score loading in `src/fantasy_sim/data/actuals.py`.
- Depends on: `nflreadpy`, `polars`, `numpy`, dataclasses from `src/fantasy_sim/models/`.
- Used by: `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/validation/backtester.py`, `scripts/validate.py`, data utility scripts in `scripts/`.

**Pre-Simulation Intelligence Engines:**
- Purpose: Mutate `TeamDistributions` and `TeamRoster` before simulation based on external or derived signals.
- Location: `src/fantasy_sim/data/pff/`, `src/fantasy_sim/data/weather/`, `src/fantasy_sim/data/vegas/`, `src/fantasy_sim/data/usage/`, `src/fantasy_sim/data/tracking/`, `src/fantasy_sim/data/availability/`, `src/fantasy_sim/data/game_script/`, `src/fantasy_sim/data/target_selection/`, `src/fantasy_sim/data/td_tendency.py`, `src/fantasy_sim/data/goal_line_concentration.py`
- Contains: Engine classes such as `MatchupEngine`, `TierEngine`, `CoverageEngine`, `KickerEngine`, `DstBaselineEngine`, `VegasEngine`, `PlayerPropsEngine`, `WeatherEngine`, `UsageEngine`, `TrackingEngine`, `AvailabilityEngine`, `GameScriptEngine`, `TargetSelectionModel`, and `TdTendencyEngine`.
- Depends on: `GameContextBuilder` orchestration, `DataLoader`, PFF loaders, weather/props/market caches, config dataclasses.
- Used by: `GameContextBuilder.__init__()` and `GameContextBuilder.build_game()` in `src/fantasy_sim/data/game_context.py`.

**Context Assembly:**
- Purpose: Build the four objects required to simulate a game: home distributions, away distributions, home roster, and away roster.
- Location: `src/fantasy_sim/data/game_context.py`
- Contains: `GameContextBuilder`, `pre_resolve_overrides()`, `apply_overrides()`, cache warming, crosswalk setup, and the ordered pre-sim adjustment chain.
- Depends on: `src/fantasy_sim/data/pipeline.py`, `src/fantasy_sim/data/player_builder.py`, signal engines, config dataclasses, `src/fantasy_sim/engine/types.py`.
- Used by: `src/fantasy_sim/cli.py`, `src/fantasy_sim/validation/parallel.py`, `src/fantasy_sim/validation/backtester.py`, `scripts/validate.py`.

**Domain Models:**
- Purpose: Define the stable data contracts shared across layers.
- Location: `src/fantasy_sim/models/`, `src/fantasy_sim/engine/types.py`
- Contains: `GameStateBucket` in `src/fantasy_sim/models/game_state.py`; distribution models in `src/fantasy_sim/models/distributions.py`; player and roster models in `src/fantasy_sim/models/player.py`; runtime simulation types in `src/fantasy_sim/engine/types.py`.
- Depends on: Standard dataclasses, `numpy` arrays for empirical distributions.
- Used by: Data preprocessing, context assembly, engine simulation, scoring, tests.

**Simulation Engine:**
- Purpose: Simulate games play-by-play from prepared distributions and rosters.
- Location: `src/fantasy_sim/engine/`
- Contains: Monte Carlo loop in `src/fantasy_sim/engine/monte_carlo.py`; game loop in `src/fantasy_sim/engine/game_sim.py`; play resolution in `src/fantasy_sim/engine/play_resolver.py`; play calling in `src/fantasy_sim/engine/play_caller.py`; player selection in `src/fantasy_sim/engine/player_selector.py`; flow/clock helpers in `src/fantasy_sim/engine/game_flow.py` and `src/fantasy_sim/engine/clock.py`; runtime game-script adjustments in `src/fantasy_sim/engine/game_script.py`.
- Depends on: `TeamDistributions`, `TeamRoster`, `GameState`, `PlayResult`, explicit `np.random.Generator`.
- Used by: CLI commands, validation harnesses, smoke/statistical scripts.

**Scoring And Projection:**
- Purpose: Convert simulated box scores into fantasy projections, then apply post-simulation layers.
- Location: `src/fantasy_sim/scoring/`
- Contains: Scoring primitives in `src/fantasy_sim/scoring/engine.py`; projection aggregation in `src/fantasy_sim/scoring/projections.py`; layer ordering and protocols in `src/fantasy_sim/scoring/projection_layers.py`; post-sim adjusters in `src/fantasy_sim/scoring/role_trend.py`, `src/fantasy_sim/scoring/market_history.py`, `src/fantasy_sim/scoring/ensemble.py`, `src/fantasy_sim/scoring/dynamic_blend.py`, `src/fantasy_sim/scoring/residual_calibration.py`.
- Depends on: `GameResult` and box-score dataclasses, scoring config dictionaries, post-sim data loaders.
- Used by: `src/fantasy_sim/cli.py`, `scripts/validate.py`, `src/fantasy_sim/validation/backtester.py`, fitting scripts.

**Output:**
- Purpose: Render projections for humans or write projection files.
- Location: `src/fantasy_sim/output/`
- Contains: Rich table formatters in `src/fantasy_sim/output/tables.py`; CSV/JSON exporters in `src/fantasy_sim/output/export.py`.
- Depends on: Projection row dictionaries.
- Used by: `src/fantasy_sim/cli.py`.

**Validation And Evidence:**
- Purpose: Run season-level and weekly A/B validation, cache baselines, compute metrics, and persist ledger evidence.
- Location: `src/fantasy_sim/validation/`, `scripts/validate.py`
- Contains: `Backtester` in `src/fantasy_sim/validation/backtester.py`; parallel build/sim helpers in `src/fantasy_sim/validation/parallel.py`; metrics in `src/fantasy_sim/validation/metrics.py`; weekly diagnostics in `src/fantasy_sim/validation/weekly.py`; signal coverage in `src/fantasy_sim/validation/coverage.py`; cache helpers in `src/fantasy_sim/validation/cache.py`; ledger models in `src/fantasy_sim/validation/ledger.py`; report formatting in `src/fantasy_sim/validation/report.py`.
- Depends on: Data loading, context building, Monte Carlo engine, scoring/projection layers, actual-score loading.
- Used by: `scripts/validate.py`, `src/fantasy_sim/cli.py backtest`, fitting scripts, tests in `tests/test_validation/`.

**Overrides:**
- Purpose: Apply user-specified player/team mutations while preserving share normalization semantics.
- Location: `src/fantasy_sim/overrides/`
- Contains: Config and CLI parsing in `src/fantasy_sim/overrides/parser.py`; share mutation in `src/fantasy_sim/overrides/engine.py`; fuzzy/exact player resolution in `src/fantasy_sim/overrides/resolver.py`.
- Depends on: `TeamRoster`, `TeamDistributions`.
- Used by: `src/fantasy_sim/cli.py` and helper functions in `src/fantasy_sim/data/game_context.py`.

## Data Flow

**Projection CLI Flow:**

1. `fantasy-sim` dispatches through `main()` in `src/fantasy_sim/cli.py`.
2. `load_defaults()` and `_resolve_config_chain()` in `src/fantasy_sim/cli.py` resolve `config/defaults.yaml`, optional season config, optional custom scoring, and CLI flags.
3. `_make_builder()` in `src/fantasy_sim/cli.py` builds a `GameContextBuilder` with config dataclasses from `src/fantasy_sim/data/*/config.py`.
4. `GameContextBuilder.build_game()` in `src/fantasy_sim/data/game_context.py` returns `TeamDistributions` and `TeamRoster` for both teams.
5. `run_simulations()` in `src/fantasy_sim/engine/monte_carlo.py` repeatedly calls `simulate_game()` in `src/fantasy_sim/engine/game_sim.py`.
6. `build_player_projections()`, `build_dst_projections()`, and `build_kicker_projections()` in `src/fantasy_sim/scoring/projections.py` aggregate simulated games.
7. `apply_projection_layers()` in `src/fantasy_sim/scoring/projection_layers.py` applies post-sim adjusters in the approved order.
8. `src/fantasy_sim/output/tables.py` or `src/fantasy_sim/output/export.py` renders tables, CSV, or JSON.

**Context Build Flow:**

1. `DataLoader` in `src/fantasy_sim/data/loader.py` loads and parquet-caches PBP, rosters, schedules, player stats, snap counts, participation, FTN charting, NGS, PFF facets, injuries, and draft picks.
2. `DataPipeline.build()` in `src/fantasy_sim/data/pipeline.py` feeds raw PBP into `Preprocessor` methods in `src/fantasy_sim/data/preprocessor.py`.
3. `Preprocessor` builds `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel`, and `PenaltyRates`.
4. `_aggregate_pbp_stats()` and `_assemble_models()` in `src/fantasy_sim/data/player_builder.py` merge historical PBP stats with current rosters into `PlayerModel` objects.
5. `build_team_roster()` in `src/fantasy_sim/data/player_builder.py` deep-copies current-team players and normalizes target/carry shares.
6. `GameContextBuilder.build_game()` applies configured pre-sim engines before returning the final context.

**Pre-Simulation Adjustment Order:**

Use `GameContextBuilder.build_game()` in `src/fantasy_sim/data/game_context.py` as the source of truth. The ordered chain is:

1. Base PBP distributions and current rosters from `build_team_distributions()` and `build_team_roster()`.
2. Vegas environment adjustments via `_apply_vegas()` and `src/fantasy_sim/data/vegas/engine.py`.
3. Availability mutations via `src/fantasy_sim/data/availability/engine.py`, then share normalization.
4. Usage mutations via `src/fantasy_sim/data/usage/engine.py`, then share normalization.
5. Tracking mutations via `src/fantasy_sim/data/tracking/engine.py`, then share normalization.
6. Player props mutations via `src/fantasy_sim/data/vegas/props_engine.py`, then share normalization.
7. PFF matchup adjustments via `src/fantasy_sim/data/pff/matchup.py`.
8. PFF tier or talent layer via `src/fantasy_sim/data/pff/tier_engine.py` or `src/fantasy_sim/data/pff/talent.py`, then share normalization.
9. RB scheme fit via `src/fantasy_sim/data/pff/rb_scheme_fit.py`.
10. QB split via `src/fantasy_sim/data/pff/qb_split.py`.
11. Depth role via `src/fantasy_sim/data/pff/depth_role.py`, then share normalization.
12. Coverage matchup via `src/fantasy_sim/data/pff/coverage.py`.
13. DST baseline via `src/fantasy_sim/data/pff/dst_baseline.py`.
14. Kicker replacement via `src/fantasy_sim/data/pff/kicker.py`.
15. TD tendency via `src/fantasy_sim/data/td_tendency.py`.
16. Weather via `src/fantasy_sim/data/weather/engine.py`.
17. Game-script profiles via `src/fantasy_sim/data/game_script/engine.py`.
18. Target-selection runtime context via `src/fantasy_sim/data/target_selection/runtime.py`.

**Simulation Flow:**

1. `run_simulations()` in `src/fantasy_sim/engine/monte_carlo.py` creates one explicit `np.random.Generator` and loops for `n_sims`.
2. `simulate_game()` in `src/fantasy_sim/engine/game_sim.py` initializes `GameState`, kickoff state, `TeamBoxScore`, and per-player `PlayerBoxScore` storage.
3. Each play selects a play type via `select_play_type()` in `src/fantasy_sim/engine/play_caller.py`.
4. `resolve_play()` in `src/fantasy_sim/engine/play_resolver.py` handles scramble, sack, interception, QB fumble, receiver/rusher selection, catch/yards, TD gate, fumble, safety, and penalties.
5. `src/fantasy_sim/engine/game_flow.py` mutates field position, possession, scores, kickoffs, punts, field goals, PATs, turnovers, touchdowns, and safeties.
6. `src/fantasy_sim/engine/clock.py` applies runoff, two-minute warning, quarter transitions, halftime possession, and overtime termination.
7. `simulate_game()` returns a `GameResult` from `src/fantasy_sim/engine/types.py`; `SimulationSummary` stores all games.

**Post-Simulation Projection Flow:**

1. `build_player_projections()` in `src/fantasy_sim/scoring/projections.py` averages player box scores over all sims.
2. `apply_projection_layers()` in `src/fantasy_sim/scoring/projection_layers.py` applies `RoleTrendProjectionAdjuster` first.
3. If `DynamicBlendProjectionBlender` exists, it replaces the fixed `market_history` plus `ff_opportunity` sequence.
4. If dynamic blend is disabled, `MarketHistoryProjectionAdjuster` runs before `FfOpportunityProjectionEnsembler`.
5. `ResidualCalibrationProjectionAdjuster` runs last and adjusts final `fpts`.
6. Projection rows are sorted and ranked after each layer that changes fantasy points.

**Validation Flow:**

1. `scripts/validate.py` builds an argparse CLI in `build_cli()`.
2. `main()` loads `config/defaults.yaml`, applies `--set` dot-notation overrides through `src/fantasy_sim/validation/config.py`, resolves Arm A and Arm B configs, and checks signal coverage with `src/fantasy_sim/validation/coverage.py`.
3. `run_season()` builds game arguments from `DataLoader.load_schedules()` and actuals from `src/fantasy_sim/data/actuals.py`.
4. `build_games_parallel()` in `src/fantasy_sim/validation/parallel.py` builds contexts either as dual-arm pairs for bare baselines or separate single-arm builds for defaults baselines.
5. `simulate_games_parallel()` in `src/fantasy_sim/validation/parallel.py` runs each `GameSpec` and returns projection rows.
6. `run_season()` applies post-sim layers, computes rank correlation, weekly MAE, season MAE, boom/bust calibration, weekly fantasy-point KS, stat KS, and weekly directional diagnostics.
7. `main()` saves bare-baseline cache via `src/fantasy_sim/validation/cache.py` and appends labeled results to `results/ab_ledger.json` via `src/fantasy_sim/validation/ledger.py`.

**State Management:**
- Use immutable `GameStateBucket` objects from `src/fantasy_sim/models/game_state.py` as distribution keys.
- Use mutable `GameState`, `TeamBoxScore`, and `PlayerBoxScore` objects from `src/fantasy_sim/engine/types.py` only inside a single simulation.
- Pass `np.random.Generator` explicitly through `run_simulations()`, `simulate_game()`, and play-resolution helpers.
- Use `DataLoader._memory_cache` and parquet files under the configured cache directory for raw data.
- Use `GameContextBuilder` caches for pipeline output, PBP stats, and player models; call `GameContextBuilder.warm()` before threaded validation builds.
- Keep validation worker builders in the module-level `_worker_builders` registry inside `src/fantasy_sim/validation/parallel.py`.

## Key Abstractions

**DataLoader:**
- Purpose: Single access layer for nflverse and local parquet cache reads.
- Examples: `src/fantasy_sim/data/loader.py`
- Pattern: Class wrapper with `load_*()` methods and `_cache_key()`/`_load_cached()` helpers. Add new nflverse reads here when multiple layers need the data.

**DataPipeline And Preprocessor:**
- Purpose: Turn raw PBP into reusable empirical distributions.
- Examples: `src/fantasy_sim/data/pipeline.py`, `src/fantasy_sim/data/preprocessor.py`
- Pattern: `DataPipeline.build()` orchestrates `Preprocessor.compute_*()` methods. Keep distribution derivation here instead of in engine code.

**GameContextBuilder:**
- Purpose: Compose all pre-simulation data and feature layers for one matchup.
- Examples: `src/fantasy_sim/data/game_context.py`
- Pattern: Constructor wires enabled engines; `build_game()` applies them in order. Add new pre-sim layers by adding config, initializing the engine, and inserting one ordered mutation block.

**TeamDistributions:**
- Purpose: Container for all team-level distributions and runtime contexts needed by the engine.
- Examples: `src/fantasy_sim/engine/types.py`, `src/fantasy_sim/models/distributions.py`
- Pattern: Dataclass passed into simulation. Add team-level runtime knobs here only when the engine must consume them.

**TeamRoster And PlayerModel:**
- Purpose: Current-team player pool, usage shares, and outcome distributions.
- Examples: `src/fantasy_sim/models/player.py`, `src/fantasy_sim/data/player_builder.py`
- Pattern: Build from historical stats plus current rosters; deep-copy and normalize shares before per-game mutation.

**GameStateBucket:**
- Purpose: Discrete lookup key for play-calling and outcome distributions.
- Examples: `src/fantasy_sim/models/game_state.py`, `src/fantasy_sim/data/preprocessor.py`, `src/fantasy_sim/engine/play_resolver.py`
- Pattern: Frozen dataclass with helper bucketing functions. Use `bucket_play()` for all state-to-bucket mapping.

**GameState, PlayResult, GameResult:**
- Purpose: Runtime state, single-play outcome, and finished-game contract.
- Examples: `src/fantasy_sim/engine/types.py`, `src/fantasy_sim/engine/game_sim.py`
- Pattern: Mutable state inside `simulate_game()`; return immutable result snapshots as dataclasses.

**Signal Engine Classes:**
- Purpose: Encapsulate one feature family and expose `compute()` or `apply()` behavior.
- Examples: `src/fantasy_sim/data/pff/matchup.py`, `src/fantasy_sim/data/pff/coverage.py`, `src/fantasy_sim/data/weather/engine.py`, `src/fantasy_sim/data/vegas/engine.py`, `src/fantasy_sim/data/usage/engine.py`, `src/fantasy_sim/data/tracking/engine.py`
- Pattern: `__init__(config, loader)` or equivalent, then `compute()` returns context/factors or `apply()` mutates a roster/distribution.

**Projection Layer Protocols:**
- Purpose: Keep post-simulation layer ordering independent of concrete classes.
- Examples: `src/fantasy_sim/scoring/projection_layers.py`
- Pattern: Implement `adjust_week()` or `blend_week()` and pass instances to `apply_projection_layers()`.

**Validation GameSpec:**
- Purpose: Portable, pre-built game context for validation simulation workers.
- Examples: `src/fantasy_sim/validation/parallel.py`
- Pattern: Build contexts first, simulate second, aggregate metrics third. Preserve deterministic seeds by game id.

**LedgerEntry And SeasonMetrics:**
- Purpose: Persist A/B validation evidence in a stable schema.
- Examples: `src/fantasy_sim/validation/ledger.py`, `results/ab_ledger.json`
- Pattern: Add schema fields deliberately and keep `load_ledger()` backward-compatible when changing ledger data.

## Entry Points

**CLI:**
- Location: `src/fantasy_sim/cli.py`
- Triggers: `fantasy-sim` console script declared in `pyproject.toml`.
- Responsibilities: `demo`, `week`, `season`, `game`, `player`, and `backtest` commands; config resolution; simulation orchestration; output formatting/export.

**Unified A/B Validation:**
- Location: `scripts/validate.py`
- Triggers: `uv run python scripts/validate.py ...`
- Responsibilities: Compare bare/defaults baseline against defaults plus overrides; run seasons in parallel; compute promotion metrics; update `results/ab_ledger.json`.

**Backtester API:**
- Location: `src/fantasy_sim/validation/backtester.py`
- Triggers: `fantasy-sim backtest`; direct test/script imports.
- Responsibilities: Build contexts, simulate historical seasons, compare projections against actuals, return `BacktestResult`.

**Monte Carlo Library Call:**
- Location: `src/fantasy_sim/engine/monte_carlo.py`
- Triggers: CLI, validation harnesses, tests, legacy validation scripts.
- Responsibilities: Repeat `simulate_game()` and return `SimulationSummary`.

**Data Utility Scripts:**
- Location: `scripts/`
- Triggers: Direct `uv run python scripts/<name>.py`.
- Responsibilities: PFF scraping (`scripts/scrape_pff.py`, `scripts/scrape_pff_props.py`), market history import/fetch (`scripts/import_market_history.py`, `scripts/fetch_market_history_events.py`, `scripts/fetch_market_history_props.py`, `scripts/build_market_history_player_markets.py`), fitting artifacts (`scripts/fit_dynamic_blend_weights.py`, `scripts/fit_residual_calibration.py`, `scripts/fit_target_selection.py`), targeted validation (`scripts/validate_data.py`, `scripts/validate_sim.py`, `scripts/validate_players.py`, `scripts/validate_passing.py`, `scripts/validate_tier_spotcheck.py`).

## Error Handling

**Strategy:** Prefer explicit config errors, CLI exits for user-facing problems, and structured validation build results for batch failures.

**Patterns:**
- Raise `ConfigError` from `src/fantasy_sim/config/loader.py` for missing config files, invalid YAML mappings, unknown scoring formats, and circular scoring inheritance.
- Use `click.BadParameter`, `click.echo(..., err=True)`, and `SystemExit(1)` in `src/fantasy_sim/cli.py` for invalid command inputs and empty schedules.
- Use `ValueError` for invalid runtime invariants such as `n_sims <= 0` in `src/fantasy_sim/engine/monte_carlo.py` and missing QBs in `src/fantasy_sim/models/player.py`.
- In validation builds, return dictionaries with `status`, `error`, and `error_type` from `src/fantasy_sim/validation/parallel.py` instead of crashing the full batch.
- In `Backtester.run()` in `src/fantasy_sim/validation/backtester.py`, assert that game build failure rate stays below the validation threshold.
- In parallel simulation, log failed games and continue in `simulate_games_parallel()` in `src/fantasy_sim/validation/parallel.py`.
- Use exact pre-resolution for overrides in `src/fantasy_sim/data/game_context.py`; skip unresolved player overrides with a CLI warning.

## Cross-Cutting Concerns

**Logging:** Use Python `logging` in core orchestration files such as `src/fantasy_sim/data/game_context.py` and `src/fantasy_sim/validation/parallel.py`. Use `click.echo()` in `src/fantasy_sim/cli.py` and `print()` in standalone scripts such as `scripts/validate.py`.

**Validation:** Use `scripts/validate.py` for A/B evidence, `src/fantasy_sim/validation/backtester.py` for hold-out backtests, and tests under `tests/test_validation/` for harness behavior. Keep bare-baseline caches in `results/cache/` and ledger evidence in `results/ab_ledger.json`.

**Authentication:** Runtime code has no app login layer. External data auth belongs in provider-specific local caches/env files outside the repo, such as PFF and props credentials; do not read or commit those files.

**Caching:** Raw nflverse cache lives behind `DataLoader` in `src/fantasy_sim/data/loader.py`. Validation context build caching lives in `GameContextBuilder` in `src/fantasy_sim/data/game_context.py`. Baseline validation result caching lives in `src/fantasy_sim/validation/cache.py`.

**Determinism:** Use deterministic CRC32 game-id seeds in CLI/validation paths (`src/fantasy_sim/cli.py`, `scripts/validate.py`, `src/fantasy_sim/validation/backtester.py`) and pass `np.random.Generator` explicitly through engine functions.

---

*Architecture analysis: 2026-04-24*
