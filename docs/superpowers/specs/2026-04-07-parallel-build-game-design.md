# Parallelize build_game() in Validation Harness

**Date**: 2026-04-07
**Status**: Approved

## Problem

The A/B validation harness (PR #23) restructured into 3 phases:

1. **Phase 1**: Build game contexts sequentially via `GameContextBuilder.build_game()`
2. **Phase 2**: Simulate games in parallel via `ProcessPoolExecutor`
3. **Phase 3**: Aggregate results

Phase 2 parallelism works well, but Phase 1 dominates runtime at ~92% of total
time when all PFF layers are enabled. Real numbers from `--mode all --sims 50`
on a 12-core Mac:

- PFF-OFF arm: ~117s for 288 games (~0.4s/game)
- PFF-ON arm: ~1,705s for 288 games (~5.9s/game -- 6 PFF layers)
- Total wall time: ~1,829s

**Goal**: Reduce Phase 1 from ~1700s to ~400-500s by parallelizing
`build_game()` calls across games within each week.

## Approach: ProcessPoolExecutor with Worker-Local Builders

Each worker process owns its own `GameContextBuilder` instance, created once
via a pool initializer and reused across all games assigned to that worker.
Workers warm their caches on the first game and reuse them for all subsequent
games.

### Why not threading?

Python 3.14.3 is running with GIL enabled (`Py_GIL_DISABLED: 0`).
`ThreadPoolExecutor` would not provide true parallelism for the CPU-bound PFF
computation. Polars releases the GIL for its internal operations, but the
Python orchestration logic between Polars calls holds it. Realistic thread
speedup: 1.5-2x -- insufficient for the 3-4x target.

### Why not batch vectorization?

Refactoring all 6 PFF engines to support batch `compute_week()` methods would
target the root cause (redundant per-game DataFrame operations), but:
- Uncertain speedup without profiling (depends on redundant vs per-game work ratio)
- TierEngine has significant per-player logic that can't be vectorized across games
- Largest code change of any approach

Process pool gives guaranteed, predictable speedup proportional to core count.
Batch optimizations can be layered on later if more speed is needed.

## Design

### Prerequisite: KickingModel Defensive Copy

`build_team_distributions()` assigns `pipeline_output["kicking"]` as a shared
reference across all games. When `_apply_weather()` mutates `fg_make_rate` or
`xp_rate` in-place (and kicker engine doesn't replace it), later games see
stale values.

**Fix**: `copy.deepcopy(pipeline_output["kicking"])` in `build_team_distributions()`.

`play_outcomes` and `drive_start` are also shared references but never mutated --
no copy needed. `KickingModel` is a small dataclass (one dict + one float) --
negligible cost.

**Location**: `src/fantasy_sim/data/game_context.py`, `build_team_distributions()` return.

### Worker Functions

Module-level functions in `parallel.py` for `ProcessPoolExecutor`:

**Worker state**: A module-level `_worker_builders` dict holds one or two
`GameContextBuilder` instances per worker process. Initialized once via pool
`initializer`.

**Single-arm worker** (Backtester use case):
- `_init_build_worker_single(cache_dir, pff_config, weather_config)` -- creates
  one builder per worker
- `_build_game_worker_single(args)` -- builds one game, returns dict with
  dists + rosters

**Dual-arm worker** (weekly validation use case):
- `_init_build_worker(cache_dir, pff_config, weather_config)` -- creates two
  builders per worker: `"off"` (no PFF/weather) and `"on"` (with PFF/weather)
- `_build_game_worker(args)` -- builds both off+on contexts for one game,
  captures matchup/coverage auxiliary data from the `"on"` builder's engines,
  returns dict with both arms' results + aux data

**Error handling**: Workers catch exceptions and return
`{"status": "error", "game_id": ..., "error": ...}` rather than raising. This
prevents `BrokenExecutor` cascades and matches the current sequential behavior
(log and skip failed games). `BrokenExecutor` is caught at the pool level with
a message directing users to `--workers 1`.

### build_games_parallel()

New public function in `parallel.py`:

```python
def build_games_parallel(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config: PffConfig | None = None,
    weather_config: WeatherConfig | None = None,
    max_workers: int | None = None,
    dual_arm: bool = False,
    on_complete: Callable[[int, int], None] | None = None,
) -> list[dict]:
```

- `game_args`: list of `(home, away, training_seasons, target_season, week, game_id, seed)` tuples
- `dual_arm`: `False` for Backtester (single builder), `True` for weekly validation (off+on builders)
- `max_workers`: `None`/`0` = auto-detect, `1` = sequential fallback
- `on_complete`: progress callback matching `simulate_games_parallel` signature
- Returns results sorted by `(week, game_id)` for deterministic ordering

Sequential fallback (`max_workers <= 1`): calls `_build_games_sequential()` which
creates its own builder(s) from the same config args and processes games in a
loop. This ensures the sequential path uses the exact same code as workers
(own builder instance, same cache warming sequence) -- not a separate code path
that could diverge.

### Consumer Integration

All three validation entry points use the new infrastructure:

**`backtester.py` -- `Backtester.run()`**:
- Phase 1 replaces the nested `for wk / for game` loop with a single
  `build_games_parallel()` call (`dual_arm=False`)
- Assembles `GameSpec` list from results
- Phase 2 (simulate) and Phase 3 (aggregate) unchanged

**`validate_weekly_signal.py` -- `run_weekly_comparison()`**:
- Phase 1 replaces the inline loop with `build_games_parallel(dual_arm=True)`
- Assembles both off+on `GameSpec` pairs and `game_aux` dict from results
- Phase 2 and Phase 3 unchanged

**`validate_pff_signal.py`**:
- Uses `Backtester.run()` -- gets Phase 1 parallelism for free via the
  `Backtester` changes above

### Config Serialization

`PffConfig`, `WeatherConfig`, and all sub-configs are dataclasses -- they
serialize cleanly for cross-process transfer. `Path` objects transfer fine.
`PffLoader` is created fresh inside each worker's `GameContextBuilder.__init__()`,
reading from the same parquet files (concurrent reads are safe -- read-only,
OS-level file locking).

## Determinism

**Seeds**: Derived from `zlib.crc32(game_id)`, not processing order. Same game
always gets same seed regardless of worker assignment.

**PFF computation**: Pure functions of (team, season, max_week, cached data).
Same inputs produce same factors.

**Cache warming**: Each worker warms caches independently on its first game.
Cache contents are deterministic (same `training_seasons` -> same pipeline output).

**Result ordering**: `as_completed()` returns in arbitrary order.
`build_games_parallel()` sorts results by `(week, game_id)` before returning.

**Floating point**: Identical computation paths in each worker -- no operation
reordering vs sequential. Bit-for-bit identical results.

## Estimated Performance

On a 12-core Mac with 5 workers per season (2 seasons running concurrently):

| Phase | Current | Parallel | Speedup |
|-------|---------|----------|---------|
| Phase 1 (PFF-ON) | ~1,705s | ~342s | ~5x |
| Phase 1 (PFF-OFF) | ~117s | ~50s | ~2x |
| Phase 2 (simulate) | ~7s | ~7s | -- |
| **Total** | **~1,829s** | **~399s** | **~4.6x** |

Worker cache warming (~10s) is one-time and parallel. Player models cache
re-warms per week (~1-2s) -- included in estimate. Memory: ~1-2GB per worker x
5 workers = 5-10GB additional.

## Files Changed

| File | Change |
|------|--------|
| `src/fantasy_sim/data/game_context.py` | KickingModel defensive copy (1 line) |
| `src/fantasy_sim/validation/parallel.py` | Worker functions + `build_games_parallel()` (~80 lines) |
| `src/fantasy_sim/validation/backtester.py` | Phase 1 -> `build_games_parallel()` (~15 lines) |
| `scripts/validate_weekly_signal.py` | Phase 1 -> `build_games_parallel()` (~25 lines) |
| `tests/test_validation/test_parallel.py` | 8 new tests (~120 lines) |

No changes to PFF engines, weather engine, player_builder, DataLoader, or CLI.

## Testing

| Test | Validates |
|------|-----------|
| `test_build_games_parallel_matches_sequential` | Core correctness: workers=4 produces identical results to workers=1 |
| `test_build_games_parallel_workers_1_fallback` | Sequential path matches direct `build_game()` calls |
| `test_build_games_parallel_empty_input` | Empty game list returns empty results |
| `test_build_games_parallel_single_game` | One game with workers=4 works correctly |
| `test_build_games_parallel_dual_arm` | dual_arm=True produces both off+on contexts with matchup_aux |
| `test_build_games_parallel_error_handling` | Bad game skipped, others succeed |
| `test_kicking_model_isolation` | Two games don't see each other's weather mutations on KickingModel |
| `test_determinism_across_runs` | Same inputs + same workers -> bit-identical outputs |

Tests use existing `conftest.py` fixtures (KC/BUF PBP data) with mocked
nflreadpy (no network calls).

## Future Optimization

If more speedup is needed beyond the ~4-5x from process pool parallelism,
batch-vectorized PFF engine computation can be layered on:

- Add `compute_week()` methods to MatchupEngine and TeamContextEngine
  (most DataFrame-heavy engines)
- Eliminates redundant filter/groupby/zscore operations across games in the
  same week
- Workers would do less redundant work -- estimated additional 1.5-2x
