# PFF Intelligence Layer — Design Spec

**Date**: 2026-04-02
**Status**: Draft
**Replaces**: Previous PFF modifier approach (removed — never committed)

## Problem Statement

The simulator has zero awareness of defensive quality. KC's offense produces identical projections whether facing the #1 or #32 defense. Additionally, players whose PBP stats misrepresent their true talent (breakout candidates, regression candidates) are projected at face value.

A previous attempt to integrate PFF data used a "modifier" approach — nudging existing player parameters (catch_rate, target_share, carry_share) using PFF grades and stats. This **hurt projections** in A/B backtesting:

- Rank correlation: -0.002 (neutral)
- Weekly MAE: +0.577 (12% worse)
- Season MAE: +6.070 (15% worse)
- Calibration: +0.033 (worse)

**Root cause**: PFF grades and nflverse PBP evaluate the same plays. Using one to adjust the other double-counts shared signal, adds noise, and confuses quality metrics (grades) with volume metrics (shares).

## Design Philosophy

PFF data should add information the sim **cannot derive from PBP**:

1. **Defensive matchup quality** — how the opposing defense changes what an offense can do this week
2. **OL/environmental context** — how blocking quality affects sack rates and rushing efficiency
3. **Process-over-results talent signal** — identifying players whose PBP stats likely misrepresent their true ability

PFF layers produce **adjustments to the base model**, not replacements. The nflverse PBP model remains the source of truth. PFF creates multiplicative factors (matchups) and blended estimates (talent) that modify the base.

## Architecture

```
Current pipeline:
  nflverse PBP → DataPipeline → TeamDistributions + TeamRoster → simulate_game()

New pipeline:
  nflverse PBP → DataPipeline → TeamDistributions + TeamRoster
                                        ↓
  PFF parquets → PffLoader → ┌─ MatchupEngine (Layer 1+2) → adjusted TeamDistributions + player params
                              └─ TalentStabilizer (Layer 3) → adjusted TeamRoster
                                        ↓
                                  simulate_game()
```

### Key Architectural Decisions

1. **PFF layers produce adjustments, not replacements.** The base model from nflverse PBP remains the source of truth.
2. **All PFF logic lives in `src/fantasy_sim/data/pff/`** — a subpackage containing: `loader.py` (existing, moved), `matchup.py` (Layer 1+2), `talent.py` (Layer 3), `models.py` (shared data types), `config.py`.
3. **Integration point is `GameContextBuilder`** — gains an optional PFF step after base model construction but before user overrides.
4. **Ordering**: Base model → PFF matchup adjustments → PFF talent stabilization → share re-normalization → user overrides → share re-normalization.

### Override Interaction

User overrides (season.yaml, CLI `--override`) are **always applied last** and **replace** PFF-adjusted values. This means:

- If you override `catch_rate=0.68`, that's the final value regardless of PFF.
- PFF matchup adjustments on overridden parameters are effectively bypassed for that player.
- PFF **reduces the need** for many manual overrides — matchup-based and talent-based adjustments that users previously had to set manually are now automatic.

| Override category | PFF handles it? | Still need manual override? |
|---|---|---|
| WR projections vs elite defense | Yes — matchup engine | No |
| RB behind elite/bad OL | Yes — OL context | No |
| QB facing tough pass rush | Yes — matchup engine | No |
| Breakout/bounceback candidate | Yes — talent stabilizer | Usually no |
| Regression candidate | Yes — talent stabilizer | Usually no |
| Mid-season trade / role change | No | Yes |
| Injury not yet in data | No | Yes |
| Coaching decision / scheme change | No | Yes |
| Gut feel / insider knowledge | No | Yes |

**Migration note**: Users with existing season.yaml files should review and simplify their overrides when enabling PFF. Many schedule-strength and talent-based overrides will be redundant.

---

## Layer 1+2: Defensive Matchup Engine

### Purpose

Answers: "How does the opposing defense change what this offense can do this week?"

The sim currently treats every game identically for a given offense. This layer creates per-game adjustments based on the opposing defense's PFF grades and stats, plus the offense's own OL quality.

### Core Data Type: MatchupContext

```python
@dataclass
class MatchupContext:
    """Per-game adjustment factors derived from PFF defensive + OL data."""
    # Pass defense impact on opposing offense
    catch_rate_factor: float      # 1.0 = neutral, <1.0 = tough secondary
    pass_yards_factor: float      # determines additive shift on receiving yards distributions
    sack_rate_factor: float       # >1.0 = strong pass rush
    int_rate_factor: float        # >1.0 = ball-hawking secondary

    # Run defense impact on opposing offense
    rush_yards_factor: float      # determines additive shift on rushing yards distributions

    # OL context (own team's blocking quality)
    ol_pass_block_factor: float   # team's own OL quality → sack rate
    ol_run_block_factor: float    # team's own OL quality → rush efficiency
```

### Factor Computation: Z-Score Approach

Each factor is derived from z-scores — how many standard deviations a defense/OL unit is from league average — mapped to a bounded multiplier.

```
Example: catch_rate_factor for "WRs facing BAL defense"

1. Load defense_coverage for BAL's games in training window
2. Compute BAL's avg catch_rate_allowed = 0.58 (league avg = 0.64, std = 0.04)
3. z_score = (0.58 - 0.64) / 0.04 = -1.5  (BAL is 1.5 SD better than avg)
4. factor = clamp(1.0 + z_score * sensitivity, min=0.80, max=1.20)
5. catch_rate_factor = 0.88  (BAL secondary reduces opposing catch rates by 12%)
```

The z-score approach is:
- **Self-calibrating** — automatically accounts for year-to-year league-wide changes
- **Tunable** — sensitivity parameter controls how much matchup matters
- **Bounded** — clamp range prevents extreme adjustments from dominating the base model

### PFF Stats → Factor Mapping

| MatchupContext Field | Primary PFF Stat | Facet | Grade Fallback |
|---|---|---|---|
| `catch_rate_factor` | `catch_rate` allowed (inverted) | `defense_coverage` | `grades_coverage_defense` |
| `pass_yards_factor` | `yards_per_reception` allowed | `defense_coverage` | `grades_coverage_defense` |
| `sack_rate_factor` | `pass_rush_win_rate` | `defense_pass_rush` | `grades_pass_rush_defense` |
| `int_rate_factor` | `interceptions` per coverage snap | `defense_coverage` | `forced_incompletion_rate` |
| `rush_yards_factor` | `stop_percent` (inverted) | `defense_run` | `grades_run_defense` |
| `ol_pass_block_factor` | `pbe` (pass block efficiency) | `offense_pass_blocking` | `pressures_allowed` rate |
| `ol_run_block_factor` | `grades_run_block` | `offense_run_blocking` | `run_block_percent` |

Each factor uses a primary stat (direct measurement) with a grade fallback. The fallback triggers when: (a) the primary stat column is missing from the PFF data, or (b) the team has fewer than 4 games of data in the training window (insufficient sample for stable z-scores).

### How Factors Are Applied

The `MatchupEngine` produces a `MatchupContext` for each team. `GameContextBuilder` applies it:

- `catch_rate_factor` → scales every receiver's `catch_rate` and `red_zone_catch_rate` on the opposing offense
- `pass_yards_factor` → additive shift on `receiving_yards_dist` arrays (shift preserves distribution shape)
- `sack_rate_factor` × `ol_pass_block_factor` → combined multiplier on `TurnoverRates.sack_rate`
- `int_rate_factor` → scales `TurnoverRates.int_rate`
- `rush_yards_factor` × `ol_run_block_factor` → additive shift on `rushing_yards_dist` arrays

**Directional flow**: Away defense creates home `MatchupContext` and vice versa. Defensive PFF data adjusts the *opposing* offense — zero double-counting risk.

**OL factors combine with defensive factors**: bad OL × good pass rush = very high sack rate. Good OL shifts rushing floor up, good run D shifts it down — net effect partially cancels.

### Training Window

Matchup factors use a recency-weighted window of PFF game-level data, consistent with the base model's use of nflverse data. The same `recency_weights` from `defaults.yaml` apply.

---

## Layer 3: Talent Stabilizer

### Purpose

Answers: "Is this player's PBP stat line an accurate reflection of their true talent, or should we expect regression?"

Instead of blindly adjusting every player (what the old modifier did), the talent stabilizer only intervenes when PFF process metrics **meaningfully diverge** from PBP outcome metrics. No divergence = no adjustment.

### Core Concept: Divergence Detection

```
Example: "Is Keenan Allen's 59% catch rate real?"

PBP says:     catch_rate = 0.59 (based on 92 targets)
PFF says:     drop_rate = 2.1% (elite), route_grade = 89.4 (elite)
PFF prior:    expected catch_rate ≈ 0.68 (based on route quality + drop rate)
Divergence:   0.09 — significant, likely bad luck or QB-driven
Sample size:  92 targets — moderate

Adjustment:   blend toward PFF prior → adjusted catch_rate ≈ 0.63
              (not all the way to 0.68 — PBP still gets majority weight)
```

Compare to a player with no divergence:
```
PBP says:     catch_rate = 0.66
PFF says:     drop_rate = 4.8% (average), route_grade = 71.2 (average)
PFF prior:    expected catch_rate ≈ 0.65
Divergence:   0.01 — negligible

Adjustment:   none (below min_divergence threshold)
```

### Blending Formula

```python
def stabilize(pbp_value, pff_prior, n_observations, prior_strength, min_divergence):
    divergence = abs(pbp_value - pff_prior)
    if divergence < min_divergence:
        return pbp_value  # no adjustment needed

    # Bayesian blend: more observations → trust PBP more
    pbp_weight = n_observations / (n_observations + prior_strength)
    pff_weight = 1.0 - pbp_weight

    return pbp_value * pbp_weight + pff_prior * pff_weight
```

`prior_strength` represents "how many PBP observations is a PFF grade worth?" With `prior_strength = 40`:
- 20 real targets → PFF is ~67% of the blend (rookie/small sample)
- 80 real targets → PFF is ~33% of the blend (moderate sample)
- 200 real targets → PFF is ~17% of the blend (large sample)
- 500 real targets → PFF is ~7% of the blend (PBP overwhelmingly reliable)

### Parameters That Get Stabilized

| Player Parameter | PFF Prior Derived From | Why PFF Adds Signal |
|---|---|---|
| `catch_rate` | `drop_rate` + `contested_catch_rate` + QB `accuracy_%` | PBP catch rate conflates receiver skill with QB accuracy and coverage luck |
| `receiving_yards_dist` | `yprr` + `avg_depth_of_target` | YPRR strips out volume effects; depth reveals true field-stretching ability |
| `rushing_yards_dist` | `yco_attempt` + `elusive_rating` | YCO isolates the runner's contribution from OL blocking quality |
| `target_share` | `route_grade` + `yprr` | Elite route runners who haven't gotten volume yet (new team, emerging role) |
| `fumble_rate` | `grades_hands_fumble` | PFF tracks ball security independently from fumble luck |
| `scramble_rate` | `scrambles` / `dropbacks` from passing_summary | PFF separates designed runs from true scrambles more reliably |

### Parameters That Do NOT Get Stabilized

- `carry_share` — coaching decision, not a talent signal
- `red_zone_target_share` / `red_zone_carry_share` — too small sample for PFF priors
- `air_yards_share` — already well-captured by PBP depth-of-target data

### Computing PFF Priors

Each prior is computed via a simple regression from PFF process metrics to expected PBP outcomes:

```
expected_catch_rate = baseline
    + β1 * (league_avg_drop_rate - player_drop_rate)
    + β2 * (player_contested_catch_rate - league_avg)
    + β3 * (qb_accuracy - league_avg)
```

Regression coefficients (β values) are fit once on historical data (PFF stats from year N → PBP outcomes in year N+1) and stored in config. Z-score inputs handle year-to-year normalization.

### Who Benefits Most

1. **Rookies / sophomore players** — small PBP sample, PFF grades are the main signal
2. **Players who changed teams** — PBP from old system, PFF evaluates talent independently
3. **Injury returners** — limited recent PBP, pre-injury PFF grades still valid
4. **Breakout candidates** — elite PFF process metrics with suppressed PBP stats
5. **Regression candidates** — mediocre PFF grades with inflated PBP stats

---

## Configuration

### defaults.yaml

```yaml
pff:
  enabled: false
  data_dir: null  # defaults to ~/.fantasy-sim/pff/processed/nfl/

  matchup:
    enabled: true
    # Sensitivity: how much matchup quality moves the needle (per z-score unit)
    pass_defense_sensitivity: 0.08
    pass_rush_sensitivity: 0.10
    run_defense_sensitivity: 0.08
    int_rate_sensitivity: 0.06
    # OL context
    ol_pass_sensitivity: 0.08
    ol_run_sensitivity: 0.06
    # Bounds: maximum adjustment in either direction
    factor_clamp: [0.80, 1.20]

  talent:
    enabled: true
    prior_strength: 40          # PFF grade = equivalent of N PBP observations
    min_divergence: 0.03        # minimum PBP-PFF gap before adjusting
    # Per-parameter regression coefficients (fit on historical data)
    catch_rate_coefficients:
      drop_rate: -0.15
      contested_catch_rate: 0.10
      qb_accuracy: 0.08
    rushing_yards_coefficients:
      yco_attempt: 0.6
      elusive_rating: 0.008
```

Each layer can be independently enabled/disabled. CLI gains `--pff / --no-pff` to override the config-level `enabled` flag.

---

## Integration into GameContextBuilder

```python
def build_game(home, away, ...):
    # 1. Base model (unchanged)
    home_dists = self.build_team_distributions(home, ...)
    away_dists = self.build_team_distributions(away, ...)
    home_roster = self.build_team_roster(home, ...)
    away_roster = self.build_team_roster(away, ...)

    # 2. PFF Layer 1+2: Matchup adjustments (NEW)
    if self._matchup_engine:
        # away defense affects home offense, and vice versa
        home_ctx = self._matchup_engine.compute(defense_team=away, offense_team=home, ...)
        away_ctx = self._matchup_engine.compute(defense_team=home, offense_team=away, ...)
        self._apply_matchup(home_dists, home_roster, home_ctx)
        self._apply_matchup(away_dists, away_roster, away_ctx)

    # 3. PFF Layer 3: Talent stabilization (NEW)
    if self._talent_stabilizer:
        self._talent_stabilizer.stabilize_roster(home_roster, ...)
        self._talent_stabilizer.stabilize_roster(away_roster, ...)
        normalize_roster_shares(home_roster)
        normalize_roster_shares(away_roster)

    # 4. User overrides (unchanged, always last)
    if overrides:
        apply_overrides(overrides, home_dists, away_dists, home_roster, away_roster)

    return home_dists, away_dists, home_roster, away_roster
```

---

## File Structure

```
src/fantasy_sim/data/pff/
    __init__.py
    loader.py          # existing PffLoader (moved from data/pff_loader.py)
    models.py          # MatchupContext, TalentAdjustment, PffConfig dataclasses
    matchup.py         # MatchupEngine — computes MatchupContext from defensive PFF data
    talent.py          # TalentStabilizer — Bayesian blending with divergence detection
    config.py          # load_pff_config(), default coefficients

tests/test_data/test_pff/
    test_loader.py     # existing (moved from test_data/test_pff_loader.py)
    test_matchup.py    # matchup engine unit tests
    test_talent.py     # talent stabilizer unit tests
    test_integration.py # end-to-end PFF pipeline tests
```

---

## Testing & Validation Strategy

### Unit Tests (per layer)

- **test_matchup.py**: Given known defensive PFF stats, assert MatchupContext factors are computed correctly. Test z-score math, clamp bounds, fallback to grades when stats missing, edge cases (no data for a team).
- **test_talent.py**: Given known PBP stats + PFF grades, assert blending formula produces expected values. Test divergence threshold, sample size weighting, no-adjustment when aligned, edge cases (zero observations).

### Integration Tests

- Wire up full pipeline with real PFF data, verify `simulate_game()` produces sane results (scores in 0-60 range, stat distributions reasonable).
- Verify matchup factors actually differ by opponent (KC vs BAL should differ from KC vs CAR).

### A/B Backtest (rebuilt validate_pff_signal.py)

Same framework as previous backtest but tests each layer independently:
- `--mode matchup`: Only matchup engine enabled
- `--mode talent`: Only talent stabilizer enabled
- `--mode all`: Both layers

Same kill-point criteria: rank_corr, weekly MAE, season MAE, calibration. If one layer helps and the other hurts, keep only the one that helps.

### Sensitivity Sweep

New script that varies key parameters (`pass_defense_sensitivity`, `prior_strength`, `min_divergence`) across a range and records accuracy metrics at each point. Helps find optimal calibration systematically rather than by manual trial-and-error.

---

## Implementation Phases

| Phase | What | Depends On | Parallel? |
|---|---|---|---|
| **0. Clean slate** | Remove old modifier code, keep pff_loader.py + tests | Done | - |
| **1. Foundation** | Create `pff/` subpackage, `models.py`, `config.py`. Move `loader.py` into subpackage. Update all imports. | Phase 0 | - |
| **2. Matchup Engine** | `pff/matchup.py` — MatchupEngine class: load PFF defensive + OL data, compute z-scores, produce MatchupContext. Unit tests. | Phase 1 | Yes (with 5) |
| **3. Matchup Integration** | Wire MatchupEngine into GameContextBuilder. `_apply_matchup()` method. Integration tests. | Phase 2 | - |
| **4. Matchup Backtest** | Rebuild `validate_pff_signal.py` with matchup-only mode. Run A/B. Tune sensitivities. | Phase 3 | - |
| **5. Talent Stabilizer** | `pff/talent.py` — TalentStabilizer class: compute PFF priors, divergence detection, Bayesian blending. Fit regression coefficients on historical data. Unit tests. | Phase 1 | Yes (with 2) |
| **6. Talent Integration** | Wire TalentStabilizer into GameContextBuilder. Integration tests. | Phase 5 | - |
| **7. Talent Backtest** | A/B backtest talent-only mode. Tune prior_strength and min_divergence. | Phase 6 | - |
| **8. Combined Backtest** | A/B backtest both layers together. Verify they don't interfere. Sensitivity sweep. | Phase 4 + 7 | - |
| **9. CLI + Config + Docs** | `--pff` flag on CLI commands, `pff:` section in `defaults.yaml`, update CONFIG.md with PFF configuration section, update CLAUDE.md. | Phase 8 | - |

Phases 2-4 (matchup) and 5-7 (talent) are independent tracks and can be built in parallel.

---

## PFF Data Inventory

Available facets (21 total, 2022-2025 NFL seasons, game-level granularity):

| Category | Facet | Rows (2024) | Cols | Used By |
|---|---|---|---|---|
| **Passing** | `passing_summary` | 664 | 46 | Talent (QB accuracy, TWP, BTT) |
| | `passing_detail` | 664 | 898 | Future Layer 4 (pressure/PA splits) |
| **Receiving** | `receiving_summary` | 4,212 | 49 | Talent (drop rate, YPRR, route grade, YAC) |
| | `receiving_depth` | 4,212 | 477 | Talent (depth-of-target, direction splits) |
| | `receiving_coverage` | 20,789 | 40 | Matchup (coverage vs WR matchups) |
| **Rushing** | `rushing_summary` | 2,255 | 51 | Talent (YCO, elusive, breakaway) |
| | `rushing_direction` | 2,220 | 14 | Future (directional efficiency) |
| **Defense** | `defense_summary` | 10,713 | 59 | Matchup (overall defensive quality) |
| | `defense_coverage` | 7,212 | 44 | Matchup (secondary quality, catch rate allowed) |
| | `defense_pass_rush` | 7,564 | 38 | Matchup (pass rush win rate, pressure) |
| | `defense_run` | 10,258 | 28 | Matchup (run stop %, missed tackles) |
| | `defense_coverage_matchup` | ~20K | 40 | Matchup (player-vs-player) |
| **Blocking** | `offense_pass_blocking` | 5,678 | 34 | Matchup/OL (PBE, pressures allowed) |
| | `offense_run_blocking` | 9,414 | 26 | Matchup/OL (zone/gap grades) |
| | `offense_blocking` | 9,866 | 35 | Matchup/OL (overall blocking) |
| | `offense_summary` | 10,252 | 28 | Reference (snap counts) |
| **Special** | `field_goal_summary` | ~160 | ~20 | Not used (kicking modeled at team level) |
| | `kickoff_summary` | ~170 | ~20 | Not used |
| | `punting_summary` | ~170 | ~20 | Not used |
| | `return_summary` | ~200 | ~20 | Not used |
| | `special_summary` | ~10K | ~20 | Not used |

---

## Future: Layer 4 — Situational Splits

Out of scope for this implementation but designed to be addable on top of Layers 1-3.

Layer 4 would use PFF's deep split data to create **context-dependent performance models** within the play resolver:
- QB clean-pocket vs under-pressure accuracy (from `passing_detail`)
- WR catch rates vs man vs zone coverage (from `receiving_coverage`)
- RB efficiency in zone vs gap runs (from `rushing_summary`)

Each play, the sim would determine the context (pressure? coverage type?) and use the appropriate split. This requires changes to `play_resolver.py` and is higher complexity — best attempted after Layers 1-3 are validated.
