# Codebase Structure

**Analysis Date:** 2026-04-24

## Directory Layout

```
fantasy-projections-simulator/
├── AGENTS.md                         # Project instructions and domain constraints
├── README.md                         # Project overview and user-facing command docs
├── pyproject.toml                    # Package metadata, dependencies, CLI entry point, pytest config
├── uv.lock                           # Locked Python dependency graph
├── config/                           # YAML defaults and example runtime configs
├── docs/                             # Architecture, setup, validation, and hypothesis docs
├── results/                          # Validation ledgers, caches, and fitted artifact outputs
├── scripts/                          # Standalone validation, fitting, scraping, and import CLIs
├── src/fantasy_sim/                  # Installable application package
│   ├── cli.py                        # Click CLI and top-level projection orchestration
│   ├── config/                       # Generic YAML and scoring config loading
│   ├── data/                         # Data loading, preprocessing, context building, signal engines
│   ├── engine/                       # Play-by-play simulation engine
│   ├── models/                       # Shared distribution, player, and game-state dataclasses
│   ├── output/                       # Rich table and CSV/JSON output formatting
│   ├── overrides/                    # CLI/config override parsing, resolution, and application
│   ├── scoring/                      # Fantasy scoring, projection aggregation, post-sim layers
│   └── validation/                   # Backtesting, A/B metrics, caches, ledger, parallel harness
└── tests/                            # pytest suite mirroring package structure
```

## Directory Purposes

**Root:**
- Purpose: Package metadata, repo instructions, user docs, and top-level project assets.
- Contains: `pyproject.toml`, `uv.lock`, `README.md`, `AGENTS.md`, `CLAUDE.md`.
- Key files: `pyproject.toml` defines the `fantasy-sim` console script and pytest settings; `AGENTS.md` defines repo-specific workflow and simulation constraints.

**`config/`:**
- Purpose: YAML runtime configuration and examples.
- Contains: `config/defaults.yaml`, `config/season.example.yaml`, `config/custom_scoring.example.yaml`, `config/season.2025.yaml`.
- Key files: Put default feature flags and scoring presets in `config/defaults.yaml`; put user-editable examples in `config/*.example.yaml`.

**`docs/`:**
- Purpose: Human-readable design, validation, setup, and hypothesis documentation.
- Contains: Top-level docs such as `docs/CONFIG.md`, `docs/AB-TESTING.md`, `docs/CLI-COMMANDS.md`, `docs/pff-setup.md`, `docs/hypotheses-list.md`; archived docs in `docs/archive/`; planning docs in `docs/hypothesis-plans/`; handoff/spec/plan docs in `docs/superpowers/`.
- Key files: Use `docs/AB-TESTING.md` for validation workflow context; use `docs/CONFIG.md` for config semantics; use `docs/hypotheses-list.md` for accuracy backlog context.

**`results/`:**
- Purpose: Local validation outputs and fitted artifacts.
- Contains: `results/ab_ledger.json`, `results/cache/`, `results/dynamic_blend/`, `results/residual_calibration/`, `results/target_selection/`.
- Key files: `results/ab_ledger.json` is the persistent A/B validation ledger; `results/cache/` stores validation baseline caches; `results/dynamic_blend/decision_s200/` and `results/residual_calibration/decision_s200/` store fitting outputs.

**`scripts/`:**
- Purpose: Operational CLIs for validation, fitting, scraping, importing, and diagnostics.
- Contains: Unified validation in `scripts/validate.py`; fitting scripts in `scripts/fit_dynamic_blend_weights.py`, `scripts/fit_residual_calibration.py`, `scripts/fit_target_selection.py`; data ingestion scripts in `scripts/scrape_pff.py`, `scripts/scrape_pff_props.py`, `scripts/import_market_history.py`, `scripts/fetch_market_history_events.py`, `scripts/fetch_market_history_props.py`; legacy/targeted validators in `scripts/validate_pff_signal.py`, `scripts/validate_weekly_signal.py`, `scripts/validate_data.py`, `scripts/validate_sim.py`, `scripts/validate_players.py`, `scripts/validate_passing.py`.
- Key files: Use `scripts/validate.py` as the primary validation entry point; keep new one-off operational scripts in `scripts/` and tests in `tests/test_scripts/`.

**`src/fantasy_sim/config/`:**
- Purpose: Generic config loading and scoring preset resolution.
- Contains: `src/fantasy_sim/config/loader.py`.
- Key files: Add generic YAML/scoring helpers to `src/fantasy_sim/config/loader.py`; keep feature-specific config in `src/fantasy_sim/data/<feature>/config.py`.

**`src/fantasy_sim/data/`:**
- Purpose: Raw data access, preprocessing, player model construction, game context assembly, and all pre-simulation signal engines.
- Contains: Core files `src/fantasy_sim/data/loader.py`, `src/fantasy_sim/data/pipeline.py`, `src/fantasy_sim/data/preprocessor.py`, `src/fantasy_sim/data/player_builder.py`, `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/data/actuals.py`; signal packages `availability/`, `ensemble/`, `game_script/`, `market_history/`, `pff/`, `role_trend/`, `target_selection/`, `tracking/`, `usage/`, `vegas/`, `weather/`; standalone layers `src/fantasy_sim/data/td_tendency.py`, `src/fantasy_sim/data/goal_line_concentration.py`, `src/fantasy_sim/data/rookie_builder.py`.
- Key files: `src/fantasy_sim/data/game_context.py` is the pre-sim composition root; `src/fantasy_sim/data/player_builder.py` owns `PlayerModel` assembly and share normalization.

**`src/fantasy_sim/data/pff/`:**
- Purpose: PFF-derived pre-simulation intelligence.
- Contains: `src/fantasy_sim/data/pff/config.py`, `src/fantasy_sim/data/pff/models.py`, `src/fantasy_sim/data/pff/loader.py`, and engines including `matchup.py`, `tier_engine.py`, `team_context.py`, `coverage.py`, `depth_role.py`, `rb_scheme_fit.py`, `qb_split.py`, `kicker.py`, `dst_baseline.py`, `talent.py`.
- Key files: Put PFF config dataclasses in `src/fantasy_sim/data/pff/models.py`; put config parsing in `src/fantasy_sim/data/pff/config.py`; implement one engine per signal file.

**`src/fantasy_sim/data/market_history/`:**
- Purpose: Historical odds/player market ingestion, normalization, and signal loading.
- Contains: `src/fantasy_sim/data/market_history/models.py`, `config.py`, `loader.py`, `features.py`, `importer.py`, `player_markets.py`, `events_inventory.py`, `props_backfill.py`, `crosswalk.py`, `teams.py`.
- Key files: Use `src/fantasy_sim/data/market_history/loader.py` for runtime reads and `src/fantasy_sim/data/market_history/features.py` for normalization consumed by `src/fantasy_sim/scoring/market_history.py`.

**`src/fantasy_sim/data/ensemble/`:**
- Purpose: External prior configuration, normalization, loaders, and bundled learned artifacts.
- Contains: `src/fantasy_sim/data/ensemble/models.py`, `config.py`, `loader.py`, `normalizer.py`, and artifact directories under `src/fantasy_sim/data/ensemble/artifacts/`.
- Key files: Bundled dynamic blend weights live in `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/`; bundled residual calibration artifacts live in `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/`.

**`src/fantasy_sim/engine/`:**
- Purpose: Pure simulation runtime.
- Contains: `src/fantasy_sim/engine/monte_carlo.py`, `game_sim.py`, `play_resolver.py`, `play_caller.py`, `player_selector.py`, `game_flow.py`, `clock.py`, `game_script.py`, `types.py`.
- Key files: Add game-loop behavior to `src/fantasy_sim/engine/game_sim.py`; add play outcome mechanics to `src/fantasy_sim/engine/play_resolver.py`; add shared runtime dataclasses to `src/fantasy_sim/engine/types.py`.

**`src/fantasy_sim/models/`:**
- Purpose: Stable domain dataclasses independent of orchestration.
- Contains: `src/fantasy_sim/models/game_state.py`, `src/fantasy_sim/models/distributions.py`, `src/fantasy_sim/models/player.py`.
- Key files: Put distribution models in `src/fantasy_sim/models/distributions.py`; put player/roster models in `src/fantasy_sim/models/player.py`; put bucket definitions in `src/fantasy_sim/models/game_state.py`.

**`src/fantasy_sim/scoring/`:**
- Purpose: Fantasy point scoring, projection aggregation, and post-simulation projection layers.
- Contains: `src/fantasy_sim/scoring/engine.py`, `projections.py`, `projection_layers.py`, `role_trend.py`, `market_history.py`, `ensemble.py`, `dynamic_blend.py`, `residual_calibration.py`.
- Key files: Add fantasy scoring keys to `src/fantasy_sim/scoring/engine.py`; add projection row aggregation to `src/fantasy_sim/scoring/projections.py`; add layer ordering to `src/fantasy_sim/scoring/projection_layers.py`.

**`src/fantasy_sim/validation/`:**
- Purpose: Validation orchestration, metrics, caches, ledger, coverage, and parallel execution.
- Contains: `src/fantasy_sim/validation/backtester.py`, `parallel.py`, `config.py`, `metrics.py`, `weekly.py`, `coverage.py`, `cache.py`, `ledger.py`, `report.py`, `game_script.py`.
- Key files: Put A/B context build and simulation parallelism in `src/fantasy_sim/validation/parallel.py`; put ledger schema in `src/fantasy_sim/validation/ledger.py`; put reusable metrics in `src/fantasy_sim/validation/metrics.py`.

**`src/fantasy_sim/output/`:**
- Purpose: User-facing table and file output.
- Contains: `src/fantasy_sim/output/tables.py`, `src/fantasy_sim/output/export.py`.
- Key files: Add table formatters to `src/fantasy_sim/output/tables.py`; add export format logic to `src/fantasy_sim/output/export.py`.

**`src/fantasy_sim/overrides/`:**
- Purpose: User override parsing, fuzzy/exact player resolution, and share mutations.
- Contains: `src/fantasy_sim/overrides/parser.py`, `engine.py`, `resolver.py`.
- Key files: Put CLI/config string parsing in `src/fantasy_sim/overrides/parser.py`; put mutation semantics in `src/fantasy_sim/overrides/engine.py`; put fuzzy matching in `src/fantasy_sim/overrides/resolver.py`.

**`tests/`:**
- Purpose: pytest suite organized around package layers and operational scripts.
- Contains: Root tests `tests/test_cli.py`, `tests/test_smoke.py`, `tests/test_edge_cases.py`, shared fixtures in `tests/conftest.py`; package-mirrored directories `tests/test_data/`, `tests/test_engine/`, `tests/test_models/`, `tests/test_output/`, `tests/test_overrides/`, `tests/test_scoring/`, `tests/test_validation/`, `tests/test_config/`, `tests/test_scripts/`, `tests/test_integration/`.
- Key files: Add tests beside the closest package analog, such as `tests/test_engine/test_play_resolver.py` for `src/fantasy_sim/engine/play_resolver.py`.

## Key File Locations

**Entry Points:**
- `pyproject.toml`: Declares `fantasy-sim = "fantasy_sim.cli:main"`.
- `src/fantasy_sim/cli.py`: Click command group and all user-facing projection commands.
- `scripts/validate.py`: Primary A/B validation CLI.
- `src/fantasy_sim/validation/backtester.py`: Backtest API used by `fantasy-sim backtest`.
- `src/fantasy_sim/engine/monte_carlo.py`: Library entry point for repeated simulations.

**Configuration:**
- `config/defaults.yaml`: Master feature flags, simulation settings, scoring presets, and layer config.
- `src/fantasy_sim/config/loader.py`: YAML load, scoring inheritance, custom scoring resolution.
- `src/fantasy_sim/validation/config.py`: Dot-notation override application and validation engine config resolution.
- `src/fantasy_sim/data/pff/config.py`, `src/fantasy_sim/data/weather/config.py`, `src/fantasy_sim/data/vegas/config.py`, `src/fantasy_sim/data/usage/config.py`, `src/fantasy_sim/data/tracking/config.py`, `src/fantasy_sim/data/availability/config.py`, `src/fantasy_sim/data/ensemble/config.py`, `src/fantasy_sim/data/market_history/config.py`: Feature-specific config loaders.

**Core Logic:**
- `src/fantasy_sim/data/game_context.py`: Ordered pre-simulation assembly and feature-layer application.
- `src/fantasy_sim/data/loader.py`: nflverse and local parquet cache access.
- `src/fantasy_sim/data/preprocessor.py`: PBP-to-distribution computation.
- `src/fantasy_sim/data/player_builder.py`: PBP-to-player model and roster normalization.
- `src/fantasy_sim/engine/game_sim.py`: Full game loop.
- `src/fantasy_sim/engine/play_resolver.py`: Pass/run play resolution.
- `src/fantasy_sim/engine/player_selector.py`: QB, receiver, and rusher selection.
- `src/fantasy_sim/scoring/projection_layers.py`: Post-simulation layer order.
- `src/fantasy_sim/scoring/projections.py`: Projection aggregation.

**Validation:**
- `scripts/validate.py`: A/B runner, ledger append, CLI arguments.
- `src/fantasy_sim/validation/parallel.py`: Build and simulation workers.
- `src/fantasy_sim/validation/metrics.py`: Spearman, MAE, boom/bust, KS metrics.
- `src/fantasy_sim/validation/weekly.py`: Weekly summaries and directional accuracy.
- `src/fantasy_sim/validation/ledger.py`: `SeasonMetrics`, `LedgerEntry`, load/save/table formatting.
- `src/fantasy_sim/validation/coverage.py`: Signal coverage discovery for validation runs.
- `results/ab_ledger.json`: Persistent validation evidence.

**Testing:**
- `tests/conftest.py`: Shared fixtures and sample PBP/roster data.
- `tests/test_data/`: Data, context, and signal-layer tests.
- `tests/test_engine/`: Engine and simulation tests.
- `tests/test_scoring/`: Scoring and post-sim layer tests.
- `tests/test_validation/`: Validation harness, metrics, ledger, coverage, and script tests.
- `tests/test_scripts/`: Script behavior tests.

## Naming Conventions

**Files:**
- Use snake_case Python modules: `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/scoring/residual_calibration.py`, `src/fantasy_sim/validation/parallel.py`.
- Use package-per-signal directories for larger feature families: `src/fantasy_sim/data/market_history/`, `src/fantasy_sim/data/target_selection/`, `src/fantasy_sim/data/tracking/`.
- Use a consistent `models.py`, `config.py`, `engine.py` split inside feature packages when a feature has typed config plus runtime behavior: `src/fantasy_sim/data/weather/models.py`, `src/fantasy_sim/data/weather/config.py`, `src/fantasy_sim/data/weather/engine.py`.
- Use `test_*.py` for pytest files: `tests/test_engine/test_game_sim.py`, `tests/test_validation/test_parallel.py`.
- Use verb-first operational script names: `scripts/validate.py`, `scripts/fit_dynamic_blend_weights.py`, `scripts/fetch_market_history_props.py`, `scripts/build_market_history_player_markets.py`.

**Directories:**
- Mirror package structure in tests: `src/fantasy_sim/engine/` maps to `tests/test_engine/`; `src/fantasy_sim/scoring/` maps to `tests/test_scoring/`; `src/fantasy_sim/validation/` maps to `tests/test_validation/`.
- Place domain signal packages under `src/fantasy_sim/data/` when they mutate inputs before simulation or provide data for scoring.
- Place user-facing operational scripts under `scripts/`, not under `src/fantasy_sim/`.
- Place persistent human docs under `docs/`; place generated GSD codebase maps under `.planning/codebase/`.

**Python Symbols:**
- Use `CamelCase` for dataclasses and engine classes: `GameContextBuilder`, `PlayerModel`, `TeamDistributions`, `MarketHistoryProjectionAdjuster`.
- Use `snake_case` for functions and methods: `build_game()`, `run_simulations()`, `apply_projection_layers()`, `load_defaults()`.
- Use leading underscore for module-private helpers: `_ensure_pipeline()`, `_normalize_roster_shares()`, `_compute_distribution_ks()`.
- Use all-caps constants for shared calibration values: `MIN_BUCKET_PLAYS`, `PASS_TD_GATE`, `RZ_CATCH_RATE_MODIFIER`, `CURRENT_LEDGER_SCHEMA_VERSION`.

## Where to Add New Code

**New Projection CLI Command:**
- Primary code: `src/fantasy_sim/cli.py`
- Tests: `tests/test_cli.py`
- Use existing helpers such as `_make_builder()`, `_resolve_config_chain()`, `_display_projections()`, and `_get_training_seasons()` before adding new orchestration helpers.

**New Pre-Simulation Data Signal:**
- Primary code: `src/fantasy_sim/data/<signal>/models.py`, `src/fantasy_sim/data/<signal>/config.py`, `src/fantasy_sim/data/<signal>/engine.py`
- Config: Add section defaults to `config/defaults.yaml`.
- Context wiring: Add config argument and engine initialization to `GameContextBuilder.__init__()` in `src/fantasy_sim/data/game_context.py`; add an ordered application block to `GameContextBuilder.build_game()`.
- Validation wiring: Add config resolution to `src/fantasy_sim/validation/config.py` and thread it through `src/fantasy_sim/validation/parallel.py`.
- Tests: `tests/test_data/test_<signal>/` for package features or `tests/test_data/test_<signal>.py` for single-file layers.

**New Post-Simulation Projection Layer:**
- Primary code: `src/fantasy_sim/scoring/<layer>.py`
- Layer order: `src/fantasy_sim/scoring/projection_layers.py`
- Config/data support: `src/fantasy_sim/data/<layer>/` or `src/fantasy_sim/data/ensemble/` depending on ownership.
- CLI wiring: `_make_<layer>()` style helper in `src/fantasy_sim/cli.py`.
- Validation wiring: `scripts/validate.py`, `src/fantasy_sim/validation/backtester.py`, and `src/fantasy_sim/validation/config.py`.
- Tests: `tests/test_scoring/test_<layer>.py` and validation path tests under `tests/test_validation/`.

**New Engine Rule Or Play Mechanic:**
- Primary code: `src/fantasy_sim/engine/play_resolver.py`, `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/engine/game_flow.py`, or `src/fantasy_sim/engine/player_selector.py`, depending on whether the change affects play outcome, game loop, flow, or player choice.
- Shared type changes: `src/fantasy_sim/engine/types.py` or `src/fantasy_sim/models/`.
- Tests: `tests/test_engine/test_play_resolver.py`, `tests/test_engine/test_game_sim.py`, `tests/test_engine/test_game_flow.py`, or `tests/test_engine/test_player_selector.py`.

**New Domain Model:**
- Primary code: `src/fantasy_sim/models/` when the type is shared across data and engine layers.
- Runtime-only type: `src/fantasy_sim/engine/types.py`.
- Feature-specific type: `src/fantasy_sim/data/<feature>/models.py`.
- Tests: `tests/test_models/` for shared models; `tests/test_data/test_<feature>/` for feature-specific models.

**New Data Loader Method:**
- Primary code: `src/fantasy_sim/data/loader.py` for nflverse or shared parquet cache reads.
- Feature-specific loader: `src/fantasy_sim/data/<feature>/loader.py` when the data source belongs to one signal family.
- Tests: `tests/test_data/test_loader.py` or feature-specific loader tests.

**New Validation Metric Or Ledger Field:**
- Primary code: `src/fantasy_sim/validation/metrics.py`, `scripts/validate.py`, and `src/fantasy_sim/validation/ledger.py`.
- Compatibility: Update `CURRENT_LEDGER_SCHEMA_VERSION` and keep `load_ledger()` compatible with existing `results/ab_ledger.json`.
- Tests: `tests/test_validation/test_metrics.py`, `tests/test_validation/test_ledger.py`, `tests/test_validation/test_validate_script.py`.

**New Operational Script:**
- Implementation: `scripts/<verb>_<noun>.py`
- Tests: `tests/test_scripts/test_<verb>_<noun>.py`
- Reuse package APIs from `src/fantasy_sim/` rather than duplicating pipeline logic in `scripts/`.

**New Output Format:**
- Implementation: `src/fantasy_sim/output/export.py` for file exports or `src/fantasy_sim/output/tables.py` for terminal rendering.
- CLI wiring: `src/fantasy_sim/cli.py`.
- Tests: `tests/test_output/test_export.py`, `tests/test_output/test_tables.py`, `tests/test_cli.py`.

## Special Directories

**`.planning/codebase/`:**
- Purpose: GSD codebase map documents consumed by planning and execution workflows.
- Generated: Yes
- Committed: Yes, when the orchestrator commits the map.

**`src/fantasy_sim/data/ensemble/artifacts/`:**
- Purpose: Bundled dynamic blend and residual calibration artifacts used as default runtime fallbacks.
- Generated: Yes, by fitting scripts such as `scripts/fit_dynamic_blend_weights.py` and `scripts/fit_residual_calibration.py`.
- Committed: Yes.

**`results/`:**
- Purpose: Validation outputs, ledgers, caches, and local fitting run outputs.
- Generated: Yes
- Committed: Mixed. Treat `results/ab_ledger.json` and selected decision artifacts as project evidence; treat transient run caches under `results/cache/` as generated validation support.

**`dist/`:**
- Purpose: Python package build artifacts.
- Generated: Yes
- Committed: Not required for source changes.

**`.venv/`:**
- Purpose: Local virtual environment for `uv`.
- Generated: Yes
- Committed: No.

**`.pytest_cache/`, `.ruff_cache/`, `__pycache__/`:**
- Purpose: Tool/runtime caches.
- Generated: Yes
- Committed: No.

**`.claude/worktrees/` and `.worktrees/`:**
- Purpose: Local agent/worktree scratch directories.
- Generated: Yes
- Committed: No.

**External `~/.fantasy-sim/` Caches:**
- Purpose: nflverse parquet cache, PFF processed data, weather cache, props/market-history cache, and local credentials outside the repo.
- Generated: Yes
- Committed: No. Never inspect or quote credential files such as `~/.fantasy-sim/pff/.env` or `~/.fantasy-sim/props/.env`.

---

*Structure analysis: 2026-04-24*
