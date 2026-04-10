# Handoff: A/B Validation Performance Optimization

## Problem Statement

A/B validation runs (`scripts/validate.py --sims 50`) take 15-20 minutes per run on a 14-core Apple Silicon Mac with 48GB RAM. Only one run can execute at a time, severely limiting sweep throughput (e.g., a 10-point parameter sweep takes 3+ hours).

## What Was Tried: Cloud Compute (Failed)

We attempted to offload validation runs to a GCP `c3-highcpu-88` (88 vCPUs, 176GB RAM, SSD) spot VM. Results:

1. **Nested `ProcessPoolExecutor` deadlock on Linux**: `validate.py` uses 3 layers of `ProcessPoolExecutor` (seasons -> build games -> simulate games). On Linux, the default `fork` start method causes inner pools to deadlock due to inherited locks from outer pools. macOS uses `spawn` by default, which is why it works locally.

2. **Fix applied**: Added `mp_context=multiprocessing.get_context("forkserver")` to both inner `ProcessPoolExecutor` calls in `src/fantasy_sim/validation/parallel.py` (lines ~141 and ~465). This fix resolved the deadlock — the VM successfully used all 88 cores. **This fix should be committed** as it's necessary for any Linux deployment.

3. **Still slow**: Even with parallelism working, the cloud VM was not faster than the Mac. Reasons:
   - Apple Silicon single-core performance is ~50% faster than cloud Intel Sapphire Rapids
   - Mac's NVMe SSD + unified memory architecture outperforms cloud SSD for the I/O-heavy build phase
   - The build phase (not simulation) is the bottleneck, and it's I/O + memory bound, not CPU bound

**Conclusion**: Throwing more cores at this workload doesn't help. The optimization needs to happen in the code itself.

## Architecture of the Bottleneck

The validation pipeline has two phases:

### Phase 1: Build Game Contexts (THE BOTTLENECK)
- `build_games_parallel()` in `src/fantasy_sim/validation/parallel.py`
- Builds ~272 game contexts per season (816 total for 3 seasons)
- Each worker initializes a `GameContextBuilder` (`src/fantasy_sim/data/game_context.py`) which loads:
  - PFF data via `PffLoader` (6 engines: matchup, tier, team_context, coverage, kicker, dst_baseline)
  - nflverse data via `DataLoader` (PBP parquet files, rosters, schedules, snap counts)
  - Weather, Vegas, Props, Usage, TD Tendency engines
- **Currently capped at `_MAX_BUILD_WORKERS = 4`** (line 439 of parallel.py) — was bumped to 14 for the VM test
- Each worker independently loads all PFF/nflverse data into memory — massive redundancy
- The `GameContextBuilder` has internal caches (`_pipeline_cache`, `_pbp_stats_cache`, `_player_models_cache`) but these are per-instance and don't share across workers

### Phase 2: Simulate Games (NOT the bottleneck)
- `simulate_games_parallel()` — pure CPU numpy Monte Carlo
- Scales well with cores, already parallelized properly
- Uses 28 workers per season on the Mac

## Key Optimization Opportunities

### 1. Reduce Per-Worker Data Loading (Highest Impact)
The biggest waste is that each of the 4 build workers independently initializes a `GameContextBuilder`, which loads the same PFF parquet files, creates the same engine instances, and builds the same pipeline caches. With `_MAX_BUILD_WORKERS = 4`, this means 4x redundant data loading.

**Possible approaches:**
- Pre-load shared data (PBP, PFF, rosters) once in the parent process, then pass pre-loaded dataframes to workers via shared memory or serialization
- Use a single `GameContextBuilder` instance with a thread pool instead of process pool (the build phase does polars/numpy work which releases the GIL)
- Pre-compute the `_ensure_pipeline()` output once and serialize it to workers

### 2. Cache Build Phase Output More Aggressively
Currently only the "bare baseline" Arm A results are cached (`results/cache/`). The build phase for Arm B (the test arm) is never cached because the config changes each run.

**But**: Much of the build phase work is config-independent:
- PBP data loading and preprocessing is the same regardless of PFF/weather/vegas config
- Roster loading is the same
- Pipeline output (play calling distributions, play outcomes) is the same

Caching the config-independent intermediate results and only recomputing the config-dependent parts (PFF adjustments, weather, vegas) would dramatically reduce build time.

### 3. Restructure Build to Separate Data Loading from Adjustment
Currently `GameContextBuilder.build_game()` does everything: load data, build distributions, apply PFF, apply weather, apply vegas, apply overrides, normalize. 

If this were split into:
1. `build_base_game()` — load data, build distributions (cacheable, same every run)
2. `apply_adjustments()` — apply PFF/weather/vegas/overrides (config-dependent, cheap)

Then step 1 could be cached/shared and only step 2 runs per-config.

### 4. Thread Pool for Build Phase
The build phase does mostly polars DataFrame operations (which release the GIL) and numpy array construction. A `ThreadPoolExecutor` instead of `ProcessPoolExecutor` for the build phase would:
- Share a single `GameContextBuilder` instance (with its caches) across all workers
- Avoid the overhead of process spawning and data serialization
- Avoid the `_MAX_BUILD_WORKERS` cap that exists to limit I/O contention from redundant loads

Caveat: Need to verify that `GameContextBuilder` is thread-safe (the caching dicts would need locks, or the cache could be pre-warmed before parallelizing).

### 5. Reduce PFF Engine Initialization Cost
Each `GameContextBuilder.__init__()` creates instances of: PffLoader, MatchupEngine, TalentStabilizer, TierEngine, TeamContextEngine, CoverageEngine, KickerEngine, DstBaselineEngine, WeatherEngine, VegasEngine, PropsEngine, UsageEngine, TdTendencyEngine.

Many of these load PFF parquet data during initialization or on first `.compute()` call. If the loaded data could be shared (e.g., via a shared `PffLoader` that pre-loads all facets), the per-worker init cost drops significantly.

## Files to Study

- `src/fantasy_sim/validation/parallel.py` — parallelization logic, worker functions, pool management
- `src/fantasy_sim/data/game_context.py` — `GameContextBuilder` class, the main build orchestrator
- `src/fantasy_sim/data/loader.py` — `DataLoader`, nflverse data with parquet caching
- `src/fantasy_sim/data/pipeline.py` — `DataPipeline`, builds distributions from PBP
- `src/fantasy_sim/data/pff/loader.py` — `PffLoader`, loads PFF parquet facets
- `src/fantasy_sim/data/player_builder.py` — player model assembly
- `scripts/validate.py` — the validation script, outer season-level parallelism

## Current Numbers

- **Typical run**: `--sims 50 --seasons 2022 2023 2024` = 15-20 min on Mac
- **Games per season**: ~272 (16 games/week × 17 weeks)
- **Total game contexts built**: ~816 (dual-arm = 1632 build_game calls)
- **Build workers**: 4 (capped by `_MAX_BUILD_WORKERS`)
- **Sim workers**: ~12 per season (auto from CPU count)
- **Tests**: 1248+ tests, `uv run pytest tests/ -v`
- **Build phase**: Estimated 70-80% of total runtime
- **Simulate phase**: Estimated 20-30% of total runtime

## Uncommitted Changes

1. `src/fantasy_sim/validation/parallel.py`:
   - Added `import multiprocessing`
   - Added `mp_context=multiprocessing.get_context("forkserver")` to both inner `ProcessPoolExecutor` calls (simulate pool ~line 141, build pool ~line 465)
   - `_MAX_BUILD_WORKERS` was changed from 4 to 14 on the VM — **local copy may still say 14, should be reset to 4 or made configurable**

## Constraints

- A/B tests are run manually by the user — agents must not run validation scripts
- All improvements must be validated through A/B harness before merging
- Must maintain 1248+ test suite; new features need tests
- Style: polars (not pandas), numpy, dataclasses, type hints, TDD
