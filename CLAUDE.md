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
uv run pytest tests/test_data/test_preprocessor.py -v

# Run integration validation (requires network)
uv run python scripts/validate_data.py

# Install dependencies
uv pip install -e ".[dev]"
```

## Architecture

The project is organized as a pipeline:

1. **Data Layer** (`data/loader.py`, `data/preprocessor.py`, `data/pipeline.py`) — Fetches nflverse data, caches as parquet, preprocesses into probability distributions
2. **Models** (`models/game_state.py`, `models/distributions.py`) — Shared data types used by both preprocessing and simulation
3. **Engine** (Phase 2) — Game simulation state machine
4. **Scoring** (Phase 4) — Config-driven fantasy point calculation
5. **Output** (Phase 4) — CLI, terminal tables, CSV/JSON export

## Key Patterns

- **GameStateBucket**: Discretized game state (down, distance, score_diff, quarter, yard_zone) used as dict keys for probability lookups. Defined in `models/game_state.py`, used everywhere.
- **Distribution types**: `PlayCallingDist`, `PlayOutcomeDist`, `TurnoverRates`, `KickingModel`, `DriveStartModel` in `models/distributions.py`. The sim engine samples from these.
- **Empirical distributions**: Play outcomes are stored as numpy arrays of historical values and sampled from directly (non-parametric).
- **MIN_BUCKET_PLAYS = 10**: Buckets with fewer than 10 plays fall back to team/league defaults.

## Testing

- Tests mirror src structure: `tests/test_data/`, `tests/test_models/`, etc.
- Fixtures in `tests/conftest.py` provide sample PBP data (20 plays, KC/BUF)
- Tests use `unittest.mock.patch` to mock nflreadpy calls (no network in unit tests)
- Integration tests marked with `@pytest.mark.integration`
- Statistical tests marked with `@pytest.mark.statistical`

## Current State

- **Branch**: `phase1/data-pipeline`
- **Phase 1 (Data Pipeline)**: Complete — 67 tests passing
- **Phases 2-6**: Not started. See design spec for full roadmap.

## Style

- Use polars, not pandas
- Use numpy for arrays and random sampling
- Dataclasses for data types (frozen when used as dict keys)
- Type hints on all function signatures
- Tests follow TDD: test first, then implement
