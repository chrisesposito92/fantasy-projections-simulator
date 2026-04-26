# Distribution Shape / Variance Compression Audit

## Summary

- **The KS metric is across-player KS, not within-player KS.** `scripts/validate.py:229,244` and `src/fantasy_sim/validation/metrics.py:88-119` compute `ks_2samp(arm_a, actual)` where `arm_a/b` is one **mean** projection per `(player_id, week)` and `actual` is one **realized** value per `(player_id, week)`. So "variance compression" means the ensemble is shrinking *across-player-week dispersion of projections*, making the projection cloud narrower than the actual cloud. This reframes the search: the most lethal compressors are the post-sim layers that pull all players in a (position, tier, week-bucket) toward a common point estimate.
- **`residual_calibration` and the post-sim ensemble touch `fpts` only.** `src/fantasy_sim/scoring/residual_calibration.py:422` rewrites `row["fpts"] = max(fpts + correction, 0.0)` and never touches `pass_yards / receiving_yards / receptions / rush_yards / etc.` `role_trend` (`role_trend.py:191`) only multiplies fpts. `dynamic_blend` only blends stat columns when `market_history` is in the mask AND `market_weight > 0` (`dynamic_blend.py:779-793`); for any TE bucket with `market_weight == 0`, stat columns stay at simulator means while fpts is replaced wholesale by `ff_opportunity`. So the **fpts column drifts away from being a function of the stat columns** — that decoupling is the structural source of the fpts-KS regression.
- **`dynamic_blend` zeroes the simulator weight for nearly all TE/WR buckets.** Inspecting `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json`: every TE bucket has `simulator ≤ 0.05, ff_opportunity ≥ 0.95`. The post-sim fpts becomes ~100% `ff_opportunity` prior, which is a **single learned mean per (pid, week)**. Across the TE population this collapses fpts dispersion toward the ff_opportunity mean function, exactly the across-player variance the KS test consumes.
- **Three structural compressors stack on the simulator outputs:** (1) `tier_engine._blend_player()` proportionally resamples player yards arrays toward a tier pool of `pool_size=250` (`tier_engine.py:1034-1052`), (2) `_normalize_roster_shares()` re-scales target/carry shares to sum to 1.0 every week (`player_builder.py:618-693`), and (3) `MIN_BUCKET_PLAYS=10` swaps thin buckets for team/league defaults (`preprocessor.py:9,100,137`). Each shaves cross-player tails toward the team/tier center.
- **`residual_calibration` correction is bucket-wide, not player-specific.** `residual_calibration.py:233-273` fits one `median_residual * shrinkage` per `(position, usage_tier, source_confidence_bucket)` and adds the same constant to every player in the bucket — preserving across-player rank but adding **no within-bucket variance**. Combined with point-estimate ff_opportunity, this stacks two consecutive flat shifts on top of compressed simulator fpts and looks like a translated, narrowed Gaussian — exactly the KS regression pattern observed.

## The TE puzzle

Why TE goes 0.20 → 0.32 KS bare → defaults — the largest single delta in the table:

1. **TE has the smallest absolute fpts magnitude.** Position usage thresholds in `residual_calibration.py:25-30` are `TE: high=9.0, mid=4.0` — half the magnitude of WR (`12.0/6.0`) and a third of QB (`18.0/12.0`). A 1.5-fpt `max_abs_adjustment` (defaults.yaml:374) is **15-37% of a typical mid-tier TE projection** vs **5-10%** for a high-tier QB. Same correction magnitude → much larger relative shift → much larger distortion of the across-player TE distribution.
2. **TE is the position where dynamic_blend most aggressively kills the simulator.** From `weights_2024.json`:
   - `TE|13-18|sim+ff|none`: sim=0.00, ff=1.00 (n=370)
   - `TE|5-12|sim+ff+mkt|medium`: sim=0.00, ff=1.00 (n=249)
   - `TE|5-12|sim+ff|none`: sim=0.05, ff=0.95 (n=478)

   Effectively **all TE projections become `prior_fpts(player, week)` from ff_opportunity** — a single mean per (player, week). The simulator's natural across-player TE fpts dispersion (driven by share normalization, target distributions, RZ catch rate, depth-of-target archetype, etc.) is **discarded**, replaced by a smoother point-estimate function. Across-player KS gets worse because actuals retain the natural NFL TE variance while projections collapse toward an ff_opportunity-derived ridge.
3. **TE residual_calibration buckets all carry negative corrections.** From `calibration_2024.json` lines 125-170: `TE|low|external_no_market: -0.49`, `TE|low|market_high: -0.84`, `TE|mid|external_no_market: -0.29`, `TE|mid|market_medium: +0.60`. The combination of sign-mixed bucketed corrections on top of an already-compressed ff_opportunity fpts moves the TE projection cloud rigidly relative to the actuals — KS sees both the reduced spread *and* the bucket-wise translation as distance.
4. **TE stat columns (`receptions`, `receiving_yards`) get NO post-sim correction.** Because `dynamic_blend.blend_supported_stats` (`dynamic_blend.py:779-793`) is gated on `market_weight > 0` and TE buckets typically have `market_weight = 0` (see weights_2024.json), the stat columns retain their simulator means while fpts is replaced. So **stat-level KS regression for TE receptions/yards is driven entirely by the simulator-side compression** (tier_blend, share normalization, MIN_BUCKET_PLAYS fallback) plus the absence of any post-sim stat calibration.
5. **Tier pools merge thin tiers into TE tier 3.** `tier_engine.py:441-477` (`_merge_thin_tiers`) merges tiers 1→2 and 5→4 first, then 2→3 and 4→3 if any pool has fewer than `MIN_TIER_POOL_SIZE=20` player-seasons. Because there are far fewer "elite TE" player-seasons (Travis Kelce, Mark Andrews, etc.) than elite WRs, **TE pools merge much earlier**, producing a single fat-middle pool that all TEs blend toward. This aggressively flattens the TE skill spectrum into one yards distribution.

## Hypotheses Ranked by ROI

### H-DS-01: dynamic_blend zeroes simulator weight, replacing fpts with a point-estimate ff_opportunity mean

- **Stat(s) affected**: fpts (all positions, but most severe for TE/WR/RB)
- **Mechanism**: `src/fantasy_sim/scoring/dynamic_blend.py:795-799` computes `row["fpts"] = self._apply_weights(context.sources, weights)` where weights come from `weights_2024.json`. The bundled artifact assigns `simulator <= 0.05` for nearly every TE/WR/RB bucket, replacing the simulator's natural across-player fpts variance with ff_opportunity's smoother prior. ff_opportunity (`scoring/ensemble.py:97-105`) is itself a point estimate — a single `prior_fpts` per (player, week) — so the across-player projection cloud narrows toward a ridge.
- **Evidence**:
  - `dynamic_blend/decision_s200/weights_2024.json` line 1-220 shows simulator weights:
    - `TE|*` buckets: 0.00, 0.00, 0.05
    - `WR|*` buckets: 0.00–0.05
    - `RB|*` buckets: 0.00–0.05
    - `QB|*` buckets: 0.00–0.20 (only QB preserves any simulator signal)
  - `src/fantasy_sim/scoring/dynamic_blend.py:795-799`: applied weights produce a deterministic fpts substitution.
  - `src/fantasy_sim/scoring/ensemble.py:102-105`: the source `prior_fpts` is a single number per player-week, so blending cannot expand variance.
  - `scripts/validate.py:198-227`: KS samples are means per (pid, week), so a deterministic point-estimate substitution must reduce across-player variance.
- **Proposed correction (Option A — lightest)**: floor the simulator weight at 0.30 in `dynamic_blend.py` so the simulator's variance contribution never disappears. Concretely, after `normalize_weights(...)` in `_artifact_weights()`, clamp `weights[SIMULATOR_SOURCE] = max(weights[SIMULATOR_SOURCE], 0.30)` and renormalize. Re-fit `dynamic_blend` with that floor in `scripts/fit_dynamic_blend_weights.py` so MAE-greedy search isn't penalized.
- **Proposed correction (Option B — better)**: use `ff_opportunity` as a **shrinkage center for the simulator's fpts mean**, not a replacement. Replace the convex blend with `proj_fpts = sim_fpts + alpha * (ff_opportunity_fpts - sim_fpts) + epsilon * randn()` where `epsilon` is calibrated from per-bucket residual std so projections preserve realistic dispersion.
- **KS gain potential**: large (this is the dominant compression for TE/WR fpts; expected to recover most of the 0.20→0.25 fpts regression and a chunk of the position-level fpts buckets)
- **rank_corr/MAE risk**: medium. ff_opportunity is winning MAE because it's calibrated; restoring simulator weight will cost some MAE. The 0.30 floor (Option A) is a tunable knob — pick the smallest floor that recovers the KS while staying within `MAE +0.05`. Option B is safer because it can be tuned to preserve mean.
- **Effort**: hours (Option A), days (Option B re-fit)
- **Dependencies**: re-running `scripts/fit_dynamic_blend_weights.py` with the new constraint; manual A/B validation

### H-DS-02: residual_calibration touches only fpts, never stat columns

- **Stat(s) affected**: receptions, receiving_yards, rush_yards, pass_yards, etc. (all stat columns for QB/RB/WR/TE)
- **Mechanism**: `src/fantasy_sim/scoring/residual_calibration.py:422` updates `row["fpts"] = round(max(fpts + correction, 0.0), 1)` and explicitly **does not touch any stat column**. So when `dynamic_blend` doesn't blend stat columns (because `market_weight == 0` or market_history is missing), stat columns are left at the raw simulator output — which carries the share-normalization and tier-blend compressions in full. The fpts correction is then added on top, decoupling fpts from the stat columns it should be derived from.
- **Evidence**:
  - `residual_calibration.py:367-431` — `adjust_week()` only writes to `row["fpts"]`. No iteration over stat keys.
  - `dynamic_blend.py:166-180` (`market_history.blend_supported_stats`) — only the seven market-line stats get blended, only when market_weight > 0.
  - For TE in 2024, `weights_2024.json` shows `market_history` weight = 0 in 2 of 3 buckets — so stat columns get zero post-sim correction for TE.
  - `scripts/validate.py:91-122` (STAT_KS_BY_POSITION) — the KS test pulls the stat columns directly from the projection rows, so any compression at the simulator stage flows straight into the KS metric.
- **Proposed correction**: extend `residual_calibration` to fit and apply **per-stat residuals**. Add a parallel artifact format `calibration_<season>.json` with `buckets[bucket_key].stat_corrections.{pass_yards, receiving_yards, ...}` containing additive shifts. In `adjust_week()`, after the fpts correction, apply the per-stat correction with a clamp like `±2 * sqrt(actual_var)`. Re-derive fpts from the corrected stats using the scoring config to keep fpts internally consistent.
- **KS gain potential**: large (this is the only mechanism that can target stat-level KS directly; TE receptions, WR receiving_yards, RB rush_yards all expected to improve materially)
- **rank_corr/MAE risk**: low if the correction is bucketed by `(position, usage_tier, source_confidence_bucket)` like fpts already is. The `min_training_mae_delta=-0.01` gate (defaults.yaml:375) prevents corrections that don't lift training MAE.
- **Effort**: days. Need to extend `fit_residual_calibration.py`, `residual_calibration.py`, the artifact schema, and add tests for the extended adjuster.
- **Dependencies**: re-running `scripts/fit_residual_calibration.py` to produce stat-level artifacts

### H-DS-03: tier_engine._blend_player proportionally resamples yards toward a 250-element tier pool

- **Stat(s) affected**: receiving_yards (WR/TE), rush_yards (RB)
- **Mechanism**: `src/fantasy_sim/data/pff/tier_engine.py:1034-1052` (`_blend_yards`) implements:
  ```
  n_pbp = max(1, int(reliability * pool_size))
  n_tier = pool_size - n_pbp
  pbp_sample = rng.choice(personal, size=n_pbp, replace=True)
  tier_sample = rng.choice(tier_pool, size=n_tier, replace=True)
  return np.concatenate([pbp_sample, tier_sample])
  ```
  with `pool_size=250` (defaults.yaml:84) and `reliability` clipped to `[0.20, 0.80]` (defaults.yaml:82-83). For a player with reliability=0.50, **125 of 250 yards samples come from the tier pool** (a fat aggregated distribution mixing all players in that tier) and only 125 come from the player's own PBP. This pulls every player's per-play yards distribution toward the tier center, compressing tails for elite players (Kelce, A. Brown) and inflating tails for sub-tier players. **Cross-player variance shrinks** in the simulator output — exactly what KS measures.
- **Evidence**:
  - `tier_engine.py:1034-1052` — concrete blend implementation.
  - `tier_engine.py:441-477` — thin-tier merging consolidates tiers 1+5 into 2+4 then into 3, so tier pools for less-populated positions (TE, top-tier RBs) become a single fat-middle distribution.
  - Per-position reliability cap of `0.80` (defaults.yaml:83) means **even the most reliable player has 20% of their yards distribution drawn from the tier pool** — variance leaks to the center even for the best signal.
  - For TE, post-merge there is typically only one or two pools; ALL TE receiving_yards distributions look similar after blend — across-player KS regresses.
- **Proposed correction**: raise `reliability_cap` to `0.95` for high-touch players (TE/WR/RB with `min_targets >= 30` or `min_carries >= 50`) so signal players keep their own distribution intact. Apply via `position_reliability` map in `tier_engine.py:961-965`:
  ```yaml
  pff.tier_engine.position_reliability:
    WR: { floor: 0.30, cap: 0.95 }
    TE: { floor: 0.30, cap: 0.95 }
    RB: { floor: 0.25, cap: 0.92 }
  ```
  Additionally, replace the proportional resample with a **mixture-of-CDFs at low frequency** (only blend in the lowest 10th percentile and highest 90th percentile to fill tails, leaving the body of the distribution alone). That way the tier pool fills missing tails for thin-data players without compressing tails for high-data players.
- **KS gain potential**: medium-large (TE: large; WR: medium; RB: medium)
- **rank_corr/MAE risk**: low for high-touch players (their PBP is the better signal anyway). Risk for thin-data players is mitigated by keeping the tier-pool floor at 0.30. Per AGENTS.md "QBs only blend fumble_rate" — same principle should extend to high-touch skill players.
- **Effort**: 1-2 days (config + targeted re-test, no schema change)
- **Dependencies**: A/B validation showing recovery on TE/WR receiving_yards KS

### H-DS-04: _normalize_roster_shares re-scales carry/target shares to sum to 1.0 every week

- **Stat(s) affected**: receptions, receiving_yards, rush_yards (all positions where shares determine selection)
- **Mechanism**: `src/fantasy_sim/data/player_builder.py:618-693` rescales `target_share` and `carry_share` (plus 6 RZ-zoned variants) so each sums to 1.0 across the current roster. This is correct for the selection-probability invariant, but **it removes legitimate week-to-week variation** in absolute targets. If a real WR1 has target_share=0.30 in the historical PBP (3-year average), then on a new roster the WR1 might have target_share=0.34 after renormalization. The simulator now systematically projects more targets for the WR1 than they actually receive — and **across the roster**, this homogenizes the target distribution. Combined with `select_receiver`'s use of these as weights, the across-player target/yards distribution narrows.
- **Evidence**:
  - `player_builder.py:683-693` (`_scale_shares`): `factor = 1.0 / total; setattr(p.usage, attr, getattr(p.usage, attr) * factor)`.
  - `game_context.py:1073-1259`: `_normalize_roster_shares` is called **9+ times per game build** (after each adjustment layer that modifies usage). Each renormalize amplifies any drift introduced by an upstream layer.
  - The existing `MIN_QB_CARRY_SHARE = 0.10` filter (player_builder.py:630) excludes pocket passers from the carry pool — but no analogous filter excludes injured WRs or backup TEs that don't actually play.
- **Proposed correction**: instead of normalizing to sum exactly 1.0, normalize to a **target sum based on availability**. Compute `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` and let small remainders go to a "league-default" residual that is **not** allocated to a roster player. That residual represents plays that go to non-modeled players (special teams, no-target plays, etc.) and prevents the renormalization from amplifying the strongest player on the roster.
- **KS gain potential**: medium for WR/TE receptions, small for RB
- **rank_corr/MAE risk**: medium. This is a calibration knob that affects mean targets — needs A/B validation that mean targets stay aligned with actuals. The `availability` engine (defaults.yaml:398-420) already adjusts shares, so the residual approach should compose cleanly.
- **Effort**: days
- **Dependencies**: must coordinate with `availability` engine and player props blending

### H-DS-05: residual_calibration max_abs_adjustment=1.5 + bucket-wide flat correction is disproportionately large for TE

- **Stat(s) affected**: TE fpts (and downstream TE rank_corr / MAE / KS)
- **Mechanism**: `src/fantasy_sim/scoring/residual_calibration.py:109-111` (`clamp_adjustment`) limits the per-row correction to `max_abs_adjustment=1.5` (defaults.yaml:374). For TE with usage tier thresholds at `high=9.0, mid=4.0` (residual_calibration.py:30), a 1.5-fpt correction is up to **37% of a mid-TE projection**. The correction is the **same flat number for every TE in the bucket** — it shifts the entire bucket's mean rigidly without expanding cross-player variance. Combined with H-DS-01, this stacks a flat translation on a compressed cloud — KS sees the compression *and* the bucket-wise mean shift.
- **Evidence**:
  - `residual_calibration.py:240-243`: `correction = clamp_adjustment(median_residual * shrinkage, max_abs_adjustment)`. Single number per bucket.
  - `residual_calibration.py:418-422`: applied flat to every row matching the bucket key.
  - `calibration_2024.json` TE bucket corrections: -0.49, -0.84, -0.29, +0.60 — magnitudes are 5-21% of TE fpts averages.
  - `USAGE_TIER_THRESHOLDS` in `residual_calibration.py:25-30`: only three tiers per position. TE has the smallest absolute thresholds, so flat corrections are proportionally largest.
- **Proposed correction**: scale `max_abs_adjustment` per position by the position's typical fpts magnitude. Concrete change in defaults.yaml:374:
  ```yaml
  ensemble.residual_calibration:
    max_abs_adjustment_by_position:
      QB: 2.5
      RB: 2.0
      WR: 1.5
      TE: 0.8
  ```
  And update `residual_calibration.py:109-111` to look up the per-position cap. Additionally, refine the `usage_tier` threshold for TE to add a fourth "elite" tier above 14.0 fpts so Kelce/Andrews-class players don't blend into "high" with mid-tier TEs.
- **KS gain potential**: small-medium for TE
- **rank_corr/MAE risk**: very low — this only loosens an over-aggressive cap on bucket-wide shifts.
- **Effort**: hours
- **Dependencies**: minor; doesn't require re-fitting if the artifact's stored `correction_fpts` already passes the new clamp

### H-DS-06: ff_opportunity is a point-estimate prior — no within-bucket spread

- **Stat(s) affected**: fpts (all positions where ff_opportunity weight is high — TE, WR, RB)
- **Mechanism**: `src/fantasy_sim/scoring/ensemble.py:102-105` blends fpts as `simulator * (1-w) + prior_fpts * w` where `prior_fpts` is **one scalar** per (player, week) from the FF Opportunity loader. By construction, blending two point estimates produces a point estimate — no across-player variance is introduced. When `dynamic_blend` weight is high (H-DS-01) AND ff_opportunity is the dominant source, projections collapse toward the ff_opportunity mean function.
- **Evidence**:
  - `ensemble.py:97`: `prior_fpts = float(prior["prior_fpts"])` — one scalar.
  - `data/ensemble/normalizer.py` (referenced from ensemble.py:11) normalizes `total_fantasy_points_exp` per (player_id, week) — single scalar per row.
  - `defaults.yaml:351-356`: ff_opportunity weights `QB: 0.35, RB: 0.15, WR: 0.25, TE: 0.15` — but H-DS-01 shows the dynamic_blend artifact effectively pushes these to ~1.0 for non-QB.
- **Proposed correction**: load the ff_opportunity confidence interval (it ships with `total_fantasy_points_exp_lo` and `_hi`) and convert the blend into a **prior with width**. Rather than `prior_fpts` as a scalar, treat ff_opportunity as a Gaussian with mean = `prior_fpts` and std = `(prior_hi - prior_lo) / (2 * 1.28)` (80% interval). When dynamic_blend uses ff_opportunity at high weight, sample N independent fpts shifts per player — preserves across-player variance even when ff_opportunity dominates.
- **KS gain potential**: medium (works with H-DS-01, not as standalone)
- **rank_corr/MAE risk**: low — adds noise centered on the ff_opportunity mean, leaves rank ordering and mean unchanged.
- **Effort**: days. Requires verifying the ff_opportunity loader exposes lo/hi columns and adding a sampling step in dynamic_blend.
- **Dependencies**: H-DS-01 changes; ff_opportunity raw data must contain quantile columns (verify via `data/ensemble/loader.py`)

### H-DS-07: MIN_BUCKET_PLAYS=10 fallback in preprocessor collapses thin-bucket variance

- **Stat(s) affected**: all yards distributions (rush_yards, pass_yards, receiving_yards) at rare game states (4th-and-long, deep red zone, late game with large deficit)
- **Mechanism**: `src/fantasy_sim/data/preprocessor.py:9, 100, 137` — when a `(play_type, GameStateBucket)` has fewer than 10 plays, the bucket is dropped from `distributions` and the simulator falls back to the team-wide default distribution. For rare buckets (e.g., 4th-and-15+ inside the 5), this means **every team uses the same default distribution** — across-team variance disappears. For players, the same effect compounds because per-player buckets are even thinner.
- **Evidence**:
  - `preprocessor.py:9`: `MIN_BUCKET_PLAYS = 10`. Hard-coded.
  - `preprocessor.py:100, 137`: `if total_bucket >= MIN_BUCKET_PLAYS` guards bucket retention; otherwise fallback to team default.
  - `play_resolver.py:303` and `play_resolver.py:393`: simulator falls back to `play_outcomes.sample_yards("pass" or "run", _bucket_from_state(state), rng)` when player distribution is None or empty — this routes through the fallback chain.
  - For TE and backup RB, per-player buckets often have <10 plays — they sample from the team-wide pool, removing within-team distinctiveness.
- **Proposed correction**: lower `MIN_BUCKET_PLAYS` to 5 with a Bayesian shrinkage prior on the parametric estimate — `samples = personal_plays + 5 * team_default_plays`. This preserves bucket-level signal even at low n while regularizing toward the team mean. Add an audit metric in `validation/coverage.py` that reports per-position fallback rate (% of player-weeks where any bucket fell back) so we can see when we are using fallbacks vs. real distributions.
- **KS gain potential**: small-medium (mostly affects the long tails of yards distributions)
- **rank_corr/MAE risk**: very low — Bayesian shrinkage is a soft version of the existing hard fallback.
- **Effort**: 1-2 days. Need to add the shrinkage logic in preprocessor.py and add the audit metric.
- **Dependencies**: none

### H-DS-08: Yards distribution is sampled per-play, but field-position clamping truncates the tail asymmetrically

- **Stat(s) affected**: pass_yards (QB), receiving_yards (WR/TE)
- **Mechanism**: `src/fantasy_sim/engine/play_resolver.py:437-446` (`_clamp_yards`) truncates yards to `[max_loss, yard_line]`. A receiver whose empirical yards distribution has 95th percentile = 35 yards, sampling at yard_line=20, gets the sample clamped to 20. **The upper tail is truncated more than the lower tail**, which biases the mean **down** AND compresses the upper tail. The existing `CATCH_YARDS_BOOST=1` (play_resolver.py:32) tries to compensate the mean but does nothing for the tail compression.
- **Evidence**:
  - `play_resolver.py:32`: `CATCH_YARDS_BOOST = 1` is documented as compensating for clamping bias.
  - `play_resolver.py:437-446`: `_clamp_yards` truncates `yards > yard_line`.
  - `play_resolver.py:265-274`: catch yards path samples the full distribution then clamps — losing tail information.
  - `CONCERNS.md:108-114`: explicitly flags this as a fragile area.
- **Proposed correction**: rather than clamping, **convert truncated samples into TDs** (when `yard_line <= sample`). Currently, the sample is clamped to the goal line and a TD is recognized when `state.yard_line - yards <= 0`, but the clamped value loses the "remainder" — the player is treated as though they ran exactly to the goal line. Restoring the un-clamped sample as `min(yard_line, sample)` for yards and using the un-clamped sample for the TD probability gate produces correct expected yards but no behavior change for TDs. **This is a bug-fix-class change**, not a calibration knob.
- **KS gain potential**: medium for QB pass_yards, small-medium for WR receiving_yards
- **rank_corr/MAE risk**: low. May slightly increase mean yards (offsetting the catch-yards-boost manual compensation), so we may need to reduce `CATCH_YARDS_BOOST` from 1 → 0 in the same change.
- **Effort**: days (need careful test work to avoid double-counting yards)
- **Dependencies**: regression-test the existing RZ TD calibration (PASS_TD_GATE / RUN_TD_GATE)

### H-DS-09: Multiplicative factor stack composes 5+ clamps that asymptote toward 1.0 in the product

- **Stat(s) affected**: rush_yards (RB), receiving_yards (WR/TE), pass_yards (QB)
- **Mechanism**: The pipeline (AGENTS.md:75) applies in order: vegas pace + pass rate factors, matchup (7 factors), team_context (3 factors), rb_scheme_fit, qb_split, depth_role, coverage, weather (3 factors). Each factor is centered on 1.0 and clamped:
  - `matchup.factor_clamp = [0.90, 1.10]` (defaults.yaml:120)
  - `team_context.factor_clamp = [0.90, 1.10]` (defaults.yaml:108)
  - `coverage.factor_clamp = [0.97, 1.03]` (defaults.yaml:130)
  - `weather.factor_clamp = [0.80, 1.20]` (defaults.yaml:246)
  - `vegas.itt.factor_clamp = [0.88, 1.12]`, `vegas.spread.factor_clamp = [0.92, 1.08]` (defaults.yaml:253-256)

  When a player gets simultaneously favorable matchup (1.10), favorable team_context (1.10), favorable coverage (1.03), favorable weather (1.20), favorable vegas (1.12, 1.08), the **product is 1.10 × 1.10 × 1.03 × 1.20 × 1.12 × 1.08 ≈ 1.81**. But because each factor is independently clamped at its own band, the **realization** is rarely the full product — most weeks each factor is closer to 1.0, so the product clusters narrowly around 1.0 with rare excursions. This compresses cross-week dispersion and homogenizes weeks.
- **Evidence**:
  - `matchup.py:43`: `return max(clamp[0], min(clamp[1], factor))` — each factor independently clamped.
  - `tier_engine.compute_reliability` clipping `np.clip(raw, floor, cap)` (tier_engine.py:982) — additional clamp.
  - The `compute_factor` formula `1.0 + z * sensitivity` with sensitivities like 0.06 means a 1-sigma move is only a ±6% factor — even before clamping, factors live in `[0.94, 1.06]` 68% of the time.
- **Proposed correction**: fit factor sensitivities on **log-scale** so the geometric mean of factors remains 1.0 over a season (currently the *arithmetic mean* is approximately 1.0 but the geometric mean drifts because of clamping). Concretely: `log_factor = z * sensitivity_log` clamped in log-space, then `factor = exp(log_factor)`. Equivalent for small z but stabilizes the multiplicative composition.
- **KS gain potential**: small (most factors are ±10% with sensitivities ≤0.075, so the compression they introduce is modest)
- **rank_corr/MAE risk**: low (mathematical equivalence at small z)
- **Effort**: hours per engine, would touch all factor-using engines
- **Dependencies**: re-tuning sensitivities; this is more of a hygiene fix than a primary KS lever

### H-DS-10: Bayesian shrinkage in kicker / DST / TD tendency uses prior_strength too high for tail signals

- **Stat(s) affected**: kicker fpts (small impact), dst_tds, fumbles_lost
- **Mechanism**: `src/fantasy_sim/data/pff/kicker.py:124-127` shrinks kicker FG rate toward league mean with `prior_strength=20` (defaults.yaml:186). For a kicker with 30 short FG attempts, the shrinkage weight is `30 / (30 + 20) = 0.60` — so 40% of the FG rate is the league mean. Same pattern in `dst_baseline.py:213-225` (`prior_strength=10`) and `td_tendency` (defaults.yaml:461 `prior_strength=20`). High prior_strength pulls all teams/players toward league mean, compressing across-team variance.
- **Evidence**:
  - `kicker.py:127`: `(made + prior * league) / (att + prior)` with `prior=20`.
  - `dst_baseline.py:213-225`: `(team_int_tds + prior * DEFAULT_INT_RETURN_TD_RATE) / (team_ints + prior)` with `prior=10`.
  - For DST, with `min_games=4` and modest sample, the team contribution is ≤4 picks vs prior=10 — **DST TD rate is dominated by the league average for most of the season**.
- **Proposed correction**: lower kicker `prior_strength` to 10 (cuts shrinkage in half), DST `prior_strength` to 5. Re-run validation. For TD tendency, consider raising `min_opportunities` from 5 to 8 instead of lowering prior — keeps the prior strength but excludes noisy thin-data players.
- **KS gain potential**: small (kicker/DST not in the priority KS targets)
- **rank_corr/MAE risk**: low if prior_strength change is small.
- **Effort**: hours
- **Dependencies**: A/B validation

### H-DS-11: Monte Carlo sims produce per-player histograms but only the mean is exported and validated

- **Stat(s) affected**: meta-issue, not a direct compressor — but it explains why we cannot validate stat-level KS within a player
- **Mechanism**: `src/fantasy_sim/scoring/projections.py:7-60` (`build_player_projections`) computes `np.mean` for every stat. `build_detailed_projections:71-127` additionally exports `_floor`/`_ceiling`/`_stddev` but the values exported are quantiles of the **boxes**, not raw histograms. The validation harness in `scripts/validate.py:198-227` reads only the mean projection and the single actual value. So **all "KS" measurements are across-player KS, never within-player KS**. This is fine for measuring across-player calibration, but it means the simulator's per-player Monte Carlo distribution is **not being used in the KS metric at all** — the team gives up the simulator's natural distribution shape during scoring aggregation.
- **Evidence**:
  - `projections.py:40-52`: `round(float(sum(b.X for b in boxes) / n_games), 1)` for every stat. Mean only.
  - `validate.py:208-214`: only `_numeric_value(arm_a_row.get("fpts"))` and `_numeric_value(getattr(actual, stat))` — both scalars.
  - `monte_carlo.py:75-94`: returns a `SimulationSummary` with the per-game histograms intact, but they are discarded at `build_player_projections` boundary.
- **Proposed correction (light)**: in addition to current per-stat means, export per-stat **quantiles** (10th, 50th, 90th) and **stddev** through the validation pipeline. Add a new KS variant `within_player_ks` that compares the simulator's per-player distribution to a Gaussian fit on the actuals' season residuals — this would surface within-player compression separately from across-player.
- **Proposed correction (deep)**: when computing fpts, also propagate the per-sim `fpts` array through `dynamic_blend` and `residual_calibration`. The corrections become **vector shifts** (one number per sim) that allow `residual_calibration` to be a per-sim adjustment rather than a per-player flat add. This preserves the simulator's natural distribution.
- **KS gain potential**: medium (only via the deep variant — the light one is a measurement upgrade)
- **rank_corr/MAE risk**: low (light variant is purely additive); medium (deep variant changes how corrections compose)
- **Effort**: days (light), weeks (deep)
- **Dependencies**: revisiting validation harness output

### H-DS-12: TE residual_calibration usage_tier thresholds collapse all viable TEs into 'low' or 'mid'

- **Stat(s) affected**: TE fpts (KS, MAE)
- **Mechanism**: `residual_calibration.py:25-30`: `TE: high=9.0, mid=4.0`. In a typical week only ~2-3 TEs (Kelce, Andrews, McBride at peak) project ≥9 fpts. The vast majority of fantasy-relevant TEs (TE2-TE12) project 4-9 fpts and fall into "mid". TE13+ falls into "low". So **all TE bucket corrections are dominated by tier-mid behavior**, which mixes very different player archetypes into one correction value.
- **Evidence**:
  - `residual_calibration.py:25-30`: thresholds.
  - `calibration_2024.json` lines 137-170: `TE|low|*` and `TE|mid|*` exist; `TE|high|*` does not (no entries — too few rows). So elite TEs **always fall back to "missing_bucket"** and get **zero correction**, while mid-tier TEs get the bucket-wide correction.
- **Proposed correction**: refine `USAGE_TIER_THRESHOLDS["TE"]` to `(elite=14.0, high=9.0, mid=5.0, low=2.0)` — four tiers — and lower `min_bucket_rows` for TE to 100 (from 200) so the thinner elite bucket can populate. Re-fit residual_calibration. This keeps Kelce-class TEs in their own correction pool.
- **KS gain potential**: small-medium for TE specifically
- **rank_corr/MAE risk**: low (more granular buckets generally improve calibration if they have enough rows)
- **Effort**: hours (config change + re-fit)
- **Dependencies**: re-running `fit_residual_calibration.py`

## Cross-references

- **Mean Bias overlap**:
  - H-DS-01 (dynamic_blend zeroing simulator) directly explains the QB pass_yards mean bias of -28 yd/game from PROJECT.md context: when sim weight is small for QB, the projection drifts toward ff_opportunity which models fpts, not pass_yards. Stat columns retain simulator means (which carry `_clamp_yards` truncation). Fixing H-DS-08 (clamping) addresses pass_yards mean bias directly; fixing H-DS-02 (stat-level residual_calibration) addresses it indirectly by allowing per-stat correction.
  - H-DS-08 (clamping truncating tail) explains WR receiving_yards mean bias of -9 yd/game. Removing the asymmetric truncation should close most of this gap.
- **Phase 5 slice readiness**:
  - `pff.depth_role` (defaults.yaml:133-160) — implemented but disabled. Could **replace tier_engine yards blending for WR/TE** because it has narrower clamps and bypasses the proportional-resampling compression. Worth A/B-testing as a tier_engine alternative.
  - `pff.rb_scheme_fit` (defaults.yaml:162-170) — implemented but disabled. Could provide per-game variance for RB rush_yards instead of the season-flat tier_blend.
  - `pff.qb_split` (defaults.yaml:172-181) — implemented but disabled. Provides QB-pressure-conditioned receiver efficiency. Could expand WR/TE catch_rate variance for the same QB across different pressure scenarios.
  - `qb_rushing.scramble` and `qb_rushing.designed_runs` (defaults.yaml:303-315) — implemented but disabled. Per-QB temporal artifacts; would expand QB rush_yards variance via week-to-week scramble probability changes.
- **Existing CONCERNS.md alignment**:
  - "Play-Outcome Sampling at Field Position" (CONCERNS.md:108-114) directly maps to H-DS-08
  - "PFF Depth-Role Layer Disabled" (CONCERNS.md:21-25) maps to "Phase 5 slice readiness" above
  - "Artifact Fallback Gaps" (CONCERNS.md:60-64) is the structural concern that residual_calibration falls back to 0.0 for missing-bucket — this is benign for KS (no compression added) but masks that we're leaving variance on the table.

## Open questions

- **Is the ff_opportunity loader actually exporting `prior_lo`/`prior_hi` quantile columns?** H-DS-06 depends on this — need to inspect `src/fantasy_sim/data/ensemble/normalizer.py` and the FF Opportunity raw schema. If quantiles are not available, H-DS-06 requires fitting our own residual variance model.
- **What is the bucket fallback rate in the 2022-2024 backtest?** Per CONCERNS.md:60-64, residual_calibration falls back to zero adjustment when bucket is missing; for TE elite tier (H-DS-12 evidence) this is currently 100%. Adding fallback telemetry to `coverage.py` would tell us the empirical fraction of player-weeks getting zero adjustment. (Mean Bias research should verify this; it's likely high for TE.)
- **Does QB-only behavior in tier_engine generalize?** AGENTS.md says "QBs only blend fumble_rate" via the `is_qb` skip in `tier_engine.py:1011-1052`. H-DS-03's proposed `position_reliability` cap=0.95 for high-touch WR/TE/RB is the next logical step — but we should confirm via A/B that it doesn't hurt rookies and thin-data backup players.
- **Why is dynamic_blend artifact picking ff_opportunity at >95% weight for non-QB?** The grid search in `fit_dynamic_blend_weights.py` is MAE-greedy. If ff_opportunity is biased smoother than the simulator at the population level, MAE-greedy will always pick ff_opportunity. The fix is to either (a) constrain the search to a minimum simulator weight (H-DS-01 Option A), or (b) use a multi-objective fit that targets MAE-and-KS, or (c) penalize the search for not preserving variance. Option (c) is the "right" answer but requires defining a variance-preservation loss.
- **Are TE bucket corrections in residual_calibration reflecting sample-population biases (TE rosters typically have 1 productive starter and 2 backups) rather than projection biases?** Need to compare the median residual sign across positions: if TE is uniquely negative across all buckets, the simulator may simply be over-projecting TE absolute fpts (overcounting backup TE targets), in which case the fix is at the share-normalization step (H-DS-04), not at calibration. The Mean Bias research should disambiguate.
