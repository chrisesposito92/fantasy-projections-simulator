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

# Run data validation (requires network)
uv run python scripts/validate_data.py

# Install dependencies
uv pip install -e ".[dev]"
```

## Architecture

The project is organized as a pipeline:

1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions
2. **Models** (`models/game_state.py`, `models/distributions.py`) — Shared data types used by both preprocessing and simulation
3. **Engine** (`engine/types.py`, `engine/play_caller.py`, `engine/play_resolver.py`, `engine/game_flow.py`, `engine/clock.py`, `engine/game_sim.py`, `engine/monte_carlo.py`) — Play-by-play game simulation with Monte Carlo runner
4. **Scoring** (Phase 4) — Config-driven fantasy point calculation
5. **Output** (Phase 4) — CLI, terminal tables, CSV/JSON export

## Key Patterns

- **GameStateBucket**: Discretized game state (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups. Defined in `models/game_state.py`, used everywhere.
- **Distribution types**: `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel` in `models/distributions.py`. The sim engine samples from these.
- **Empirical distributions**: Play outcomes are stored as numpy arrays of historical values and sampled from directly (non-parametric).
- **MIN_BUCKET_PLAYS = 10**: Buckets with fewer than 10 plays fall back to team/league defaults.
- **GameState**: Mutable dataclass tracking game state (quarter, clock, possession, down, distance, yard_line, scores). `score_differential` is from possessing team's perspective.
- **yardline_100 convention**: 99=own 1, 75=own 25 (touchback), 50=midfield, 20=red zone, 1=goal line. TD when `yard_line - yards <= 0`. Safety when `yard_line - yards >= 100`.
- **Play resolution priority**: Sack check → interception check → normal pass outcome. Fumble cancels TD.
- **simulate_game()**: Main loop: 4th down decision → select play → resolve play → update box scores → handle outcome (safety/TD/turnover/yards) → clock → quarter transitions.
- **TeamDistributions**: Bundles all distribution types needed per team. Passed to `simulate_game()` for home and away.

## Testing

- Tests mirror src structure: `tests/test_data/`, `tests/test_models/`, etc.
- Fixtures in `tests/conftest.py` provide sample PBP data (20 plays, KC/BUF)
- Tests use `unittest.mock.patch` to mock nflreadpy calls (no network in unit tests)
- Integration tests marked with `@pytest.mark.integration`
- Statistical tests marked with `@pytest.mark.statistical`

## Current State

- **Phase 1 (Data Pipeline)**: Complete — 67 tests
- **Phase 2 (Game State Machine)**: Complete — 80 tests (147 total)
- **Phases 3-6**: Not started. See design spec for full roadmap.

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures
- Tests follow TDD: test first, then implement
