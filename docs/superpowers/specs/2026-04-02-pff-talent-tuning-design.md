# PFF Talent Stabilizer — Full Tuning + Extension Pipeline

**Date:** 2026-04-02
**Status:** Design approved
**Context:** Talent stabilizer shipped with SOFT_PASS backtest (PR #17). All metrics improved directionally but below PASS thresholds. Matchup engine parked. This spec covers all 7 improvements from `docs/pff-future-improvements.md` plus a persistent A/B testing harness.

## Goal

Push the talent stabilizer from SOFT_PASS to PASS by:
1. Replacing hand-tuned coefficients with empirically fitted values
2. Optimizing hyperparameters (prior_strength, min_divergence)
3. Adding new stabilization targets (target_share, fumble_rate, scramble_rate)
4. Making the stabilizer position-aware and team-change-aware
5. Adding schedule-adjusted talent evaluation
6. Building NCAA rookie priors from college PFF data
7. Tracking all changes via a persistent A/B results ledger

## Execution Strategy

**Approach B — Parallel agent development, sequential integration.**

Improvements are developed in parallel using agent teams (worktrees), then integrated one at a time with A/B testing between each. Each improvement gets both an isolation test (only this change vs baseline) and a cumulative test (all changes so far stacked). Any improvement that regresses cumulative rank_corr by >0.005 or weekly MAE by >0.3 is reverted.

Sensitivity sweeps run twice: once after coefficients land (sweep #1), once after all improvements (sweep #2).

---

## Component 1: A/B Harness with Persistent Ledger

### Changes to `scripts/validate_pff_signal.py`

**New CLI flags:**
- `--label TEXT` — tags the run in the ledger (required for ledger-appending runs)
- `--show-ledger` — prints the progression table without running a backtest
- `--config-override JSON` — PFF config overrides as JSON string, merged on top of defaults (e.g., `'{"talent": {"prior_strength": 30}}'`)

**Ledger file:** `results/pff_ab_ledger.json`

Each entry records:
```json
{
  "label": "fitted-coefficients",
  "timestamp": "2026-04-02T14:30:00",
  "mode": "talent",
  "sims": 50,
  "test_seasons": [2024],
  "training_years": 2,
  "pff_config": { "...full PffConfig used..." },
  "results": [
    {
      "test_season": 2024,
      "off": {
        "weekly_mae": 5.80,
        "season_mae": 22.10,
        "rank_correlations": {"QB": 0.85, "RB": 0.82, "WR": 0.88, "TE": 0.79},
        "boom_bust_calibration": 0.08
      },
      "on": { "...same structure..." },
      "deltas": {
        "rank_corr_avg": 0.006,
        "weekly_mae": -0.030,
        "season_mae": -0.483,
        "calibration": -0.005
      }
    }
  ],
  "verdict": "SOFT_PASS"
}
```

**Progression table** (printed after each run and via `--show-ledger`):
```
#  Label                     rank_corr   wk_mae    szn_mae   calibr    Verdict
1  baseline-v0               +0.0060    -0.030    -0.483    -0.005    SOFT_PASS
2  fitted-coefficients       +0.0120    -0.050    -0.800    -0.008    PASS
3  sweep-v1-ps30-md02        +0.0150    -0.060    -1.200    -0.010    PASS
```

Deltas: positive rank_corr = better, negative MAE/calibration = better.

**`results/` directory:** Gitignored (results are machine-specific and depend on local PFF data).

### Backtester Changes

The `Backtester` class needs to accept a `pff_config` parameter so the harness can inject custom PFF configs without monkey-patching the builder:

```python
class Backtester:
    def __init__(self, ..., pff_config: PffConfig | None = None):
        ...
        self.builder = GameContextBuilder(
            cache_dir=self.loader.cache_dir,
            pff_config=pff_config or PffConfig(),
        )
```

---

## Component 2: Fit Regression Coefficients

### Script: `scripts/fit_talent_coefficients.py`

**Data:** Year-N PFF stats predicting Year-N+1 PBP outcomes.
- Pairs: PFF 2022 → PBP 2023, PFF 2023 → PBP 2024
- Cross-validation: leave-one-pair-out

**Regressions (OLS):**

1. **catch_rate**: `next_season_pbp_catch_rate ~ drop_rate_delta + contested_catch_delta + qb_accuracy_delta`
   - Deltas computed from league average (matching how the stabilizer computes priors)
   - Minimum targets threshold to filter low-volume players

2. **receiving_yards**: `next_season_pbp_yards_per_catch ~ yprr_delta + adot_delta`

3. **rushing_yards**: `next_season_pbp_yards_per_carry ~ yco_delta + elusive_delta`

**Output:**
- Fitted coefficients with R² and cross-validation MAE
- Recommended `defaults.yaml` values
- Comparison of fitted vs hand-tuned coefficients

**Dependencies:** Uses `PffLoader.aggregate_player_stats()` for PFF data, `_aggregate_pbp_stats()` for PBP data, and the existing crosswalk for player matching.

---

## Component 3: Sensitivity Sweep

### Script: `scripts/sweep_talent_params.py`

**Grid search:**
- `prior_strength`: [20, 30, 40, 60, 80]
- `min_divergence`: [0.01, 0.02, 0.03, 0.05]
- Total: 20 combinations

**Per combination:**
1. Build `PffConfig` with specified params (all other settings at current defaults)
2. Run A/B backtest via `run_backtest_pair()`
3. Record results

**Output:**
- Ranked table sorted by avg rank_corr delta
- Best combination highlighted
- Optionally updates `defaults.yaml` with winner (with `--apply` flag)

**Run schedule:** Twice — once after coefficients land (sweep #1), once after all improvements (sweep #2).

---

## Component 4: Stabilize Additional Parameters

### New stabilization targets in `talent.py`

**target_share:**
- PFF signal: `route_grade` + `yprr` from receiving_summary
- Prior: `league_avg_target_share * (player_route_grade / league_avg_route_grade)`
- Coefficient dict in config: `target_share_coefficients: {route_grade: 0.5, yprr: 0.3}`
- Only applied to WR/TE with target_share > 0
- After stabilization, roster shares are re-normalized (existing `_normalize_roster_shares()`)

**fumble_rate (pass_fumble_rate for QBs, general fumble propensity for RB/WR):**
- PFF signal: `grades_hands_fumble` from receiving_summary and rushing_summary
- Prior: inverse relationship — lower hands grade → higher fumble rate
- Coefficient dict: `fumble_rate_coefficients: {grades_hands_fumble: -0.002}`
- Applied to players with existing `pass_fumble_rate` (QB) or carry_share > 0 (RB)

**QB scramble_rate:**
- PFF signal: scramble data from passing_summary (`scrambles`, `dropbacks`)
- Prior: `pff_scrambles / pff_dropbacks` — PFF separates scrambles from designed runs more cleanly than nflverse
- No coefficient needed — the PFF rate IS the prior directly
- Applied to QBs only

### Config additions in `defaults.yaml`

```yaml
talent:
  target_share_coefficients:
    route_grade: 0.5
    yprr: 0.3
  fumble_rate_coefficients:
    grades_hands_fumble: -0.002
  scramble_rate_enabled: true
```

### Model changes

`TalentConfig` gets three new coefficient dicts and a `scramble_rate_enabled` bool.

---

## Component 5: Position-Specific prior_strength

### Config format (backward compatible)

```yaml
# Scalar (current, still works):
prior_strength: 40

# Dict (new):
prior_strength:
  QB: 60
  WR: 40
  TE: 35
  RB: 30
  default: 40
```

### Code changes

**`models.py`:** `TalentConfig.prior_strength` type changes to `float | dict[str, float]`.

**`config.py`:** `load_pff_config()` handles both scalar and dict formats.

**`talent.py`:** New helper method:
```python
def _resolve_prior_strength(self, position: str) -> float:
    ps = self._config.prior_strength
    if isinstance(ps, (int, float)):
        return float(ps)
    return ps.get(position, ps.get("default", 40.0))
```

All calls to `stabilize_value()` pass the resolved strength instead of `self._config.prior_strength`.

---

## Component 6: Team-Change Boost

### Detection logic in `talent.py`

In `stabilize_roster()`, for each player:
1. Look up the player's PFF data team (most frequent `team` value in PFF training data)
2. Compare to `player.team` (current roster assignment)
3. If different: multiply effective `prior_strength` by `team_change_factor`

```python
pff_team = pff_row.get("team", player.team)
effective_strength = self._resolve_prior_strength(player.position)
if pff_team != player.team:
    effective_strength *= self._config.team_change_factor
```

Lower prior_strength → more PFF weight. A traded player's PBP stats are from a different offensive system, so PFF talent grades (system-independent) should carry more influence.

### Config

```yaml
talent:
  team_change_factor: 0.5  # multiply prior_strength by this for team changers
```

`TalentConfig` gets `team_change_factor: float = 0.5`.

---

## Component 7: Schedule-Adjusted Talent Evaluation

### Concept

Before computing PBP-PFF divergence, adjust PBP observations for schedule difficulty. A WR with 0.60 catch rate against top-10 secondaries is more talented than one with 0.65 against bottom-10 secondaries.

### Implementation in `talent.py`

New method `_compute_schedule_adjustments()`:
1. Load PFF `defense_coverage` grades per team from training seasons
2. For each receiver, look up opponents faced (from PBP game data) and compute average opponent defensive grade
3. Compute adjustment: `schedule_adj = weight * (opponent_grade - league_avg_grade) * sensitivity`
4. Adjust PBP value upward for tough schedules, downward for easy schedules

Applied BEFORE `stabilize_value()`:
```python
adjusted_pbp = pbp_catch_rate + schedule_catch_rate_adj
new_catch = stabilize_value(adjusted_pbp, prior, n_obs, strength, min_div)
```

Same logic for rushing yards using `defense_run` grades.

### Config

```yaml
talent:
  schedule_adjustment:
    enabled: true
    weight: 0.3
    catch_rate_sensitivity: 0.005
    rush_yards_sensitivity: 0.3
```

### Data requirements

Needs PFF defensive data per team per season. The `MatchupEngine` already loads this via `defense_summary` facets — we reuse the same PffLoader calls but aggregate differently (per-team-season averages instead of per-game).

---

## Component 8: NCAA Rookie Priors

### Sub-step 1: NCAA data loading

`PffLoader` gains:
```python
def load_ncaa_facet(self, facet: str, seasons: list[int]) -> pl.DataFrame:
    """Load from ~/.fantasy-sim/pff/processed/ncaa/"""
```

Same structure as `load_facet()` but reads from the NCAA directory.

### Sub-step 2: NCAA-to-NFL crosswalk

New method `PffLoader.build_ncaa_crosswalk()`:
- Input: NCAA PFF data, nflverse roster with `draft_number`, `draft_club`
- Match: Player name + college team → draft pick → NFL player_id
- Fuzzy matching with manual override dict for common mismatches
- Returns: `dict[int, str]` (NCAA PFF player_id → NFL player_id)

### Sub-step 3: Rookie talent prior

New class `RookieTalentPrior` (or integrated into `TalentStabilizer`):

For players with 0 NFL PBP observations (rookies):
- Load their college PFF grades (route_grade, yprr, contested_catch_rate, yards_after_catch, etc.)
- Map college grades to NFL-scale priors using position-specific regression
- Weight the prior by draft capital: 1st rounders get `draft_weight`, 7th rounders get `draft_weight * 0.3`

The prior feeds into `stabilize_value()` with `n_observations=0`, so the result is pure PFF prior — but now it's an informed prior from college grades rather than a generic positional archetype.

### Sub-step 4: Integration with existing rookie system

- `rookie_builder.py` continues to provide the fallback archetype system
- When NCAA PFF data is available for a rookie, the PFF-derived prior replaces the archetype
- When NCAA data is NOT available (undrafted free agents, missing data), the archetype system is used as-is

### Config

```yaml
talent:
  ncaa_priors:
    enabled: true
    draft_weight: 0.6
    ncaa_data_dir: null  # defaults to ~/.fantasy-sim/pff/processed/ncaa/
```

---

## Development Phases

### Phase 0: Foundation
- Build A/B harness with ledger (evolve `validate_pff_signal.py`)
- Add `pff_config` param to `Backtester`
- Run baseline A/B test to establish starting numbers (label: `baseline-v0`)

### Phase 1: Core Tuning (3 parallel agents)

**Develop simultaneously:**
| Agent | Work | Files touched |
|-------|------|---------------|
| 1 | Coefficient fitting script | `scripts/fit_talent_coefficients.py` (new) |
| 2 | Position-specific prior_strength | `models.py`, `config.py`, `talent.py` |
| 3 | Team-change boost | `talent.py`, `config.py` |

**Integrate sequentially:**
1. Land fitted coefficients → update `defaults.yaml` → A/B test (label: `fitted-coefficients`)
2. Land position-specific strength → A/B test (label: `+pos-specific-strength`)
3. Land team-change boost → A/B test (label: `+team-change-boost`)

### Phase 2: Sweep + Extensions (3 parallel agents)

**Develop simultaneously:**
| Agent | Work | Files touched |
|-------|------|---------------|
| 1 | Sensitivity sweep script | `scripts/sweep_talent_params.py` (new) |
| 2 | Additional parameters (target_share, fumble_rate, scramble_rate) | `talent.py`, `models.py`, `config.py`, `defaults.yaml` |
| 3 | Schedule-adjusted talent | `talent.py`, `config.py`, `defaults.yaml` |

**Integrate sequentially:**
1. Run sweep #1 → update `defaults.yaml` → A/B test (label: `sweep-v1`)
2. Land additional parameters → A/B test (label: `+additional-params`)
3. Land schedule-adjusted talent → A/B test (label: `+schedule-adjusted`)

### Phase 3: NCAA + Final
1. Build NCAA rookie priors (single agent, largest scope) → A/B test (label: `+ncaa-rookie-priors`)
2. Run sweep #2 → update params → A/B test (label: `sweep-v2-final`)
3. Final comprehensive validation at 200 sims (label: `final-200sims`)

## Revert Protocol

If any improvement regresses cumulative metrics:
- rank_corr avg delta < -0.005, OR
- weekly MAE delta > +0.3

Then:
1. Revert the config/code change
2. Record a `REVERTED` entry in the ledger with the reason
3. Move on to the next improvement

## Files Modified (Summary)

**New files:**
- `scripts/fit_talent_coefficients.py`
- `scripts/sweep_talent_params.py`
- `results/pff_ab_ledger.json` (generated, gitignored)

**Modified files:**
- `scripts/validate_pff_signal.py` — ledger support, config override, show-ledger
- `src/fantasy_sim/validation/backtester.py` — accept `pff_config` param
- `src/fantasy_sim/data/pff/talent.py` — additional params, pos-specific strength, team-change boost, schedule adjustment
- `src/fantasy_sim/data/pff/models.py` — new config fields, TalentConfig extensions
- `src/fantasy_sim/data/pff/config.py` — load new config fields
- `src/fantasy_sim/data/pff/loader.py` — NCAA facet loading, NCAA crosswalk
- `src/fantasy_sim/data/game_context.py` — pass position to stabilizer calls if needed
- `config/defaults.yaml` — new coefficient/config sections
- `.gitignore` — add `results/`

**Test files (new):**
- Tests for each new stabilization target
- Tests for position-specific strength
- Tests for team-change boost
- Tests for schedule adjustment
- Tests for NCAA loader + crosswalk + priors
- Tests for ledger read/write
- Tests for coefficient fitting logic
