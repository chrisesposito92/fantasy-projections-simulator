**Status:** Implemented — see `scripts/validate_weekly_signal.py`

**Validation module:** `src/fantasy_sim/validation/weekly.py`
**Tests:** `tests/test_validation/test_weekly.py`
**Ledger:** `results/weekly_ab_ledger.json`

---

# Weekly Validation Harness — Notes

**Purpose:** A per-week, per-player validation harness that retains weekly granularity instead of aggregating to season-level metrics. Supports all positions (QB, RB, WR, TE). The standard A/B harness aggregates across 17 games, which washes out per-game effects like matchup adjustments. This harness keeps the weekly signal visible.

## What We Need

A harness that retains per-week, per-player data so we can answer questions like:
- "Does knowing the CB matchup improve our WR ordering within each week?"
- "Are our QB projections better in weeks where the matchup engine applied a strong factor?"
- "Which position benefits most from PFF adjustments at the weekly level?"

### Core Data Structure

For each player-week, capture:
- `player_id`, `position`, `week`, `season`, `team`
- `projected_fpts` (PFF-on), `projected_fpts_baseline` (PFF-off)
- `actual_fpts`
- PFF modifiers applied (where applicable):
  - Coverage: `catch_rate_modifier`, `ypr_modifier` (WR only for now, TE in v2)
  - Team matchup: `catch_rate_factor`, `pass_yards_factor`, `rush_yards_factor`, etc. (all positions)

### Metrics — All Positions

**1. Per-position weekly rank_corr**
- Per week: rank all players within a position by projected fpts, rank by actual fpts, Spearman
- Average across weeks → one number per position per season
- Compare PFF-on vs PFF-off
- This is the core metric: does PFF improve within-week ordering for each position?

**2. Per-position weekly MAE**
- MAE computed per week per position, then averaged
- Compare PFF-on vs PFF-off
- More granular than the season-level weekly_mae in the standard harness (which averages across all positions)

**3. Per-position weekly MAE by matchup difficulty**
- For each position, split player-weeks into terciles by the magnitude of the PFF adjustment applied:
  - Strong adjustment (top third by |factor - 1.0|)
  - Weak adjustment (bottom third)
  - Neutral (middle third)
- Compute MAE within each bucket
- Signal: PFF-on should have lower MAE in strong-adjustment weeks (where PFF provides useful info) vs neutral

### Metrics — Coverage-Specific (WR Focus)

**4. WR directional accuracy**
- For each WR-week where coverage modifier deviates meaningfully from 1.0 (|modifier - 1.0| > 0.01):
  - Did the actual catch rate move in the predicted direction vs the WR's season average?
  - e.g., modifier < 1.0 (tough CB) → did actual catch rate fall below season avg?
- Target: >55% directional accuracy (above coin flip)
- This validates the coverage signal quality independent of magnitude
- Extend to TEs when TE coverage is added in v2

## Implementation Notes

- Requires running projections TWICE per week: once PFF-on, once PFF-off
- Need to capture the PFF modifiers applied per player (both team-level matchup factors and coverage modifiers)
- The existing `Backtester` runs per-week internally but only exposes aggregated `BacktestResult` — need to either:
  - (a) Extend `BacktestResult` with a `weekly_details: list[WeekDetail]` field, or
  - (b) Build a separate script that wraps `GameContextBuilder` + `run_simulations` directly
- Option (b) is probably cleaner — avoids modifying the backtester for a validation-only concern
- Could live at `scripts/validate_weekly_signal.py` as a dedicated script
- Should support `--positions QB RB WR TE` flag to filter which positions are analyzed
- Should support `--mode` flag same as the standard harness for testing different PFF layer combos

## When to Build

Baseline A/B (`coverage-v1` through `coverage-tight-clamp`) confirmed no regressions. The standard harness serves as a guardrail; this weekly harness is what proves per-game features (coverage, matchup) add value.

## Expected Results

- Per-position weekly rank_corr: small but consistent improvement across positions (maybe +0.01-0.03)
- WR should show the most improvement from coverage (it's the only position with per-player CB adjustments)
- RB/TE should show improvement from team-level matchup factors
- QB improvement likely smallest (QB projections are already well-calibrated from tier engine)
- Directional accuracy (WR coverage): 55-65% would be a strong result
- MAE by difficulty: lower MAE in strong-adjustment terciles, no change in neutral
