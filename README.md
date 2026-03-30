# Fantasy Projections Simulator

Simulate NFL games play-by-play to project fantasy points for every player, every week, or a full season.

## What This Does

- Simulates NFL games using a state machine driven by historical play-by-play data from [nflverse](https://github.com/nflverse/nflreadpy)
- Runs Monte Carlo simulations (1,000+ per game) to produce statistical distributions — not just point estimates
- Outputs full stat lines (passing yards, rushing yards, receptions, TDs, etc.) alongside fantasy points
- Supports any scoring format (PPR, half-PPR, standard, custom) via YAML config
- Enables "what if" analysis via player and team overrides (`--override`, `--config`) with fuzzy name matching and automatic share redistribution

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

**Phase 4: Scoring + Config + CLI** — Complete (52 tests, 260 total)

- YAML config system with scoring preset inheritance (`_inherit` chains: PPR → half-PPR, standard)
- Fantasy scoring engine: `score_player()`, `score_dst()` (7 points-allowed brackets), `score_kicker()` (FG distance buckets)
- Projection builder: aggregates Monte Carlo results into mean stats + fantasy points, ranked by position
- Rich terminal tables for QB, RB, WR, TE, K, and DST projections
- CSV and JSON export
- Click CLI: `fantasy-sim demo` runs full pipeline end-to-end with synthetic data
- FG distance tracking added to engine (0-39, 40-49, 50+ yard buckets)

**Phase 5: Validation + Tuning** — Complete (31 tests, 291 total)

- GameContextBuilder: bridges real nflverse data to the simulation engine
- New CLI commands: `fantasy-sim week 1 --season 2024` and `fantasy-sim season --season 2024`
- Actual results loader: scores real player stats with config for backtest comparisons
- Accuracy metrics: Spearman rank correlation, MAE (weekly + season total), boom/bust calibration
- Backtesting framework: hold-out validation using only prior-season data (no leakage)
- Validation report with pass/fail indicators per metric against spec targets
- CLI: `fantasy-sim backtest --season 2024` runs full historical validation

**Phase 6: Overrides + Polish** — Complete (38 tests, 329 total)

- Override engine: `apply_player_override()` and `apply_team_override()` with proportional share redistribution
- Fuzzy player name resolver: resolves CLI names (e.g., "mahomes") to nflverse player IDs via thefuzz
- Override config parser: reads `season.yaml` files and `--override` CLI strings into structured OverrideSet
- CLI integration: `--override "name.field=value"` and `--config season.yaml` flags on demo, week, season commands
- Rich progress bars on `week` and `season` commands
- Helpful error messages for common issues (missing data, invalid weeks)
- 6 integration tests covering all Phase 6 spec requirements

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
│   ├── rookie_builder.py   # Rookie archetypes by draft capital
│   ├── game_context.py     # GameContextBuilder — real data → sim engine
│   └── actuals.py          # Load + score actual player stats for backtesting
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
├── config/
│   └── loader.py           # YAML config loading with _inherit inheritance
├── scoring/
│   ├── engine.py           # score_player(), score_dst(), score_kicker()
│   └── projections.py      # Aggregate sim results into ranked projections
├── output/
│   ├── tables.py           # Rich terminal tables (QB/RB/WR/TE/K/DST)
│   └── export.py           # CSV and JSON file export
├── overrides/
│   ├── engine.py           # apply_player_override(), apply_team_override(), redistribution
│   ├── resolver.py         # PlayerResolver — fuzzy name → player_id matching
│   └── parser.py           # OverrideSet, parse_override_config(), parse_cli_override()
├── cli.py                  # Click CLI entry point (demo, week, season, backtest)
└── validation/
    ├── metrics.py          # Spearman correlation, MAE, boom/bust calibration
    ├── backtester.py       # Hold-out backtest runner (no data leakage)
    └── report.py           # Rich-formatted validation report
```

## Tech Stack

- **Python 3.12+** with uv for package management
- **nflreadpy** — NFL play-by-play data from nflverse
- **polars** — Fast DataFrames for data processing
- **numpy/scipy** — Numerical simulation and distribution fitting
- **thefuzz** — Fuzzy string matching for player name resolution
- **rich** — Progress bars and terminal formatting
- **pytest** — Testing with pytest-xdist and hypothesis

## Quick Simulation

### CLI (easiest)

```bash
# Demo with synthetic data (no network needed)
uv run fantasy-sim demo --sims 100

# Change scoring format
uv run fantasy-sim demo --sims 100 --scoring half_ppr

# Export to file
uv run fantasy-sim demo --sims 100 --format csv --output projections.csv
uv run fantasy-sim demo --sims 100 --format json --output projections.json

# Simulate a real NFL week (requires network for nflverse data)
uv run fantasy-sim week 1 --season 2024 --sims 100

# Simulate a full season
uv run fantasy-sim season --season 2024 --sims 50

# Backtest against historical actuals
uv run fantasy-sim backtest --season 2024 --sims 50

# Override player stats ("what if" scenarios)
uv run fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.30"
uv run fantasy-sim week 1 --season 2024 --sims 100 --override "mahomes.games_played=14"

# Load overrides from config file
uv run fantasy-sim week 1 --season 2024 --config config/season.example.yaml
```

### Python API

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
- [Phase 5 Plan](docs/superpowers/plans/2026-03-29-phase5-validation-tuning.md)
- [Phase 6 Plan](docs/superpowers/plans/2026-03-30-phase6-overrides-polish.md)
- [Phase 7A Plan](docs/superpowers/plans/2026-03-30-phase7a-data-engine-accuracy.md)
- [Phase 7B Plan](docs/superpowers/plans/2026-03-30-phase7b-scoring-config-cli.md)
- [Phase 7C Plan](docs/superpowers/plans/2026-03-30-phase7c-polish-tests-ci.md)
