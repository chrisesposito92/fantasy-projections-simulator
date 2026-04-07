# Parallel A/B Validation Harness

**Date:** 2026-04-07
**Status:** Approved
**Goal:** Utilize available CPU cores to get A/B validation runs completing in ~25-33% of current wall time.

## Problem

The A/B validation scripts (`validate_pff_signal.py`, `validate_weekly_signal.py`) run game simulations sequentially within each test season. On a 12+ core Mac with 48GB RAM, each Python process uses ~1.5 cores (GIL-bound) with 73% CPU idle. A full 2-season A/B run takes far longer than necessary.

Current architecture:
- Season-level parallelism already exists (ProcessPoolExecutor, 1 process per season)
- Within each season, ~288 games (18 weeks x 16 games) are simulated sequentially
- Each game: `build_game()` (~100-200ms, cache-dependent) + `run_simulations()` (~300-750ms, CPU-bound) + `build_player_projections()` (~5ms)
- The weekly harness doubles this -- PFF-off AND PFF-on per game

## Approach: Pre-build + ProcessPoolExecutor

Separate context-building (sequential, cache-friendly) from simulation (CPU-bound, embarrassingly parallel).

1. **Phase 1 -- Build contexts** (sequential): Iterate all weeks/games, call `build_game()` for each. GameContextBuilder's 3-layer cache is fully utilized.
2. **Phase 2 -- Simulate** (parallel): Submit pre-built game contexts to ProcessPoolExecutor workers that run `run_simulations()` + `build_player_projections()`.
3. **Phase 3 -- Aggregate** (sequential): Collect results, compute metrics.

### Why not fork-based or thread-based?

- **Fork:** macOS fork safety issues with numpy/polars, non-portable, fragile.
- **Threads:** GIL limits CPU-bound simulation speedup. `build_game()` PFF engines are Python-heavy.
- **ProcessPoolExecutor with serialization:** Safe, portable, deterministic. Serialization overhead for game contexts is modest (~10-50KB per game, using standard Python dataclass serialization via multiprocessing).

## Design

### New Module: `src/fantasy_sim/validation/parallel.py`

```python
@dataclass
class GameSpec:
    """Pre-built game context ready for parallel simulation."""
    game_id: str
    home_dists: TeamDistributions
    away_dists: TeamDistributions
    home_roster: TeamRoster | None
    away_roster: TeamRoster | None
    seed: int
    week: int
    metadata: dict  # arbitrary tags, e.g. {"arm": "off"} for weekly harness

@dataclass
class GameSimResult:
    """Result from one parallel simulation."""
    game_id: str
    projections: list[dict]  # from build_player_projections()
    metadata: dict            # passed through from GameSpec
```

**Functions:**

- `_simulate_worker(args: tuple) -> GameSimResult` -- module-level worker function (must be importable at module level for multiprocessing). Runs `run_simulations()` + `build_player_projections()` for one game. Returns projections (small), not full SimulationSummary (avoids serializing ~50 GameResult objects back).
- `simulate_games_parallel(specs, n_sims, scoring_config, max_workers=None, on_complete=None) -> list[GameSimResult]` -- main entry point. Adaptive worker default. Sequential fallback when `max_workers <= 1`.
- `default_max_workers(batch_size: int, num_concurrent: int = 1) -> int` -- computes `max(1, min((cpu_count - 2) // num_concurrent, batch_size))`.

**Key decisions:**
- Worker returns `projections` (list of dicts), not `SimulationSummary` -- cuts return serialization size ~100x.
- `metadata` dict enables the weekly harness to tag specs as `"off"/"on"` and match results without a separate paired API.
- Sequential fallback is a simple list comprehension -- same code path, no branching.

### Backtester Integration

Add `max_workers: int = 1` param to `Backtester.__init__()`. Restructure `run()` into three phases:

```
Phase 1 -- Build contexts (sequential, cache-friendly):
    for week in weeks:
        for game in week_games:
            context = build_game(...)
            specs.append(GameSpec(...))

Phase 2 -- Simulate (parallel):
    results = simulate_games_parallel(specs, n_sims, scoring_config, max_workers)

Phase 3 -- Aggregate (sequential, same logic as current):
    for result in results:
        for proj in result.projections:
            accumulate into projected_by_player_week, all_weekly_errors
```

Default `max_workers=1` preserves backward compatibility.

### validate_pff_signal.py Integration

`run_backtest_pair()` passes `max_workers` to each Backtester. Backtester handles parallelism internally.

Season-level parallelism interaction: each season's `run_backtest_pair` gets workers scaled by number of concurrent seasons:
```python
per_season_workers = default_max_workers(batch_size=288, num_concurrent=num_seasons)
```

On a 12-core Mac with 2 seasons: `(12 - 2) // 2 = 5` workers per season.

### validate_weekly_signal.py Integration

`run_weekly_comparison()` restructured into three phases:

```
Phase 1 -- Build all contexts (sequential):
    for wk in weeks:
        for game in week_games:
            off_context = builder_off.build_game(...)
            on_context = builder_on.build_game(...)
            specs.append(GameSpec(..., metadata={"arm": "off"}))
            specs.append(GameSpec(..., metadata={"arm": "on"}))
            # Capture matchup/coverage contexts (cheap, engines cached)

Phase 2 -- Simulate all (parallel):
    results = simulate_games_parallel(specs, n_sims, scoring_config, max_workers)

Phase 3 -- Pair and aggregate (sequential):
    Group results by game_id, match off+on pairs
    Build WeeklyPlayerRecords (same logic as current)
    Skip incomplete pairs (one arm failed)
```

All 576 specs (288 games x 2 arms) go into one pool for maximum load balancing.

### CLI

Both scripts get `--workers` flag:
```
--workers N    Worker processes for game simulation (default: auto)
               0 or omit = auto-detect based on CPU count
               1 = sequential (no multiprocessing)
```

### Progress Reporting

- Phase 1 (context building): per-week prints -- `[2024] Building contexts... Week 1/18`
- Phase 2 (simulation): periodic completion -- `[2024] Simulating... 120/288 games complete`

`simulate_games_parallel` accepts an optional `on_complete` callback.

### Error Handling

- Worker exceptions: `future.result()` wrapped in try/except. Failed games logged, result skipped. Matches current per-game skip behavior.
- Worker crashes (OOM): `BrokenProcessPool` caught at top level with message suggesting `--workers 1`.
- Keyboard interrupt: ProcessPoolExecutor context manager handles cleanup.

## Testing

New file: `tests/test_validation/test_parallel.py`

1. **Determinism** -- `workers=4` produces identical projections to `workers=1`. Same seeds, same numbers.
2. **Sequential fallback** -- `workers=1` runs without multiprocessing overhead.
3. **Adaptive worker count** -- `default_max_workers()` edge cases (batch_size=0, cpu_count=1).
4. **Error isolation** -- broken spec doesn't prevent other specs from completing.
5. **Metadata passthrough** -- metadata survives worker round-trip.
6. **Backtester parity** (integration) -- `Backtester(workers=1).run()` == `Backtester(workers=2).run()`.

## Files Changed

| File | Change |
|---|---|
| `src/fantasy_sim/validation/parallel.py` | **New** -- GameSpec, GameSimResult, simulate_games_parallel, default_max_workers |
| `src/fantasy_sim/validation/backtester.py` | **Modify** -- add max_workers, restructure run() into 3 phases |
| `scripts/validate_pff_signal.py` | **Modify** -- add --workers flag, pass to Backtester |
| `scripts/validate_weekly_signal.py` | **Modify** -- add --workers, restructure into 3 phases |
| `tests/test_validation/test_parallel.py` | **New** -- 6 tests |

## Constraints

- Must preserve deterministic results -- same seeds produce same projections regardless of worker count.
- `--workers 1` (or default for Backtester) is identical to current sequential behavior.
- No changes to ledger writing, scoring config, or existing season-level parallelism.
- GameContextBuilder caches remain sequential -- only simulation work is parallelized.

## Expected Outcome

~3-5x faster A/B validation runs on a 12-core Mac (simulations are ~60-70% of time, near-perfect parallelism on that portion). With 2 seasons x 5 workers: each season completes in ~20-33% of current wall time.
