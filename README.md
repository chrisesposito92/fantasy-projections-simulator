# Fantasy Projections Simulator

Simulate NFL games play-by-play to project fantasy points for every player, every week, or a full season.

## What This Does

- Simulates NFL games using a state machine driven by historical play-by-play data from [nflverse](https://github.com/nflverse/nflreadpy)
- Runs Monte Carlo simulations (1,000+ per game) to produce statistical distributions — not just point estimates
- Outputs full stat lines (passing yards, rushing yards, receptions, TDs, etc.) alongside fantasy points
- Supports any scoring format (PPR, half-PPR, standard, custom) via YAML config
- Enables "what if" analysis via player and team overrides (target share, games missed, pace, pass rate)

## Project Status

**Phase 1: Data Pipeline** — Complete (67 tests)

- nflreadpy data loading with filesystem caching (parquet)
- Play-calling distributions (P(run|state), P(pass|state)) per team
- Play outcome distributions (yards gained by play type and game state)
- Turnover/sack rates per team
- Kicking model (FG probability by distance, XP rate)
- Drive start model (kickoff return/touchback distributions)
- Game state bucketing system (shared between preprocessing and sim engine)

**Phase 2: Game State Machine** — Complete (80 tests, 147 total)

- Core engine types: `GameState`, `TeamBoxScore`, `PlayResult`, `GameResult`, `TeamDistributions`
- Play caller with 4th down decisions (punt/FG/go-for-it)
- Play resolver for pass and run outcomes (sacks, turnovers, TDs, safeties)
- Game flow: scoring, possession changes, kickoffs, punts, FG attempts, PAT/2PT
- Clock management with quarter/halftime/overtime transitions
- Full game simulation loop (`simulate_game()`) with OT walk-off support
- Monte Carlo runner (`run_simulations()`) with aggregate statistics
- Statistical validation (2000+ game tests produce NFL-realistic averages)

**Phase 3: Player Models** — Complete (61 tests, 208 total)

- Per-player data types: `PlayerModel`, `PlayerUsage`, `PlayerOutcomes`, `TeamRoster`
- Player builder: constructs player models from historical PBP + roster data
- Rookie archetype system: draft-capital-based models for rookies without PBP history
- Player selector: weighted selection of passer/receiver/rusher from roster
- Player-aware play resolution: uses player-specific catch rates and yards distributions
- Per-player box scores tracked through game simulation and Monte Carlo runner
- Statistical validation (500+ sims produce plausible player-level stats)

**Upcoming:**
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
│   ├── pipeline.py         # Orchestrates loading + preprocessing
│   ├── player_builder.py   # Build PlayerModels from PBP + roster data
│   └── rookie_builder.py   # Rookie archetypes by draft capital
├── models/
│   ├── game_state.py       # GameStateBucket + bucketing functions
│   ├── distributions.py    # Distribution dataclasses (PlayCallingDist, etc.)
│   └── player.py           # PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster
├── engine/
│   ├── types.py            # GameState, TeamBoxScore, PlayerBoxScore, PlayResult, GameResult
│   ├── play_caller.py      # Play type selection + 4th down decisions
│   ├── play_resolver.py    # Pass/run outcome resolution (player-aware)
│   ├── player_selector.py  # Select passer/receiver/rusher from roster
│   ├── game_flow.py        # Scoring, possession, kickoff, punt, FG, PAT
│   ├── clock.py            # Clock runoff + quarter/OT transitions
│   ├── game_sim.py         # simulate_game() main loop with player tracking
│   └── monte_carlo.py      # run_simulations() + per-player aggregation
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

## Quick Simulation

```python
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
# ... set up TeamDistributions for home and away teams ...
results = run_simulations(home_dists, away_dists, n_sims=1000, seed=42)
print(results.summary())
```

## Docs

- [Design Spec](docs/superpowers/specs/2026-03-29-fantasy-projections-simulator-design.md)
- [Phase 1 Plan](docs/superpowers/plans/2026-03-29-phase1-data-pipeline.md)
- [Phase 2 Plan](docs/superpowers/plans/2026-03-29-phase2-game-state-machine.md)
- [Phase 3 Plan](docs/superpowers/plans/2026-03-29-phase3-player-models.md)
- [Phase 4 Plan](docs/superpowers/plans/2026-03-29-phase4-scoring-config-cli.md)
