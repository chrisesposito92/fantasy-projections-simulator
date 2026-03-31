# CLAUDE.md

## Project Overview

NFL fantasy football projections simulator. Simulates games play-by-play using historical nflverse data, runs Monte Carlo simulations, and produces fantasy point projections with full stat distributions.

## Tech Stack

- Python 3.12+ (currently running 3.14)
- uv for package management and virtual environment
- polars for DataFrames (NOT pandas)
- numpy for numerical simulation
- nflreadpy for NFL data from nflverse
- pytest for testing (with pytest-xdist, hypothesis)
- YAML for configuration

## Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test module
uv run pytest tests/test_engine/test_game_sim.py -v

# Run statistical validation tests only
uv run pytest tests/ -v -m statistical

# Run simulation validation script (5000 games)
uv run python scripts/validate_sim.py

# Run player validation (1000 sims, no network needed)
uv run python scripts/validate_players.py

# Run data validation (requires network)
uv run python scripts/validate_data.py

# Install dependencies
uv pip install -e ".[dev]"

# Run CLI demo (synthetic data, no network needed)
uv run fantasy-sim demo --sims 100
uv run fantasy-sim demo --sims 100 --scoring half_ppr
uv run fantasy-sim demo --sims 100 --format csv --output projections.csv
uv run fantasy-sim demo --sims 100 --format json --output projections.json

# Simulate real NFL week (requires network)
uv run fantasy-sim week 1 --season 2024 --sims 100

# Simulate real NFL season (regular season only by default, requires network)
uv run fantasy-sim season --season 2024 --sims 50

# Season with per-week breakdowns
uv run fantasy-sim season --season 2024 --sims 50 --by-week

# Season export (format auto-inferred from extension)
uv run fantasy-sim season --season 2024 --sims 50 --output rankings.json

# Backtest against historical actuals
uv run fantasy-sim backtest --season 2024 --sims 50

# Override player/team stats
uv run fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.30"
uv run fantasy-sim week 1 --season 2024 --override "mahomes.games_played=14"
uv run fantasy-sim week 1 --season 2024 --config config/season.example.yaml

# Game command (single-game deep dive)
uv run fantasy-sim game KC BUF --week 5 --sims 100
uv run fantasy-sim game HOME AWAY --demo --sims 100

# Player command (single-player projection)
uv run fantasy-sim player "nico_collins" --week 5 --sims 100
uv run fantasy-sim player HOME_QB --demo --sims 100

# Detail mode (floor/ceiling/stddev)
uv run fantasy-sim demo --sims 100 --detail
uv run fantasy-sim week 1 --sims 100 --detail

# Custom scoring
uv run fantasy-sim week 1 --scoring-config config/custom_scoring.yaml
```

## Architecture

The project is organized as a pipeline:

1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`, `data/player_builder.py`, `data/rookie_builder.py`, `data/game_context.py`, `data/actuals.py`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions, builds per-player models from PBP data, generates rookie archetypes, bridges real data to sim engine, loads actual player stats for backtesting. Player models separate stats (historical PBP) from team assignment (current-season roster) via `_aggregate_pbp_stats()` (cached, expensive) + `_assemble_models()` (cheap, per-week). `build_kicker_model()` creates placeholder kicker models for scoring attribution.
2. **Models** (`models/game_state.py`, `models/distributions.py`, `models/player.py`) — Shared data types used by both preprocessing and simulation, including player usage/outcome models and team rosters
3. **Engine** (`engine/types.py`, `engine/play_caller.py`, `engine/play_resolver.py`, `engine/player_selector.py`, `engine/game_flow.py`, `engine/clock.py`, `engine/game_sim.py`, `engine/monte_carlo.py`) — Play-by-play game simulation with player-level tracking and Monte Carlo runner
4. **Config** (`config/loader.py`, `config/defaults.yaml`) — YAML config loading with `_inherit` scoring preset inheritance (PPR, half-PPR, standard)
5. **Scoring** (`scoring/engine.py`, `scoring/projections.py`) — Config-driven fantasy point calculation for players, DST, and kickers; projection builder aggregates sim results into ranked projections
6. **Output** (`output/tables.py`, `output/export.py`) — Rich terminal tables by position, CSV/JSON export
7. **Validation** (`validation/metrics.py`, `validation/backtester.py`, `validation/report.py`) — Accuracy metrics (Spearman, MAE, boom/bust calibration), hold-out backtesting framework, formatted validation reports
8. **Overrides** (`overrides/engine.py`, `overrides/resolver.py`, `overrides/parser.py`) — Player/team override engine with proportional share redistribution, fuzzy name matching, YAML + CLI parsing
9. **CLI** (`cli.py`) — Click-based CLI with `demo`, `week`, `season`, `game`, `player`, `backtest` commands, `--override`, `--config`, `--detail`, `--scoring-config` flags, rich progress bars

## Key Patterns

- **ConfigLoader**: `load_config()` loads YAML, `resolve_scoring()` resolves `_inherit` chains. `load_defaults()` loads `config/defaults.yaml`. Scoring presets: PPR (base), half_ppr (_inherit: ppr, reception: 0.5), standard (_inherit: ppr, reception: 0).
- **ScoringEngine**: `score_player(box, config)` for QB/RB/WR/TE with position-specific reception keys (`reception_wr`, `reception_te`) and yardage bonus thresholds (`rushing_bonus_100`, `passing_bonus_300`). `score_dst(box, opponent_score, config)` with 7 points-allowed brackets. `score_kicker(box, config)` with FG distance buckets.
- **CustomScoring**: `load_custom_scoring(path, presets)` reads `custom_scoring.yaml` with `inherit` + `overrides` format. `_resolve_config_chain()` merges defaults -> season.yaml -> --scoring-config.
- **ProjectionBuilder**: `build_player_projections(games, config)` aggregates PlayerBoxScore across sims into mean stats + fpts, sorted by fpts. `build_detailed_projections(games, config)` adds floor (10th pct), ceiling (90th pct), and stddev for fpts and all tracked stats. `build_dst_projections(games, config, team_map)` for DST. `build_kicker_projections()` accepts optional rosters for real kicker attribution.
- **GameContextBuilder**: `build_game(home, away, training_seasons, target_season, week)` constructs `TeamDistributions` + `TeamRoster` per team from real nflverse data. Three-layer cache: pipeline output (training_seasons), PBP stats (training_seasons), player models (training_seasons + target_season + week). Falls back to league-average distributions for unknown teams. Roster loaded from `target_season`, optionally filtered to `week` for per-week accuracy (mid-season trades, IR moves).
- **ActualPlayerWeek**: Loads real player stats, scores with config. Used by backtester for comparison.
- **Backtester**: `Backtester(test_season, n_sims, num_training_seasons)` runs hold-out validation. `run(scoring_config)` returns `BacktestResult` with `passes_targets()` method. Targets: rank_corr > 0.80, weekly_mae < 6.0, season_mae < 25, calibration < 0.10.
- **OverrideEngine**: `apply_player_override(roster, player_id, overrides)` applies usage/outcome/meta overrides; automatically triggers `redistribute_target_shares()` or `redistribute_carry_shares()` for share fields. `apply_team_override(dists, overrides)` modifies PlayCallingDist and TurnoverRates. Both raise on unknown fields.
- **PlayerResolver**: `PlayerResolver(rosters).resolve(query)` resolves names to player_id via exact ID → exact name → underscore conversion → fuzzy match (thefuzz, MIN_MATCH_SCORE=70).
- **OverrideParser**: `parse_override_config(path)` reads season.yaml into `OverrideSet`. `parse_cli_override("name.field=value")` parses CLI strings. `_build_overrides()` in CLI merges config + CLI overrides (CLI takes precedence).
- **CLI**: `fantasy-sim demo` runs synthetic simulations. `fantasy-sim week N --season YYYY` simulates a real NFL week. `fantasy-sim season --season YYYY` simulates a full season (regular season only by default). `fantasy-sim game HOME AWAY` simulates a single matchup with per-team breakdowns. `fantasy-sim player QUERY` shows single-player projection via fuzzy matching. `fantasy-sim backtest --season YYYY` runs historical validation. Common options: `--sims`, `--scoring` (ppr/half_ppr/standard), `--scoring-config path/to/custom.yaml`, `--detail` (floor/ceiling/stddev), `--format` (table/csv/json), `--output`, `--override "name.field=value"`, `--config path/to/season.yaml`. `--by-week` on season command outputs per-week breakdowns with week headers instead of season totals. `--output` auto-infers format from `.json`/`.csv` extension. Season config `season:` and `weeks:` keys are used as defaults when CLI flags are not explicitly provided; `scoring_format:` always overrides CLI `--scoring`. See `docs/CONFIG.md` for full configuration reference.
- **GameStateBucket**: Discretized game state (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups. Defined in `models/game_state.py`, used everywhere.
- **Distribution types**: `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel` in `models/distributions.py`. The sim engine samples from these.
- **Empirical distributions**: Play outcomes are stored as numpy arrays of historical values and sampled from directly (non-parametric).
- **MIN_BUCKET_PLAYS = 10**: Buckets with fewer than 10 plays fall back to team/league defaults.
- **GameState**: Mutable dataclass tracking game state (quarter, clock, possession, down, distance, yard_line, scores). `score_differential` is from possessing team's perspective.
- **yardline_100 convention**: 99=own 1, 75=own 25 (touchback), 50=midfield, 20=red zone, 1=goal line. TD when `yard_line - yards <= 0`. Safety when `yard_line - yards >= 100`.
- **Play resolution priority**: Scramble check (if roster) → sack check → interception check → normal pass outcome → home-field bonus. Fumble cancels TD. Penalty check post-play in game loop.
- **simulate_game()**: Main loop: 4th down decision → select play → resolve play → update box scores → update player stats → penalty check → handle outcome (safety/TD/turnover/yards) → clock → two-minute warning → quarter transitions. Optional `home_roster`/`away_roster` params enable player-level tracking.
- **TeamDistributions**: Bundles all distribution types needed per team. Passed to `simulate_game()` for home and away.
- **PlayerModel / TeamRoster**: Per-player usage rates (target_share, carry_share) and outcome distributions (catch_rate, yards distributions). `TeamRoster` provides weighted selection of passer/receiver/rusher. When rosters are provided, play resolution uses player-specific distributions instead of team-level ones.
- **PlayerBoxScore**: Per-player stats for one game (pass/rush/receiving). Tracked in `GameResult.player_stats` dict keyed by player_id.
- **player_builder**: Builds `PlayerModel` objects from PBP + roster data. `MIN_PLAYER_PLAYS = 5` for per-player yards distributions. Computes red zone shares (yardline_100 <= 20), air_yards_share, QB scramble_rate/scramble_yards_dist, and games_played. Optional `rookie_blend_games` param enables automatic archetype blending. `blend_with_archetype()` blends sparse player data with positional archetypes.
- **rookie_builder**: Generates `PlayerModel` for rookies using draft-capital-based archetypes (3 tiers by round).
- **Recency weighting**: `Preprocessor` methods accept `season_weights: dict[int, float]` to bias toward recent seasons via row replication.
- **Penalty modeling**: `check_penalty()` samples penalties from `PenaltyRates`; `apply_penalty()` creates penalty PlayResults. Wired into game_sim loop with `getattr` fallback for backward compatibility.
- **Home-field advantage**: `resolve_play(is_home=True)` gives 50% chance of +1 yard per play. `HOME_FIELD_YARDS_BONUS = 0.5`.
- **Two-minute warning**: `check_two_minute_warning()` snaps clock to 120s once per half in Q2/Q4. `GameState.two_min_warning_fired` resets at halftime.
- **Two-point conversions**: `attempt_pat()` returns scorer_id on 2PT success. `PlayerBoxScore.two_point_conversions` flows through `score_player()` via `config["two_point"]`.
- **Defensive TDs**: `_update_box_scores(rng=rng)` rolls for pick-six (~20% of INTs via `INT_RETURN_TD_RATE`) and fumble return TD (~10% via `FUMBLE_RETURN_TD_RATE`). `TeamBoxScore.defensive_tds` flows through `score_dst()` and `build_dst_projections()`.
- **Per-week availability**: `PlayerModel.weeks_missed: list[int]` stores specific weeks a player misses. `_filter_available()` in `player_selector.py` excludes them during those weeks. `GameState.week` tracks current week (0 = unset). Set via `games_missed` override.
- **Pace factor**: `TeamDistributions.pace_factor` (default 1.0) scales clock runoff via `_scale_clock_runoff()` in `play_resolver.py`. Set via `pace_plays_per_game` team override (baseline 65 plays/game).
- **Ambiguous match detection**: `PlayerResolver.resolve()` raises `AmbiguousMatchError(KeyError)` when 2+ players match within `AMBIGUITY_THRESHOLD=5` points. Exact ID/name lookups bypass the check.
- **Red Zone TD Gate**: `_red_zone_td_gate(yard_line, play_type, rng)` in `play_resolver.py` applies a per-play probability check when a play would score inside the 20. Constants `PASS_TD_GATE` (0.55-0.15) and `RUN_TD_GATE` (0.35-0.08) are calibrated so drive-level TD rates match NFL averages (~55% of RZ drives end in TD). Failed gates result in the player being tackled short. `_clamp_yards()` prevents exceeding yard_line; no additional RZ yards capping is needed.
- **Red Zone Catch Rate**: `PlayerOutcomes.red_zone_catch_rate` stores per-player RZ catch rate from PBP data (≥10 RZ targets) or `catch_rate * 0.92` fallback. Used in `_resolve_pass()` when `yard_line <= 20`. `MIN_RZ_TARGETS = 10` constant in `player_builder.py`. `RZ_CATCH_RATE_MODIFIER = 0.92` (real NFL RZ catch rates are ~92% of overall).
- **Catch Yards Boost**: `CATCH_YARDS_BOOST = 1` in `play_resolver.py` adds 1 yard to each sampled catch **outside the red zone only** to compensate for field-position clamping bias. Inside the 20, the boost is disabled to prevent TD inflation (the TD gate controls scoring probability). Per-player `receiving_yards_dist` arrays are field-position-independent, but `_clamp_yards()` truncates long catches near the goal line, systematically reducing yards/completion by ~1-2 yd vs the distribution mean.
- **QB Designed Run Separation**: `MIN_QB_CARRY_SHARE = 0.10` in `models/player.py` excludes pocket-passer QBs from the designed-run rusher pool. In `player_builder.py`, QB carry_share is computed from **designed runs only** (scramble carries are subtracted when `qb_scramble` data is available) to prevent double-counting — scrambles are already modeled separately in `_resolve_pass()` via the scramble_rate check.
- **Sack-Fumble Attribution**: In `game_sim.py`, sack-fumbles increment `qb.fumbles_lost` (fantasy football charges sack-fumbles to the QB). The condition checks `is_fumble and not is_complete and not is_interception` (no `not is_sack` exclusion).
- **RZ Receiving Yards**: `PlayerOutcomes.rz_receiving_yards_dist` stores per-player catch yards from PBP plays inside the 20 (≥5 RZ catches). Built in `player_builder.py`. Currently populated but not used in play resolution (field-position clamping + boost is the active approach).
- **QB Pass Fumble Rate**: `PlayerOutcomes.pass_fumble_rate` stores per-QB non-sack fumble rate (≥100 passes) or league average 0.0034. Checked pre-throw in `_resolve_pass()` after INT check, before receiver selection.
- **Scramble Rate**: Uses `qb_scramble` column from nflverse PBP to separate actual scrambles from designed runs. Falls back to all QB rushes if column is missing. `scramble_yards_dist` built from scramble-only plays.
- **GitHub Actions CI**: `.github/workflows/ci.yml` runs pytest on push/PR across Python 3.12/3.13/3.14 with uv caching. Statistical tests gated by PR label.

## Testing

- Tests mirror src structure: `tests/test_data/`, `tests/test_models/`, etc.
- Fixtures in `tests/conftest.py` provide sample PBP data (20 plays, KC/BUF)
- Tests use `unittest.mock.patch` to mock nflreadpy calls (no network in unit tests)
- Integration tests marked with `@pytest.mark.integration`
- Statistical tests marked with `@pytest.mark.statistical`

## Current State

- **Phase 1 (Data Pipeline)**: Complete — 67 tests
- **Phase 2 (Game State Machine)**: Complete — 80 tests (147 total)
- **Phase 3 (Player Models)**: Complete — 61 tests (208 total)
- **Phase 4 (Scoring + Config + CLI)**: Complete — 52 tests (260 total)
- **Phase 5 (Validation + Tuning)**: Complete — 31 tests (291 total)
- **Phase 6 (Overrides + Polish)**: Complete — 38 tests (329 total)
- **Phase 7A (Data + Engine Accuracy)**: Complete — 41 tests (370 total)
- **Phase 7B (Scoring + Config + CLI)**: Complete — 48 tests (418 total)
- **Phase 7C (Polish + Tests + CI)**: Complete — 87 tests (505 total)
- **Roster/Team Assignment Fix**: Complete — 21 tests (533 total). Separated player team assignment (current-season roster) from statistical profile (historical PBP). Fixes traded players, missing kickers, missing rookies, and retired player inclusion.
- **Red Zone Accuracy**: Complete — 45 tests (578 total). Red zone TD probability gates, per-player RZ catch rates, QB pre-throw fumble check, scramble rate fix using qb_scramble column.
- **Passing Yards Calibration**: Complete — 579 tests. Removed broken RZ yards blending (team distribution included incompletions/sacks, capping RZ completions to 1 yard ~45% of the time). Calibrated clock runoff for ~65 plays/team/game. Fixed fallback yards for players without personal distributions.
- **Passing Yards Boost**: Complete — 582 tests. Fixed wasted RNG call in `_resolve_pass()` (team_yards sample moved to fallback-only). Added `CATCH_YARDS_BOOST = 1` to compensate for field-position clamping bias (per-player distributions are field-position-independent; clamping near the goal line systematically reduces yards/completion by ~1-2 yd). Raised `RZ_CATCH_RATE_MODIFIER` from 0.85 to 0.92 (real NFL RZ completion rates are ~92% of overall). Added `rz_receiving_yards_dist` to PlayerOutcomes. Added passing diagnostic script (`scripts/validate_passing.py`). Added 3 statistical validation tests for completion rate, yards/completion, and pass yards/team. Top QB now projects ~4,000+ season passing yards (was ~3,500).
- **Post-Boost Bug Fixes**: Complete — 582 tests. Fixed three bugs: (1) QB carry_share double-counted scrambles — now subtracts scramble carries in `player_builder.py` + `MIN_QB_CARRY_SHARE=0.10` threshold excludes pocket passers from designed runs (Herbert 850→208 RuYd). (2) `CATCH_YARDS_BOOST` restricted to outside the red zone, preventing TD inflation (Goff 43.7→37.1 PaTD). (3) Sack-fumbles now attributed to QB's `fumbles_lost` in `game_sim.py` (QBs now show 1.3-4.2 FL/season, was 0.0-0.4).

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures
- Tests follow TDD: test first, then implement
