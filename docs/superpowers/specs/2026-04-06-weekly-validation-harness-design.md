# Weekly Validation Harness Design

**Date:** 2026-04-06
**Status:** Approved
**Purpose:** Per-week, per-player validation harness that retains weekly granularity for all positions (QB, RB, WR, TE) to measure whether PFF layers add value at the game level.

## Context

The standard A/B harness (`scripts/validate_pff_signal.py`) aggregates to season-level metrics, which washes out per-game effects like matchup adjustments and coverage modifiers. This harness keeps the weekly signal visible so we can answer questions like:

- "Does knowing the CB matchup improve our WR ordering within each week?"
- "Are our QB projections better in weeks where the matchup engine applied a strong factor?"
- "Which position benefits most from PFF adjustments at the weekly level?"

## Architecture

**Approach:** Script + validation module (approach B from brainstorming).

- `src/fantasy_sim/validation/weekly.py` — data structures, metric functions, ledger I/O
- `scripts/validate_weekly_signal.py` — CLI, orchestration, simulation loop
- `results/weekly_ab_ledger.json` — separate ledger (different schema from season-level ledger)

Metric computation lives in `src/` for testability. The script handles orchestration. This mirrors the existing `metrics.py` / `validate_pff_signal.py` split.

## Data Structures

All defined in `src/fantasy_sim/validation/weekly.py`.

### WeeklyPlayerRecord

The atomic unit collected during simulation — one per player per week:

```python
@dataclass
class WeeklyPlayerRecord:
    player_id: str
    name: str
    position: str           # QB, RB, WR, TE
    team: str
    week: int
    season: int
    projected_fpts_on: float    # PFF-on projection
    projected_fpts_off: float   # PFF-off projection
    actual_fpts: float
    matchup_factors: dict[str, float]       # MatchupContext field -> factor value
    coverage_modifiers: CoverageModifiers | None  # WR only, None for other positions
```

`matchup_factors` stores position-filtered factors:
- **QB:** `sack_rate_factor`, `int_rate_factor`, `ol_pass_block_factor`
- **RB:** `rush_yards_factor`, `ol_run_block_factor`
- **WR/TE:** `catch_rate_factor`, `pass_yards_factor`

### WeeklyPositionSummary

Computed from records — one per position:

```python
@dataclass
class WeeklyPositionSummary:
    position: str
    weekly_rank_corr_on: float
    weekly_rank_corr_off: float
    weekly_mae_on: float
    weekly_mae_off: float
    mae_by_tercile: dict[str, float]  # "strong"/"neutral"/"weak" -> MAE (PFF-on)
    n_player_weeks: int
    n_weeks: int
```

### DirectionalAccuracyResult

WR-specific coverage signal quality:

```python
@dataclass
class DirectionalAccuracyResult:
    total_eligible: int       # WR-weeks with |modifier - 1.0| > 0.01 and >= 4 targets
    correct_direction: int    # actual catch rate moved in predicted direction
    accuracy: float           # correct_direction / total_eligible
```

### WeeklyLedgerEntry

Stored in `results/weekly_ab_ledger.json`:

```python
@dataclass
class WeeklyLedgerEntry:
    label: str
    timestamp: str
    mode: str
    sims: int
    test_seasons: list[int]
    training_years: int
    position_summaries: list[WeeklyPositionSummary]
    directional_accuracy: DirectionalAccuracyResult | None
```

The ledger stores computed summaries, not raw per-player records. Raw records exist only in-memory during the run.

## Metrics

### Metric 1: Per-Position Weekly Rank Correlation

```python
def compute_weekly_rank_corr(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
```

Groups records by week. Per week, ranks players within the position by projected fpts and by actual fpts, computes Spearman via existing `spearman_rank_correlation()`. Averages across weeks. Weeks with < 5 players in the position are skipped.

### Metric 2: Per-Position Weekly MAE

```python
def compute_weekly_mae(
    records: list[WeeklyPlayerRecord],
    position: str,
    use_pff_on: bool = True,
) -> float:
```

Groups by week. Per week, computes MAE between projected and actual fpts for all players in the position. Averages across weeks.

### Metric 3: MAE by Matchup Difficulty Tercile

```python
def compute_mae_by_difficulty(
    records: list[WeeklyPlayerRecord],
    position: str,
) -> dict[str, float]:
```

Per record, computes adjustment magnitude = `max(|factor - 1.0|)` across all applicable factors (`matchup_factors` values + coverage modifiers if present). This captures "did PFF have a strong opinion about this matchup?" without biasing positions with more factors.

Sorts records by magnitude descending, splits into equal thirds by count:
- **Strong** (top third): highest PFF adjustment magnitude
- **Neutral** (middle third)
- **Weak** (bottom third): lowest PFF adjustment magnitude (includes 0.0 = no PFF data)

Ties at tercile boundaries are assigned arbitrarily (stable sort order). This is a rank-based split, not threshold-based — every run produces three equal-sized groups regardless of the magnitude distribution.

Computes MAE within each tercile using PFF-on projections vs actuals.

Edge cases:
- All modifiers at 1.0: records distributed equally across terciles (all magnitudes tied at 0.0, split by sort position). The "strong" tercile MAE should equal the "weak" tercile MAE in this case, confirming no spurious signal.
- Tercile with < 3 entries (few total records): MAE still computed, warning printed
- Fewer than 3 total records: returns empty dict

### Metric 4: WR Directional Accuracy

```python
def compute_directional_accuracy(
    records: list[WeeklyPlayerRecord],
    actuals_by_player: dict[str, list[ActualPlayerWeek]],
    min_weekly_targets: int = 4,
) -> DirectionalAccuracyResult:
```

For each WR record with coverage modifiers where `|catch_rate_modifier - 1.0| > 0.01`:

1. Compute the WR's season-average actual catch rate from `actuals_by_player` (receptions / targets across all weeks EXCLUDING the current week, to avoid bias from the week being evaluated)
2. Get this week's actual catch rate from `ActualPlayerWeek`
3. Skip if weekly targets < 4
4. Check direction: modifier < 1.0 (tough CB) → did actual catch rate fall below season avg? (and vice versa)
5. Count correct / total

Target: > 55% accuracy (above coin flip).

## Script Orchestration

`scripts/validate_weekly_signal.py`

### CLI Flags

```
--mode            Same choices as validate_pff_signal.py
--sims            Sims per game (default: 50)
--seasons         Test seasons (default: [2023, 2024])
--training-years  Num training seasons (default: 2)
--scoring         ppr/half_ppr/standard (default: ppr)
--positions       Space-separated (default: QB RB WR TE)
--label           Label for ledger entry
--show-ledger     Print progression table and exit
--config-override JSON overrides, same format as existing harness
```

### Simulation Loop

```python
def run_weekly_comparison(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    positions: list[str],
) -> list[WeeklyPlayerRecord]:
```

1. Load schedules and player_stats via `DataLoader`
2. Load actuals via `load_actual_scores()`
3. Create two `GameContextBuilder` instances:
   - `builder_off` with `PffConfig(enabled=False)`
   - `builder_on` with the provided `pff_config`
4. For each week 1-18, for each game:
   - **PFF-off:** `builder_off.build_game()` -> `run_simulations()` -> `build_player_projections()`
   - **PFF-on:** `builder_on.build_game()` -> `run_simulations()` -> `build_player_projections()`
   - **Capture modifiers** via `builder_on._matchup_engine.compute()` and `builder_on._coverage_engine.compute()`. These re-run cheap z-score math on cached facet data.
   - Build `WeeklyPlayerRecord` for each player matching requested positions with actuals data
5. Return all records

### Design Decisions

- **Same seed for on/off:** `zlib.crc32(game_id.encode()) % (2**31)`. Variance differences come from the model, not RNG.
- **Modifier capture via private attributes:** `builder_on._matchup_engine` and `builder_on._coverage_engine`. This is internal tooling, same pattern as tests. No public API changes to `GameContextBuilder`.
- **Position-filtered matchup_factors:** QB gets `{sack_rate_factor, int_rate_factor, ol_pass_block_factor}`, RB gets `{rush_yards_factor, ol_run_block_factor}`, WR/TE get `{catch_rate_factor, pass_yards_factor}`.
- **Multi-season parallelism:** `ProcessPoolExecutor` when `len(seasons) > 1`, same as existing harness.

### Output

ASCII summary table with per-position deltas (rank_corr on-off, MAE on-off, MAE by tercile) and directional accuracy for WR. If `--label` provided, appends `WeeklyLedgerEntry` to ledger.

## Testing

Tests in `tests/test_validation/test_weekly.py`. ~20-25 tests, all synthetic data, no network.

### Metric 1 & 2 (rank_corr and MAE)

- 3 weeks, 5 players per week, known values -> verify averaged result
- Weeks with < 5 players skipped for rank_corr
- Single-week edge case
- Position filtering across mixed-position records

### Metric 3 (MAE by difficulty tercile)

- 9 records with known magnitudes -> verify tercile boundaries
- All modifiers at 1.0 -> all "weak", others handled gracefully
- Mixed matchup + coverage factors -> verify max-deviation picks correctly
- Small tercile (< 3 entries) -> still computes, no crash

### Metric 4 (directional accuracy)

- Modifier < 1.0, actual below season avg -> correct
- Modifier > 1.0, actual above season avg -> correct
- Modifier < 1.0, actual above season avg -> incorrect
- < 4 weekly targets -> excluded
- Modifier within dead zone (|mod - 1.0| <= 0.01) -> excluded
- Zero eligible records -> `DirectionalAccuracyResult(0, 0, 0.0)`
- Season average from available weeks only

### Ledger

- Round-trip save/load to temp file
- `format_weekly_progression_table` with 0, 1, multiple entries

### Data structures

- `WeeklyPlayerRecord` with and without coverage modifiers
- `matchup_factors` position filtering

## Files Changed

| File | Change |
|------|--------|
| `src/fantasy_sim/validation/weekly.py` | New — data structures, metrics, ledger I/O |
| `scripts/validate_weekly_signal.py` | New — CLI, orchestration, simulation loop |
| `tests/test_validation/test_weekly.py` | New — ~20-25 unit tests |
| `CLAUDE.md` | Update commands section with new script usage |
| `docs/weekly-validation-notes.md` | Mark as implemented, link to script |
