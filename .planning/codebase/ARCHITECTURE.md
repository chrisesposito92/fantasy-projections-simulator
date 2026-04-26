# Architecture

**Analysis Date:** 2026-04-26

## Pattern Overview

**Overall:** Layered pipeline with multi-stage data transformation and Monte Carlo simulation engine

**Key Characteristics:**
- Five-stage pipeline: Data → Models → Engine → Scoring → Output
- Play-by-play game simulation with team distribution sampling
- Modular adjustment engines (PFF, Vegas, Weather, Availability, etc.) applied in strict order
- Non-parametric empirical distributions (numpy arrays of historical values)
- Frozen dataclasses for game state and configuration (dict keys safe)
- Three-layer cache: pipeline output, PBP stats, player models

## Layers

**Data Layer:**
- Purpose: Load nflverse data, cache as parquet, preprocess into probability distributions
- Location: `src/fantasy_sim/data/`
- Contains: DataLoader (nflreadpy bridge), DataPipeline (build distributions), Preprocessor (PBP→stats), player/roster builders
- Key files: `loader.py` (nflreadpy wrapping), `pipeline.py` (orchestration), `preprocessor.py` (bucketing by game state)
- Depends on: nflreadpy (public NFL data), httpx (API calls for PFF/weather/props)
- Used by: GameContextBuilder
- **Sub-layer: PFF Intelligence** (`data/pff/`): TierEngine, MatchupEngine, TeamContextEngine, RbSchemeFitEngine, QbSplitEngine, CoverageEngine, KickerEngine, DstBaselineEngine. Loaded conditionally via config flags.
- **Sub-layer: Vegas** (`data/vegas/`): ITT pace (VEG-01), spread pass-rate (VEG-02), player props (VEG-03)
- **Sub-layer: Weather** (`data/weather/`): Open-Meteo API, wind/temp/precipitation factors
- **Sub-layer: Availability** (`data/availability/`): Injury flags and snap availability
- **Sub-layer: Ensemble** (`data/ensemble/`): Dynamic blend weights and residual calibration artifacts
- **Sub-layer: Role Trend** (`data/role_trend/`): Historical role changes post-sim
- **Sub-layer: Market History** (`data/market_history/`): Opening line and closing line for projection adjustment
- **Sub-layer: Usage** (`data/usage/`): Override target/carry shares
- **Sub-layer: Game Script** (`data/game_script/`): Win probability / game script effects on play calling
- **Sub-layer: Play Call Model** (`data/play_call_model/`): Fitted model for 4th down, goal line, red zone decisions
- **Sub-layer: QB Rushing** (`data/qb_rushing/`): Designed runs + scrambles with artifacts
- **Sub-layer: Target Selection** (`data/target_selection/`): Per-game receiver efficiency
- **Sub-layer: Tracking** (`data/tracking/`): High-level route concepts and receiver participation
- **Sub-layer: TD Tendency** (`data/td_tendency/`): Per-player TD rate factors

**Models Layer:**
- Purpose: Dataclass definitions for game state, distributions, players, rosters
- Location: `src/fantasy_sim/models/`
- Contains: `distributions.py` (PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel), `player.py` (PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster), `game_state.py` (GameStateBucket)
- Key abstractions: PlayerUsage (snap_share, carry_share, target_share, red_zone variants), PlayerOutcomes (catch_rate, yards_dist, fumble_rate), GameStateBucket (down, distance, score_diff, quarter, yard_zone)
- Depends on: numpy (arrays for outcome distributions)
- Used by: Engine, Data layer

**Engine Layer:**
- Purpose: Play-by-play game simulation with player selection and outcome resolution
- Location: `src/fantasy_sim/engine/`
- Contains: Game simulation, play calling, play resolution, clock/scoring logic, player selection
- Key files:
  - `monte_carlo.py`: Run N simulations, aggregate results
  - `game_sim.py`: Main game loop—initialize state, execute plays until game over
  - `play_caller.py`: Select play type (pass/run) using PlayCallingDist, 4th down decisions
  - `play_resolver.py`: Resolve single play outcome (catch rate, yards, TD, sack, INT, fumble)
  - `player_selector.py`: Select QB, receiver, or rusher from roster using weights
  - `game_flow.py`: Handle yards gained, possessions, turnovers, scoring, special teams
  - `clock.py`: Update game time, check quarter end
  - `game_script.py`: Effective pace from Vegas ITT, game win probability
- Depends on: Models layer, Data layer distributions
- Used by: Scoring layer (aggregates N simulations to projections)
- **Adjustment Pipeline Order** (in `GameContextBuilder.build_game()`):
  1. Base PBP model (from pipeline)
  2. Vegas: ITT pace + spread pass-rate factors
  3. Availability: Snap availability (injuries)
  4. Normalize
  5. Usage: Override carry/target shares
  6. Normalize
  7. Tracking: Route concepts
  8. Normalize
  9. Props: Player props (Odds API)
  10. Normalize
  11. Matchup: Per-game defensive z-scores
  12. Team context + tier blend: Season-level environment
  13. Normalize
  14. RB scheme fit: Rushing efficiency from blocking
  15. QB split: QB pressure effect on receivers
  16. Depth role: Role-level efficiency
  17. Normalize
  18. Coverage: CB matchup modifiers (WR only)
  19. DST baseline: Defense fumble rate + TD rate
  20. Kicker: FG accuracy with shrinkage
  21. TD tendency: Per-player TD multipliers
  22. Normalize
  23. Weather: Wind/temp/precipitation final layer

**Scoring Layer:**
- Purpose: Convert raw play-by-play simulation results to fantasy point projections
- Location: `src/fantasy_sim/scoring/`
- Contains: Projection builders (aggregate stats), post-sim adjusters (ensemble, blending), scoring engines
- Key files:
  - `projections.py`: build_player_projections (aggregate N sims to mean/floor/ceiling)
  - `engine.py`: score_player, score_dst, score_kicker (position-specific fantasy point rules)
  - `projection_layers.py`: apply post-sim layers in order
  - `dynamic_blend.py`: Ensemble blend of multiple pre-computed model outputs
  - `residual_calibration.py`: Final season/bucket-specific adjustment with zero fallback
  - `role_trend.py`: Historical role trend adjustments
  - `market_history.py`: Opening/closing line adjustments
  - `ensemble.py`: FF opportunity ensemble (QB/RB/WR/TE)
- **Post-Sim Projection Order**:
  1. role_trend (if enabled)
  2. dynamic_blend (if enabled) — fallback: market_history + ff_opportunity
  3. residual_calibration (if enabled)
- Depends on: Engine (GameResult, PlayerBoxScore), Models (position-specific config)
- Used by: CLI output, validation, export

**Output Layer:**
- Purpose: Format and export projections in various formats
- Location: `src/fantasy_sim/output/`
- Contains: Rich terminal tables, CSV/JSON export
- Key files:
  - `tables.py`: format_qb_table, format_rb_table, format_wr_table, format_te_table, format_kicker_table, format_dst_table (position-specific Rich Table formatting)
  - `export.py`: export_csv, export_json (serialize projections)
- Depends on: Scoring layer (projections list)
- Used by: CLI commands

**Validation Layer:**
- Purpose: A/B test projections against actuals using hold-out seasons
- Location: `src/fantasy_sim/validation/`
- Contains: Backtester, metrics, ledger, parallel runner
- Key files:
  - `backtester.py`: Backtester class — run hold-out on single test_season, compute rank_corr/MAE/boom-bust
  - `parallel.py`: simulate_games_parallel, build_games_parallel (multi-threaded game simulation)
  - `coverage.py`: KS distribution metrics, distribution compression/deflation detection
  - `ledger.py`: Persistent A/B results cache (JSON)
  - `metrics.py`: spearman_rank_correlation, boom_bust_calibration, KS test
  - `weekly.py`: Weekly projection breakdown
  - `cache.py`: Bare baseline caching for control condition
- Depends on: Data layer, Engine, Scoring
- Used by: validation scripts (scripts/validate.py, scripts/validate_pff_signal.py, scripts/validate_weekly_signal.py)
- **Key Pattern:** Backtester holds out one season (2025 by default if configured), trains on prior N seasons, tests projections against actual scores. Ledger persists results for A/B comparison.

**Overrides Layer:**
- Purpose: Apply player/team overrides with fuzzy matching and share redistribution
- Location: `src/fantasy_sim/overrides/`
- Contains: Parser (YAML/CLI), resolver (name matching), engine (apply updates)
- Key files:
  - `parser.py`: parse_override_config (YAML), parse_cli_override (--override flag)
  - `resolver.py`: PlayerResolver (fuzzy match with Levenshtein ≥70)
  - `engine.py`: apply_player_override (update model), apply_team_override (proportional redistribution)
- Depends on: Models layer (PlayerModel)
- Used by: GameContextBuilder, CLI (pre_resolve_overrides + apply_overrides_fn)

## Data Flow

**Simulation Request:**
1. User invokes CLI command (e.g., `fantasy-sim week 1 --season 2024 --sims 100`)
2. CLI loads defaults.yaml + season.yaml + CLI flags → resolved config
3. Config loader instantiates GameContextBuilder with all sub-engine configs
4. GameContextBuilder:
   - Loads PBP data (or uses test dataframe)
   - Runs DataPipeline → empirical distributions
   - Builds TeamRoster from player_builder (PBP stats + rookie blending)
   - Applies PFF/Vegas/Weather engines in adjustment order
   - Returns (TeamDistributions, TeamRoster) for each team
5. monte_carlo.run_simulations runs N games in sequence
6. Each game: simulate_game executes play-by-play with roster player selection
7. Results: GameResult (list of plays, player stats boxes)
8. Scoring aggregates N GameResults → list of projection dicts
9. Post-sim layers (dynamic_blend, residual_calibration) adjust final projections
10. Output formats tables or exports CSV/JSON

**Validation (A/B Testing):**
1. Backtester.run() selects test_season (e.g., 2024)
2. For each week in test_season:
   - Load actual scores from nflverse
   - Build projections using default config
   - Build projections using test config (e.g., with new layer enabled)
   - Compare: rank_corr, MAE, boom-bust
3. Aggregate week results → season metrics
4. Ledger persists comparison results (control vs treatment)

**State Management:**

Three-layer cache in GameContextBuilder:
1. **Pipeline cache** (keyed by training_seasons tuple): Raw distributions (play_calling, play_outcomes, turnover_rates, kicking, drive_start)
2. **PBP stats cache** (keyed by training_seasons tuple): Aggregated historical stats (pass yards by bucket, rush yards by bucket, etc.)
3. **Player models cache** (keyed by (training_seasons, target_season, week, props_enabled)): Final PlayerModel objects (usage + outcomes after all adjustments)

Caches are built once and reused across multiple game simulations in same run. Locks prevent race conditions in multi-threaded validation.

## Key Abstractions

**GameStateBucket:**
- Purpose: Immutable key for distribution lookups
- Definition: (down, distance, score_diff, quarter, yard_zone)
- Usage: dict[GameStateBucket, list[int]]→outcome samples
- Pattern: Frozen dataclass so it can be dict key

**Empirical Distributions:**
- Purpose: Non-parametric outcome sampling
- Implementation: numpy arrays of historical values
- Fallback: MIN_BUCKET_PLAYS=10 → fall back to team/league defaults
- Sampling: rng.choice(distribution_array) → single outcome

**yardline_100 Convention:**
- 99 = own 1-yard line (deep own territory)
- 75 = own 25-yard line (touchback starting point)
- 50 = midfield
- 20 = red zone (outside 20)
- 1 = goal line
- TD when `yard_line - yards <= 0`
- Safety when `yard_line - yards >= 100`

**Red Zone Constants:**
- `RED_ZONE_MAX_YARDLINE = 20`
- `OUTER_RZ_MIN_YARDLINE = 6`
- `GOAL_LINE_MAX_YARDLINE = 5`
- Per-player RZ catch rate: if ≥10 RZ targets, use per-player override; else use league default (0.92x overall)

**Catch Yards Boost:**
- `CATCH_YARDS_BOOST = 1`: Add 1 yard per catch outside red zone to correct for field-position clamping bias
- Red zone catches: no boost (accurate RZ catch rate model)

**QB Carry Share Filter:**
- `MIN_QB_CARRY_SHARE = 0.10`: Excludes pocket passers from designed-run pool
- Dual-threat QBs (Allen ~0.22, Hurts ~0.18) included; pocket passers (Herbert ~0.05) scramble-only

**Sack-Fumble Attribution:**
- Sack-fumbles charge to QB's `fumbles_lost` (fantasy convention)

**Share Normalization:**
- build_team_roster() deepcopies players and normalizes carry/target shares to sum 1.0 among eligible players
- Ensures selection probability weights are valid

## Entry Points

**CLI (fantasy_sim/cli.py):**
- Location: `src/fantasy_sim/cli.py`
- Triggers: `uv run fantasy-sim <command>`
- Commands:
  - `demo` — demo mode with synthetic rosters and distributions
  - `week <week> --season <year>` — project single week
  - `season <year>` — project full season by week
  - `game <team> <team> --week <N>` — project single matchup
  - `player <name> --week <N>` — project single player
  - `backtest --season <year>` — run A/B validation
- Responsibilities:
  - Parse config (defaults, season, CLI flags)
  - Instantiate GameContextBuilder
  - Run simulations
  - Format output
  - Export if requested

**Validation Scripts (scripts/):**
- `validate.py` — Main A/B harness with ledger persistence
- `validate_pff_signal.py` — A/B test individual PFF engines
- `validate_weekly_signal.py` — Weekly breakdown
- `validate_sim.py` — 5000-game smoke test
- `validate_players.py` — Roster validation (offline)
- `validate_data.py` — Data quality checks (network)
- Fit/sweep scripts: `fit_dynamic_blend_weights.py`, `fit_residual_calibration.py`, `fit_talent_coefficients.py`, etc.

## Error Handling

**Strategy:** Graceful degradation with fallbacks

**Patterns:**
- Missing distributions → fall back to team/league defaults
- Missing player data → use positional archetype blending (rookie_builder.py)
- PFF unavailable → run without PFF engines (config.enabled=false)
- Missing bucketed stats → use unbucketed league average
- Residual calibration missing season artifact → zero adjustment + log warning
- Invalid player match → raise AmbiguousMatchError (human review required)

## Cross-Cutting Concerns

**Logging:**
- Framework: Python logging module
- Key loggers: `fantasy_sim.data.game_context` (GameContextBuilder), `fantasy_sim.engine.game_sim` (simulation progress)
- Level: INFO for layer initialization, DEBUG for per-game details

**Validation:**
- All DataFrames validated against nflreadpy schema in DataLoader
- Player IDs matched by exact ID, then exact name, then fuzzy (Levenshtein ≥70)
- Distributions validated min_bucket_plays (>=10 samples)
- Share normalization checked: sum(target_share) ≤ 1.0 per roster

**Authentication:**
- PFF: Cookie-based auth via `~/.fantasy-sim/pff/.env` (read but never logged)
- The Odds API: API key via `~/.fantasy-sim/props/.env`
- Open-Meteo: Public API, no auth required

**Configuration:**
- YAML chain: defaults.yaml → season.yaml → --scoring-config → CLI flags
- All config files in `config/` directory
- CLI flags override YAML precedence: --scoring always overrides YAML `scoring_format:`

---

*Architecture analysis: 2026-04-26*
