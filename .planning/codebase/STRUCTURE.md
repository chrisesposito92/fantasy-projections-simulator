# Codebase Structure

**Analysis Date:** 2026-04-26

## Directory Layout

```
fantasy-projections-simulator/
├── src/fantasy_sim/              # Main application code
│   ├── cli.py                    # Click CLI entry point
│   ├── config/                   # Configuration loading
│   ├── data/                     # Data layer (load, preprocess, build distributions)
│   ├── engine/                   # Play-by-play simulation engine
│   ├── models/                   # Dataclass definitions
│   ├── output/                   # Formatting and export
│   ├── overrides/                # Player/team override system
│   ├── scoring/                  # Projection aggregation and post-sim adjusters
│   └── validation/               # A/B backtesting and metrics
├── tests/                        # Test suite (mirrors src structure)
├── scripts/                      # Data processing, fitting, validation harnesses
├── config/                       # YAML configuration files
├── docs/                         # Documentation
├── results/                      # Output directory for validation runs
├── .planning/                    # GSD planning artifacts (phases, plans, research)
├── .agents/                      # Agent skills (if present)
├── pyproject.toml                # Python package configuration
├── uv.lock                       # Locked dependency versions
└── AGENTS.md                     # Project architecture + commands reference
```

## Directory Purposes

**src/fantasy_sim/**
- Purpose: Main application package
- Contains: All source code (data, models, engine, scoring, output, validation, CLI)
- Key files: `cli.py` (entry point), `__init__.py` (version, package marker)

**src/fantasy_sim/config/**
- Purpose: Configuration loading and resolution
- Contains: Config loader (YAML parsing, flag merging)
- Key files: `loader.py` (load_defaults, resolve_scoring, load_season_config)

**src/fantasy_sim/data/**
- Purpose: Data loading, preprocessing, and player/roster building
- Contains: DataLoader (nflreadpy bridge), DataPipeline (distribution building), Preprocessor (PBP→distributions), player_builder, rookie_builder
- Key files:
  - `loader.py`: DataLoader (caches parquet at ~/.fantasy-sim/cache/)
  - `pipeline.py`: DataPipeline.build() orchestrates all distribution computation
  - `preprocessor.py`: Compute play calling, play outcomes, turnover rates, kicking, drive start, penalties bucketed by game state
  - `player_builder.py`: build_team_roster(), blend_with_archetype() for rookies
  - `game_context.py`: GameContextBuilder—main facade that applies all sub-engine adjustments in order
  - Subdirectories (sub-engines):
    - `pff/`: TierEngine, MatchupEngine, TeamContextEngine, RbSchemeFitEngine, QbSplitEngine, CoverageEngine, KickerEngine, DstBaselineEngine, TalentStabilizer, tier_engine.py (58KB, most complex)
    - `vegas/`: VegasEngine (ITT pace + spread), PlayerPropsEngine, props_loader
    - `weather/`: WeatherEngine (Open-Meteo), stadiums registry, provider
    - `availability/`: AvailabilityEngine (snap availability tracking)
    - `ensemble/`: DynamicBlendProjectionBlender, normalizer, artifacts (pre-fit weights)
    - `role_trend/`: RoleTrendEngine (historical role changes)
    - `market_history/`: MarketHistoryConfig, player_markets, events_inventory
    - `usage/`: UsageEngine (override carry/target shares)
    - `game_script/`: GameScriptEngine (win probability effects)
    - `tracking/`: TrackingEngine (route concepts)
    - `play_call_model/`: PlayCallModelConfig (fitted 4th down, goal line decisions)
    - `qb_rushing/`: QbDesignedRunModel, QbScrambleModel (fitted scramble artifacts)
    - `target_selection/`: TargetSelectionModel
    - `td_tendency/`: TdTendencyEngine (per-player TD multipliers)

**src/fantasy_sim/models/**
- Purpose: Frozen dataclasses for type safety and dict-key use
- Contains:
  - `distributions.py`: PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel
  - `player.py`: PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster, MIN_QB_CARRY_SHARE constant
  - `game_state.py`: GameStateBucket (frozen, used as dict key)

**src/fantasy_sim/engine/**
- Purpose: Play-by-play game simulation
- Contains:
  - `monte_carlo.py`: run_simulations() entry point, SimulationSummary aggregator
  - `game_sim.py`: simulate_game() main loop (400 play max, coin toss, drive-by-drive resolution)
  - `play_caller.py`: select_play_type(), fourth_down_decision()
  - `play_resolver.py`: resolve_play() (catch rate, yards, TD gates, sack/INT/fumble logic, RZ_CATCH_RATE_MODIFIER=0.92)
  - `player_selector.py`: select_receiver(), select_rusher() from roster using share weights
  - `game_flow.py`: apply_yards(), change_possession(), score_points(), handle_turnover(), perform_kickoff(), perform_punt(), attempt_field_goal(), attempt_pat()
  - `clock.py`: apply_clock(), check_quarter_end(), check_two_minute_warning()
  - `game_script.py`: effective_pace_factor(), resolve_game_script() (win prob effects)
  - `types.py`: GameState, GameResult, PlayerBoxScore, TeamBoxScore, TeamDistributions, PlayResult

**src/fantasy_sim/scoring/**
- Purpose: Convert simulation results to fantasy point projections
- Contains:
  - `projections.py`: build_player_projections(), build_detailed_projections() (aggregate N sims)
  - `engine.py`: score_player(), score_dst(), score_kicker() (position-specific fantasy point rules)
  - `projection_layers.py`: apply_projection_layers() (post-sim order)
  - `dynamic_blend.py`: DynamicBlendProjectionBlender (ensemble model blending with artifacts)
  - `residual_calibration.py`: ResidualCalibrationProjectionAdjuster (season/bucket-specific calibration)
  - `role_trend.py`: RoleTrendProjectionAdjuster
  - `market_history.py`: MarketHistoryProjectionAdjuster (opening/closing line adjustment)
  - `ensemble.py`: FfOpportunityProjectionEnsembler (fallback when dynamic_blend off)

**src/fantasy_sim/output/**
- Purpose: Terminal and file output formatting
- Contains:
  - `tables.py`: format_qb_table(), format_rb_table(), format_wr_table(), format_te_table(), format_kicker_table(), format_dst_table() (Rich Table formatting)
  - `export.py`: export_csv(), export_json()

**src/fantasy_sim/overrides/**
- Purpose: Player/team override resolution and application
- Contains:
  - `parser.py`: parse_override_config() (YAML file), parse_cli_override() (--override flag strings)
  - `resolver.py`: PlayerResolver (fuzzy name matching, Levenshtein ≥70)
  - `engine.py`: apply_player_override(), apply_team_override() (share redistribution)

**src/fantasy_sim/validation/**
- Purpose: A/B backtesting against historical actuals
- Contains:
  - `backtester.py`: Backtester class (hold-out on one season, compute rank_corr/MAE/boom-bust)
  - `parallel.py`: simulate_games_parallel(), build_games_parallel() (multi-threaded)
  - `coverage.py`: KS distribution metrics, compression/deflation detection (57KB)
  - `ledger.py`: Persistent A/B results cache (JSON, keyed by config hash)
  - `metrics.py`: spearman_rank_correlation(), boom_bust_calibration()
  - `weekly.py`: Weekly projection breakdown
  - `config.py`: BacktestConfig (seasons, n_sims, scoring format)
  - `cache.py`: Bare baseline caching for control condition

**tests/**
- Purpose: Unit and integration tests (1200+ tests)
- Structure mirrors src/: `test_data/`, `test_models/`, `test_engine/`, `test_scoring/`, `test_validation/`, `test_overrides/`, `test_output/`, `test_integration/`, `test_scripts/`, `test_config/`
- Key files: `conftest.py` (fixtures: sample_pbp, sample_rosters, sample_schedules, sample_kickoffs, sample_field_goals, expanded_pbp)
- Markers: `@pytest.mark.integration`, `@pytest.mark.statistical`

**scripts/**
- Purpose: Data processing, model fitting, and validation harnesses
- 23 Python scripts:
  - **Validation**: `validate.py` (main A/B harness), `validate_pff_signal.py`, `validate_weekly_signal.py`, `validate_sim.py`, `validate_passing.py`, `validate_players.py`, `validate_tier_spotcheck.py`, `validate_data.py`
  - **Fitting**: `fit_dynamic_blend_weights.py`, `fit_residual_calibration.py`, `fit_talent_coefficients.py`, `fit_qb_designed_run_model.py`, `fit_qb_scramble_model.py`, `fit_play_call_model.py`, `fit_target_selection.py`, `sweep_talent_params.py`
  - **Data**: `scrape_pff.py`, `scrape_pff_props.py`, `fetch_market_history_*.py`, `backfill_tracking_data.py`, `build_market_history_player_markets.py`, `import_market_history.py`

**config/**
- Purpose: YAML configuration files (scoring rules, feature flags, thresholds)
- Key files:
  - `defaults.yaml` (10.8 KB): Master config with all feature flags (pff.*, vegas.*, weather.*, ensemble.*, etc.), scoring presets (ppr/half_ppr/standard), constants (PASS_TD_GATE, RUN_TD_GATE, etc.)
  - `season.2025.yaml`: Season-specific overrides (if 2025 has custom rules)
  - `season.example.yaml`: Template for new season configs
  - `custom_scoring.example.yaml`: Template for custom scoring formats

**docs/**
- Purpose: User-facing documentation
- Includes: PFF setup guide (pff-setup.md), API reference, examples

**.planning/**
- Purpose: GSD workflow artifacts (phases, plans, research, decisions)
- Structure: Roadmap, phase specifications, phase plans, decision records

**results/**
- Purpose: Output directory for validation runs (user-run backtests, A/B ledgers)
- Generated at runtime: `results/dynamic_blend/`, `results/residual_calibration/`, etc.

## Key File Locations

**Entry Points:**
- `src/fantasy_sim/cli.py`: Main CLI entry point (Click app with demo, week, season, game, player, backtest commands)
- `src/fantasy_sim/data/game_context.py`: GameContextBuilder (main facade for data preparation)
- `src/fantasy_sim/engine/monte_carlo.py`: run_simulations() entry for game engine

**Configuration:**
- `config/defaults.yaml`: Master feature flags and constants
- `config/season.2025.yaml`: Season-specific overrides
- `src/fantasy_sim/config/loader.py`: Config loading logic

**Core Logic:**
- `src/fantasy_sim/data/game_context.py`: GameContextBuilder.build_game() — applies all adjustments in order
- `src/fantasy_sim/data/pipeline.py`: DataPipeline.build() — orchestrates distribution computation
- `src/fantasy_sim/engine/game_sim.py`: simulate_game() — play-by-play loop
- `src/fantasy_sim/engine/play_resolver.py`: resolve_play() — single-play outcome resolution
- `src/fantasy_sim/scoring/projections.py`: build_player_projections() — aggregate N sims to final projections

**Testing:**
- `tests/conftest.py`: Pytest fixtures (sample_pbp, sample_rosters, expanded_pbp)
- `tests/test_engine/test_game_sim.py`: Game simulation tests
- `tests/test_data/test_player_builder.py`: Roster/player model tests

**Validation:**
- `src/fantasy_sim/validation/backtester.py`: Backtester class
- `src/fantasy_sim/validation/ledger.py`: Persistent A/B cache
- `scripts/validate.py`: Main validation harness (47 KB)

**Artifacts:**
- `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/`: Pre-fit ensemble weights for 2023-2024
- `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/`: Pre-fit calibration factors for 2023-2024

## Naming Conventions

**Files:**
- Modules: `snake_case.py` (e.g., `play_resolver.py`, `player_builder.py`)
- Config YAML: `section.YEAR.yaml` or `section.example.yaml` (e.g., `season.2025.yaml`)
- Scripts: `action_subject.py` (e.g., `fit_dynamic_blend_weights.py`, `validate_pff_signal.py`)
- Test files: `test_*.py` (e.g., `test_game_sim.py`)

**Directories:**
- Sub-packages: `snake_case/` (e.g., `play_call_model/`, `qb_rushing/`)
- Artifacts: `artifact_name/` within `data/*/artifacts/` (e.g., `dynamic_blend/`, `residual_calibration/`)
- Results: feature-based (e.g., `results/dynamic_blend/decision_s200/`)

**Classes:**
- Dataclasses: `PascalCase` (e.g., `PlayerModel`, `GameStateBucket`, `TeamDistributions`)
- Engines: `*Engine` suffix (e.g., `TierEngine`, `MatchupEngine`, `GameScriptEngine`)
- Config models: `*Config` suffix (e.g., `PffConfig`, `VegasConfig`, `EnsembleConfig`)
- Builders: `*Builder` suffix (e.g., `GameContextBuilder`)

**Functions:**
- camelCase starting with verb (e.g., `build_team_roster()`, `resolve_play()`, `apply_overrides()`)
- Helpers prefixed with `_` (private module-level functions)

**Constants:**
- SCREAMING_SNAKE_CASE (e.g., `MIN_BUCKET_PLAYS`, `PASS_TD_GATE`, `RZ_CATCH_RATE_MODIFIER`)
- Defined in config/defaults.yaml or at module top

## Where to Add New Code

**New Feature (simulation logic):**
- Core logic: `src/fantasy_sim/engine/` (if play-by-play) or `src/fantasy_sim/data/` (if data-driven)
- Tests: `tests/test_engine/` or `tests/test_data/` (matching structure)
- Config: Add flags to `config/defaults.yaml` under appropriate section

**New Adjustment Engine:**
- Implementation: `src/fantasy_sim/data/{feature_name}/`
  - Minimal structure: `config.py` (ConfigModel), `engine.py` (Engine class), `models.py` (data models)
  - Load in GameContextBuilder if enabled via config flag
- Integration: Update GameContextBuilder.build_game() adjustment order in `src/fantasy_sim/data/game_context.py`
- Tests: `tests/test_data/test_{feature_name}/`
- Config: Add to defaults.yaml under feature section with enabled/disabled flag

**New Post-Sim Layer (scoring adjustment):**
- Implementation: `src/fantasy_sim/scoring/{feature_name}.py` (class with __call__ or compute method)
- Integration: Update projection_layers.py apply_projection_layers() order
- Tests: `tests/test_scoring/test_{feature_name}.py`
- Config: Add to defaults.yaml under ensemble or projection section

**New Validation Metric:**
- Implementation: `src/fantasy_sim/validation/metrics.py` (new function)
- Usage: Referenced in backtester.py or validation scripts
- Tests: `tests/test_validation/test_metrics.py`

**New CLI Command:**
- Implementation: Add @cli.command() in `src/fantasy_sim/cli.py`
- Usage: Follows Click conventions with @click.option() decorators

**Utilities:**
- Shared helpers: `src/fantasy_sim/{layer}/` (in appropriate layer)
- Math/stat helpers: Add to `src/fantasy_sim/validation/metrics.py` if generic

## Special Directories

**src/fantasy_sim/data/ensemble/artifacts/:**
- Purpose: Pre-fit model weights and calibration factors
- Contents: `dynamic_blend/decision_s200/` (2023-2024 blend weights), `residual_calibration/decision_s200/` (2023-2024 calibration)
- Generated: Yes (via fit_dynamic_blend_weights.py, fit_residual_calibration.py)
- Committed: Yes (production-critical)
- Format: JSON files (weights_YEAR.json, calibration_YEAR.json)

**~/.fantasy-sim/ (cache directories):**
- Purpose: User-level caches (not committed)
- Locations:
  - `~/.fantasy-sim/cache/`: nflreadpy parquet (keyed by season)
  - `~/.fantasy-sim/pff/processed/`: PFF processed parquet (keyed by season)
  - `~/.fantasy-sim/weather/`: Weather JSON cache (6-hour forecast TTL)
  - `~/.fantasy-sim/props/`: Player props parquet
  - `~/.fantasy-sim/pff/.env`: PFF cookie auth (never read in code)
  - `~/.fantasy-sim/props/.env`: Odds API key
- Generated: Yes (at runtime)
- Committed: No

**tests/test_data/:**
- Purpose: Unit and fixture tests for data layer
- Subdirectories mirror `src/fantasy_sim/data/`: `test_pff/`, `test_vegas/`, `test_weather/`, `test_availability/`, etc.
- Fixtures: sample_pbp (20 plays), sample_rosters, expanded_pbp (60 plays per team)

**results/:**
- Purpose: Output from validation runs
- Structure: `results/{phase}/{config_name}/` (e.g., `results/dynamic_blend/decision_s200/`)
- Contents: Backtest reports, ledger JSON, metric CSVs
- Generated: Yes (by validation scripts)
- Committed: No (user-generated)

## Three-Layer Cache Structure

**Layer 1: Pipeline Output** (`GameContextBuilder._pipeline_cache`)
- Key: tuple of training_seasons (e.g., (2022, 2023, 2024))
- Value: dict with keys: play_calling, play_outcomes, turnover_rates, kicking, drive_start, penalty_rates
- Invalidates when: training_seasons change
- Builds: DataPipeline.build() → Preprocessor methods
- Thread-safe: Protected by threading.Lock (_pipeline_lock)

**Layer 2: PBP Stats Cache** (`GameContextBuilder._pbp_stats_cache`)
- Key: tuple of (training_seasons, ...) + config flags that affect stats
- Value: dict with per-team, per-bucket statistics (yards distributions, completion rates, etc.)
- Invalidates when: training_seasons or config flags change
- Builds: Derived from pipeline output via Preprocessor
- Reused by: Player model building (build_team_roster), PFF engines

**Layer 3: Player Models Cache** (`GameContextBuilder._player_models_cache`)
- Key: tuple of (training_seasons, target_season, week, props_enabled)
- Value: dict[player_id, PlayerModel] for all relevant players
- Invalidates when: Training seasons, target season, week, or props configuration change
- Builds: build_team_roster() + all adjustment engines applied
- Reused by: Simulations for same week (multiple sims reuse same roster models)

**Cache Invalidation:**
- Caches are instance-level (per GameContextBuilder instance)
- Each game/week request checks if key matches cached key before recomputing
- Validation harness creates new GameContextBuilder for each test condition to ensure isolation

---

*Structure analysis: 2026-04-26*
