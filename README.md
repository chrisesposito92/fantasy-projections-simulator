# Fantasy Projections Simulator

Simulate NFL games play-by-play to project fantasy points for every player, every week, or a full season.

## What This Does

- Simulates NFL games using a state machine driven by historical play-by-play data from [nflverse](https://github.com/nflverse/nflreadpy)
- Runs Monte Carlo simulations (1,000+ per game) to produce statistical distributions — not just point estimates
- Outputs full stat lines (passing yards, rushing yards, receptions, TDs, etc.) alongside fantasy points
- Supports any scoring format (PPR, half-PPR, standard, custom) via YAML config
- Enables "what if" analysis via player and team overrides (target share, games missed, pace, pass rate)

## Project Status

**Phase 1: Data Pipeline** — Complete (67 tests passing)

- nflreadpy data loading with filesystem caching (parquet)
- Play-calling distributions (P(run|state), P(pass|state)) per team
- Play outcome distributions (yards gained by play type and game state)
- Turnover/sack rates per team
- Kicking model (FG probability by distance, XP rate)
- Drive start model (kickoff return/touchback distributions)
- Game state bucketing system (shared between preprocessing and sim engine)

**Upcoming:**
- Phase 2: Game State Machine (play-by-play simulation loop)
- Phase 3: Player Models (per-player usage and outcome distributions)
- Phase 4: Scoring + Config + CLI
- Phase 5: Validation + Tuning (backtest against 2023/2024 seasons)
- Phase 6: Overrides + Polish

## Quick Start

```bash
# Clone and set up
git clone <repo-url>
cd fantasy-projections-simulator
uv venv
uv pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v

# Run integration validation (requires network, downloads ~500MB of nflverse data)
uv run python scripts/validate_data.py
```

## Project Structure

```
src/fantasy_sim/
├── data/
│   ├── loader.py           # nflreadpy wrapper with parquet caching
│   ├── preprocessor.py     # Distribution fitting from historical PBP
│   └── pipeline.py         # Orchestrates loading + preprocessing
├── models/
│   ├── game_state.py       # GameStateBucket + bucketing functions
│   └── distributions.py    # Distribution dataclasses (PlayCallingDist, etc.)
├── engine/                 # (Phase 2) Game simulation state machine
├── scoring/                # (Phase 4) Config-driven fantasy scoring
├── config/                 # (Phase 4) YAML config loading
├── output/                 # (Phase 4) Terminal tables, CSV/JSON export
└── validation/             # (Phase 5) Backtesting framework
```

## Tech Stack

- **Python 3.12+** with uv for package management
- **nflreadpy** — NFL play-by-play data from nflverse
- **polars** — Fast DataFrames for data processing
- **numpy/scipy** — Numerical simulation and distribution fitting
- **pytest** — Testing with pytest-xdist and hypothesis

## Docs

- [Design Spec](docs/superpowers/specs/2026-03-29-fantasy-projections-simulator-design.md)
- [Phase 1 Plan](docs/superpowers/plans/2026-03-29-phase1-data-pipeline.md)
