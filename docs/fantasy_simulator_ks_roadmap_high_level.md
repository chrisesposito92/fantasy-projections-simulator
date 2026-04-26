# Fantasy Projections Simulator — High-Level KS Improvement Roadmap

## Purpose

Improve distributional calibration for the simulator, with special focus on:

- **QB pass_yards KS**
- **WR receiving_yards KS**

The goal is not to blindly optimize KS at the expense of the already-strong ranking and MAE results. The goal is to determine whether the current KS weakness reflects a real simulator problem, a validation-universe issue, or a metric-design issue, then make targeted changes that preserve season-long projection quality.

---

## Guiding Principles

1. **Do not tune before validating the validation.**
   The current KS readout may be comparing actual outcomes against projected means rather than simulated outcome distributions.

2. **Separate model error from validation-population error.**
   WR receiving_yards likely has a population mismatch caused by missing zero/near-zero actual outcomes.

3. **Protect rank_corr and MAE.**
   Any KS improvement should be checked against weekly MAE, season MAE, and positional rank correlation.

4. **Prefer component-level diagnostics over blanket multipliers.**
   QB pass_yards should be decomposed into attempts, completions, yards per completion, explosive plays, and QB/team allocation before calibration.

5. **Treat QB and WR differently.**
   QB pass_yards appears more likely to be a true under-centering issue. WR receiving_yards appears more likely to be affected first by validation-universe mismatch, then by target concentration and tail modeling.

---

# Objective 1 — Establish Reliable Baselines

## Objective

Create a clear baseline for the current simulator and validation output so that later changes can be evaluated consistently.

## Acceptance Criteria

- Current `defaults` versus `bare` validation can be reproduced for 2022, 2023, and 2024.
- Output includes rank_corr, weekly MAE, season MAE, fpts KS, and component-stat KS.
- Baseline results are saved in a durable form that can be compared after each objective.
- No modeling changes are introduced in this objective.

---

# Objective 2 — Audit the Validation Universe

## Objective

Determine whether KS and mean gaps are being distorted by mismatched actual/projection populations, especially for WR receiving_yards.

## Acceptance Criteria

- Validation output reports row counts by season, position, and stat.
- Output includes actual rows per team-game and projected rows per team-game.
- Output includes zero-rate diagnostics for actuals and projections.
- WR receiving_yards validation clearly shows whether actual rows are closer to a full active WR universe or a conditional stats-row-only universe.
- The team can answer whether the WR receiving_yards mean gap is real or mostly caused by missing zero-yard players.

---

# Objective 3 — Add Full-Universe Actual Validation

## Objective

Validate projections against a complete player-week universe instead of only players present in actual stat rows.

## Acceptance Criteria

- A full player-week validation grid is available for projected/available players.
- Actual stats are left-joined onto the grid.
- Missing actual stat values are filled with zero where appropriate.
- Validation can report both:
  - stats-row-only results
  - full-universe zero-filled results
- WR, TE, and RB receiving metrics are re-evaluated under the full-universe approach.
- The team can determine whether WR receiving_yards KS still requires model changes after the population issue is addressed.

---

# Objective 4 — Correct the Distribution Metric Design

## Objective

Distinguish between projected-mean calibration and simulated-distribution calibration.

## Acceptance Criteria

- Existing KS is explicitly labeled as actuals versus projected means.
- A new simulated-draw KS metric is available.
- The simulator can compare actual outcomes against the full simulated outcome distribution, not only averaged projections.
- PIT or similar calibration diagnostics are available for key stats.
- The validation report makes it clear whether poor KS is caused by:
  - biased means,
  - under-dispersed simulations,
  - over-dispersed simulations,
  - tail-shape mismatch,
  - or validation-population mismatch.

---

# Objective 5 — Decompose QB Pass Yards

## Objective

Identify why QB pass_yards is consistently under-projected by roughly 25–31 yards per game.

## Acceptance Criteria

- Validation output decomposes QB pass_yards into meaningful components.
- At minimum, the report compares projected versus actual:
  - team pass attempts
  - team completions
  - completion rate
  - team pass yards
  - yards per attempt
  - yards per completion
  - primary QB pass yards
  - primary QB share of team passing
  - explosive completion rates
- The team can identify whether the QB pass_yards deficit is primarily caused by volume, efficiency, explosive-play tail, or QB/team allocation.
- No permanent QB calibration is added until the source of the deficit is understood.

---

# Objective 6 — Add QB Pass-Yards Calibration

## Objective

Correct any confirmed QB pass_yards under-centering while preserving strong QB rank correlation.

## Acceptance Criteria

- A stat-specific calibration layer exists for QB pass_yards.
- Calibration is trained and evaluated out-of-fold across 2022, 2023, and 2024.
- The calibrated result improves QB pass_yards KS and mean bias.
- QB rank_corr does not materially degrade.
- Weekly MAE and season MAE do not materially degrade.
- Fantasy points are adjusted consistently when pass_yards changes.
- Calibration can be disabled or compared against uncalibrated defaults.

---

# Objective 7 — Reassess WR Receiving Yards After Validation Fixes

## Objective

Determine whether WR receiving_yards still needs simulator changes after full-universe validation and simulated-draw KS are implemented.

## Acceptance Criteria

- WR receiving_yards is evaluated under both old and corrected validation modes.
- The report identifies whether the remaining issue is mean bias, insufficient variance, insufficient tail weight, or target allocation shape.
- WR receiving_yards changes are not made solely to satisfy the old projected-mean KS metric.
- Any remaining WR issue has a clear diagnosis before model tuning begins.

---

# Objective 8 — Improve Receiver Distribution Shape

## Objective

If WR receiving_yards remains poorly calibrated, improve the distributional shape of receiver outcomes without damaging projection quality.

## Acceptance Criteria

- WR receiving_yards distribution better matches actual p50, p75, p90, and p95 behavior.
- Spike-week frequency improves for relevant WR buckets.
- Zero and near-zero rates remain realistic.
- Target concentration by WR rank bucket is evaluated before and after changes.
- Changes preserve or improve WR rank_corr, weekly MAE, and season MAE.
- The simulator avoids simply inflating all WR receiving_yards with a broad multiplier.

---

# Objective 9 — Evaluate Game Script, Target Allocation, Weather, and Vegas Effects

## Objective

Run controlled ablations to determine whether existing contextual systems are helping or hurting distributional calibration.

## Acceptance Criteria

- Validation can compare defaults against targeted ablations.
- At minimum, the following can be evaluated:
  - game script on/off
  - trailing-late target-rank effects on/off
  - weather on/off
  - Vegas/context adjustments on/off
- Each ablation reports impact on:
  - QB pass_yards KS and mean
  - WR receiving_yards KS and mean
  - fpts KS
  - weekly MAE
  - season MAE
  - positional rank_corr
- Any contextual system that improves MAE but harms distribution is identified and documented.

---

# Objective 10 — Finalize Reporting and Regression Protection

## Objective

Make the improved validation suite durable so future model changes cannot silently regress KS, MAE, or rank correlation.

## Acceptance Criteria

- Validation reports include both point-mean and simulated-distribution metrics.
- Reports include population diagnostics for each stat/position pair.
- Reports include key distribution percentiles, not only means and KS.
- A before/after comparison is available for each objective.
- Regression thresholds are defined for:
  - QB pass_yards KS
  - WR receiving_yards KS
  - fpts KS
  - weekly MAE
  - season MAE
  - positional rank_corr
- The final validation output clearly distinguishes between model quality, simulation quality, and validation-population quality.

---

# Recommended Objective Order

1. **Establish Reliable Baselines**
2. **Audit the Validation Universe**
3. **Add Full-Universe Actual Validation**
4. **Correct the Distribution Metric Design**
5. **Decompose QB Pass Yards**
6. **Add QB Pass-Yards Calibration**
7. **Reassess WR Receiving Yards After Validation Fixes**
8. **Improve Receiver Distribution Shape**
9. **Evaluate Game Script, Target Allocation, Weather, and Vegas Effects**
10. **Finalize Reporting and Regression Protection**

---

# Decision Framework

## If WR receiving_yards improves after full-universe validation

Treat the original WR issue primarily as a validation-population problem. Avoid broad WR yardage inflation.

## If WR receiving_yards remains poor after full-universe validation

Focus on receiver distribution shape, target concentration, explosive-play modeling, and role-specific yardage tails.

## If QB pass_yards team totals are low

Investigate team passing volume, completion rate, yards per completion, weather, Vegas/context adjustments, and play-calling assumptions.

## If team passing totals are fine but QB pass_yards is low

Investigate QB allocation, starter share, backup leakage, and player/team attribution.

## If projected-mean KS is poor but simulated-draw KS is strong

The simulator distribution is likely acceptable. The old KS metric should not drive model changes.

## If both projected-mean KS and simulated-draw KS are poor

The simulator likely has a true distributional calibration problem that should be addressed in model logic or stat-specific calibration.

---

# Definition of Success

The roadmap is successful when:

- QB pass_yards KS improves or the remaining gap is clearly explained.
- WR receiving_yards KS improves under a corrected validation universe and corrected distribution metric.
- Rank correlation remains strong across positions.
- Weekly and season MAE do not materially regress.
- Validation output clearly separates projected-mean quality from simulated-distribution quality.
- Future simulator changes can be evaluated without ambiguity around population mismatch or metric interpretation.
