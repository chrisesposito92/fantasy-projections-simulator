# Distribution Calibration — Hypothesis Backlog

**Synthesized:** 2026-04-25
**Sources:** `MEAN_BIAS.md` (H-MB-01..13), `DISTRIBUTION_SHAPE.md` (H-DS-01..12), `SIGNAL_COVERAGE.md` (H-SC-01..12), `PHASE5_SLICES.md` (H-P5-01..05).
**Cross-ref:** `.planning/codebase/CONCERNS.md`.

The hard floor is: **no change ships if it regresses rank_corr by >0.005 or MAE by >0.05**. KS gain *under that floor* is the ranking signal.

## Top 3 Quick Wins

1. **KS-01: Fix the RZ TD-gate `_tackled_short()` truncation bug** — confirmed mechanism, hours of work, large gain on QB pass_yards / WR/TE/RB receiving_yards mean bias. Replaces a punitive rewrite with `min(yard_line - 1, sampled_yards)`. Files: `src/fantasy_sim/engine/play_resolver.py:43-49, 264-265, 279-284, 421-424`.
2. **KS-02: Enable `pff.rb_scheme_fit`** — only off-by-default slice with **already-positive** rank_corr / weekly_mae / season_mae deltas in its decision artifact (`+0.0018 / -0.003 / -0.040`). Targets the RB rush_yards 0.22→0.29 defaults regression. Hours of work.
3. **KS-03: Fix matchup engine's hardcoded `* 10.0` yard anchor** — replace with per-player `np.mean(receiving_yards_dist)` to mirror the (correctly-implemented) weather engine. Widens dynamic range for receiver yards adjustments. Files: `src/fantasy_sim/data/game_context.py:534-544, 591`.

## Quantitative Summary

| KS-ID | Theme | Source | Target Stat | KS Gain | Risk | Effort | Phase |
|-------|-------|--------|-------------|---------|------|--------|-------|
| KS-01 | A | H-MB-01 | QB pass_yards, WR/TE/RB receiving_yards | large | low-med | hours | P1 |
| KS-02 | C | H-P5-01 | RB rush_yards | medium-large | low | hours | P1 |
| KS-03 | A | H-MB-04 | WR/TE/RB receiving_yards | small-medium | low | hours | P1 |
| KS-04 | E | H-MB-02 | QB pass_yards, WR/TE/RB receiving_yards | medium-large | low | hours | P1 |
| KS-05 | A | H-MB-03 | QB pass_yards, WR/TE recv_yds | small-medium | low | hours | P1 |
| KS-06 | A | H-MB-06 | WR/TE receiving_yards (backups) | small | low | hours | P1 |
| KS-07 | E | H-MB-10 | WR/TE/RB receiving_yards | small | low | hours | P1 |
| KS-08 | B | H-DS-01 | fpts (TE/WR/RB) | large | medium | hours-days | P2 |
| KS-09 | B | H-DS-02 + H-MB-09 + H-DS-11 | All stat columns (per-stat residuals) | very large | medium | days-weeks | P2 |
| KS-10 | B | H-DS-05 + H-DS-12 | TE fpts | small-medium | very low | hours | P2 |
| KS-11 | B | H-DS-03 | WR/TE receiving_yards, RB rush_yards | medium-large | low-med | days | P2 |
| KS-12 | B | H-DS-04 | WR/TE receptions, RB rush_yards | medium | medium | days | P2 |
| KS-13 | B | H-DS-06 | fpts (TE/WR/RB) | medium | low | days | P2 |
| KS-14 | B | H-DS-07 | All yards distributions (rare buckets) | small-medium | very low | 1-2 days | P2 |
| KS-15 | A | H-DS-08 | QB pass_yards, WR receiving_yards | medium | low | days | P2 |
| KS-16 | C | H-P5-02 | WR/TE receiving_yards, WR/TE receptions | medium-large | low-med | days | P3 |
| KS-17 | C | H-P5-03 | QB pass_yards, WR/TE receiving_yards | medium | medium | days | P3 |
| KS-18 | C | H-P5-04 + H-P5-05 | QB rush_yards, RB rush_yards | small-medium | medium | hours-days | P3 |
| KS-19 | D | H-SC-01 | All 7 prop stats | large | low | 1-2 days | P4 |
| KS-20 | D | H-SC-05 | QB pass_yards/attempts/cmp/tds, WR recv_yds | medium | low | 2-3 days | P4 |
| KS-21 | D | H-SC-02 + H-SC-04 | QB pass_yards, WR recv_yds, RB rush_yds | large | low-med | 5-10 days | P4 |
| KS-22 | D | H-SC-03 | QB pass_yards | large | medium | 5-10 days | P5 |
| KS-23 | D | H-SC-06 | QB pass_yards | medium | low | 1-2 days | P5 |
| KS-24 | D | H-SC-07 | RB rush_yards (tail) | medium | low-med | 2-3 days | P5 |
| KS-25 | D | H-SC-10 | WR receiving_yards, WR receptions | small-medium | medium | 3-5 days | P5 |
| KS-26 | D | H-SC-08 + H-SC-12 | QB pass_yards (windy games) | small-medium | low | 2-3 days | P5 |
| KS-27 | D | H-SC-09 | WR/TE/RB receiving + rushing | medium | low | 2-3 days | P5 |
| KS-28 | D | H-SC-11 | WR receiving_yards | medium | low | <1 day | P5 |
| KS-29 | E | H-MB-07 | QB pass_yards, WR receiving_yards | small | low-med | hours | P1 |
| KS-30 | E | H-DS-09 | All yards (cross-week dispersion) | small | low | hours | P5 |
| KS-31 | E | H-DS-10 | kicker fpts, dst_tds | small | low | hours | P5 |
| KS-32 | E | H-MB-13 | QB pass_yards (volume) | small-medium | low | hours | P1 |
| KS-33 | E | H-MB-12 + H-MB-11 | QB pass_yards (sack/RZ TD validation) | small | low | hours-days | P5 |

## Suggested Phase Structure

Bug fixes first; structural per-stat calibration next; off-by-default activations after; new signal integration last.

### P1 — Bug fixes & cheap calibration (Top 3 + adjacents)

**Outcome target:** QB pass_yards mean bias closes from -28 to within ±10 yd/game; QB pass_yards KS drops to ≤0.28; WR receiving_yards mean bias closes from -9 to within ±4 yd/game; RB rush_yards KS recovers from 0.26 back to ≤0.23 (matches bare).

Hypotheses: KS-01, KS-02, KS-03, KS-04, KS-05, KS-06, KS-07, KS-29, KS-32. All hours of work; all confirmed mechanisms or already-validated artifacts.

Rationale: every item is an isolated low-risk change with a confirmed mechanism. Most expected per-item KS gain in the project. Doing this first removes signal noise that would otherwise muddy P2 and P3 measurements.

### P2 — Structural per-stat calibration

**Outcome target:** All stat-column KS values come out of the "fpts-only correction" bottleneck. TE receptions KS recovers from 0.32 to ≤0.25; WR receptions KS to ≤0.24; aggregate fpts KS to ≤0.20 (currently 0.15-0.25).

Hypotheses: KS-08 (dynamic_blend simulator-weight floor), KS-09 (per-stat `residual_calibration`), KS-10 (per-position `max_abs_adjustment` + TE elite tier), KS-11 (`tier_engine` reliability cap raised for high-touch players), KS-12 (share-normalization residual), KS-13 (ff_opportunity prior with width), KS-14 (Bayesian shrinkage for thin buckets), KS-15 (clamping fix bug-class change).

Rationale: KS-09 is the structural blocker — without per-stat residual calibration, all stat KS regressions remain unaddressable. KS-08 unblocks fpts KS by restoring simulator variance contribution. KS-10–KS-14 are tuning knobs that compose with KS-09. KS-15 is a follow-up clamping fix that preserves more upper-tail yardage; sequenced after P1 since P1 also touches the clamping/RZ stack.

### P3 — Off-by-default Phase 5 slice activation (KS-priority retune)

**Outcome target:** WR receiving_yards KS to ≤0.22; TE receiving_yards KS to ≤0.27; RB rush_yards KS to ≤0.21 (post-P1); QB pass_yards KS to ≤0.23.

Hypotheses: KS-16 (`pff.depth_role` + `pff.depth_role.efficiency` for WR/TE yards), KS-17 (`pff.qb_split` retuned for KS), KS-18 (QB designed-run + tracking.rb_efficiency stat-KS-specific re-measurement).

Rationale: Phase 5 slices were parked under rank_corr/MAE-priority validation. Under KS-priority floor, they may pass — but only after P1+P2 stabilize the baseline so Phase 5 measurements aren't contaminated by clamping/calibration noise.

### P4 — Cached unused signals (zero scrape cost first)

**Outcome target:** QB pass_yards KS to ≤0.20; WR receiving_yards KS to ≤0.20.

Hypotheses: KS-19 (`last_ten_json` empirical CDF blend), KS-20 (`projections_json` cross-stat consistency), KS-21 (Odds API alternate-line markets + props historical backfill).

Rationale: KS-19 is the highest-ROI new-signal item — data is already on disk in `~/.fantasy-sim/pff/props/props_*.parquet`, just needs to be parsed. KS-20 is adjacent. KS-21 builds the Odds API CDF pipeline which subsumes most of the future "variance shaping" work and unlocks a 2025+ validation path. Sequenced after P3 because the props signal's Bayesian-blend mechanism interacts with calibration constants tuned in P1/P2.

### P5 — Long-tail signal integration

**Outcome target:** QB pass_yards KS to ≤0.18; WR receiving_yards KS to ≤0.18; cross-position fpts KS to ≤0.16.

Hypotheses: KS-22 (`passing_detail` per-zone QB depth distribution), KS-23 (aDOT/time-to-throw priors), KS-24 (`rushing_summary.breakaway_*` columns for RB tail), KS-25 (`receiving_coverage.coverage_player_id` per-target CB matchup), KS-26 (wind direction + gusts), KS-27 (snap-count variance), KS-28 (NGS expected-yards re-validation), KS-30 (log-scale factor composition), KS-31 (kicker/DST shrinkage), KS-33 (sack rate + RZ TD gate validation).

Rationale: highest-engineering items, most uncertain payoff per item, but compose well after P1-P4 establish a stable baseline. KS-22 in particular is engineering-heavy (build a `QbDepthEngine`) and benefits from doing P3 retunes first so the KS deltas attribute correctly.

---

## Hypotheses

### A. Bugs

#### KS-01: Red-zone TD-gate replaces clamped yards with strictly shorter `_tackled_short()` values

- **Source:** H-MB-01
- **Theme:** A — Bug
- **Mechanism:** When a completed pass inside the 20 yields enough yards for a TD (`(yard_line - yards) <= 0`), `_red_zone_td_gate()` fires. If the gate fails (probabilities 0.55-0.15 → 45-85% chance of failure), `yards = _tackled_short(state.yard_line, rng)` overwrites the sample with `yard_line - rng.integers(1, max(2, yard_line // 3))` — strictly less than `yard_line`. At yard_line=15 this returns 10-14 (mean ~12) instead of the natural clamped sample of 15. Across the league: ~5-6 RZ pass attempts/game × ~3.5 completions × ~80% gate-fail × ~3-4 yards lost = **~10-15 yard/game shortfall on pass yards** from this mechanism alone.
- **Files:** `src/fantasy_sim/engine/play_resolver.py:43-49` (gate probabilities), `src/fantasy_sim/engine/play_resolver.py:279-284` (gate-fail rewrite), `src/fantasy_sim/engine/play_resolver.py:421-424` (`_tackled_short`).
- **Proposed change:** Replace the punitive rewrite. Cleanest variant: `yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))`. Preserves the sampled distance while denying the TD by reserving 1 yard short of the goal. Calibrated variant: only enforce "stopped 1 yard short" at goal-line distance (`yard_line ≤ 3`); outside the 3, use `min(yard_line - 1, sampled_yards)` directly.
- **Targeted KS metric(s):** QB pass_yards (primary), WR/TE/RB receiving_yards.
- **Expected KS gain:** **large.** Most-likely-single-biggest source of QB pass_yards mean bias.
- **Hard-floor risk:** **low-medium.** Slightly more RZ yards = slightly more fpts upside on RZ targets — should not change rank ordering. A/B with isolated flag would confirm.
- **Effort:** **hours** (≤30 lines + 6-10 unit tests).
- **Dependencies:** None. Self-contained.
- **Confidence:** **high** — mechanism grounded in source.

#### KS-03: `_apply_matchup` and `_apply_coverage` use hardcoded 10-yard anchor instead of distribution mean

- **Source:** H-MB-04
- **Theme:** A — Bug
- **Mechanism:** Matchup's `pass_yards_factor` (clamped [0.90, 1.10]) is converted to additive shift via `shift = (ctx.pass_yards_factor - 1.0) * 10.0`. NFL average yards/reception is ~11.5; the hardcoded 10.0 undersizes the shift by 15%. Symmetric so no league-wide mean bias, but compresses the per-game distribution variance. **`_apply_weather` correctly uses dynamic per-player `mean_yards`** (`game_context.py:701-712`), so this is an inconsistency bug, not a design decision.
- **Files:** `src/fantasy_sim/data/game_context.py:534-544` (matchup), `src/fantasy_sim/data/game_context.py:591` (coverage YPR modifier — same `* 10.0` pattern), `src/fantasy_sim/data/game_context.py:701-712` (weather — correct reference implementation).
- **Proposed change:** Replace `* 10.0` with `* float(np.mean(player.outcomes.receiving_yards_dist))` in matchup and coverage. Mirrors weather pattern.
- **Targeted KS metric(s):** WR/TE/RB receiving_yards (KS shape, not mean).
- **Expected KS gain:** **small-medium.** Widens per-game distribution to match real NFL spread.
- **Hard-floor risk:** **low.** Better-calibrated shifts produce more accurate expectations for high-volume receivers.
- **Effort:** **hours.**
- **Dependencies:** None.
- **Confidence:** **high** — bug is observable as an inconsistency vs `_apply_weather`.

#### KS-05: Player Props engine `_DEFAULT_TEAM_PASS_YDS = 230.0` is below NFL mean and `_apply_recv_yds` has a magnitude bug

- **Source:** H-MB-03
- **Theme:** A — Bug
- **Mechanism (constant):** `_apply_pass_yds()` uses `prop_ratio = prop_point / historical_pass_pg` with `historical_pass_pg = _DEFAULT_TEAM_PASS_YDS = 230.0` (production fallback). NFL 2022-2024 average is ~240-244. A 220-yd prop produces `ratio = 220/230 = 0.957`, blended down WR/TE distributions ~1.6% × dist_mean ≈ **3-4 yard/game**. **Mechanism (magnitude bug):** `_apply_recv_yds` line 248 computes `historical_season_yds = dist_mean * games_played`, treating per-catch dist_mean as if per-game. This dramatically underestimates historical season yards for any player with >1 catch/game. The blended ratio → `min_divergence` check at line 196 still triggers shifts, just incorrectly scaled.
- **Files:** `src/fantasy_sim/data/vegas/props_engine.py:43` (constant), `src/fantasy_sim/data/vegas/props_engine.py:248` (magnitude bug), `src/fantasy_sim/data/vegas/props_engine.py:380-409` (`_apply_pass_yds`).
- **Proposed change:** (1) Update `_DEFAULT_TEAM_PASS_YDS` to 240.0 or pass per-team rolling mean from pipeline. (2) Fix `_apply_recv_yds` formula to `historical_season_yds = dist_mean * catches_per_game * games_played`. (3) Long-term: pass actual historical pass yards from pipeline instead of using a default constant.
- **Targeted KS metric(s):** QB pass_yards, WR/TE receiving_yards (when props enabled).
- **Expected KS gain:** **small-medium.** Props is opt-in; impact only when active.
- **Hard-floor risk:** **low** — Bayesian weight protects against extreme shifts.
- **Effort:** **hours.**
- **Dependencies:** Only impactful if `vegas.props.enabled=true`.
- **Confidence:** **high** — both issues grounded in source.

#### KS-06: Backup receiver yards fallback is `rng.integers(3, 12)` — way below NFL average

- **Source:** H-MB-06
- **Theme:** A — Bug
- **Mechanism:** `play_resolver.py:268-271` falls back to `int(rng.integers(3, 12))` (uniform [3, 11], mean=7) when (a) the player has no `receiving_yards_dist` and (b) the team-bucket sample comes back ≤0. This produces a fallback mean of ~7 yards/catch vs NFL ~11.5.
- **Files:** `src/fantasy_sim/engine/play_resolver.py:268-271`, `src/fantasy_sim/data/player_builder.py:11` (`MIN_PLAYER_PLAYS = 5`).
- **Proposed change:** (1) Filter team-bucket distribution to completed plays only (in `preprocessor.py`). (2) Change integer fallback to `rng.integers(5, 18)` (mean=11). (3) Lower `MIN_PLAYER_PLAYS = 5` to 3 to give more players their own dist.
- **Targeted KS metric(s):** WR/TE receiving_yards (only for backups).
- **Expected KS gain:** **small** — affects backups with small target shares.
- **Hard-floor risk:** **low.**
- **Effort:** **hours.**
- **Dependencies:** None.
- **Confidence:** **high.**

#### KS-15: Field-position clamping truncates upper tail asymmetrically

- **Source:** H-DS-08
- **Theme:** A — Bug (composes with KS-01 and KS-04)
- **Mechanism:** `_clamp_yards()` truncates yards to `[max_loss, yard_line]`. A receiver whose 95th-percentile yards = 35 sampling at yard_line=20 gets the sample clamped to 20 — upper tail truncated more than lower, biasing mean down AND compressing upper tail. `CATCH_YARDS_BOOST=1` is documented as a band-aid for this (`play_resolver.py:32` comments).
- **Files:** `src/fantasy_sim/engine/play_resolver.py:32` (boost), `src/fantasy_sim/engine/play_resolver.py:265-274` (catch yards path samples then clamps), `src/fantasy_sim/engine/play_resolver.py:437-446` (`_clamp_yards`). `CONCERNS.md:108-114` flags this as fragile.
- **Proposed change:** Convert truncated samples into TDs rather than truncating to goal line. Currently the code clamps the sample to goal line and then a TD is detected by `state.yard_line - yards <= 0`. Restoring the un-clamped sample as `min(yard_line, sample)` for yards while using the un-clamped sample for the TD probability gate produces correct expected yards. **Bug-fix-class change.** May allow `CATCH_YARDS_BOOST` reduction to 0 in the same change.
- **Targeted KS metric(s):** QB pass_yards, WR receiving_yards (tail shape + mean).
- **Expected KS gain:** **medium.**
- **Hard-floor risk:** **low.** Need careful test work to avoid double-counting yards.
- **Effort:** **days.**
- **Dependencies:** Should ship after KS-01 (RZ TD gate fix) so they don't trade off; regression-test existing `PASS_TD_GATE` calibration.
- **Confidence:** **high** — well-mapped to source.

### B. Structural fixes

#### KS-08: `dynamic_blend` zeros the simulator weight, replacing fpts with point-estimate ff_opportunity mean

- **Source:** H-DS-01
- **Theme:** B — Structural
- **Mechanism:** Bundled artifact `dynamic_blend/decision_s200/weights_2024.json` shows `simulator ≤ 0.05, ff_opportunity ≥ 0.95` for nearly every TE/WR/RB bucket. `dynamic_blend.py:795-799` replaces `row["fpts"]` deterministically. ff_opportunity (`scoring/ensemble.py:97-105`) is itself a point estimate per (player, week). Since KS samples are means per (player, week), substituting a point estimate collapses across-player projection variance toward an ff_opportunity ridge.
- **Files:** `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json`, `src/fantasy_sim/scoring/dynamic_blend.py:795-799`, `src/fantasy_sim/scoring/ensemble.py:102-105`, `scripts/fit_dynamic_blend_weights.py` (re-fit).
- **Proposed change:** **Option A (lightest):** floor simulator weight at 0.30 in `_artifact_weights()` after `normalize_weights(...)`; clamp `weights[SIMULATOR_SOURCE] = max(weights[SIMULATOR_SOURCE], 0.30)` and renormalize. Re-fit with the floor in `fit_dynamic_blend_weights.py`. **Option B (better):** use ff_opportunity as a *shrinkage center* not a replacement: `proj_fpts = sim_fpts + alpha * (ff_opp - sim_fpts) + epsilon * randn()` where `epsilon` is per-bucket residual std.
- **Targeted KS metric(s):** fpts (TE/WR/RB primary).
- **Expected KS gain:** **large.** Dominant compression for TE/WR fpts.
- **Hard-floor risk:** **medium.** ff_opportunity is winning MAE because it's calibrated; restoring simulator weight will cost MAE. The 0.30 floor is a tunable knob — pick the smallest floor that recovers KS while staying within MAE +0.05.
- **Effort:** **hours** (Option A), **days** (Option B re-fit).
- **Dependencies:** Re-running `fit_dynamic_blend_weights.py` with new constraint; manual A/B.
- **Confidence:** **high** — confirmed by inspecting bundled artifact.

#### KS-09: Extend post-sim calibration to stat columns (per-stat `residual_calibration`)

- **Source:** H-MB-09 + H-DS-02 + H-DS-11
- **Theme:** B — Structural (architectural)
- **Mechanism:** `residual_calibration.py:422` writes only `row["fpts"]`. `dynamic_blend` only blends stat columns when `market_weight > 0`; bundled artifact has `market_weight = 0` for most TE buckets. Result: fpts gets corrected, stat columns retain raw simulator output (clamping bias, share normalization, tier-blend compression). KS measured on stat columns therefore has no remediation path. Compounding: `residual_calibration` writes a single per-bucket flat correction adding no within-bucket variance.
- **Files:** `src/fantasy_sim/scoring/residual_calibration.py:367-431` (adjuster), `scripts/fit_residual_calibration.py` (training), `src/fantasy_sim/scoring/projections.py:7-60` (where stat aggregations happen with no post-sim hook). Light variant requires changes to `scripts/validate.py:198-227`.
- **Proposed change:** **Tactical:** add per-stat residuals — extend `calibration_<season>.json` schema to include `buckets[bucket_key].stat_corrections.{pass_yards, receiving_yards, ...}`. In `adjust_week()`, after fpts correction, apply per-stat correction with clamp like `±2 * sqrt(actual_var)`. Re-derive fpts from corrected stats using scoring config to keep fpts internally consistent. **Light measurement upgrade (H-DS-11):** export per-stat quantiles (10th/50th/90th) and stddev through validation pipeline; add `within_player_ks` variant. **Deep variant:** propagate per-sim fpts arrays through `dynamic_blend`/`residual_calibration` so corrections become vector shifts rather than per-player flat adds.
- **Targeted KS metric(s):** All stat columns: QB pass_yards, WR/TE/RB receiving_yards, RB rush_yards, receptions.
- **Expected KS gain:** **very large.** Only mechanism that can target stat-level KS directly. Removes the structural bottleneck called out in `PROJECT.md:73-74`.
- **Hard-floor risk:** **medium.** fpts is a linear combination of stats; re-stating stats may produce inconsistent fpts. Need either (a) stat shifts produce fpts shifts that match existing residual_calibration, or (b) re-derive fpts from corrected stats and rerun residual_calibration. Easy to break the pipeline if not carefully composed. The `min_training_mae_delta=-0.01` gate (`defaults.yaml:375`) protects against bad corrections.
- **Effort:** **days–weeks** (tactical); add additional days for deep variant.
- **Dependencies:** Re-run `scripts/fit_residual_calibration.py` for stat-level artifacts. Composes with KS-08 (simulator-weight floor) and KS-15 (clamping fix) — measure those individually first so per-stat residuals don't bake in remediable biases.
- **Confidence:** **high** on structural diagnosis; **medium** on exact integration shape (depends on validation harness output design).

#### KS-10: `residual_calibration` `max_abs_adjustment` per-position + TE elite tier

- **Source:** H-DS-05 + H-DS-12
- **Theme:** B — Structural (calibration knob)
- **Mechanism:** `residual_calibration.py:109-111` clamps per-row correction to `max_abs_adjustment=1.5` regardless of position. For TE (usage tier `high=9.0, mid=4.0`) this is up to **37% of a mid-TE projection**. Same flat correction applied to every TE in the bucket → rigid translation, no within-bucket variance. Compounded with H-DS-12: TE thresholds collapse all viable TEs into "low" or "mid"; `calibration_2024.json:125-170` shows `TE|high|*` has no entries, so elite TEs always fall back to "missing_bucket" with zero correction while mid-TEs get the bucket-wide correction.
- **Files:** `src/fantasy_sim/scoring/residual_calibration.py:25-30` (`USAGE_TIER_THRESHOLDS`), `src/fantasy_sim/scoring/residual_calibration.py:109-111` (clamp lookup), `config/defaults.yaml:374` (`max_abs_adjustment`), `src/fantasy_sim/data/ensemble/artifacts/.../calibration_2024.json:125-170` (artifact evidence).
- **Proposed change:** Per-position cap in `defaults.yaml`:
  ```yaml
  ensemble.residual_calibration:
    max_abs_adjustment_by_position:
      QB: 2.5
      RB: 2.0
      WR: 1.5
      TE: 0.8
  ```
  Update `residual_calibration.py:109-111` to look up per-position cap. Add fourth "elite" tier above 14.0 fpts for TE (and lower `min_bucket_rows` for TE to 100 from 200) so Kelce/Andrews-class don't blend with mid-tier.
- **Targeted KS metric(s):** TE fpts (KS, MAE).
- **Expected KS gain:** **small-medium** for TE specifically.
- **Hard-floor risk:** **very low.** Loosens an over-aggressive cap and adds granularity.
- **Effort:** **hours** (config change + re-fit).
- **Dependencies:** Re-run `fit_residual_calibration.py`.
- **Confidence:** **high.**

#### KS-11: `tier_engine._blend_player()` proportionally resamples yards toward 250-element tier pool

- **Source:** H-DS-03
- **Theme:** B — Structural
- **Mechanism:** `tier_engine.py:1034-1052` samples `n_pbp = max(1, int(reliability * pool_size))` from player's PBP and `pool_size - n_pbp` from tier pool. With `pool_size=250` and `reliability` clipped to `[0.20, 0.80]`, the most reliable player still has 20% of yards distribution drawn from tier pool. Tier pools are aggregated across all players in tier — pulls every distribution toward tier center, compresses tails for elite players. After thin-tier merging (`tier_engine.py:441-477`), TE pools collapse to ~one fat-middle distribution.
- **Files:** `src/fantasy_sim/data/pff/tier_engine.py:1034-1052` (`_blend_yards`), `src/fantasy_sim/data/pff/tier_engine.py:441-477` (merge), `src/fantasy_sim/data/pff/tier_engine.py:961-965` (`position_reliability`), `src/fantasy_sim/data/pff/tier_engine.py:982` (`np.clip(raw, floor, cap)`), `config/defaults.yaml:82-84` (clamps + pool_size).
- **Proposed change:** Add `position_reliability` map for high-touch positions:
  ```yaml
  pff.tier_engine.position_reliability:
    WR: { floor: 0.30, cap: 0.95 }
    TE: { floor: 0.30, cap: 0.95 }
    RB: { floor: 0.25, cap: 0.92 }
  ```
  with `min_targets >= 30` / `min_carries >= 50` gate. Additionally: replace proportional resample with **mixture-of-CDFs at low frequency** — only blend in the 10th and 90th percentile bands, leave the body alone. Tier pool fills missing tails for thin-data players without compressing tails for high-data ones.
- **Targeted KS metric(s):** WR/TE receiving_yards (TE: large; WR: medium); RB rush_yards (medium).
- **Expected KS gain:** **medium-large.**
- **Hard-floor risk:** **low** for high-touch players; risk for thin-data players mitigated by tier-pool floor at 0.30.
- **Effort:** **1-2 days** (config + targeted re-test, no schema change).
- **Dependencies:** A/B validation.
- **Confidence:** **high** — mechanism well-documented in source.

#### KS-12: `_normalize_roster_shares` re-scales shares to sum to 1.0 every week, removing legitimate week-to-week variation

- **Source:** H-DS-04
- **Theme:** B — Structural
- **Mechanism:** `player_builder.py:618-693` rescales `target_share` and `carry_share` (and 6 RZ variants) to sum to 1.0. This is correct for selection-probability invariant but removes week-to-week variation. Called 9+ times per game build (after each adjustment layer that modifies usage; `game_context.py:1073-1259`). Each renormalize amplifies upstream drift and homogenizes target distributions across the roster.
- **Files:** `src/fantasy_sim/data/player_builder.py:618-693` (normalization), `src/fantasy_sim/data/player_builder.py:683-693` (`_scale_shares`), `src/fantasy_sim/data/player_builder.py:630` (`MIN_QB_CARRY_SHARE = 0.10` excludes pocket passers but no equivalent for backup TEs/WRs), `src/fantasy_sim/data/game_context.py:1073-1259` (9+ calls).
- **Proposed change:** Normalize to a target sum based on availability rather than exactly 1.0. Compute `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)`; let small remainders go to a "league-default" residual not allocated to any roster player. Compose with `availability` engine.
- **Targeted KS metric(s):** WR/TE receptions (medium); RB rush_yards (small).
- **Expected KS gain:** **medium** for WR/TE receptions.
- **Hard-floor risk:** **medium.** Calibration knob affecting mean targets — needs A/B validation that mean targets stay aligned with actuals.
- **Effort:** **days.**
- **Dependencies:** Coordinate with `availability` engine and player props blending.
- **Confidence:** **medium-high.**

#### KS-13: `ff_opportunity` is a point-estimate prior — load `prior_lo`/`prior_hi` for width

- **Source:** H-DS-06
- **Theme:** B — Structural
- **Mechanism:** `scoring/ensemble.py:97` reads `prior_fpts = float(prior["prior_fpts"])` — single scalar per (player, week). When `dynamic_blend` weight is high AND ff_opportunity dominates (KS-08), projections collapse toward ff_opportunity mean.
- **Files:** `src/fantasy_sim/scoring/ensemble.py:97-105`, `src/fantasy_sim/data/ensemble/normalizer.py` (potential `prior_lo`/`prior_hi` exposure), `src/fantasy_sim/data/ensemble/loader.py` (raw schema verification).
- **Proposed change:** Verify `total_fantasy_points_exp_lo` and `_hi` columns exist. Convert `prior_fpts` from scalar to Gaussian with mean = `prior_fpts`, std = `(prior_hi - prior_lo) / (2 * 1.28)` (80% interval). When `dynamic_blend` uses ff_opportunity at high weight, sample N independent fpts shifts per player.
- **Targeted KS metric(s):** fpts (TE/WR/RB).
- **Expected KS gain:** **medium.** Composes with KS-08; not a standalone fix.
- **Hard-floor risk:** **low** — adds noise centered on ff_opportunity mean, leaves rank ordering and mean unchanged.
- **Effort:** **days.**
- **Dependencies:** Verify ff_opportunity loader exposes lo/hi quantiles. Composes with KS-08.
- **Confidence:** **medium** — depends on whether quantile data is actually available.

#### KS-14: `MIN_BUCKET_PLAYS=10` fallback collapses thin-bucket variance

- **Source:** H-DS-07
- **Theme:** B — Structural
- **Mechanism:** `preprocessor.py:9, 100, 137` — when a `(play_type, GameStateBucket)` has fewer than 10 plays, the bucket is dropped from `distributions` and the simulator falls back to team-wide default. For rare buckets (4th-and-15+ inside the 5), every team uses the same default, removing across-team variance. Per-player buckets are even thinner.
- **Files:** `src/fantasy_sim/data/preprocessor.py:9` (`MIN_BUCKET_PLAYS = 10`), `src/fantasy_sim/data/preprocessor.py:100, 137` (guards), `src/fantasy_sim/engine/play_resolver.py:303, 393` (fallback chain).
- **Proposed change:** Lower `MIN_BUCKET_PLAYS` to 5 with Bayesian shrinkage prior on the parametric estimate: `samples = personal_plays + 5 * team_default_plays`. Add audit metric in `validation/coverage.py` reporting per-position fallback rate.
- **Targeted KS metric(s):** All yards distributions at rare game states.
- **Expected KS gain:** **small-medium.**
- **Hard-floor risk:** **very low** — Bayesian shrinkage is a soft version of the hard fallback.
- **Effort:** **1-2 days.**
- **Dependencies:** None.
- **Confidence:** **high.**

### C. Phase 5 Slice Activation

#### KS-02: Enable `pff.rb_scheme_fit` for RB rush_yards KS

- **Source:** H-P5-01
- **Theme:** C — Phase 5 activation
- **Mechanism:** Per-RB rushing-yards-distribution multiplicative scaling (clamp `[0.94, 1.06]`) conditioned on team scheme (gap vs zone) and RB directional preference. Directly reshapes `rushing_yards_dist` numpy array sampled in `play_resolver._resolve_run()`. **Decision artifact already shows positive deltas: `rank_corr Δ +0.0018, weekly_mae Δ -0.003, season_mae Δ -0.040`** — parked because lift was "too small to justify promotion" under rank/MAE-priority.
- **Files:** `src/fantasy_sim/data/pff/rb_scheme_fit.py:273-341`, `config/defaults.yaml:162-170`.
- **Proposed change:** Set `pff.rb_scheme_fit.enabled=true`. No code changes needed. If KS improves and QB/WR weekly regressions stay inside floor, promote.
- **Targeted KS metric(s):** RB rush_yards (KS, mean).
- **Expected KS gain:** **medium-large** — closest lever to RB rush_yards 0.22→0.29 gap.
- **Hard-floor risk:** **low** — already-positive decision artifact.
- **Effort:** **hours.**
- **Dependencies:** PFF `rushing_direction` and `offense_run_blocking` parquets (cached).
- **Confidence:** **high.**

#### KS-16: Enable `pff.depth_role` + `pff.depth_role.efficiency` for WR/TE receiving_yards KS

- **Source:** H-P5-02
- **Theme:** C — Phase 5 activation
- **Mechanism:** When `efficiency.enabled=true`, scales WR/TE `receiving_yards_dist` by yards-per-reception ratio AND scales `catch_rate` by observed catch efficiency. Volume mutations skipped (per `_volume_mutations_enabled()` gating at `depth_role.py:228`). Only WR/TE-specific layer that mutates the empirical receiving-yards array. Activated artifact: `rank_corr Δ +0.0000, weekly_mae Δ -0.002, season_mae Δ +0.030` — under rank/MAE-priority parked; under KS-priority floor potentially passes.
- **Files:** `src/fantasy_sim/data/pff/depth_role.py:148-160` (config), `src/fantasy_sim/data/pff/depth_role.py:277-317` (`apply_efficiency`), `src/fantasy_sim/data/pff/depth_role.py:387-394` (gating), `config/defaults.yaml:133-160`.
- **Proposed change:** Enable `pff.depth_role.enabled=true` AND `pff.depth_role.efficiency.enabled=true`. Run KS-priority A/B. If clamps `[0.94, 1.06]` / `[0.92, 1.08]` are too tight to move KS, widen to `[0.90, 1.10]` and re-run.
- **Targeted KS metric(s):** WR/TE receiving_yards (KS, mean); secondary WR/TE receptions.
- **Expected KS gain:** **medium-large.**
- **Hard-floor risk:** **low-medium.** Season MAE risk is the watchpoint; under KS-priority acceptable provided rank_corr stays at-zero.
- **Effort:** **days.**
- **Dependencies:** PFF `receiving_depth` parquet (cached). Best done after P1+P2 stabilize baseline.
- **Confidence:** **high.**

#### KS-17: Retune `pff.qb_split` sensitivities + re-enable for QB pass_yards mean bias

- **Source:** H-P5-03
- **Theme:** C — Phase 5 activation
- **Mechanism:** Per-game receiver-side adjustment from QB pressure splits in PFF `passing_detail`. Computes QB pressure-completion / clean-completion ratio + pressure-YPA / clean-YPA ratio, scales by current matchup pressure environment. Applies `catch_rate_factor` (clamp `[0.95, 1.05]`) and `yards_scale_factor` (clamp `[0.94, 1.06]`) to all eligible WR/TE pass-catchers — mutates `catch_rate`, `red_zone_catch_rate`, `receiving_yards_dist`. v1 artifact: `rank_corr Δ +0.0000, weekly_mae Δ +0.006, season_mae Δ +0.020`.
- **Files:** `src/fantasy_sim/data/pff/qb_split.py`, `config/defaults.yaml:172-181`.
- **Proposed change:** Lower `completion_sensitivity` from 0.10 to 0.06; lower `yards_sensitivity` from 0.12 to 0.08. Tighten gating: `min_pressure_dropbacks=30` (from 20), `min_clean_dropbacks=60` (from 40). Re-validate.
- **Targeted KS metric(s):** QB pass_yards (mean + KS), WR/TE receiving_yards (mean + KS).
- **Expected KS gain:** **medium.** High if mean bias is QB-specific; low if uniform across QBs.
- **Hard-floor risk:** **medium.** v1 regressed weekly_mae +0.006; retune lowers sensitivities, should reduce variance contribution.
- **Effort:** **days** (1 day toggle + measurement, 1-2 days retune).
- **Dependencies:** PFF `passing_detail` (cached); matchup engine enabled (default on).
- **Confidence:** **medium-high.**

#### KS-18: Stat-specific KS re-measurement of QB designed-run + isolated `tracking.rb_efficiency`

- **Source:** H-P5-04 + H-P5-05
- **Theme:** C — Phase 5 activation (re-measurement)
- **Mechanism (QB designed-run):** Replaces QB's `rushing_yards_dist` with mobility-tier-bucketed tail samples from learned artifact when designed-run play. Smoke evidence showed `fpts_ks Δ +0.003` regression but **stat-specific QB rush-yards KS was not isolated**. **Mechanism (rb_efficiency tracking):** 4-week rolling window of NGS rushing data scales RB `carry_share` and `rushing_yards_dist` by clamped `[0.93, 1.07]`. Same KS-shaping mechanism as KS-02 but on different signal. v1 had `weekly_mae Δ +0.000, season_mae Δ -0.063`.
- **Files:** `src/fantasy_sim/data/qb_rushing/runtime.py` (designed-run), `config/defaults.yaml:310-315` (designed-run), `src/fantasy_sim/data/tracking/rb_efficiency.py`, `config/defaults.yaml:317-342` (tracking). Artifacts at `results/qb_rushing/designed_runs/smoke_v1/` and NGS rushing parquet.
- **Proposed change:** (1) Enable QB designed-run chain temporarily for one A/B; measure stat-level KS for QB rushing_yards specifically (not aggregate fpts_ks). (2) Selectively enable `tracking.enabled=true, tracking.rb_efficiency.enabled=true` (other tracking slices off); measure RB rush_yards KS. Test stack vs conflict with KS-02.
- **Targeted KS metric(s):** QB rushing_yards; RB rush_yards.
- **Expected KS gain:** **small-medium.**
- **Hard-floor risk:** **medium.** QB designed-run smoke had `rank_corr Δ -0.0007` (inside hard floor) but TE weekly regressed -0.0049 (essentially at floor). Tracking rb_efficiency had flat weekly MAE.
- **Effort:** **hours** (designed-run KS-only re-measurement); **days** (rb_efficiency isolated re-test).
- **Dependencies:** Existing artifacts. Sequence after KS-02 to test stack vs conflict.
- **Confidence:** **medium** — both items are "re-measurement under new metric priority" rather than new code paths.

### D. New Signal Integration

#### KS-19: Use PFF `last_ten_json` as per-player empirical distribution prior

- **Source:** H-SC-01
- **Theme:** D — New signal (zero scrape cost)
- **Mechanism:** `last_ten_json` column in `~/.fantasy-sim/pff/props/props_*.parquet` contains last 10 game-level actuals per player+market (e.g., QB pass_yds: `[257, 205, 99, 264, 174, 190, 272, 316, 228, 262]`). PropsLoader / PlayerPropsEngine throw it away — only consume `consensus_line` (the mean). This is **literally an empirical sample of the player's recent distribution**. Replace the current Bayesian-blend on the mean with a **distribution-level blend**: form a kernel density (or empirical mix) from the 10-sample, blend with simulator's empirical at configurable weight, sample from mixture. The 10 historical results are samples from the player's distribution at the right time scale.
- **Files:** `src/fantasy_sim/data/vegas/props_loader.py:69-94` (parquet read), `src/fantasy_sim/data/vegas/props_engine.py:142-156` (consumption), `src/fantasy_sim/data/vegas/props_engine.py:_apply_recv_yds`, `:_apply_pass_yds` (mean-shift logic).
- **Proposed change:** Add `last_ten_dist` column extraction in `props_loader.py`. Add `_apply_distribution_blend` method in `props_engine.py`. Add config knob `vegas.props.last_ten_weight`. Weight by recency, drop samples >180 days old.
- **Targeted KS metric(s):** All 7 prop_keys: QB pass_yards, WR/TE receiving_yards, RB rush_yards, RB/WR/TE receptions, QB pass_tds, QB pass_attempts. Directly attacks KS-01..KS-07 from PROJECT.md.
- **Expected KS gain:** **large.** Fundamental KS issue is that simulator's per-game distribution is built from training-season aggregates and shrinks toward team/league means; the 10 most-recent actuals capture role and form changes that bucketed PBP doesn't.
- **Hard-floor risk:** **low.** Mean of 10-sample is close to consensus_line; replacing mean-only blend with distribution-aware blend that retains same mean keeps rank_corr stable. Tail risk: mid-season role change → bimodal 10-sample. Mitigation: recency weighting.
- **Effort:** **1-2 days.**
- **Dependencies:** None — data is cached. **Historical coverage caveat:** only 2025 props are scraped. For 2022-2024 backtest, this requires KS-21 (props historical backfill) or validation against 2025 only.
- **Confidence:** **high** on mechanism; **medium-high** on backtest validation due to data coverage.

#### KS-20: Read `projections_json` and `averages_json` for cross-stat consistency

- **Source:** H-SC-05
- **Theme:** D — New signal (zero scrape cost)
- **Mechanism:** `projections_json` field in props parquet contains PFF's full per-stat model: `{passingYards, passingAttempts, passingCompletions, passingTouchdowns, passingInterceptions, rushingYards, rushingAttempts, anyTimeTouchdowns}`. `averages_json` has recent-form season averages. Currently `PlayerPropsEngine` adjusts each stat independently. PFF's `projections_json` provides self-consistent multi-stat model.
- **Files:** `src/fantasy_sim/data/vegas/props_engine.py:151` (`_apply_market` independent-key loop), `src/fantasy_sim/data/vegas/props_loader.py` (parsing extension).
- **Proposed change:** Parse JSON columns in `props_loader.py`; add `_apply_consistent_multistat` method in `props_engine.py`. Use projection vector as multi-dimensional Bayesian prior: when `pass_yards` prop and `pass_attempts` prop disagree on direction, the prior is more informative.
- **Targeted KS metric(s):** QB pass_yards / pass_attempts / pass_completions / pass_tds / ints; WR receiving_yards (cross-stat: yards = receptions × YPR).
- **Expected KS gain:** **medium.** Smaller than KS-19 because most signal is already in consensus_line, but cross-stat consistency reduces independent-stat regression-to-mean compression.
- **Hard-floor risk:** **low** — PFF projections are professionally curated.
- **Effort:** **2-3 days.**
- **Dependencies:** None.
- **Confidence:** **high.**

#### KS-21: Scrape Odds API alternate-line markets + props historical backfill

- **Source:** H-SC-02 + H-SC-04
- **Theme:** D — New signal (paid + scraping infrastructure)
- **Mechanism (Odds API alt lines):** Markets `player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate` return multiple yardage thresholds + over/under prices per player. Convert prices to implied probabilities (`prob = 100 / (price + 100)` for negative, `prob = -price / (-price + 100)` for positive), de-vig pairs, construct empirical CDF: `P(pass_yds > threshold)` per line. Solve simulator's distribution to match: scale empirical PBP variance and/or mean such that simulated `P(X > threshold)` matches market for each line. **Goes beyond Bayesian-blending the mean — shapes the variance.** **Mechanism (historical backfill):** Per `INTEGRATIONS.md`, props cache is "current season only". Per `AB-TESTING.md`, historical props validation is an explicit coverage hole. Test PFF Consumer endpoint with historical season; fall back to Odds API if PFF historical access denied.
- **Files:** `scripts/scrape_odds_api.py` (new), `src/fantasy_sim/data/vegas/odds_api_loader.py` (new), `src/fantasy_sim/data/vegas/props_engine.py:apply()` (variance fitting after current mean-blend), `~/.fantasy-sim/odds/` (cache), `~/.fantasy-sim/props/.env` (key already exists), `scripts/scrape_pff_props.py` (extend for historical seasons).
- **Proposed change:** (1) Probe PFF Consumer API `/{season}/player-props/{week}` with 2022-2024 — test if historical works. (2) Write `scrape_odds_api.py` analogous to `scrape_pff_props.py` for alt-line endpoints; cache as parquet at `~/.fantasy-sim/odds/`. (3) Build `OddsApiCdfLoader`. (4) Wire variance-fitting in `PlayerPropsEngine.apply()`.
- **Targeted KS metric(s):** QB pass_yards (KS-01 primary — alt-line passing markets typically have 5-7 lines per QB), WR receiving_yards (KS-02), WR receptions (KS-03), RB rush_yards (KS-06), TE receptions (KS-04).
- **Expected KS gain:** **large.** Most direct CDF-construction signal external to simulator.
- **Hard-floor risk:** **low** for line means; **low-medium** for distribution shaping if vig mishandled.
- **Effort:** **3-5 days** (scrape + load + wire); **+1 day** (PFF historical investigation); **+2-3 days** if PFF historical works; **+5-10 days** if must fall back to Odds API for backfill.
- **Dependencies:** Odds API key (exists). Cost ~$30-150/mo depending on tier. Historical alt-line coverage may be enterprise-only at Odds API. Pair with KS-19 which has backward-looking 10-game window.
- **Confidence:** **high** on mechanism; **medium** on data coverage feasibility.

#### KS-22: Replace mean-only QB-pass-yds shift with per-zone distribution from `passing_detail`

- **Source:** H-SC-03
- **Theme:** D — New signal (cached, requires new engine)
- **Mechanism:** `passing_detail` has 898 cols per QB-game with per-zone breakdowns: `{left,center,right} × {behind_los, short, medium, deep}` for `attempts`, `completions`, `yards`, `accuracy_percent`, `qb_rating`. Plus context splits: `pa_*` (play-action), `blitz_*`, `pressure_*`, `screen_*`. **Per-QB depth-of-target distribution at game grain.** For each QB, build per-zone yards distribution from training-season `passing_detail` rows; combine with QB's per-zone attempt rate. Captures both mean (Justin Fields aDOT vs Brock Purdy aDOT) and **variance** (deep-heavy QBs have heavier tails).
- **Files:** `src/fantasy_sim/data/pff/passing_detail.py` (referenced by disabled QbSplitEngine — only for receiver factors), `src/fantasy_sim/engine/play_resolver.py` (current league-wide depth/yards relationship). New: `QbDepthEngine`.
- **Proposed change:** (1) Build `QbDepthEngine` reading per-QB zone attempts/yards from `passing_detail`. (2) Wire into `play_resolver.py` as yards-distribution selector keyed by QB+zone instead of league-wide bucket. (3) Bayesian shrinkage to position+aDOT-bucket priors for thin-data QBs.
- **Targeted KS metric(s):** QB pass_yards (primary).
- **Expected KS gain:** **large.** Current QB pass_yards distribution lacks inter-QB variance from depth tendencies because all QBs draw yards from same league-level depth/yards relationship. Per `hypotheses-list.md` parked `play_call_model` experiment ("QB pass-yards KS worsened in every tested season"), pass-volume changes alone don't fix QB pass_yards distribution shape.
- **Hard-floor risk:** **medium.** Shifts QB-specific per-zone distributions could affect WR yardage (yards = QB depth × WR completion). Validate against constraint that high-aDOT QBs may not actually outscore low-aDOT QBs in fantasy.
- **Effort:** **5-10 days.**
- **Dependencies:** None — data cached. Coverage gap: QBs <100 dropbacks have thin per-zone samples; mitigation Bayesian shrinkage.
- **Confidence:** **medium** — large new engineering item.

#### KS-23: aDOT and time-to-throw priors from `passing_summary`

- **Source:** H-SC-06
- **Theme:** D — New signal (cached)
- **Mechanism:** `passing_summary.avg_depth_of_target` and `avg_time_to_throw` per QB-game directly index pass distribution shape. High-aDOT QBs have heavier pass_yards tails; low-aDOT QBs have tighter distributions. Long-developing throws → bimodal (deep completion or sack). TierEngine reads `passing_summary` for QB but only grade columns (`grades_pass`, `grades_offense`, `twp_rate`, `btt_rate`); aDOT and time-to-throw excluded by metadata filter.
- **Files:** `src/fantasy_sim/data/pff/tier_engine.py:317-322` (current grade-only read).
- **Proposed change:** Add aDOT-conditional variance scaling in QB yards-distribution sampling.
- **Targeted KS metric(s):** QB pass_yards.
- **Expected KS gain:** **medium.** Smaller than KS-22 because aDOT is one summary number per QB vs full per-zone distribution; much cheaper to wire.
- **Hard-floor risk:** **low.** aDOT well-known; using as variance scaler doesn't shift mean.
- **Effort:** **1-2 days.**
- **Dependencies:** None.
- **Confidence:** **high.**

#### KS-24: Use `rushing_summary.breakaway_*` columns for RB rush_yards tail

- **Source:** H-SC-07
- **Theme:** D — New signal (cached)
- **Mechanism:** `rushing_summary.breakaway_attempts`, `breakaway_yards`, `breakaway_percent`, `explosive` per RB-game. RB long-run frequency = direct tail signal. Currently simulator samples rushing yards from league-level empirical per game state. Per-RB breakaway rate governs tail. Add per-RB explosive-run probability (Bayesian-shrunk to position prior with low n) and route those rushes to dedicated long-run distribution. TierEngine reads `rushing_summary` for RB but only grades; RbSchemeFitEngine uses direction only.
- **Files:** `src/fantasy_sim/data/pff/tier_engine.py:317-322`, `src/fantasy_sim/data/pff/rb_scheme_fit.py` (uses direction not breakaway).
- **Proposed change:** Add per-RB breakaway probability + dedicated long-run distribution.
- **Targeted KS metric(s):** RB rush_yards (tail).
- **Expected KS gain:** **medium.** Inter-RB tail variance (Saquon Barkley vs Najee Harris) flattened by league-level distribution.
- **Hard-floor risk:** **low-medium.** Risk of compounding with TierEngine if both adjust rushing distribution.
- **Effort:** **2-3 days.**
- **Dependencies:** None. Sequence after KS-02 (rb_scheme_fit) to test stack vs conflict.
- **Confidence:** **high.**

#### KS-25: Use `receiving_coverage.coverage_player_id` for per-target CB matchup conditioning

- **Source:** H-SC-10
- **Theme:** D — New signal (cached)
- **Mechanism:** `receiving_coverage` has 40-col per-target table including `targets`, `receptions`, `yards`, `yards_after_catch`, `yards_per_reception`, `targeted_qb_rating` per (WR, defender) matchup with `coverage_player_id` linking each WR-game to primary defender. Current `CoverageEngine` uses `defense_coverage_matchup` for alignment-based pairing (RWR→LCB) at season-mean catch-rate scaling, with clamps `[0.97, 1.03]` (very tight). Shadow corners (Sauce Gardner) compress WR yards more than zone-heavy CBs regardless of season-mean grade.
- **Files:** `src/fantasy_sim/data/pff/coverage.py` (current alignment-based logic), `~/.fantasy-sim/pff/processed/nfl/receiving_coverage_*.parquet` (unused data).
- **Proposed change:** Use per-target `receiving_coverage` for actual matchups. Widen clamps if KS supports.
- **Targeted KS metric(s):** WR receiving_yards, WR receptions.
- **Expected KS gain:** **small-medium.** Bounded by how deterministic CB-WR pairing is week-over-week.
- **Hard-floor risk:** **medium.** Coverage matchups noisy week-over-week.
- **Effort:** **3-5 days.**
- **Dependencies:** None.
- **Confidence:** **medium.**

#### KS-26: Wind direction + gusts + hourly variance to weather provider

- **Source:** H-SC-08 + H-SC-12
- **Theme:** D — New signal (free)
- **Mechanism:** Open-Meteo currently returns only `wind_speed_10m, temperature_2m, precipitation, snowfall`. Free additional params: `wind_direction_10m`, `wind_gusts_10m`, `relative_humidity_2m`, `dew_point_2m`, `pressure_msl`. Wind direction relative to passing axis affects deep-ball pass_yards tail; gusts add variance independent of mean wind. Hourly raw values currently averaged into 3-hour scalar (`provider.py:170-172`).
- **Files:** `src/fantasy_sim/data/weather/provider.py:18` (`_HOURLY_PARAMS`), `src/fantasy_sim/data/weather/stadiums.py` (orientation table), `src/fantasy_sim/data/weather/engine.py:71-78` (clamp), `src/fantasy_sim/data/weather/provider.py:170-180` (averaging).
- **Proposed change:** (1) Update `_HOURLY_PARAMS` with new fields. (2) Add stadium orientation table. (3) Update `WeatherContext` fields. (4) Rewire `WeatherEngine.compute_weather_factors` for direction. (5) Use min/max/std of hourly within kickoff+3h window as additional features.
- **Targeted KS metric(s):** QB pass_yards (windy outdoor games — ~25% of games).
- **Expected KS gain:** **small-medium.**
- **Hard-floor risk:** **low.** Adding shape doesn't change means.
- **Effort:** **2-3 days.**
- **Dependencies:** None — Open-Meteo free.
- **Confidence:** **high.**

#### KS-27: Snap-count variance as opportunity-variance signal

- **Source:** H-SC-09
- **Theme:** D — New signal (cached)
- **Mechanism:** Per-player-week `offense_snaps`, `offense_pct` from `load_snap_counts`. Variance of `offense_pct` across weeks measures how predictable a player's snap share is — 60%-snap player who fluctuates 40-80% has more opportunity variance than steady 60%. Currently engine treats snap share as point estimate. Compute trailing snap-pct std; use as variance multiplier on `target_share` / `carry_share` at sampling time.
- **Files:** `src/fantasy_sim/data/usage/engine.py:726`, `src/fantasy_sim/data/availability/loader.py:101` (current mean-only consumption).
- **Proposed change:** Compute trailing snap-pct std per player; use as variance multiplier.
- **Targeted KS metric(s):** WR/TE receiving (KS-02..KS-05); RB rushing/receiving (KS-06, KS-07).
- **Expected KS gain:** **medium.**
- **Hard-floor risk:** **low.**
- **Effort:** **2-3 days.**
- **Dependencies:** None.
- **Confidence:** **high.**

#### KS-28: NGS expected_yards re-validation under KS-priority

- **Source:** H-SC-11
- **Theme:** D — New signal (cached, code already exists)
- **Mechanism:** NGS publishes `expected_yards`, `air_yards`, `target_separation`, `cushion`, `racr`, `pacr`. Delta between actual and expected captures over/under-performance. Per memory, NGS+route_rate were tested and kept off — but **test was for rank_corr**. NGS expected metrics may improve KS distribution shape without improving rank correlation, since they're variance proxies more than means.
- **Files:** `src/fantasy_sim/data/usage/engine.py:497` (current gating on `usage.ngs.enabled=true`).
- **Proposed change:** Re-run NGS A/B with KS as primary metric, not rank_corr.
- **Targeted KS metric(s):** WR receiving_yards (KS-02), QB pass_yards via `pacr` (KS-01).
- **Expected KS gain:** **medium.**
- **Hard-floor risk:** **low** — already known to be neutral-to-slightly-negative on rank_corr per memory.
- **Effort:** **<1 day** to re-validate with existing harness focused on KS.
- **Dependencies:** None.
- **Confidence:** **medium-high.**

### E. Calibration Constant Retuning

#### KS-04: `CATCH_YARDS_BOOST = 1` is undersized AND disabled in red zone

- **Source:** H-MB-02
- **Theme:** E — Calibration constant
- **Mechanism:** The `+1 yard/catch` boost was added to compensate for `_clamp_yards()` truncation but is hardcoded to +1. Explicitly disabled inside the 20 (`boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0`). Current observed shortfall is ~1.0-1.4 yd/completion. With 22 completions/game, +1 buys back 22 yd/game total — not enough; need +1.4-1.8. RZ disablement leaves entire RZ pass yard problem (KS-01) without compensation.
- **Files:** `src/fantasy_sim/engine/play_resolver.py:32` (`CATCH_YARDS_BOOST`), `src/fantasy_sim/engine/play_resolver.py:264-265` (RZ gate).
- **Proposed change (best→worst):** (1) Best: condition boost on `_clamp_yards` actually firing — if `raw_yards > yard_line` (clamped TD/near-TD), boost +1.5-2.0; else +0. Tied to actual cause. (2) Reasonable: increase to `CATCH_YARDS_BOOST = 2` outside RZ. (3) Quick: drop the `if state.yard_line > 20` gate to apply boost in RZ too — combined with KS-01 fix, restores ~5 yd/game.
- **Targeted KS metric(s):** QB pass_yards, WR/TE/RB receiving_yards.
- **Expected KS gain:** **medium-large.** Each +0.5 yard/catch ≈ 11 yd/game per QB.
- **Hard-floor risk:** **low.** Boost is uniformly applied; rank ordering unchanged. MAE may improve.
- **Effort:** **hours.**
- **Dependencies:** **KS-01 must ship first** — otherwise RZ portion of boost compounds with `_tackled_short` truncation. KS-15 also adjusts the clamping stack; sequence carefully.
- **Confidence:** **high.**

#### KS-07: `RZ_CATCH_RATE_MODIFIER = 0.92` should be position-specific

- **Source:** H-MB-10
- **Theme:** E — Calibration constant
- **Mechanism:** Inside the 20, catch rate is multiplied by 0.92 (or replaced with player-specific RZ rate when ≥10 RZ targets). Real NFL RZ catch rates are positionally heterogeneous: RBs ~0.85, WRs ~0.92, TEs ~0.95.
- **Files:** `src/fantasy_sim/engine/play_resolver.py:60`, `src/fantasy_sim/data/player_builder.py:520`.
- **Proposed change:** Replace single constant with `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`.
- **Targeted KS metric(s):** WR/TE/RB receiving_yards (via missed catches).
- **Expected KS gain:** **small** — RZ catches are small fraction of all catches.
- **Hard-floor risk:** **low.**
- **Effort:** **hours.**
- **Dependencies:** None.
- **Confidence:** **high.**

#### KS-29: Re-enable `pff.team_context` for pass-rate scaling

- **Source:** H-MB-07
- **Theme:** E — Calibration / activation
- **Mechanism:** `pff.team_context.enabled=false` in `defaults.yaml:104` means simulator has no team-level pass volume signal beyond Vegas spread. Pass-heavy teams (KC, BUF) are normalized to same pass rate as run-heavy teams (BAL, ATL). Tier engine still uses `pass_rate_factor` in `apply_team_context` but with team_context off, factor defaults to 1.0.
- **Files:** `config/defaults.yaml:103-110`, `src/fantasy_sim/data/pff/tier_engine.py:1196-1215` (`apply_team_context`).
- **Proposed change:** A/B with `pff.team_context.enabled=true` and `pass_rate_sensitivity=0.05`.
- **Targeted KS metric(s):** QB pass_yards, WR receiving_yards.
- **Expected KS gain:** **small** — rate adjustments not yards adjustments.
- **Hard-floor risk:** **low-medium.** May regress rank_corr for run-heavy teams.
- **Effort:** **hours** to enable + A/B.
- **Dependencies:** A/B harness with team_context isolated.
- **Confidence:** **medium.**

#### KS-30: Fit factor sensitivities on log-scale to stabilize multiplicative composition

- **Source:** H-DS-09
- **Theme:** E — Calibration / hygiene
- **Mechanism:** Pipeline applies vegas pace + pass rate, matchup (7 factors), team_context (3), rb_scheme_fit, qb_split, depth_role, coverage, weather (3). Each factor centered on 1.0 and clamped. With clamps `matchup [0.90, 1.10]`, `team_context [0.90, 1.10]`, `coverage [0.97, 1.03]`, `weather [0.80, 1.20]`, `vegas.itt [0.88, 1.12]`, `vegas.spread [0.92, 1.08]`, simultaneous favorable factors product reaches 1.81 — but each independently clamped means realization rarely reaches full product. Compresses cross-week dispersion.
- **Files:** `src/fantasy_sim/data/pff/matchup.py:43`, `src/fantasy_sim/data/pff/tier_engine.py:982`, all factor-using engines.
- **Proposed change:** Fit on log-scale: `log_factor = z * sensitivity_log` clamped in log-space; then `factor = exp(log_factor)`. Equivalent for small z; stabilizes multiplicative composition. Geometric mean of factors stays at 1.0.
- **Targeted KS metric(s):** All yards (cross-week dispersion).
- **Expected KS gain:** **small** — most factors are ±10% with sensitivities ≤0.075.
- **Hard-floor risk:** **low** — mathematical equivalence at small z.
- **Effort:** **hours per engine; touches all factor-using engines.**
- **Dependencies:** Re-tuning sensitivities; hygiene fix not primary KS lever.
- **Confidence:** **medium-high.**

#### KS-31: Bayesian shrinkage in kicker / DST uses `prior_strength` too high

- **Source:** H-DS-10
- **Theme:** E — Calibration constant
- **Mechanism:** `kicker.py:124-127` shrinks kicker FG rate with `prior_strength=20`. Kicker with 30 short FG attempts: weight = 30/(30+20) = 0.60 → 40% league mean. Same in `dst_baseline.py:213-225` (`prior_strength=10`) and `td_tendency` (`prior_strength=20`). High prior pulls all teams/players toward league mean, compressing across-team variance.
- **Files:** `src/fantasy_sim/data/pff/kicker.py:127`, `src/fantasy_sim/data/pff/dst_baseline.py:213-225`, `config/defaults.yaml:186, 461`.
- **Proposed change:** Lower kicker `prior_strength` to 10; DST to 5. For TD tendency, raise `min_opportunities` from 5 to 8 instead of lowering prior.
- **Targeted KS metric(s):** kicker fpts; dst_tds; fumbles_lost.
- **Expected KS gain:** **small** — kicker/DST not in priority KS targets per PROJECT.md scope (out of scope).
- **Hard-floor risk:** **low.**
- **Effort:** **hours.**
- **Dependencies:** A/B validation.
- **Confidence:** **high.** **Note:** kicker/DST KS is **out of scope** per PROJECT.md ("DST and Kicker stay as-is — KS for those is a separate initiative"). Include only if it indirectly affects fpts KS in priority positions.

#### KS-32: Clock runoff calibration may be slightly aggressive

- **Source:** H-MB-13
- **Theme:** E — Calibration constant
- **Mechanism:** `CLOCK_PASS_COMPLETE = 30, CLOCK_PASS_INCOMPLETE = 5, CLOCK_RUN = 35, CLOCK_SACK = 35`. Real NFL clock runoff highly variable. Wrong ratio shifts total plays/game. `validate_passing.py:24` targets `plays_per_team: (63, 65)`; ±5% pace_factor change → ±3 plays → ±1.5 pass attempts → ~11 yd/game.
- **Files:** `src/fantasy_sim/engine/play_resolver.py:21-24`, `scripts/validate_passing.py:24`.
- **Proposed change:** Run `validate_passing.py`; check `plays_per_team` and `nfl_pass_attempts` are in range. If pass_attempts low (32-33 instead of 35-36), reduce `CLOCK_PASS_INCOMPLETE` from 5 to 3 (clock paused on incompletions in real NFL).
- **Targeted KS metric(s):** QB pass_yards (volume).
- **Expected KS gain:** **small-medium** — depends on whether attempts are off.
- **Hard-floor risk:** **low.**
- **Effort:** **hours.**
- **Dependencies:** None.
- **Confidence:** **medium-high.**

#### KS-33: Validate sack rate + `PASS_TD_GATE` empirically

- **Source:** H-MB-12 + H-MB-11
- **Theme:** E — Calibration / verification
- **Mechanism (sack):** Sacks end pass attempts (no `pass_yards` accrual) and end drives more often. NFL real sack rate per dropback ≈ 6.5%; sim's `sack_rate` from `(team_plays | sack==1).count() / total_passes` (`preprocessor.py:170`) should match closely. **Mechanism (`PASS_TD_GATE`):** `{(1,3): 0.55, (4,5): 0.50, (6,10): 0.45, (11,15): 0.25, (16,20): 0.15}`. Per-play TD gates after receiver caught at TD-distance. NFL real RZ pass TD conversion rate (per attempt) ~7-8%. With sim's catch rate ~0.55-0.58 inside 20 and these gates, conversion ~0.19/attempt — too high. Comments claim "calibrated to ~55% drive-level TD rate"; needs empirical verification.
- **Files:** `src/fantasy_sim/data/preprocessor.py:166-170`, `src/fantasy_sim/engine/play_resolver.py:202-215`, `src/fantasy_sim/engine/play_resolver.py:43-49`, `scripts/validate_passing.py`.
- **Proposed change:** (1) Run `validate_passing.py` and confirm `sacks/team/game (1.5–3.0)` is in range. (2) Write `scripts/validate_rz_td_gate.py` comparing simulated drive-level RZ TD rate against actual 2022-2024 nflverse data; tune gate probabilities to match.
- **Targeted KS metric(s):** QB pass_yards (indirect via shorter drives); QB pass_tds, WR receiving_tds.
- **Expected KS gain:** **small.**
- **Hard-floor risk:** **low.**
- **Effort:** **hours** (verification only) + **days** (RZ gate validation script).
- **Dependencies:** A/B harness with RZ-only metrics.
- **Confidence:** **medium-high** — verification task; payoff depends on findings.

---

## Sanity Check on Totals

PROJECT.md stretch targets:
- KS-01 / QB pass_yards: 0.36 → ≤0.20 (need −0.16)
- KS-02 / WR receiving_yards: 0.26 → ≤0.20 (need −0.06)
- KS-03 / WR receptions: 0.28 → ≤0.22 (need −0.06)
- KS-04 / TE receptions: 0.35 → ≤0.25 (need −0.10)
- KS-05 / TE receiving_yards: 0.31 → ≤0.25 (need −0.06)
- KS-06 / RB rush_yards: 0.26 → ≤0.22 (need −0.04)
- KS-07 / RB receiving_yards: 0.42 → ≤0.30 (need −0.12)
- KS-08 / fpts aggregate: 0.15-0.25 → ≤0.18

**QB pass_yards budget — need 0.16:**
- KS-01 (RZ TD gate fix): expected −0.05 to −0.08 (large/confirmed)
- KS-04 (catch yards boost retune): −0.02 to −0.04
- KS-15 (clamping fix): −0.02 to −0.03
- KS-09 (per-stat residual_calibration): −0.02 to −0.04
- KS-22 (per-zone passing_detail): −0.04 to −0.07
- KS-19 (last_ten_json): −0.02 to −0.04 (when props on)
- KS-21 (alt-line CDF shaping): −0.03 to −0.05
- **Plausible total:** −0.20 to −0.35. **Closes the gap with margin.**

**WR receiving_yards budget — need 0.06:**
- KS-01 + KS-15 + KS-04 (clamping/RZ stack): −0.03 to −0.05
- KS-09 (per-stat residual_calibration): −0.02 to −0.03
- KS-11 (tier_engine reliability cap): −0.02 to −0.03
- KS-16 (depth_role.efficiency): −0.02 to −0.03
- KS-19 (last_ten_json): −0.02 to −0.03
- **Plausible total:** −0.11 to −0.17. **Closes the gap with margin.**

**TE receptions budget — need 0.10:**
- KS-08 (sim weight floor) + KS-09 (per-stat residual_calibration): −0.04 to −0.06 (most direct)
- KS-10 (per-position max_abs_adjustment + TE elite tier): −0.01 to −0.03
- KS-11 (tier_engine reliability cap): −0.01 to −0.03
- KS-12 (share-normalization residual): −0.01 to −0.02
- KS-16 (depth_role.efficiency catch_rate path): −0.02 to −0.03
- **Plausible total:** −0.09 to −0.17. **Just barely closes (lower bound) to closes with margin (upper bound).** TE receptions is the tightest case in the budget.

**RB rush_yards budget — need 0.04:**
- KS-02 (rb_scheme_fit): −0.02 to −0.04 (returns to bare level)
- KS-24 (breakaway columns): −0.01 to −0.02
- KS-09 (per-stat residual_calibration): −0.01 to −0.02
- **Plausible total:** −0.04 to −0.08. **Closes the gap.**

**RB receiving_yards budget — need 0.12 (largest gap):**
- KS-01 + KS-04 + KS-15: −0.03 to −0.05 (same clamping stack)
- KS-09 (per-stat residual_calibration): −0.02 to −0.04
- KS-19 (last_ten_json for RB receiving): −0.02 to −0.04
- KS-21 (alt-line for RB receiving): −0.02 to −0.03
- **Plausible total:** −0.09 to −0.16. **Plausibly closes (upper bound).** This is the most uncertain target — KS-07 is conspicuously absent from clean structural fixes; most leverage comes from KS-09 + new signal integration.

**fpts budget — need ≤0.18 (currently 0.15-0.25):**
- KS-08 (sim weight floor): −0.04 to −0.07 (the dominant compressor)
- KS-13 (ff_opportunity prior with width): −0.02 to −0.03
- KS-09 (per-stat residual_calibration consistency): −0.02 to −0.03
- **Plausible total:** −0.08 to −0.13. **Closes the gap with margin.**

**Caveats / Flags:**
- TE receptions is the **tightest** budget — borderline. If KS-08 floor is set conservatively (0.20 instead of 0.30), TE receptions may not reach ≤0.25.
- RB receiving_yards is the **most speculative** — biggest gap and least direct levers; relies heavily on KS-09 and new-signal integration for the closure.
- KS-07 "RB receiving_yards" doesn't have a structural fix as direct as KS-08 has for TE/WR fpts. Worth flagging that this target may need to be relaxed or that we should investigate why RB receiving_yards is uniquely poor (volume? share normalization H-DS-04? backup-fallback H-MB-06?).
- **Stat KS interactions are not strictly additive.** Real KS gains are sub-additive — fixing the dominant compressor may close the gap that smaller fixes also touched, so headroom in the budgets above shrinks in practice. The plausible ranges include rough discounts but are still optimistic.

**Bottom line:** The hypothesis backlog plausibly reaches all PROJECT.md stretch targets except possibly RB receiving_yards. Expected range of total stretch closure: 70-100% of targets cleared.

---

## Open Questions

These the user should decide before / during planning:

1. **Are 2022-2024 props historically scrapeable?** PFF Consumer API may or may not allow `season=2022` queries; this gates KS-19 and KS-20 historical validation. Probe is 1 day of work. If not, KS-19/KS-20 validate against 2025 only and KS-21 (Odds API backfill) becomes more important.

2. **What's the appropriate `dynamic_blend` simulator-weight floor?** KS-08 Option A uses 0.30 as default — may be too aggressive (large MAE regression) or too conservative (insufficient KS gain). Should the user set 0.20, 0.30, or 0.40, or accept the recommendation to grid-search?

3. **Is The Odds API budget ($30-150/mo) approved for KS-21?** PROJECT.md says "open to paid sources; will consider paid if justified" — this is the most-justified paid lever in the backlog.

4. **Does the user's "QB designed-run priority parked after smoke" memory mean we should NOT re-test under KS-priority?** KS-18 proposes a re-measurement (no code changes) — cheap but may conflict with parked status. Confirm scope.

5. **Should KS-09 (per-stat residual_calibration) ship as a hard structural change or as an opt-in flag?** This is the most architecturally significant change — affects the whole post-sim ensemble. Hard ship is faster; opt-in flag is safer for rollback. Default to opt-in unless user prefers hard ship.

6. **Are the fpts mean-bias relationships (`fpts = scoring_config(stats)`) re-derived after KS-09 stat corrections, or do we keep the existing fpts residual_calibration on top?** Two valid approaches: (a) corrected stats → re-derived fpts → no further fpts correction (cleaner architecture, more risk); (b) corrected stats + existing fpts correction (safer, two-stage).

7. **For KS-22 (passing_detail per-zone QB engine), is a 5-10 day engineering item acceptable in this initiative, or should this be deferred to a future "QB-specific" sub-initiative?** Largest single new-engine item in the backlog.

8. **TE receptions target (≤0.25 from 0.35) is the tightest budget — is this target negotiable?** Sanity check shows borderline closure; the user may want to relax to ≤0.27 or accept the risk that this single target may fall short.

9. **RB receiving_yards target (≤0.30 from 0.42) — should we accept a relaxation if no clean structural fix emerges?** Largest gap; least-clear lever. Consider relaxing to ≤0.34.

10. **Are P5 long-tail items (KS-22..KS-33) in scope for this initiative or a follow-up?** P5 is 8+ items, mostly engineering-heavy. May be appropriate to scope this initiative as P1-P4 only and treat P5 as the next initiative.

---

## Traceability

| Source ID | KS-ID(s) |
|-----------|----------|
| H-MB-01 | KS-01 |
| H-MB-02 | KS-04 |
| H-MB-03 | KS-05 |
| H-MB-04 | KS-03 |
| H-MB-05 | (covered by KS-09 + KS-11; option-1 bucketed dist subsumed by per-stat residual + reliability cap retune) |
| H-MB-06 | KS-06 |
| H-MB-07 | KS-29 |
| H-MB-08 | (analysis-only invariant; KS-01/04/15/22 close the gap downstream) |
| H-MB-09 | KS-09 |
| H-MB-10 | KS-07 |
| H-MB-11 | KS-33 |
| H-MB-12 | KS-33 |
| H-MB-13 | KS-32 |
| H-DS-01 | KS-08 |
| H-DS-02 | KS-09 |
| H-DS-03 | KS-11 |
| H-DS-04 | KS-12 |
| H-DS-05 | KS-10 |
| H-DS-06 | KS-13 |
| H-DS-07 | KS-14 |
| H-DS-08 | KS-15 |
| H-DS-09 | KS-30 |
| H-DS-10 | KS-31 |
| H-DS-11 | KS-09 (light variant — measurement upgrade) |
| H-DS-12 | KS-10 |
| H-SC-01 | KS-19 |
| H-SC-02 | KS-21 |
| H-SC-03 | KS-22 |
| H-SC-04 | KS-21 |
| H-SC-05 | KS-20 |
| H-SC-06 | KS-23 |
| H-SC-07 | KS-24 |
| H-SC-08 | KS-26 |
| H-SC-09 | KS-27 |
| H-SC-10 | KS-25 |
| H-SC-11 | KS-28 |
| H-SC-12 | KS-26 |
| H-P5-01 | KS-02 |
| H-P5-02 | KS-16 |
| H-P5-03 | KS-17 |
| H-P5-04 | KS-18 |
| H-P5-05 | KS-18 |

---

*Synthesis complete: 33 KS-IDs across 5 themes, 5-phase suggested rollout. KS-01 / KS-02 / KS-03 are the top-3 quick wins (hours of work, large/medium-large gain, low risk, confirmed mechanism or already-positive artifact).*
