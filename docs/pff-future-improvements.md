# PFF Intelligence Layer — Future Improvements

Status as of 2026-04-02:
- **Talent Stabilizer**: Shipping (SOFT_PASS backtest, all metrics improved directionally)
- **Matchup Engine**: Parked (rank_corr regressed with historical training data)

## Talent Stabilizer Improvements

### 1. Empirically Fit Regression Coefficients (High Impact)

The current catch_rate prior coefficients (`drop_rate: -0.15`, `contested_catch_rate: 0.10`, `qb_accuracy: 0.08`) are hand-tuned. Fit them on historical data — PFF stats from year N predicting PBP outcomes in year N+1.

**Implementation:**
- Create `scripts/fit_talent_coefficients.py`
- For each stabilizable parameter (catch_rate, rushing_yards, receiving_yards):
  - Load PFF stats from 2022, 2023 and PBP outcomes from 2023, 2024
  - Run OLS regression: PBP outcome ~ PFF predictors
  - Output fitted coefficients
- Validate with leave-one-season-out cross-validation
- Update `defaults.yaml` with empirically-derived values

### 2. Sensitivity Sweep on prior_strength and min_divergence (High Impact)

The current `prior_strength=40` and `min_divergence=0.03` are reasonable defaults but not optimized.

**Implementation:**
- Create `scripts/sweep_talent_params.py`
- Grid search: `prior_strength` in [20, 30, 40, 60, 80], `min_divergence` in [0.02, 0.03, 0.05]
- Run A/B backtest for each combination
- Plot rank_corr and MAE vs parameter values
- Find optimal settings

### 3. Stabilize Additional Parameters (Medium Impact)

Currently only catch_rate and yards distributions are stabilized. Strong candidates:

- **target_share** — Use `route_grade` + `yprr` for players whose role is growing/shrinking faster than PBP shows. Especially valuable for emerging WRs.
- **fumble_rate** — Use `grades_hands_fumble` from receiving_summary and rushing_summary. Data is already loaded but not used.
- **QB scramble_rate** — PFF's `scrambles / dropbacks` from passing_summary separates designed runs from true scrambles more cleanly than nflverse.

### 4. Position-Specific prior_strength (Medium Impact)

QBs are more stable year-to-year and have larger PBP samples — they need less PFF blending. Rookies and small-role players need more PFF weight.

**Suggested values:** `{QB: 60, WR: 40, TE: 35, RB: 30}`

Requires changing `TalentConfig.prior_strength` from a single float to a dict, and updating `stabilize_value()` to accept position-specific strength.

### 5. Team-Change Boost (Medium Impact)

Players who switched teams should get stronger PFF priors since their PBP data is from a different scheme/QB/OL context. The PFF grades evaluate talent independently of system.

**Implementation:**
- Compare current-season roster team to PBP training data team
- If different: multiply `prior_strength` by 0.5 (double PFF weight)
- Detect via roster comparison across seasons in `_ensure_pff_crosswalk()`

### 6. NCAA Data for Rookie Priors (High Impact, Larger Scope)

PFF NCAA data (2022-2025) is already scraped and stored at `~/.fantasy-sim/pff/processed/ncaa/`. Currently rookies use draft-capital archetypes from `rookie_builder.py`.

**Implementation:**
- Extend `PffLoader` to load NCAA facets
- Build NCAA→NFL player crosswalk (draft picks)
- Create `RookieTalentPrior` from college PFF grades (route_grade, YCO, etc.)
- Feed into `TalentStabilizer` as the PFF prior for players with 0 NFL PBP observations
- An elite college route runner gets a higher catch_rate prior than a raw athlete

### 7. Schedule-Adjusted Talent Evaluation (Medium Impact)

Use PFF defensive data to context-adjust PBP observations *before* comparing to PFF priors. This repurposes the matchup engine data for talent evaluation rather than per-game adjustments.

**Example:** A WR who put up a 0.60 catch rate while facing top-10 secondaries all year is better than a WR with 0.65 catch rate against bottom-10 secondaries. Adjust the PBP observation upward before computing divergence.

**Implementation:**
- Compute schedule difficulty factor per player using opponent `defense_coverage` grades
- Adjust `pbp_value` by schedule factor before passing to `stabilize_value()`
- This adds matchup awareness without the per-game adjustment noise that failed

## Matchup Engine Improvements

### Same-Season Rolling Data Strategy (Required for Re-Enabling)

The matchup engine failed because 2022-2023 defensive quality doesn't predict 2024 game-by-game matchup difficulty. Defenses change too much year-to-year.

**Fix:** Use same-season PFF data with a rolling window:
- Week 5 matchup uses PFF defensive data from weeks 1-4 of the current season
- Requires PFF data to be available for the current season (scrape weekly)
- `MatchupEngine.compute()` would accept `current_season_weeks` parameter
- Early-season games (weeks 1-2) fall back to previous season data

This is a data strategy change, not an architecture rewrite. The existing `MatchupEngine`, `compute_factor()`, and `_apply_matchup()` code would all be reused.

## Priority Order

1. **Fit coefficients** + **Sensitivity sweep** — pure tuning, no architecture changes, could push SOFT_PASS → PASS
2. **Stabilize additional parameters** — small code extension, likely improves all metrics
3. **Position-specific prior_strength** — small config change, targeted improvement
4. **Team-change boost** — medium code change, directly targets a key use case
5. **NCAA rookie priors** — larger scope, high impact for dynasty/redraft leagues
6. **Schedule-adjusted talent** — repurposes matchup data intelligently
7. **Same-season matchup** — requires weekly PFF scraping infrastructure
