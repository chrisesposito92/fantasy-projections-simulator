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

# Simulate real NFL week/season (requires network)
uv run fantasy-sim week 1 --season 2024 --sims 100
uv run fantasy-sim season --season 2024 --sims 50

# Backtest against historical actuals
uv run fantasy-sim backtest --season 2024 --sims 50

# Override player/team stats
uv run fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.30"
uv run fantasy-sim week 1 --season 2024 --override "mahomes.games_played=14"
uv run fantasy-sim week 1 --season 2024 --config config/season.example.yaml
```

## Architecture

The project is organized as a pipeline:

1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`, `data/player_builder.py`, `data/rookie_builder.py`, `data/game_context.py`, `data/actuals.py`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions, builds per-player models from PBP data, generates rookie archetypes, bridges real data to sim engine, loads actual player stats for backtesting
2. **Models** (`models/game_state.py`, `models/distributions.py`, `models/player.py`) — Shared data types used by both preprocessing and simulation, including player usage/outcome models and team rosters
3. **Engine** (`engine/types.py`, `engine/play_caller.py`, `engine/play_resolver.py`, `engine/player_selector.py`, `engine/game_flow.py`, `engine/clock.py`, `engine/game_sim.py`, `engine/monte_carlo.py`) — Play-by-play game simulation with player-level tracking and Monte Carlo runner
4. **Config** (`config/loader.py`, `config/defaults.yaml`) — YAML config loading with `_inherit` scoring preset inheritance (PPR, half-PPR, standard)
5. **Scoring** (`scoring/engine.py`, `scoring/projections.py`) — Config-driven fantasy point calculation for players, DST, and kickers; projection builder aggregates sim results into ranked projections
6. **Output** (`output/tables.py`, `output/export.py`) — Rich terminal tables by position, CSV/JSON export
7. **Validation** (`validation/metrics.py`, `validation/backtester.py`, `validation/report.py`) — Accuracy metrics (Spearman, MAE, boom/bust calibration), hold-out backtesting framework, formatted validation reports
8. **Overrides** (`overrides/engine.py`, `overrides/resolver.py`, `overrides/parser.py`) — Player/team override engine with proportional share redistribution, fuzzy name matching, YAML + CLI parsing
9. **CLI** (`cli.py`) — Click-based CLI with `demo`, `week`, `season`, `backtest` commands, `--override` and `--config` flags, rich progress bars

## Key Patterns

- **ConfigLoader**: `load_config()` loads YAML, `resolve_scoring()` resolves `_inherit` chains. `load_defaults()` loads `config/defaults.yaml`. Scoring presets: PPR (base), half_ppr (_inherit: ppr, reception: 0.5), standard (_inherit: ppr, reception: 0).
- **ScoringEngine**: `score_player(box, config)` for QB/RB/WR/TE, `score_dst(box, opponent_score, config)` with 7 points-allowed brackets, `score_kicker(box, config)` with FG distance buckets.
- **ProjectionBuilder**: `build_player_projections(games, config)` aggregates PlayerBoxScore across sims into mean stats + fpts, sorted by fpts. `build_dst_projections(games, config, team_map)` for DST.
- **GameContextBuilder**: `build_game(home, away, seasons)` constructs `TeamDistributions` + `TeamRoster` per team from real nflverse data. Caches pipeline output across calls. Falls back to league-average distributions for unknown teams.
- **ActualPlayerWeek**: Loads real player stats, scores with config. Used by backtester for comparison.
- **Backtester**: `Backtester(test_season, n_sims, num_training_seasons)` runs hold-out validation. `run(scoring_config)` returns `BacktestResult` with `passes_targets()` method. Targets: rank_corr > 0.80, weekly_mae < 6.0, season_mae < 25, calibration < 0.10.
- **OverrideEngine**: `apply_player_override(roster, player_id, overrides)` applies usage/outcome/meta overrides; automatically triggers `redistribute_target_shares()` or `redistribute_carry_shares()` for share fields. `apply_team_override(dists, overrides)` modifies PlayCallingDist and TurnoverRates. Both raise on unknown fields.
- **PlayerResolver**: `PlayerResolver(rosters).resolve(query)` resolves names to player_id via exact ID → exact name → underscore conversion → fuzzy match (thefuzz, MIN_MATCH_SCORE=70).
- **OverrideParser**: `parse_override_config(path)` reads season.yaml into `OverrideSet`. `parse_cli_override("name.field=value")` parses CLI strings. `_build_overrides()` in CLI merges config + CLI overrides (CLI takes precedence).
- **CLI**: `fantasy-sim demo` runs synthetic simulations. `fantasy-sim week N --season YYYY` simulates a real NFL week. `fantasy-sim season --season YYYY` simulates a full season. `fantasy-sim backtest --season YYYY` runs historical validation. Common options: `--sims`, `--scoring` (ppr/half_ppr/standard), `--format` (table/csv/json), `--output`, `--override "name.field=value"`, `--config path/to/season.yaml`.
- **GameStateBucket**: Discretized game state (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups. Defined in `models/game_state.py`, used everywhere.
- **Distribution types**: `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel` in `models/distributions.py`. The sim engine samples from these.
- **Empirical distributions**: Play outcomes are stored as numpy arrays of historical values and sampled from directly (non-parametric).
- **MIN_BUCKET_PLAYS = 10**: Buckets with fewer than 10 plays fall back to team/league defaults.
- **GameState**: Mutable dataclass tracking game state (quarter, clock, possession, down, distance, yard_line, scores). `score_differential` is from possessing team's perspective.
- **yardline_100 convention**: 99=own 1, 75=own 25 (touchback), 50=midfield, 20=red zone, 1=goal line. TD when `yard_line - yards <= 0`. Safety when `yard_line - yards >= 100`.
- **Play resolution priority**: Scramble check (if roster) → sack check → interception check → normal pass outcome. Fumble cancels TD.
- **simulate_game()**: Main loop: 4th down decision → select play → resolve play → update box scores → update player stats → handle outcome (safety/TD/turnover/yards) → clock → quarter transitions. Optional `home_roster`/`away_roster` params enable player-level tracking.
- **TeamDistributions**: Bundles all distribution types needed per team. Passed to `simulate_game()` for home and away.
- **PlayerModel / TeamRoster**: Per-player usage rates (target_share, carry_share) and outcome distributions (catch_rate, yards distributions). `TeamRoster` provides weighted selection of passer/receiver/rusher. When rosters are provided, play resolution uses player-specific distributions instead of team-level ones.
- **PlayerBoxScore**: Per-player stats for one game (pass/rush/receiving). Tracked in `GameResult.player_stats` dict keyed by player_id.
- **player_builder**: Builds `PlayerModel` objects from PBP + roster data. `MIN_PLAYER_PLAYS = 5` for per-player yards distributions.
- **rookie_builder**: Generates `PlayerModel` for rookies using draft-capital-based archetypes (3 tiers by round).

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

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures
- Tests follow TDD: test first, then implement
