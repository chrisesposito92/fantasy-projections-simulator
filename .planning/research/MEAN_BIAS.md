# Mean Bias Root Cause Investigation

**Researched:** 2026-04-25
**Scope:** QB `pass_yards` (-25 to -31 yd/game), WR `receiving_yards` (-9 to -10 yd/game), and smaller mean shortfalls in WR/TE/RB receiving stats. RB rushing is within ±2 yd/game.
**Confidence:** HIGH on H-MB-01 through H-MB-04 (root cause grounded in source). MEDIUM on H-MB-05 through H-MB-08 (hypothesis-driven, requires A/B confirmation).

## Summary

* **The dominant mechanism is _red-zone TD-gate truncation combined with _tackled_short()_ tail compression**: when a sampled completion would have been a TD inside the 20, the gate fires; on gate failure, `_tackled_short()` rewrites yards to a value strictly _less than_ the clamped TD-line, capping pass yards. This systematically rewrites catches that would have produced 12-20 yards down to 7-12 yards. Magnitude estimate: 15-25 missing yards per QB game. (`src/fantasy_sim/engine/play_resolver.py:279-283, 421-424`)
* **`CATCH_YARDS_BOOST = 1` is too small** for the field-position clamping bias _and_ is explicitly disabled inside the red zone (lines 264-265), exactly where clamping bites hardest. The +1 yard per catch has no Monte Carlo justification — it is an ad-hoc constant. NFL completions average ~11.5 yd; sim per-completion is ~1.0-1.4 yd short. Magnitude estimate: ~22-30 yd/game with 22 completions.
* **The Player Props engine `_apply_pass_yds()` uses an _underestimated_ baseline** (`_DEFAULT_TEAM_PASS_YDS = 230.0`) versus actual NFL ~240 yd/game. With prior_strength=10 and ~17 games, this systematically biases WR/TE distributions DOWN ~1-2% × dist_mean for any prop_point < 230. (`src/fantasy_sim/data/vegas/props_engine.py:43, 366-409`)
* **The matchup engine `_apply_matchup` uses a _hardcoded 10-yard_ anchor** to convert `pass_yards_factor` (centered on 1.0) into an additive shift. Real yards/reception is ~11.5, so when the factor activates, the shift is undersized by ~15%. Symmetric across teams so no league-wide mean bias from this alone — but reduces the dynamic range of pass_yards adjustments. (`src/fantasy_sim/data/game_context.py:534-544`)
* **Post-sim layers do not touch stat columns**: `residual_calibration` and `dynamic_blend` adjust `fpts` only and explicitly leave `pass_yards`, `receiving_yards` unchanged (`src/fantasy_sim/scoring/residual_calibration.py:422`). Mean bias on stat columns therefore has no remediation path with the current stack — only fpts mean is repaired, while KS on stat distributions stays broken.

## Hypotheses Ranked by ROI

### H-MB-01: Red-zone TD-gate replaces clamped yards with strictly shorter `_tackled_short()` values

* **Stat affected**: QB `pass_yards`, WR `receiving_yards`, TE `receiving_yards`, RB `receiving_yards`
* **Mechanism**: When a completed pass inside the 20 yields enough yards for a TD (`(yard_line - yards) <= 0`), `_red_zone_td_gate()` fires. If the gate _fails_ (probabilities 0.55-0.15 depending on field position — i.e., 45-85% chance of failure!), the code calls `yards = _tackled_short(state.yard_line, rng)` which returns `yard_line - rng.integers(1, max(2, yard_line // 3))`. At yard_line=15, this returns 10-14 (mean ~12) instead of the clamped sample (which would have been 15). At yard_line=10, returns 7-9 (mean ~8) instead of 10. Critically, `_tackled_short` cannot return more than `yard_line - 1`, so it _structurally_ shortens vs the natural clamp. Across the league this is roughly: 5-6 RZ pass attempts/game × ~3.5 completions × 80% TD-gate failure × ~3-4 yards lost per failed-TD = **~10-15 yard/game shortfall on pass yards** from this one mechanism alone.
* **Evidence**: 
  * `src/fantasy_sim/engine/play_resolver.py:43-49` — gate probabilities (0.55, 0.50, 0.45, 0.25, 0.15) — all <0.55, so most RZ TDs are vetoed
  * `src/fantasy_sim/engine/play_resolver.py:279-284` — when gate fails, `yards = _tackled_short(state.yard_line, rng)` overwrites the clamped sample
  * `src/fantasy_sim/engine/play_resolver.py:421-424` — `_tackled_short` returns `yard_line - rng.integers(1, max(2, yard_line // 3))`, ALWAYS strictly less than `yard_line`
  * Concerns doc `CONCERNS.md:124-127` already flags the gate constants as fragile
* **Proposed correction**: Replace the punitive `_tackled_short` with a "preserve sampled yards, fail TD only" rule. Two clean variants:
  1. **Cleanest**: `yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))` — preserves the natural sampled distance while denying the TD by reserving 1 yard short of the goal.
  2. **Calibrated**: Use the pre-clamp sample, capped at `yard_line - 1`, only enforcing a "stopped 1 yard short" outcome at the goal line (yard_line ≤ 3). Outside the 3, use the sampled yards directly.
  * Either preserves the per-catch mean inside the 20 while still giving up the TD when gate fails.
* **KS gain potential**: **large** (this is likely the single biggest source of QB pass_yards and WR/TE receiving_yards mean bias, especially when RZ catches are weighted heavily by TD opportunity)
* **rank_corr/MAE risk**: **low–medium**. Risk is that more RZ yards = slightly more fpts upside on RZ targets (same as a per-receiver +1.0 to +2.5 yd boost in RZ context). Should NOT change rankings. A/B with `--set engine.rz_td_gate_yards_policy=preserve_sample` would confirm.
* **Effort**: **hours** (≤30 lines + 6-10 unit tests)
* **Dependencies**: None. Self-contained change in `play_resolver.py`.

### H-MB-02: `CATCH_YARDS_BOOST = 1` is undersized AND disabled in the red zone

* **Stat affected**: QB `pass_yards`, WR `receiving_yards`, TE `receiving_yards`, RB `receiving_yards`
* **Mechanism**: The `+1 yard/catch` boost was added to compensate for `_clamp_yards()` truncation but is hardcoded to `+1`. It's also explicitly disabled inside the 20 (`boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0`). The current observed shortfall is ~1.0-1.4 yd/completion. With 22 completions/game, +1 yard/catch buys back 22 yard/game total — not enough; need closer to +1.4-1.8. Worse, the RZ disablement leaves the entire RZ pass yard problem from H-MB-01 with no compensation.
* **Evidence**:
  * `src/fantasy_sim/engine/play_resolver.py:32` — `CATCH_YARDS_BOOST = 1`
  * `src/fantasy_sim/engine/play_resolver.py:264-265` — `boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0`
  * Comment at lines 26-32 acknowledges this is a "small additive boost" without empirical sizing
  * `CONCERNS.md:108-113` flags this as a "band-aid for field-position clamping bias"
* **Proposed correction**: Three options ranked best→worst:
  1. **Best**: Make boost _conditional on `_clamp_yards` actually firing_ — i.e., if `raw_yards > yard_line` the catch was clamped (TD or near-TD); otherwise boost +1.5 to +2.0. Track and centrally calibrate. This ties the correction to the actual cause (clamping) rather than blanket +1.
  2. **Reasonable**: Increase to `CATCH_YARDS_BOOST = 2` outside the RZ, calibrated against current backtest. Lower risk of regression because additive shifts don't affect rank.
  3. **Quick fix**: Apply the boost INSIDE the red zone too (drop the `if state.yard_line > 20` gate). Combined with H-MB-01 fix, restores ~5 yd/game.
* **KS gain potential**: **medium–large** (each +0.5 yard/catch ≈ 11 yd/game / QB)
* **rank_corr/MAE risk**: **low**. Boost is uniformly applied; rank ordering between players unchanged. MAE may improve since mean is closer to actual.
* **Effort**: **hours** (config switch + tests)
* **Dependencies**: H-MB-01 should ship first; otherwise the RZ portion of the boost compounds with `_tackled_short` truncation.

### H-MB-03: Player Props engine `_DEFAULT_TEAM_PASS_YDS = 230.0` is below NFL mean

* **Stat affected**: QB `pass_yards` (and downstream WR/TE `receiving_yards` via `_apply_pass_yds` propagation)
* **Mechanism**: `_apply_pass_yds()` uses `prop_ratio = prop_point / historical_pass_pg`. When the QB's `_test_historical_pass_yds` is unset (the production path), `historical_pass_pg = _DEFAULT_TEAM_PASS_YDS = 230.0`. Real NFL average pass yards/team/game (2022-2024) ≈ 240-244. So a typical prop point of 220 produces `ratio = 220/230 = 0.957`, and after Bayesian blend with prior_strength=10 and ~17 games (weight=0.63 historical, 0.37 prior), final ratio ≈ 0.984. This _shifts WR/TE distributions DOWN_ by ~1.6% × dist_mean ≈ 0.17 yards per catch ≈ **3-4 yard/game** for typical catch volumes. The bias is _systematic_ because the baseline (230) is consistently below the NFL mean (240), so even average prop points produce DOWN shifts.
* **Evidence**:
  * `src/fantasy_sim/data/vegas/props_engine.py:43` — `_DEFAULT_TEAM_PASS_YDS = 230.0`
  * `src/fantasy_sim/data/vegas/props_engine.py:380-409` — `_apply_pass_yds` uses this default
  * `src/fantasy_sim/data/vegas/props_engine.py:248` — `historical_season_yds = dist_mean * player.games_played` is also a magnitude bug for `_apply_recv_yds` — it treats per-catch dist_mean as if it were per-game, dramatically underestimating historical season yards. This makes `prop_ratio = prop_point / historical_season_yds` exaggerated upward (e.g., dist_mean=10 × games=17 = 170 yards/season; prop_point season-equivalent ≈ 870 yards → ratio=5.1 → blended with weight 0.63 toward 1.0 stays close to 1.0 due to Bayesian weighting, BUT the `min_divergence` check at line 196 uses `abs(blended_ratio - 1.0)`, so a blended ratio of 1.06 still triggers, applying a non-trivial shift).
* **Proposed correction**: 
  1. Update `_DEFAULT_TEAM_PASS_YDS` to 240.0 (or a per-team rolling mean from the pipeline cache).
  2. Fix the `_apply_recv_yds` magnitude bug at line 248: `historical_season_yds` must compute per-game using completions/game × dist_mean, not `dist_mean × games_played`. The current formula equates "yards per catch × games played" with "season yards" which is meaningful only if the player catches exactly 1 ball per game. The correct formula uses ` historical_season_yds = dist_mean × catches_per_game × games_played`.
  3. Consider passing actual historical pass yards from the pipeline (cached PBP stats) instead of using a default constant.
* **KS gain potential**: **small–medium** (props is opt-in, not always active; impact only when props data is available)
* **rank_corr/MAE risk**: **low** if the constant is corrected to 240. The Bayesian weight protects against extreme shifts.
* **Effort**: **hours**
* **Dependencies**: Props engine on. If `vegas.props.enabled=false`, this finding is moot.

### H-MB-04: `_apply_matchup` uses hardcoded 10-yard anchor instead of distribution mean

* **Stat affected**: WR `receiving_yards`, TE `receiving_yards`, RB `receiving_yards` (additive, via `_apply_matchup`)
* **Mechanism**: The matchup engine's `pass_yards_factor` (clamped [0.90, 1.10]) is converted to an additive shift via `shift = (ctx.pass_yards_factor - 1.0) * 10.0`. The 10.0 is hardcoded; real NFL average yards/reception is 11.5. So when factor=1.10 (good matchup), shift=+1.0 yards instead of +1.15. When factor=0.90 (tough matchup), shift=-1.0 instead of -1.15. **No expected league-wide mean bias** because the distribution of factors is centered on 1.0. BUT: this creates undersized dynamic range, contributing to KS via _shape_ compression. Symmetric, so does NOT contribute to mean bias directly, but does compress the variance of WR/TE per-game distributions.
  
  Note: `_apply_weather` at line 709 _correctly_ uses `mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))` then `shift = (ctx.pass_yards_factor - 1.0) * mean_yards`. The matchup engine uses the wrong scale; weather uses the right scale.
* **Evidence**:
  * `src/fantasy_sim/data/game_context.py:534-544` — `shift = (ctx.pass_yards_factor - 1.0) * 10.0` (hardcoded constant)
  * `src/fantasy_sim/data/game_context.py:701-712` — weather uses dynamic per-player `mean_yards`
* **Proposed correction**: Replace `* 10.0` with `* float(np.mean(player.outcomes.receiving_yards_dist))` per player (mirror `_apply_weather`). Same for `_apply_coverage` line 591 (`* 10.0` for YPR modifier).
* **KS gain potential**: **small–medium** (does NOT directly fix mean bias but improves KS by widening the per-game distribution to match real NFL spread)
* **rank_corr/MAE risk**: **low**. Better-calibrated shifts produce more accurate expectations for high-volume receivers. May slightly improve rank for top WRs against tough/easy matchups.
* **Effort**: **hours**
* **Dependencies**: None.

### H-MB-05: Empirical `receiving_yards_dist` is built from the historical _player's average yards per completion across all field positions_, with no compensation for clamping bias

* **Stat affected**: QB `pass_yards`, WR `receiving_yards`, TE `receiving_yards`
* **Mechanism**: `player_builder.py:521-522` builds `receiving_yards_dist = np.array(rs["yards"])` directly from `yards_gained` of completed plays. Per `preprocessor.py:124`, `yards_gained` includes whatever PFR/nflverse reports. In production NFL data, `yards_gained` for a completed pass that ended at the goal line includes the actual on-field gain (capped by yard_line at the time). So a player who caught a 20-yd pass at his own 30 has yards_gained=20; a player who caught a 25-yd pass at the opponent's 20 has yards_gained=20 (the catch was officially scored as a 20-yard TD). This means the empirical distribution is _already clamped_ by historical context, plus the simulator clamps _again_ at the time of sampling. The real NFL distribution for a "WR catching at opponent 25" excludes events where the WR caught at his own 25 and ran 25 yards. The simulator collapses these contexts in sampling, so the dist is field-position-naïve.
* **Evidence**:
  * `src/fantasy_sim/data/preprocessor.py:124` — `yards = row["yards_gained"]` (no field-position adjustment)
  * `src/fantasy_sim/data/player_builder.py:518-522` — `receiving_yards_dist` built from raw yards
  * `src/fantasy_sim/engine/play_resolver.py:262-274` — second clamping at sample time
* **Proposed correction**: Three-tier options:
  1. **Best (large effort)**: Build _conditional_ distributions: `receiving_yards_dist[bucket]` keyed by yard_line zone. Sample from the appropriate bucket. Eliminates double-clamping and field-position bias.
  2. **Reasonable**: Add a per-player `air_yards_dist` and `yards_after_catch_dist` separately; the catch position is determined by air_yards plus current yard_line, then YAC is added. This is closer to true play physics. Already partially supported via `air_yards_share` in usage.
  3. **Quick**: For each player, compute a "non-clamped mean" by including only catches where yard_line > 30 (where clamping rarely fires) and use that as a per-player upward adjustment.
* **KS gain potential**: **medium–large** (option 1) or **medium** (option 2). This is the architecturally correct fix.
* **rank_corr/MAE risk**: **medium**. Bucketed distributions need more data per bucket; sparse buckets will degrade. Need careful threshold selection.
* **Effort**: **days–weeks** for option 1, **days** for option 2, **hours** for option 3.
* **Dependencies**: None for option 3; Phase 5 depth_role and tracking subsystems may already collect needed data for options 1-2.

### H-MB-06: Backup receiver yards fallback is `rng.integers(3, 12)` (mean=7) — way below NFL average

* **Stat affected**: WR `receiving_yards`, TE `receiving_yards` (only when `receiving_yards_dist is None`, e.g., players with <5 catches)
* **Mechanism**: `play_resolver.py:270-271` falls back to `int(rng.integers(3, 12))` (uniform [3, 11], mean=7) when (a) the player has no `receiving_yards_dist` and (b) the team-bucket sample comes back ≤0 (which is most pass attempts since most are incomplete or sacks). This produces a fallback mean of ~7 yards/catch, well below NFL ~11.5.
* **Evidence**:
  * `src/fantasy_sim/engine/play_resolver.py:268-271`:
    ```python
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
    player_yards = (team_yards if team_yards > 0 else int(rng.integers(3, 12))) + boost
    ```
  * `src/fantasy_sim/data/player_builder.py:11` — `MIN_PLAYER_PLAYS = 5` threshold for own dist
* **Proposed correction**:
  1. Sample only from completed plays in the team-bucket distribution (filter the dist before storage in `preprocessor.py`).
  2. Change the integer fallback to `rng.integers(5, 18)` (mean=11) or use a position-archetype distribution.
  3. Lower `MIN_PLAYER_PLAYS = 5` to `3` to give more players their own dist.
* **KS gain potential**: **small** (only affects backup receivers; high-target receivers all have their own dists)
* **rank_corr/MAE risk**: **low**. Backups have small share so total impact is bounded.
* **Effort**: **hours**.
* **Dependencies**: None.

### H-MB-07: WR _team-context_ pass_rate_factor is OFF (config default) but tier-engine pass-rate scaling is ON, creating asymmetric pass volume

* **Stat affected**: QB `pass_yards`, WR `receiving_yards`
* **Mechanism**: `pff.team_context.enabled=false` in `defaults.yaml:104` but the tier engine still uses pass_rate_factor in `apply_team_context` via `target_share *= ctx.pass_rate_factor`. With team_context off, pass_rate_factor defaults to 1.0 (no effect). However, the side effect is that the simulator has _no_ team-level pass volume signal beyond Vegas spread — so volume tracks Vegas closely but NOT team identity. Pass-heavy teams (KC, BUF) are normalized to the same pass rate as run-heavy teams (BAL, ATL).
* **Evidence**:
  * `config/defaults.yaml:103-110` — team_context disabled
  * `src/fantasy_sim/data/pff/tier_engine.py:1196-1215` — `apply_team_context` would compensate
  * `CONCERNS.md:38-42` — flags team_context disablement
* **Proposed correction**: Run A/B with `pff.team_context.enabled=true` and `pass_rate_sensitivity=0.05`. May lift QB pass_yards toward the right answer for pass-heavy teams (which contribute disproportionately to the league mean).
* **KS gain potential**: **small** (rate adjustments not yards adjustments)
* **rank_corr/MAE risk**: **low–medium**. Re-enabling team_context risks regressing rank_corr for run-heavy teams.
* **Effort**: **hours** to enable + A/B.
* **Dependencies**: A/B harness with team_context isolated.

### H-MB-08: Missing tier engine yards-blending for QBs (pass_yards) is correct policy, but underlying QB pass_yards has _no_ historical signal

* **Stat affected**: QB `pass_yards`
* **Mechanism**: Tier engine explicitly skips QBs at `tier_engine.py:1011-1052` for yards blending. The rationale (per comments at 1005-1011) is sound — QB yards are emergent from team passing. So QB `pass_yards` is determined entirely by: (a) team pass rate, (b) selected receivers, (c) catch_rate, (d) per-receiver `receiving_yards_dist`. There is NO explicit QB-level pass_yards signal feeding the simulator. So if H-MB-01 through H-MB-04 are partially fixed, QB pass_yards will follow.
* **Evidence**:
  * `src/fantasy_sim/data/pff/tier_engine.py:1005-1052` — QB skip rule for yards
  * Pipeline: QB.pass_yards is computed only via `_update_player_stats:291` from pass play outcomes
* **Proposed correction**: No direct fix needed. Confirm that fixing receiving_yards bias closes ~80% of the QB pass_yards gap (since QB pass_yards = sum of all receiving yards).
* **KS gain potential**: **small** (already accounted for in WR/TE/RB receiving_yards fixes)
* **rank_corr/MAE risk**: **low**.
* **Effort**: **none** (analysis only, but a useful invariant test)
* **Dependencies**: H-MB-01 / H-MB-02 / H-MB-04 fixes.

### H-MB-09: `residual_calibration` and `dynamic_blend` adjust _fpts only_ — leave stat distributions biased

* **Stat affected**: All stat columns (pass_yards, receiving_yards, rush_yards, etc.)
* **Mechanism**: Both post-sim layers explicitly leave stat columns alone. `residual_calibration.py:422` writes only `row["fpts"]`. `dynamic_blend.py` similarly blends only `fpts`. So even if the ensemble closes the fpts mean gap, the underlying stat distributions remain whatever the play-by-play engine produced. KS is computed on stat distributions, so this is a structural bottleneck.
* **Evidence**:
  * `src/fantasy_sim/scoring/residual_calibration.py:422` — `row["fpts"] = round(max(fpts + correction, 0.0), 1)`
  * `src/fantasy_sim/scoring/dynamic_blend.py` — same pattern
  * `src/fantasy_sim/scoring/projections.py:38-52` — stat columns are simple aggregations across sims, no post-sim adjustment
  * Project `PROJECT.md:73-74` already notes this gap
* **Proposed correction**: 
  1. **Tactical**: Add a stat-level `residual_calibration_stat` engine that learns per-stat (pass_yards, receiving_yards) per-position residuals from historical data. Apply as multiplicative shift on the stat columns.
  2. **Structural**: Compute residuals _per-stat-per-position_ during fitting (`scripts/fit_residual_calibration.py`) and apply them in projection_layers.
* **KS gain potential**: **large** if we apply per-stat residuals — directly attacks the symptom.
* **rank_corr/MAE risk**: **medium**. fpts is the linear combination of stats, so re-stating stats may produce inconsistent fpts. Need to ensure: (a) stat shifts produce fpts shifts that match the existing residual_calibration, OR (b) re-derive fpts from corrected stats and rerun residual_calibration. Easy to break the pipeline if not carefully composed.
* **Effort**: **days–weeks**.
* **Dependencies**: New training data: per-stat residuals from existing backtests. Integration with projection_layers. New artifacts.

### H-MB-10: `RZ_CATCH_RATE_MODIFIER = 0.92` — verify the assumption holds for all positions

* **Stat affected**: WR `receiving_yards`, TE `receiving_yards`, RB `receiving_yards` (via missed catches, not direct yards)
* **Mechanism**: Inside the 20, catch rate is multiplied by 0.92 (or replaced with player-specific RZ rate when ≥10 RZ targets). This is a downward scalar that reduces RZ completions, indirectly reducing RZ pass yards. Real NFL RZ catch rates are positionally heterogeneous: RBs near 0.85, WRs near 0.92, TEs near 0.95. The single scalar may be miscalibrated.
* **Evidence**:
  * `src/fantasy_sim/engine/play_resolver.py:60` — single constant
  * `src/fantasy_sim/data/player_builder.py:520` — same constant for fallback
* **Proposed correction**: Replace with position-specific defaults: `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`.
* **KS gain potential**: **small** (RZ catches are a small fraction of all catches; effect dilutes)
* **rank_corr/MAE risk**: **low**.
* **Effort**: **hours**.
* **Dependencies**: None.

### H-MB-11: PASS_TD_GATE base probabilities aggregate to lower-than-real RZ TD rates

* **Stat affected**: QB `pass_tds`, WR `receiving_tds` (NOT yards directly, but catches that would have been TDs become non-TDs and then get rewritten by `_tackled_short`, see H-MB-01)
* **Mechanism**: `PASS_TD_GATE = {(1,3): 0.55, (4,5): 0.50, (6,10): 0.45, (11,15): 0.25, (16,20): 0.15}`. These are per-play TD gates _after_ the receiver has caught the ball at TD-distance. NFL real-life RZ pass TD conversion rate (per pass _attempt_, including incompletions and turnovers) is ~7-8%. With sim's catch rate ~0.55-0.58 inside the 20 (after RZ_CATCH_RATE_MODIFIER), and these gates, the conversion rate is roughly: 0.55 catch × (avg gate prob ~0.35 weighted by RZ field-position distribution) = ~0.19 per attempt — too high. But the per-play gate is multiplied across the drive, and the comments claim "calibrated to ~55% drive-level TD rate". Verifying this empirically requires backtest analysis.
* **Evidence**:
  * `src/fantasy_sim/engine/play_resolver.py:43-49` — gate dict
  * `CONCERNS.md:124-127` — flags as fragile
* **Proposed correction**: Add a backtest script `scripts/validate_rz_td_gate.py` that compares simulated drive-level RZ TD rate against actual 2022-2024 nflverse data. Tune the gate probabilities to match.
* **KS gain potential**: **small** (TDs are integer counts; mean bias on TDs is already small per the user's report)
* **rank_corr/MAE risk**: **low**.
* **Effort**: **days** (write script + tune).
* **Dependencies**: A/B harness with RZ-only metrics.

### H-MB-12: Sack rate may be too high, eating drives before pass yards accrue

* **Stat affected**: QB `pass_yards` (indirect — via shorter drives)
* **Mechanism**: Sacks end pass attempts with negative yards but DON'T add to `pass_yards` (correctly, per NFL convention). However, sacks also end drives more often (turnover on downs, punts), reducing total pass attempts/game. If `turnover_rates.sack_rate` is calibrated against PBP data that includes intentional grounding etc., the sim may sack too often. NFL real sack rate per dropback ≈ 6.5%; sim's `sack_rate` is computed from `(team_plays | sack==1).count() / total_passes` (per `preprocessor.py:170`), which should match NFL closely.
* **Evidence**:
  * `src/fantasy_sim/data/preprocessor.py:166-170`
  * `src/fantasy_sim/engine/play_resolver.py:202-215`
* **Proposed correction**: Validate via `scripts/validate_passing.py` — it already tracks `sacks/team/game (1.5–3.0)` as a target range. Just confirm this is in range. If not, audit the sack_rate computation.
* **KS gain potential**: **small** (sacks are 2-3/game, ~1-2 yards each in negative direction, doesn't directly subtract from pass_yards)
* **rank_corr/MAE risk**: **low**.
* **Effort**: **hours** (verification only).
* **Dependencies**: None.

### H-MB-13: Clock runoff calibration may be slightly too aggressive, producing fewer pass attempts/game

* **Stat affected**: QB `pass_yards` (via volume)
* **Mechanism**: `CLOCK_PASS_COMPLETE = 30`, `CLOCK_PASS_INCOMPLETE = 5`, `CLOCK_RUN = 35`, `CLOCK_SACK = 35`. Real NFL clock runoff per play is highly variable. If the ratio is wrong, total plays/game shifts. Note: total plays target is 63-65/team; a pace_factor change of ±5% changes total plays by ±3, which in turn changes pass attempts by ~1.5/game. With ~7.5 yd/attempt, that's ~11 yd/game. So clock calibration matters.
* **Evidence**:
  * `src/fantasy_sim/engine/play_resolver.py:21-24`
  * `scripts/validate_passing.py:24` — `plays_per_team: (63, 65)` target
* **Proposed correction**: Run `validate_passing.py` and check `plays_per_team` and `nfl_pass_attempts` are in range. If pass_attempts is low (32-33 instead of 35-36), reduce `CLOCK_PASS_INCOMPLETE` from 5 to 3 (clock is paused on incompletions in real NFL, so 5 is already very low; 3 is closer).
* **KS gain potential**: **small–medium** (depends on whether attempts are off).
* **rank_corr/MAE risk**: **low**.
* **Effort**: **hours**.
* **Dependencies**: None.

## Cross-references

* **Phase 5 off-by-default slices**:
  * `pff.depth_role.efficiency.enabled=false` — could counteract H-MB-04 but only when on. The depth_role efficiency engine multiplies `receiving_yards_dist * yards_factor` (`depth_role.py:314-317`) using a properly-computed `yards_factor` from PFF role stats. If this slice is enabled, it provides per-role yards adjustment that depth_role itself measures. Phase 5 work parked due to validation results — but worth re-evaluating once H-MB-01 is fixed (fewer noise sources).
  * `pff.qb_split.enabled=false` — would multiplicatively shift `receiving_yards_dist` based on QB pressure response. When pressure_environment > 1.0 and yards_trait > 1.0, scales receivers upward. Off-by-default; net effect on mean unclear without data.
  * `pff.rb_scheme_fit.enabled=false` — only RB rushing_yards_dist; doesn't address the pass-game bias.
  * `qb_rushing.scramble.enabled=false` and `qb_rushing.designed_runs.enabled=false` — QB rushing only; no impact on pass yards.
* **Calibration constants in defaults.yaml**:
  * `pff.matchup.pass_defense_sensitivity: 0.06` — tied to H-MB-04. Increasing this without fixing the 10-yard anchor would worsen mean compression.
  * `weather.wind.pass_yards_sensitivity: 0.004` — symmetric, no expected mean bias.
  * `vegas.props.prior_strength: 10.0` — tied to H-MB-03. Lowering would reduce the bias from the 230-yd default.
* **Test coverage**:
  * `tests/test_engine/test_play_resolver.py` — covers `_red_zone_td_gate`, `_clamp_yards`, `_tackled_short` individually but NOT the interaction (H-MB-01 needs new integration tests).
  * `tests/test_data/test_vegas/` — covers props_engine but does NOT validate the `_DEFAULT_TEAM_PASS_YDS=230` constant against actual NFL data (H-MB-03 needs new sanity-check test).
  * No tests cover the "additive shift × 10.0 hardcoded anchor" pattern (H-MB-04 needs new test).
  * Statistical tests in `validate_passing.py` already define target ranges; running them against the proposed fix should validate H-MB-01 / H-MB-02.

## Open questions for synthesizer

* **Confirm H-MB-01 magnitude empirically**: the fix should be validated against actual 2022-2024 RZ pass conversion rate. Need a script that pulls nflverse RZ pass plays and computes (a) mean yards/completion inside the 20 by zone bucket, (b) gate failure → `_tackled_short` distribution. If sim's RZ yards/completion is, say, 7.5 and real NFL is 11.0, the gap matches the predicted impact.
* **Confirm H-MB-02 sizing**: the right boost is empirically `target_yds_per_completion - sim_yds_per_completion`. Need a script that runs current defaults, dumps yds_per_completion, compares to NFL.
* **Confirm H-MB-03 props bias direction**: requires running A/B with props on/off and measuring per-game pass yards delta. May be small in aggregate but real.
* **Pass attempts/game**: I infer from `validate_passing.py` targets and the user's reported QB shortfall that pass attempts are roughly correct but not certain. Confirm by running `validate_sim.py` against current defaults and reading the `nfl_pass_attempts` metric. If <32, pass volume is the larger lever; if 33-35, then per-completion yards is the lever.
* **TE receptions mean shortfall (-0.1 to -0.3)** is small but the KS regression from 0.20 → 0.32 (defaults vs bare) suggests TEs lose distribution shape post-ensemble. Investigate whether `dynamic_blend` and FF Opportunity are over-shrinking TE projections toward FF prior.
* **RB receiving_yards (-0.4 to -1.6 yd/game)**: less catastrophic but consistent. Likely H-MB-01 + H-MB-02 + a smaller version of H-MB-05. Same fixes apply.

---

*Investigation complete. Recommended next steps:*

1. Implement H-MB-01 fix (hours, large gain, low risk) — single biggest expected mean-bias closure for pass yards.
2. Implement H-MB-02 fix in conjunction (hours, medium gain).
3. Run A/B harness with H-MB-01 + H-MB-02 to measure delta on pass_yards mean and KS.
4. If gap remains, layer H-MB-04 (calibrated matchup anchor).
5. H-MB-03 fix (props baseline) for marginal additional improvement.
6. Architect H-MB-09 (per-stat residual calibration) as a second-phase initiative once H-MB-01 through H-MB-04 are in.
