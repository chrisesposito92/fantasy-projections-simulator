# Validation Redesign: Unified A/B Testing Script

**Date**: 2026-04-08
**Status**: Design approved, pending implementation

## Problem

The current A/B validation system has two scripts (`validate_pff_signal.py` and `validate_weekly_signal.py`) with a combined ~1,700 lines. Each maintains a `_build_pff_config()` function with a ~160-line if/elif chain mapping 25+ mode strings to engine configurations. Adding a new engine means adding mode strings to both scripts, duplicating override logic, and maintaining separate ledgers with different schemas.

The workflow is also inefficient: the season-level script runs all baseline arms sequentially before starting any engine-on arms, and neither script caches the bare baseline even though it's identical across runs.

## Design

### CLI Interface

One script: `scripts/validate.py`. Replaces both existing scripts.

```bash
# Basic: bare baseline vs your defaults.yaml
uv run python scripts/validate.py --sims 50 --label "baseline-v1"

# Test a change: bare vs defaults + NGS enabled
uv run python scripts/validate.py --sims 50 --set usage.ngs.enabled=true --label "test-ngs"

# Marginal impact: defaults vs defaults + NGS
uv run python scripts/validate.py --sims 50 --baseline defaults \
    --set usage.ngs.enabled=true --label "ngs-marginal"

# Granularity control
uv run python scripts/validate.py --sims 50 --granularity weekly
uv run python scripts/validate.py --sims 50 --granularity season
uv run python scripts/validate.py --sims 50 --granularity both    # default

# Ledger
uv run python scripts/validate.py --show-ledger

# Other flags
--seasons 2022 2023 2024    # default
--training-years 4          # default
--scoring ppr               # default (ppr/half_ppr/standard)
--workers 0                 # 0=auto, 1=sequential
--positions QB RB WR TE     # default
--no-cache                  # force fresh bare baseline (skip cache)
```

**Key changes from today:**
- No `--mode` flag. The entire mode system is eliminated.
- `--set key=value` (repeatable) replaces both `--mode` and `--config-override`.
- `--baseline bare|defaults` controls Arm A (default: `bare`).
- `--granularity season|weekly|both` replaces choosing between two scripts (default: `both`).
- No automated verdict (PASS/SOFT_PASS/FAIL). Just numbers.

### Config Resolution

**Bare config**: A hardcoded dict mirroring `defaults.yaml` structure with every `enabled` flag set to `false`. This is the "no engines" baseline.

**Arm A resolution:**
- `--baseline bare` (default): Use the bare config.
- `--baseline defaults`: Load `defaults.yaml` as-is (no `--set` overrides applied).

**Arm B resolution:**
1. Load `defaults.yaml` via existing `load_defaults()`.
2. Deep-copy the config dict.
3. Apply `--set` overrides via dot-notation patcher.
4. Build engine configs from the resulting dict.

**Dot-notation patcher:**

```python
def apply_overrides(config: dict, overrides: list[str]) -> dict:
    """Apply 'pff.matchup.enabled=false' style overrides to a config dict."""
    for override in overrides:
        key_path, value = override.split("=", 1)
        keys = key_path.split(".")
        target = config
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = _parse_value(value)  # handles bool/int/float/str
    return config
```

Value parsing: `"true"`/`"false"` → bool, numeric strings → int/float, everything else → str.

**Engine config builders** are simplified. Instead of `_build_pff_config(mode)` with 20 branches, a single function reads the resolved config dict:

```python
def build_pff_config(pff_dict: dict) -> PffConfig:
    """Build PffConfig from a resolved config dict section."""
    # Reads enabled flags directly from the dict — one path, no branching.
```

Same pattern for weather, vegas, props, usage configs. Each builder takes its section of the config dict and returns the corresponding config dataclass.

### Execution Pipeline

**Step 1: Resolve configs** — Build Arm A and Arm B config dicts as described above.

**Step 2: Check bare cache** (when `--baseline bare`)
- Cache location: `results/cache/bare_{season}_{sims}_{scoring}_{training_years}.json`
- If cache hit for all requested seasons → skip Arm A entirely, load cached results.
- `--no-cache` bypasses this.
- Cache stores full `BacktestResult` + `WeeklyPlayerRecord` data so both granularity modes work from cache.
- Cache is valid regardless of `defaults.yaml` changes — the bare baseline has all engines off, so it's independent of engine config. Only the keyed parameters (season, sims, scoring, training_years) affect bare results.

**Step 3: Build + simulate per season** (parallel across seasons)

Each season runs as one unit in a `ProcessPoolExecutor`:

```
Season 2022 ─┐
Season 2023 ─┼─ parallel
Season 2024 ─┘

Within each season:
  1. Load nflverse data ONCE (schedules, player stats, PBP)
  2. Load actuals ONCE
  3. Dual-arm game building (shared base data, both configs applied per game)
     → yields (arm_a_spec, arm_b_spec) pairs
  4. Simulate all specs (parallel across games)
  5. Pair results by game_id + arm
  6. Compute per-season metrics
  7. Return (season_metrics, weekly_records)
```

When bare cache hits for a season, only Arm B is built and simulated.

**Step 4: Aggregate + report**
- Combine per-season results.
- Compute metrics based on `--granularity`:
  - `season`: rank_corr by position, season MAE, weekly MAE, calibration — for both arms plus delta.
  - `weekly`: weekly rank_corr, weekly MAE, MAE by difficulty tercile, WR directional accuracy.
  - `both`: all of the above.
- Print results to console.
- If `--label` provided, append to unified ledger.

**Step 5: Update bare cache** (when `--baseline bare` and cache was missed)
- Write Arm A results to cache for future runs.

### Optimizations (vs current scripts)

1. **Dual-arm building always** — Both arms' game contexts built in the same worker, sharing base data load. The weekly script already does this; now applied everywhere.

2. **Parallel by season, not by phase** — Each season runs both arms together. No more Phase A (all bare) → Phase B (all engine-on) sequencing.

3. **Bare baseline caching** — Cache bare results to disk keyed by `(season, sims, scoring, training_years)`. Skip Arm A on repeat runs. `--no-cache` to force fresh. Biggest single win — typical "test a new thing" run is ~half the compute.

4. **Shared actuals loading** — Actual scores loaded once per season and passed to both arms.

### Unified Ledger

One ledger file: `results/ab_ledger.json`.

**Entry schema:**

```python
@dataclass
class LedgerEntry:
    label: str
    timestamp: str              # ISO 8601
    sims: int
    test_seasons: list[int]
    training_years: int
    scoring: str
    baseline: str               # "bare" or "defaults"
    granularity: str            # "season", "weekly", or "both"
    overrides: list[str]        # --set strings applied (e.g. ["usage.ngs.enabled=true"])
    config_snapshot: dict       # fully-resolved Arm B config dict
    season_results: list[SeasonResult]
    weekly_results: list[WeeklyPositionSummary] | None  # when granularity includes weekly
    directional_accuracy: DirectionalAccuracy | None     # WR only, when weekly
```

`SeasonResult` carries per-season, per-arm metrics: rank_corr by position, weekly MAE, season MAE, calibration.

**`--show-ledger` output:**

```
══════════════════════════════════════════════════════════════════════════════════════════════
  #  Label                baseline  overrides                  rank_corr  wk_mae  szn_mae
──────────────────────────────────────────────────────────────────────────────────────────────
  1  baseline-v1          bare      (none)                      +0.0517  -0.210  -0.180
  2  test-ngs             bare      usage.ngs.enabled=true       +0.0530  -0.225  -0.195
  3  ngs-marginal         defaults  usage.ngs.enabled=true       +0.0013  -0.015  -0.012
══════════════════════════════════════════════════════════════════════════════════════════════
```

**Migration**: Old ledger files (`pff_ab_ledger.json`, `weekly_ab_ledger.json`) stay as-is. New runs go to `ab_ledger.json` only. No migration logic needed.

### Console Output

```
════════════════════════════════════════════════════════════════════
  A/B VALIDATION
════════════════════════════════════════════════════════════════════
  baseline    : bare
  arm B       : defaults + [usage.ngs.enabled=true]
  sims        : 50
  seasons     : [2022, 2023, 2024]
  granularity : both
  scoring     : ppr
  bare cache  : HIT (2022, 2023), MISS (2024)
════════════════════════════════════════════════════════════════════

  [2024] Loading data...
  [2024] Building 288 game pairs (dual-arm)...
  [2024] Simulating 576 game-arms...
  [2022] Simulating 288 game-arms (Arm B only, Arm A cached)...
  [2023] Simulating 288 game-arms (Arm B only, Arm A cached)...

Total time: 142.3s

════════════════════════════════════════════════════════════════════
  SEASON-LEVEL RESULTS
════════════════════════════════════════════════════════════════════

  Season 2022:
    rank_corr:  QB 0.412->0.438 (+0.026)  RB 0.351->0.370 (+0.019)
                WR 0.298->0.325 (+0.027)  TE 0.281->0.295 (+0.014)
    weekly_mae: 6.82 -> 6.54 (-0.28)
    season_mae: 2.41 -> 2.19 (-0.22)

  ... (per season) ...

  AVERAGES:
    rank_corr delta:  +0.0215
    weekly_mae delta: -0.24
    season_mae delta: -0.18

════════════════════════════════════════════════════════════════════
  WEEKLY RESULTS
════════════════════════════════════════════════════════════════════

  QB (1,842 player-weeks, 54 weeks)
    rank_corr: 0.398 -> 0.431 (+0.033)
    weekly_mae: 7.12 -> 6.88 (-0.24)
    mae_by_difficulty: strong=5.2  neutral=7.1  weak=8.4

  ... (per position) ...

  WR Directional Accuracy: 412/623 = 66.1%

  Appended to ledger as #45: test-ngs
```

### Hold-out Gate

Preserved from current scripts: seasons >= 2025 are blocked with an error message. This is unchanged.

### File Structure

**New files:**
- `scripts/validate.py` — unified validation script
- `src/fantasy_sim/validation/config.py` — config resolution (bare config, dot-notation patcher, engine config builders from dict)
- `src/fantasy_sim/validation/cache.py` — bare baseline cache read/write
- `results/ab_ledger.json` — unified ledger (created on first `--label` run)
- `results/cache/` — bare baseline cache directory
- `docs/AB-TESTING.md` — usage guide, examples, config reference

**Modified files:**
- `src/fantasy_sim/validation/parallel.py` — ensure dual-arm building works for both granularity modes, shared data loading within a season
- `src/fantasy_sim/validation/backtester.py` — accept pre-loaded data for shared actuals optimization

**Deprecated (left in place, not deleted):**
- `scripts/validate_pff_signal.py`
- `scripts/validate_weekly_signal.py`
- `results/pff_ab_ledger.json`
- `results/weekly_ab_ledger.json`

**Unchanged:**
- `config/defaults.yaml` — already the source of truth
- Engine config dataclasses (`PffConfig`, `WeatherConfig`, etc.)
- Core simulation, scoring, and data pipeline
