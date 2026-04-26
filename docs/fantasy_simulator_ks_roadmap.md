# Fantasy Projections Simulator KS Improvement Roadmap

## Purpose

This roadmap is a Codex-ready implementation handoff for improving the simulator's distributional validation, with special focus on the two weakest metrics from the recent `validate.py` run:

- `QB pass_yards KS`
- `WR receiving_yards KS`

The current model already appears strong on ranking and absolute-error metrics:

- Season-level `rank_corr` is strong across positions.
- Weekly and season MAE improve materially over the bare nflverse baseline.
- The worst failures are distributional, especially component-stat KS.

The main working thesis is:

```text
QB pass_yards:
  likely a real calibration / yards-per-completion / explosive-tail issue.

WR receiving_yards:
  likely first a validation-universe issue,
  then possibly a receiver-concentration / tail-modeling issue.

Current KS:
  likely compares actual outcomes to projected means,
  not actual outcomes to simulated predictive draws.
```

---

## Guiding Principles

1. **Do not blindly increase WR receiving yards first.**
   The current WR actual sample appears to have only about 4.4-4.5 WR rows per team-game. That likely excludes many zero-yard / no-target / low-usage WRs. Adding a blanket multiplier before fixing the validation universe could make season-long projections worse.

2. **Separate point-projection validation from simulator-distribution validation.**
   Comparing actual outcomes to projected means is not the same as comparing actual outcomes to simulated draws.

3. **Preserve the model's rank and MAE strengths.**
   The goal is not to chase KS at the expense of useful fantasy projections. Distribution changes should be checked against rank correlation, weekly MAE, season MAE, and directional accuracy.

4. **Diagnose before tuning.**
   Every objective should produce a diagnostic table or report that explains what changed and why.

5. **Use out-of-fold validation for calibration.**
   Any calibration layer should be trained and tested across seasons to avoid fitting noise:

   ```text
   train: 2022-2023, validate: 2024
   train: 2022+2024, validate: 2023
   train: 2023-2024, validate: 2022
   ```

---

## Repository Areas To Inspect

These are the likely code paths based on the current repository structure and validation behavior:

```text
scripts/validate.py
src/fantasy_sim/validation/parallel.py
src/fantasy_sim/data/actuals.py
src/fantasy_sim/engine/play_resolver.py
src/fantasy_sim/data/game_context.py
src/fantasy_sim/data/weather/engine.py
src/fantasy_sim/scoring/projection_layers.py
src/fantasy_sim/scoring/dynamic_blend.py
config/defaults.yaml
```

Also search for these symbols/functions/classes:

```text
_compute_distribution_ks
ks_2samp
build_player_projections
run_simulations
ActualPlayerWeek
receiving_yards_dist
select_receiver
_update_player_stats
trailing_late
leading_late_rb
market_history
projection_layers
```

---

# Objective 0 — Baseline, Reproducibility, And Safety Harness

## Goal

Create a stable baseline so every future objective can be compared apples-to-apples against the current defaults.

## Tasks

### 0.1 Create a baseline artifact directory

Create a local output folder for validation artifacts:

```text
artifacts/ks_roadmap/baseline/
```

Store:

```text
validate output text
config snapshot
commit SHA
runtime parameters
season list
sim count
seed mode
coverage readout
```

### 0.2 Add a lightweight validation mode

Keep the full 200-sim validation for final checks, but add or document a faster smoke-test mode for development.

Suggested modes:

```text
smoke:  2024 only, fewer sims, fast iteration
full:   2022-2024, 200 sims, final comparison
```

Do not use the smoke mode as final evidence for KS improvements; use it only to catch obvious regressions.

### 0.3 Add a compact comparison report

For every objective, produce a compact before/after table:

```text
metric                         baseline      candidate      delta
QB pass_yards KS
QB pass_yards mean proj
QB pass_yards mean actual
WR receiving_yards KS
WR receiving_yards mean proj
WR receiving_yards mean actual
WR receptions KS
fpts KS
weekly MAE
season MAE
QB rank_corr
WR rank_corr
```

## Acceptance Criteria

- Baseline can be reproduced deterministically.
- Baseline artifacts are stored and comparable.
- A smoke validation mode exists or is documented.
- No model logic changes yet.

---

# Objective 1 — Fix Metric Semantics: Mean KS vs Simulated-Draw KS

## Goal

Separate the current KS metric into two different concepts:

```text
1. actual outcomes vs projected means
2. actual outcomes vs simulated predictive draws
```

The current output appears to compute the first one. The simulator needs the second one too.

## Why This Matters

A projected mean should not have the same distribution as noisy NFL game outcomes. If the model improves MAE by producing better-smoothed means, KS against actual outcomes can get worse even though the simulator is better.

This explains the observed pattern:

```text
rank_corr: strong improvement
weekly MAE: strong improvement
season MAE: strong improvement
component KS: weak or worse
```

## Tasks

### 1.1 Rename the existing KS metric internally

Rename or label the current metric as:

```text
ks_actual_vs_projected_means
```

This makes the output more honest and prevents false interpretation.

### 1.2 Preserve per-simulation player stat draws

Currently the validation path appears to collapse simulations into player-level projected means before KS. Modify the validation flow so raw per-sim player stat draws can be passed to distribution metrics.

Desired conceptual shape:

```python
sim_draws = {
    (season, week, game_id, player_id): {
        "pass_yards": [sim_1_value, sim_2_value, ...],
        "receiving_yards": [sim_1_value, sim_2_value, ...],
        "receptions": [sim_1_value, sim_2_value, ...],
    }
}
```

Alternative storage shape is fine if it is easier:

```text
one row per season/week/game/player/sim/stat
```

### 1.3 Add simulated-draw KS

Add:

```text
ks_actual_vs_simulated_draws
```

Conceptual implementation:

```python
actual_values = []
simulated_values = []

for player_week in matched_player_weeks:
    actual_values.append(actual[player_week][stat])

    for sim_value in sim_draws[player_week][stat]:
        simulated_values.append(sim_value)

ks_sim_draws = ks_2samp(simulated_values, actual_values)
```

### 1.4 Add PIT diagnostics

For each player-week/stat, compute the percentile rank of the actual outcome inside that player's simulated distribution.

Conceptual implementation:

```python
pit = mean(sim_value <= actual_value for sim_value in sim_values)
```

Report:

```text
PIT mean
PIT p10/p25/p50/p75/p90
PIT histogram buckets
```

Interpretation:

```text
uniform-ish PIT: calibrated distribution
U-shaped PIT: simulated distribution too narrow
hump-shaped PIT: simulated distribution too wide
PIT skewed high: model biased low
PIT skewed low: model biased high
```

### 1.5 Optional: Add CRPS

Add CRPS for a proper probabilistic absolute-error metric.

For an empirical sample forecast:

```python
def empirical_crps(samples, actual):
    samples = np.asarray(samples)
    term1 = np.mean(np.abs(samples - actual))
    term2 = 0.5 * np.mean(np.abs(samples[:, None] - samples[None, :]))
    return term1 - term2
```

Use CRPS as a secondary metric, not a blocker.

## Output Format

Update `DISTRIBUTION KS` to show both metrics:

```text
QB pass_yards:
  point_mean_KS: 0.35
  sim_draw_KS:   0.xx
  PIT mean:      0.xx
  mean proj:     196.2
  mean actual:   221.9
```

## Acceptance Criteria

- Current KS is preserved but clearly labeled.
- Simulated-draw KS is added.
- PIT diagnostics are available for QB pass_yards and WR receiving_yards at minimum.
- Existing rank_corr and MAE reports still work.
- No distribution tuning yet.

---

# Objective 2 — Validation Universe Audit And Full-Grid Actuals

## Goal

Determine whether the WR receiving_yards issue is caused by comparing unconditional projections against a conditional actual sample.

## Why This Matters

Recent validation output showed approximately:

```text
2024 WR receiving_yards:
  n = 2424
  games = 272
  team-games = 544
  WR rows per team-game = 2424 / 544 = 4.46
```

That is probably not the full active/projected WR universe. If missing WRs are mostly zero-yard outcomes, actual WR receiving_yards mean is inflated.

A rough check:

```text
actual mean among current rows = 33.5
current WR rows/team-game = 4.46
if true WR universe ≈ 6.0 WR/team-game:

adjusted actual mean ≈ 33.5 * 4.46 / 6.0 = 24.9

projected mean = 24.8
```

This suggests the WR mean gap may be mostly a validation-universe artifact.

## Tasks

### 2.1 Add validation universe diagnostics

Before every KS line, compute and print:

```text
season
position
stat
team_games
actual_rows
projection_rows
joined_rows
actual_rows_per_team_game
projection_rows_per_team_game
joined_rows_per_team_game
actual_zero_count
actual_zero_rate
projection_zero_count
projection_zero_rate
actual_mean
projection_mean
actual_p25/p50/p75/p90/p95
projection_p25/p50/p75/p90/p95
```

### 2.2 Add KS location and signed CDF gap

For each KS result, report where the CDF gap is largest.

Desired output:

```text
KS location: 0.0 yards
signed gap: +0.18 actual_cdf_minus_projection_cdf
```

Interpretation examples:

```text
largest gap near 0 yards:
  zero-rate / participation / validation-universe problem

largest gap around 20-40 yards:
  mean/center problem

largest gap around 80-120 yards:
  tail/explosive-play problem
```

### 2.3 Add full-projection-universe validation mode

Build validation from the projection universe, then left-join actuals and fill missing stat values with zero.

Conceptual implementation:

```python
projection_grid = projection_rows[[
    "season",
    "week",
    "game_id",
    "player_id",
    "position",
    "team",
]]

actual_joined = projection_grid.merge(
    actual_stats,
    on=["season", "week", "game_id", "player_id"],
    how="left",
)

for stat in stat_columns:
    actual_joined[stat] = actual_joined[stat].fillna(0)
```

If `game_id` is not stable across both sides, use the existing player-week matching key and document the tradeoff.

### 2.4 Preserve the existing stats-row-only mode

Keep the current actual-row validation mode as:

```text
stats_row_only
```

Add the new one as:

```text
full_projection_universe
```

Report both until the team decides which one should be the primary health metric.

## Output Format

For WR receiving_yards, show:

```text
WR receiving_yards:
  stats_row_only:
    point_mean_KS: ...
    sim_draw_KS:   ...
    mean proj:     ...
    mean actual:   ...
    rows/team-g:   actual ... / projection ...

  full_projection_universe:
    point_mean_KS: ...
    sim_draw_KS:   ...
    mean proj:     ...
    mean actual:   ...
    rows/team-g:   actual ... / projection ...
```

## Acceptance Criteria

- Validation output clearly shows whether actual WR rows are missing zero/low-usage players.
- Full-universe zero-filled validation exists.
- WR receiving_yards is evaluated in both modes.
- No WR model multiplier is added before this objective is complete.

---

# Objective 3 — QB Pass Yards Decomposition

## Goal

Determine why QB pass_yards is consistently under-centered by roughly 25-31 yards per QB game.

Recent output:

```text
2022: proj 186.4 vs actual 217.3  delta -30.9
2023: proj 189.8 vs actual 218.6  delta -28.7
2024: proj 196.2 vs actual 221.9  delta -25.7
```

Unlike WR, this is less likely to be explained by missing zero rows. Treat it as a real calibration issue until diagnostics prove otherwise.

## Tasks

### 3.1 Add team passing decomposition

For each team-game and season aggregate, compute projected vs actual:

```text
team offensive plays
team pass attempts
team completions
team completion rate
team pass yards
team yards per attempt
team yards per completion
team sack count
team dropbacks
```

### 3.2 Add primary-QB decomposition

For each starting/primary QB game and season aggregate, compute projected vs actual:

```text
QB pass attempts
QB completions
QB completion rate
QB pass yards
QB yards per attempt
QB yards per completion
QB share of team pass attempts
QB share of team pass yards
```

### 3.3 Add explosive completion diagnostics

Because QB pass yards are attributed from completed receiver yardage, inspect the completed-pass yardage tail:

```text
completion >= 15 yards
completion >= 20 yards
completion >= 30 yards
completion >= 40 yards
completion >= 50 yards
```

Report:

```text
rate per team-game
rate per QB-game
share of total pass yards from explosive completions
```

### 3.4 Identify root cause bucket

Classify QB pass_yards deficit into one or more of these buckets:

```text
too few attempts
too low completion rate
too low yards per completion
too thin explosive tail
too much weather suppression
too much backup/QB-share leakage
team passing okay but primary QB allocation too low
```

## Output Format

Add a table like:

```text
QB PASS YARDS DECOMPOSITION

metric                         proj      actual    delta    ratio
team pass att/g
team comp/g
team comp rate
team pass yards/g
team YPA
team YPC
primary QB pass att/g
primary QB pass yards/g
primary QB YPA
primary QB share team yards
20+ completions/g
30+ completions/g
40+ completions/g
```

## Acceptance Criteria

- QB pass_yards deficit is decomposed into attempts, completions, YPC/YPA, and explosive tail.
- It is clear whether the issue is team-level passing volume or player-level QB allocation.
- No QB calibration is merged until this decomposition is available.

---

# Objective 4 — QB Pass Yards Calibration Layer

## Goal

Add a controlled, out-of-fold stat calibration layer for QB pass_yards.

## Why This Is Safe To Try

QB rank_corr is already strong, but the mean is consistently low. That is an ideal case for monotonic calibration:

```text
keep ordering mostly intact
shift/scale the stat distribution closer to actuals
improve component KS
```

## Tasks

### 4.1 Implement linear calibration

Start simple:

```python
calibrated_pass_yards = intercept + slope * raw_pass_yards
```

Fit by season folds:

```text
train: 2022-2023, validate: 2024
train: 2022+2024, validate: 2023
train: 2023-2024, validate: 2022
```

### 4.2 Keep calibration monotonic and bounded

Avoid extreme corrections.

Suggested initial guardrails:

```text
minimum multiplier: 0.95
maximum multiplier: 1.25
minimum calibrated yards: 0
```

If using intercept + slope, prevent negative low-end projections.

### 4.3 Adjust fantasy points consistently

When pass yards are changed, update fantasy points by the scoring config.

Conceptual implementation:

```python
old_pass_yards = row["pass_yards"]
new_pass_yards = calibrated_pass_yards

delta_yards = new_pass_yards - old_pass_yards
row["pass_yards"] = new_pass_yards
row["fpts"] += delta_yards * scoring_config.passing_yard
```

Do not double-count if a later projection layer recomputes fantasy points from component stats.

### 4.4 Compare against a blunt multiplier only as a diagnostic

Try a temporary diagnostic multiplier based on recent aggregate deficit:

```text
actual / projected ≈ 1.13-1.15
```

But do not ship a hard-coded global multiplier unless the out-of-fold calibration supports it.

### 4.5 Optional: isotonic calibration

If linear calibration improves the mean but harms quantiles, test isotonic regression.

Use isotonic only if:

```text
out-of-fold KS improves
rank_corr does not materially degrade
MAE does not materially degrade
```

## Acceptance Criteria

- QB pass_yards KS improves out-of-fold.
- QB pass_yards mean gap shrinks materially.
- QB rank_corr remains stable or improves.
- Weekly/season MAE does not regress materially.
- Fantasy points remain internally consistent with calibrated pass yards.

---

# Objective 5 — WR Receiving Yards Diagnostics After Full-Universe Validation

## Goal

After Objective 2 corrects the validation universe, determine whether WR receiving_yards still has a true model problem.

## Tasks

### 5.1 Re-evaluate WR receiving_yards in both validation modes

Compare:

```text
stats_row_only
full_projection_universe
```

For each, report:

```text
point_mean_KS
sim_draw_KS
mean proj
mean actual
zero rate proj
zero rate actual
p50/p75/p90/p95 proj
p50/p75/p90/p95 actual
KS location
signed CDF gap
```

### 5.2 Add WR rank-bucket diagnostics

Bucket receivers by projected target rank within team-game:

```text
WR1
WR2
WR3
WR4+
```

For each bucket, compare projected vs actual:

```text
targets
receptions
receiving_yards
yards per reception
yards per target
zero-target rate
zero-catch rate
zero-yard rate
60+ yard game rate
80+ yard game rate
100+ yard game rate
```

### 5.3 Add WR role diagnostics if available

Use PFF / local scraped data if available:

```text
routes
route participation
targets per route run
yards per route run
aDOT
slot/wide alignment
YAC
end-zone targets
deep targets
contested targets
```

Apply shrinkage. These fields can be noisy.

### 5.4 Check aggregate team receiving distribution

For each team-game:

```text
team WR receiving yards
WR share of team receiving yards
top WR share
second WR share
WR3+ share
```

This determines whether the issue is:

```text
total passing volume
WR share of passing volume
allocation among WRs
per-catch yardage / explosive tail
```

## Acceptance Criteria

- It is clear whether WR receiving_yards is still under-centered after zero-filled full-universe validation.
- WR issue is classified as one or more of:

  ```text
  validation universe
  target/reception volume
  WR share of team passing
  top-WR concentration
  yards per reception
  explosive tail
  ```

- No WR calibration or simulator tuning is merged until this classification is available.

---

# Objective 6 — Receiver Allocation And Game-Script Ablations

## Goal

Determine whether game-script and receiver-selection logic are flattening WR receiving_yards distributions.

## Why This Matters

The validation diagnostics showed many cases where trailing-late rank factors suppressed WR1/WR2 and boosted WR3+. That can help broad MAE while hurting distribution shape.

Potential failure mode:

```text
too few WR1/WR2 ceiling games
too many WR3/WR4 moderate games
too few 80+ yard WR outcomes
better MAE
worse KS
```

## Tasks

### 6.1 Run trailing-late ablation

Compare defaults against:

```yaml
game_script:
  trailing_late:
    enabled: false
```

Report:

```text
WR receiving_yards point_mean_KS
WR receiving_yards sim_draw_KS
WR receiving_yards mean
WR receiving_yards p90/p95
WR1/WR2/WR3+ receiving shares
QB pass_yards KS and mean
weekly MAE
season MAE
```

### 6.2 Run full game-script ablation

Compare defaults against:

```yaml
game_script:
  enabled: false
```

Use this as a diagnostic, not necessarily as a candidate fix.

### 6.3 Inspect target rank factor clamps

Current default appears to use a clamp around:

```text
[0.85, 1.25]
```

Test narrower and less-flattening variants:

```text
[0.90, 1.15]
[0.95, 1.10]
no rank factor adjustment
```

### 6.4 Add target concentration diagnostics

For each team-game and simulation:

```text
top receiver target share
second receiver target share
WR3+ target share
Herfindahl index of targets
Herfindahl index of receiving yards
```

Compare to actual.

### 6.5 Evaluate target selection feature path

Target selection is currently disabled in the latest validation coverage. Inspect whether enabling it improves:

```text
WR receiving_yards sim_draw_KS
WR receiving_yards p90/p95
WR rank_corr
WR MAE
```

Be careful: enabling target selection may improve realism but hurt current MAE if not calibrated.

## Acceptance Criteria

- We know whether trailing-late adjustments are helping or hurting WR distribution shape.
- We know whether target allocation is too diffuse.
- At least one candidate receiver-allocation change is identified or ruled out.

---

# Objective 7 — Completed-Pass Yardage And Explosive-Tail Modeling

## Goal

Improve the simulated distribution of passing and receiving yards if diagnostics show the completed-pass yardage tail is too thin.

## Why This Matters

In the play resolver, completed pass yardage flows into both:

```text
QB pass_yards
receiver receiving_yards
```

So a thin completed-pass yardage distribution can hurt both of the major weak KS metrics.

## Tasks

### 7.1 Audit receiving_yards_dist construction

Find where each player's `receiving_yards_dist` is built.

Inspect:

```text
mean
variance
min/max/clamps
sample size shrinkage
weather modifications
role modifications
fallback distributions
```

### 7.2 Compare simulated vs actual completed-pass yardage

For completed passes only, compare:

```text
mean yards/completion
median yards/completion
p75/p90/p95/p99 completion yards
20+ completion rate
30+ completion rate
40+ completion rate
50+ completion rate
```

Break out by:

```text
position: WR/RB/TE
receiver rank: 1/2/3+
role: short/intermediate/deep if available
team
season
```

### 7.3 Add a role-based mixture model if needed

If the simulated tail is too thin, add a mixture distribution:

```text
normal/short gain component
intermediate gain component
explosive component
```

Conceptual sample:

```python
if random() < explosive_prob:
    yards = sample_explosive_gain(player_role, defense_context)
else:
    yards = sample_regular_gain(player_role, defense_context)
```

Inputs to consider:

```text
aDOT
yards per route run
deep target rate
YAC
route participation
historical explosive rate
team offensive environment
opponent pass defense
```

Use shrinkage heavily.

### 7.4 Keep catch rate and yardage correlated

Avoid independently increasing yardage tail without accounting for lower catch rates on deep targets.

Better conceptual model:

```text
simulate target depth / target type
simulate catch probability conditional on target type
simulate yards after catch / completed yardage conditional on catch
```

This is more realistic than simply multiplying receiving yards.

## Acceptance Criteria

- Completed-pass yardage distribution better matches actual p90/p95/p99.
- QB pass_yards KS improves or mean gap shrinks.
- WR receiving_yards sim_draw_KS improves.
- WR/QB MAE and rank_corr do not materially regress.

---

# Objective 8 — Weather And Vegas Audit

## Goal

Determine whether weather or Vegas adjustments are suppressing passing too much or applying inconsistently.

## Tasks

### 8.1 Run weather ablation

Compare:

```text
defaults
defaults - weather
```

Report:

```text
QB pass_yards mean and KS
WR receiving_yards mean and KS
team pass attempts
team completion rate
team yards per completion
team yards per attempt
```

### 8.2 Check for weather double-penalization

Audit whether weather reduces both:

```text
catch rate
receiving_yards_dist / pass-yard factor
```

If both are reduced, quantify the combined effect.

### 8.3 Check weather data handling

Verify:

```text
indoor games excluded from outdoor weather penalties
roof games handled correctly
wind units correct
precipitation units/flags correct
temperature units correct
missing weather does not default to bad weather
weather penalties are not applied twice
```

### 8.4 Run Vegas ablation

Compare:

```text
defaults
defaults - vegas
```

Report:

```text
team play volume
team pass rate
QB pass_yards
WR receiving_yards
fpts MAE
```

### 8.5 Check Vegas propagation into play-calling buckets

Audit whether Vegas pass-rate or volume factors affect all relevant play-calling contexts, not only a default bucket.

Potential issue:

```text
Vegas adjustment modifies PlayCallingDist.default,
but many plays are governed by situation-specific buckets.
```

## Acceptance Criteria

- Weather is either ruled out or identified as a contributor to low passing yards.
- Vegas adjustments are either ruled out or identified as incomplete/misaligned.
- Any candidate fix has ablation evidence.

---

# Objective 9 — Market History And Stat-Specific Calibration

## Goal

Use market history, where available, to improve stat-level calibration without overfitting.

## Context

The validation coverage shows market history is partial for 2023 and 2024, and player props are not fully active in the validation run.

For QB pass_yards and WR receiving_yards, market lines can be strong calibration anchors if they are forward-valid and available before the game.

## Tasks

### 9.1 Verify market data path

For each of these markets, confirm whether historical data exists and is forward-valid:

```text
QB pass_yards
WR receiving_yards
receptions
rush_yards
pass_tds
anytime_td
```

Report:

```text
coverage by season
coverage by week
coverage by position
coverage by player rank
book count
line dispersion
snapshot timing
crosswalk match rate
```

### 9.2 Add stat-specific blend reporting

For each player-week/stat, report:

```text
raw model stat mean
market-implied stat mean
blend weight
final stat mean
```

### 9.3 Learn market-calibrated residuals

For covered seasons, train a mapping:

```text
raw model stat -> market-calibrated stat -> actual stat
```

Use this to improve non-market players via learned calibration.

### 9.4 Avoid leakage

Ensure market snapshots are only from before the game.

Add explicit assertions:

```text
snapshot_time < game_start_time
```

## Acceptance Criteria

- Market coverage is clearly reported.
- Stat-specific market blending is transparent.
- No post-game leakage is possible.
- Market calibration improves covered-season stat KS without harming uncovered-season behavior.

---

# Objective 10 — Reporting, Regression Gates, And Long-Term Health

## Goal

Turn the new diagnostics into a durable validation harness.

## Tasks

### 10.1 Add a KS health report

Create a report section that highlights:

```text
worst point_mean_KS metrics
worst sim_draw_KS metrics
largest mean biases
largest p90/p95 mismatches
largest zero-rate mismatches
largest PIT skew
```

### 10.2 Add regression thresholds

Define soft gates, not hard blockers initially:

```text
QB pass_yards mean gap should not worsen by > 5 yards
WR receiving_yards sim_draw_KS should not worsen by > 0.02
weekly MAE should not worsen by > 0.10
season MAE should not worsen by > 1.0
rank_corr should not drop by > 0.02
```

Tune these after observing several runs.

### 10.3 Save diagnostics as machine-readable artifacts

Store:

```text
JSON summary
CSV/parquet metric tables
text report
config snapshot
commit SHA
```

Suggested folder:

```text
artifacts/validation/{timestamp_or_commit}/
```

### 10.4 Add comparison command

Create or document a command that compares two validation runs:

```text
baseline artifact
candidate artifact
```

Output:

```text
metric deltas
position/stat deltas
season-level deltas
worst regressions
best improvements
```

## Acceptance Criteria

- Validation artifacts can be compared across commits.
- New distribution metrics are included in every full validation.
- A candidate change cannot quietly improve one metric while damaging core fantasy metrics.

---

# Recommended Execution Order

Do the objectives in this order:

```text
0. Baseline and reproducibility
1. Metric semantics: point-mean KS vs simulated-draw KS
2. Validation universe audit and full-grid actuals
3. QB pass_yards decomposition
4. QB pass_yards calibration
5. WR receiving_yards post-full-grid diagnostics
6. Receiver allocation and game-script ablations
7. Completed-pass yardage / explosive-tail modeling
8. Weather and Vegas audit
9. Market history / stat-specific calibration
10. Reporting and regression gates
```

The highest-leverage initial work is:

```text
Objective 1 + Objective 2 + Objective 3
```

Do not spend time tuning WR receiving_yards until Objective 2 is complete.

---

# Suggested Codex Task Prompts

Use these prompts one at a time.

## Codex Task 1 — Metric Semantics

```text
Inspect scripts/validate.py and the validation pipeline. Identify where distribution KS is computed and where simulation results are collapsed into projected means. Implement a new metric named ks_actual_vs_simulated_draws while preserving the existing KS as ks_actual_vs_projected_means. Add PIT diagnostics for QB pass_yards and WR receiving_yards. Keep the existing output working.
```

## Codex Task 2 — Validation Universe Audit

```text
Inspect src/fantasy_sim/data/actuals.py and scripts/validate.py. Add diagnostics for actual_rows, projection_rows, joined_rows, rows_per_team_game, zero rates, means, and p50/p75/p90/p95 for each position/stat KS calculation. Also add KS location and signed CDF gap. Do not change model behavior.
```

## Codex Task 3 — Full Projection Universe Validation

```text
Add a validation mode that uses the projection/player-week universe as the base grid, left-joins actual stats, and fills missing actual component stats with zero. Preserve the current stats-row-only mode. Report WR receiving_yards KS and mean in both modes.
```

## Codex Task 4 — QB Pass Yards Decomposition

```text
Add a QB pass_yards decomposition report comparing projected vs actual team passing volume, completions, completion rate, YPA, YPC, primary QB pass yards, QB share of team pass yards, and explosive completion rates. The goal is to determine whether QB pass_yards is low because of attempts, completion rate, yards per completion, explosive tail, or QB allocation.
```

## Codex Task 5 — QB Calibration Layer

```text
Implement an optional out-of-fold QB pass_yards calibration layer using intercept + slope or isotonic calibration. It should update pass_yards and fantasy points consistently. Add config flags to enable/disable it. Evaluate by season folds and report KS, mean gap, MAE, and rank_corr deltas.
```

## Codex Task 6 — WR Rank Bucket Diagnostics

```text
Add WR receiving_yards diagnostics by team target-rank bucket: WR1, WR2, WR3, WR4+. Compare projected vs actual targets, receptions, receiving_yards, YPR, YPT, zero rates, and 60+/80+/100+ yard game rates. Use this to classify whether WR KS is caused by volume, allocation, concentration, or tail behavior.
```

## Codex Task 7 — Game-Script Ablations

```text
Add a validation ablation runner or config override workflow to compare defaults against trailing_late disabled, all game_script disabled, and alternate target_rank_factor_clamp values. Report WR receiving_yards KS, p90/p95, target concentration, QB pass_yards KS, MAE, and rank_corr.
```

## Codex Task 8 — Completed-Pass Tail Audit

```text
Inspect how receiving_yards_dist is constructed and sampled. Add diagnostics comparing simulated vs actual completed-pass yardage distributions, including p75/p90/p95/p99 and 20+/30+/40+/50+ completion rates by position and receiver rank. Do not tune yet; just report.
```

## Codex Task 9 — Weather/Vegas Audit

```text
Add ablation reports for defaults vs weather disabled and defaults vs Vegas disabled. Audit whether weather penalties reduce both catch rate and receiving yardage, whether indoor/roof games are exempt, and whether Vegas pass-rate/volume adjustments propagate to all relevant play-calling contexts.
```

## Codex Task 10 — Validation Artifact Comparison

```text
Add machine-readable validation artifacts and a comparison command that compares two validation runs. Include point_mean_KS, sim_draw_KS, PIT, mean gaps, zero rates, p90/p95 gaps, MAE, season MAE, and rank_corr. Highlight best improvements and worst regressions.
```

---

# Decision Tree After Objectives 1-3

Use this to decide what to do next.

## If WR full-universe actual mean drops near projected mean

Conclusion:

```text
The WR receiving_yards mean issue was mostly validation-universe mismatch.
```

Next:

```text
Keep full-universe validation as primary.
Focus only on tail/concentration if p90/p95 or sim_draw_KS is still bad.
```

## If WR full-universe actual mean is still much higher than projected mean

Conclusion:

```text
WR model is truly under-projecting receiving yards.
```

Next:

```text
Run WR rank-bucket diagnostics.
Check target/reception volume, top-WR concentration, and YPR/explosive tail.
```

## If QB team pass yards are low

Conclusion:

```text
The issue is upstream team passing environment.
```

Next:

```text
Audit play volume, pass rate, completion rate, YPC, weather, and Vegas.
```

## If team pass yards are fine but primary QB pass yards are low

Conclusion:

```text
The issue is QB allocation / starter share / backup leakage.
```

Next:

```text
Inspect QB share assignment and player stat attribution.
```

## If attempts and completion rate are fine but YPC is low

Conclusion:

```text
The completed-pass yardage distribution is too low or too thin-tailed.
```

Next:

```text
Run completed-pass tail audit and consider role-based explosive mixture modeling.
```

## If point-mean KS is bad but simulated-draw KS and PIT are good

Conclusion:

```text
The simulator distribution is fine; the old KS metric was misleading.
```

Next:

```text
Keep both metrics, but stop treating point-mean KS as the main simulator-distribution health metric.
```

---

# Expected Early Outcomes

The most likely early outcome is:

```text
Objective 1:
  reveals that current KS is partly punishing projected means for being smoother than actual outcomes.

Objective 2:
  shows WR receiving_yards actual sample excludes many zero/near-zero WR outcomes.

Objective 3:
  shows QB pass_yards is genuinely low due to YPC/explosive-tail, team passing volume, or QB allocation.
```

If that happens, the practical next moves are:

```text
1. Use simulated-draw KS/PIT for simulator distribution health.
2. Use full-projection-universe validation for player stat components.
3. Add QB pass_yards calibration.
4. Improve completed-pass yardage tail if diagnostics support it.
5. Tune WR allocation/tail only after the validation universe is fixed.
```

---

# Changes To Avoid Initially

Avoid these until the diagnostics are complete:

```text
WR receiving_yards *= global_multiplier
QB pass_yards *= global_multiplier without out-of-fold validation
disabling weather permanently based on one run
changing game-script rank factors without rank-bucket diagnostics
tuning to point-mean KS only
optimizing KS while ignoring weekly MAE / season MAE / rank_corr
```

---

# Final Success Criteria

The roadmap is successful if the simulator can report and improve the following without damaging core fantasy quality:

```text
QB pass_yards:
  smaller mean gap
  improved point_mean_KS
  improved sim_draw_KS or calibrated PIT
  stable QB rank_corr and MAE

WR receiving_yards:
  validation universe clearly defined
  zero-rate mismatch resolved or explained
  improved sim_draw_KS
  better p90/p95 tail fit if needed
  stable WR rank_corr and MAE

Overall:
  weekly MAE does not regress materially
  season MAE does not regress materially
  fpts distribution remains reasonable
  validation reports are reproducible and machine-readable
```
