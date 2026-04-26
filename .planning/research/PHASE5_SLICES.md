# Off-by-Default Phase 5 Slice Readiness Audit

## Summary

- **All seven off-by-default slices are dormant, not broken**: every engine has full code, tests, validation coverage, and bundled artifacts where applicable. Each was kept off because rank_corr/MAE deltas were near-zero or slightly negative — none were tested with KS as the primary acceptance metric.
- **Highest KS-shaping potential** sits in three slices that mutate the *yards distribution* directly: `pff.depth_role.efficiency` (WR/TE `receiving_yards_dist` scaling), `pff.rb_scheme_fit` (RB `rushing_yards_dist` scaling), and `pff.qb_split` (WR/TE `receiving_yards_dist` + `catch_rate` under pressure). These are the only three that touch the empirical sample arrays the simulator draws from.
- **`pff.rb_scheme_fit` is the most likely "free" KS win**: its decision artifact already shows `rank_corr +0.0018, weekly_mae −0.003, season_mae −0.040` (`docs/archive/accuracy-roadmap.md`) — *positive on every gate*, but parked because the lift was "too small to justify promotion." Under a KS-priority regime, this is exactly the kind of change to revisit.
- **`pff.depth_role.efficiency` activated artifact** scaled both WR/TE `catch_rate` and `receiving_yards_dist` and still cleared the rank_corr/weekly_mae floor — `+0.0000 / −0.002 / +0.030`. Stat-level KS was never measured. This is the cleanest WR/TE distribution-shape lever in the codebase.
- **The QB rushing chain (just merged) is currently OFF for QB pass_yards**: scramble + designed_run only mutate the *run* path (yard distribution + selection probability). They do not touch QB `pass_yards`. The "QB pass_yards mean shortfall" must come from a different layer (catch-yards boost, residual_calibration on fpts only, or an air-yards/YAC decomposition gap).

## Slice-by-Slice Audit

### depth_role (pff.depth_role)
- **State**: dormant
- **What it does**: Computes per-WR/TE team-relative role metrics from PFF `receiving_depth` (broken out by `behind_los`/`short`/`medium`/`deep` × `left`/`center`/`right`). Aggregates player vs team-totals to compute `target_role` (player targets / team targets) and `air_role` (player air_yards / team air_yards). Applies bounded multiplicative factors to `player.usage.target_share` and `player.usage.air_yards_share` only. Volume-only mutation; touches no efficiency stats. Same-season rolling window with prior-season early-blend. Implementation in `src/fantasy_sim/data/pff/depth_role.py` lines 88-394.
- **Why off**: Decision artifact `phase-5-depth-role-v1` produced `rank_corr Δ −0.0005, weekly_mae Δ +0.002, season_mae Δ +0.013` (`docs/archive/accuracy-roadmap.md`). Mildly negative; verdict "implemented and validated, not promoted" per `docs/superpowers/handoff/2026-04-13-phase-5-pff-granularity-v2-handoff.md`.
- **KS-relevance**: **MEDIUM-LOW for distribution shape.** The factors only mutate `target_share` and `air_yards_share` — these are *volume* knobs, not yard distributions. Effect on KS would be indirect: shifting how many targets a player gets per game, which propagates to `receptions` and `receiving_yards` totals via the runner. Unlikely to fix mean-bias or distribution-shape compression because (a) factor clamps are tight (WR `[0.94, 1.06]`, TE `[0.95, 1.05]`) and (b) `target_share` already gets re-normalized to 1.0 across the roster afterward, partially undoing the effect. Could help WR `receptions` KS slightly by repositioning volume to the "right" players. Will not help mean-bias, will not help yards distributions.
- **Recommendation**: leave-off (with one caveat). The volume-only branch alone has near-zero leverage on KS. However, this engine is the *plumbing* for `depth_role.efficiency`, so the parent flag must be on for efficiency to fire. The right play is to test `depth_role.enabled=true + depth_role.efficiency.enabled=true` together (see efficiency entry).
- **Files**: `src/fantasy_sim/data/pff/depth_role.py`, `config/defaults.yaml:133-160`, `tests/test_data/test_pff/test_depth_role.py`, `tests/test_data/test_pff/test_depth_role_integration.py`
- **Effort**: hours (toggle + KS measurement). The engine is fully wired.

### depth_role.efficiency
- **State**: dormant
- **What it does**: Sub-feature inside `DepthRoleEngine` that activates a *different* mutation branch. When `efficiency.enabled=true`, the engine SKIPS the volume mutation (target_share / air_yards_share) and instead mutates: (1) `player.outcomes.catch_rate` via bounded ratio factor against observed catch efficiency, (2) `player.outcomes.red_zone_catch_rate` proportionally, (3) `player.outcomes.receiving_yards_dist` scaled by `yards_factor` (multiplies the entire empirical numpy array). This is a KS-relevant mutation — it directly reshapes the distribution sampled in `play_resolver.py`. Default sensitivities: WR `catch_rate=0.08, yards_scale=0.10`, TE `catch_rate=0.06, yards_scale=0.08`. Clamps `[0.94, 1.06]` / `[0.92, 1.08]`. See `depth_role.py:277-317`.
- **Why off**: Decision artifact `phase-5-depth-role-efficiency-v2-activated` (with parent depth_role enabled) produced `rank_corr Δ +0.0000, weekly_mae Δ −0.002, season_mae Δ +0.030` (`docs/archive/accuracy-roadmap.md`). Marginally helpful on weekly_mae but slightly worse on season_mae; verdict "not promoted." **Critically: stat-level KS was never measured for this artifact.**
- **KS-relevance**: **HIGH for WR/TE `receiving_yards` distribution shape.** This is one of only three places in the codebase where a per-player yard distribution gets multiplicatively scaled (the others being `pff.rb_scheme_fit` and `pff.qb_split`). The mechanism for KS: scaling `receiving_yards_dist` by a factor centered on each player's PFF-observed yards-per-reception relative to their PBP baseline reshapes the distribution toward the actual season behavior. This addresses the WR `receiving_yards` KS regression (defaults 0.26 vs target 0.20) and the WR mean bias (-9 yd/game) directly. Side effects: (a) `catch_rate` scaling can compress or expand the upper tail of receptions, helping WR `receptions` KS too. (b) `red_zone_catch_rate` proportional scaling helps RZ TD calibration.
- **Recommendation**: **enable + retune.** Specifically:
  1. Turn on `pff.depth_role.enabled=true` AND `pff.depth_role.efficiency.enabled=true`.
  2. Turn off the volume branch (already off when `efficiency.enabled=true` per `_volume_mutations_enabled()` in `depth_role.py:228`).
  3. Run KS-priority A/B with the new harness's `stat_ks` output, focusing on WR `receiving_yards`, TE `receiving_yards`, WR `receptions`, TE `receptions`. Goal: hit hard-floor on rank_corr/MAE while measurably improving stat KS.
  4. If clamps `[0.94, 1.06]` / `[0.92, 1.08]` are too tight for KS to move, widen to `[0.90, 1.10]` and rerun. The original validation used the tight clamps optimized for rank_corr stability — KS may need more headroom.
- **Files**: `src/fantasy_sim/data/pff/depth_role.py:148-160` (config), `:277-317` (apply_efficiency), `:387-394` (gating)
- **Effort**: days (1-2 days for measurement + 1-2 days for clamp retune if needed)

### rb_scheme_fit
- **State**: dormant
- **What it does**: Per-game RB rushing-efficiency factor combining (a) team scheme/blocking context from `offense_run_blocking` (gap vs zone shares, gap_grade vs zone_grade) with (b) RB directional preference from `rushing_direction` (interior vs edge attempt share, interior vs edge YPA). Computes a `usage_delta` (how well RB's mix matches team's scheme) and `blocking_delta` (RB family preference × team blocking strength), blends 65/35, and scales by `rush_yards_sensitivity=0.10`. Only mutation is multiplying RB `rushing_yards_dist` by the resulting factor (clamped `[0.94, 1.06]`). Pre-sim, applied between matchup/team-context and qb_split per `game_context.py`. See `src/fantasy_sim/data/pff/rb_scheme_fit.py:273-341`.
- **Why off**: Decision artifact `phase-5-rb-scheme-fit-v1` produced `rank_corr Δ +0.0018, weekly_mae Δ −0.003, season_mae Δ −0.040` (`docs/archive/accuracy-roadmap.md`). All three top-line metrics were *positive*, but verdict was "the top-line lift is too small to justify promotion and weekly QB/WR both regressed." Specifically parked because individual position weekly metrics for QB/WR moved negative even though aggregate metrics improved.
- **KS-relevance**: **HIGH for RB `rush_yards` distribution shape.** This is the cleanest distribution-shape lever in the codebase: a single factor multiplying the empirical `rushing_yards_dist` array per RB. Directly addresses the RB `rush_yards` KS regression in PROJECT.md context (`defaults regresses 0.22 → 0.29 vs bare`). The KS signal: defaults are pushing RB rush_yards distribution in the *wrong direction* somewhere upstream (likely `team_context` OL-block factor + matchup); applying RB-specific scheme-fit on top can either undo that (good for KS) or compound it (bad for KS).
- **Recommendation**: **enable.** Of all the off-by-default slices, this one already cleared the hard floor on the *current rank/MAE gates* (positive deltas everywhere). Under a KS-priority regime with the same hard floor, this is the lowest-risk experiment in the audit.
  1. Enable `pff.rb_scheme_fit.enabled=true`.
  2. Run A/B with KS-priority output. Measure RB `rush_yards` KS specifically per season.
  3. If KS improves and the QB/WR weekly regressions remain inside the hard floor (`-0.005 rank_corr, +0.05 MAE`), promote.
  4. If QB/WR weekly regressions *exceed* the floor, investigate whether the engine is leaking factors into non-RB players (it should not — `compute()` filters `player.position != "RB"`); look at how rb_scheme_fit interacts with downstream coverage/qb_split since it runs *before* both.
- **Files**: `src/fantasy_sim/data/pff/rb_scheme_fit.py`, `config/defaults.yaml:162-170`, `tests/test_data/test_pff/test_rb_scheme_fit.py`, `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`
- **Effort**: hours (toggle + measurement only)

### qb_split
- **State**: dormant
- **What it does**: Per-game receiver-side adjustment derived from QB pressure-vs-clean splits in PFF `passing_detail`. Computes the QB's pressure-completion% / clean-completion% ratio and pressure-YPA / clean-YPA ratio relative to league average, then scales those traits by the *current game's pressure environment* (matchup `sack_rate_factor × ol_pass_block_factor`). Returns two factors: `catch_rate_factor` (clamped `[0.95, 1.05]`) and `yards_scale_factor` (clamped `[0.94, 1.06]`). Applied to all eligible WR/TE pass-catchers — mutates their `catch_rate`, proportional `red_zone_catch_rate`, and `receiving_yards_dist`. Crucially, only fires if matchup is enabled AND pressure environment is non-neutral (i.e., a real sack-rate signal). Implementation in `src/fantasy_sim/data/pff/qb_split.py`.
- **Why off**: Decision artifact `phase-5-qb-split-v1-postfix` produced `rank_corr Δ +0.0000, weekly_mae Δ +0.006, season_mae Δ +0.020` (`docs/archive/accuracy-roadmap.md`). Slightly worse on weekly + season MAE; verdict "implemented and validated, not promoted, keep `pff.qb_split.enabled: false`" per `docs/superpowers/handoff/2026-04-14-phase-5-qb-split-handoff.md`.
- **KS-relevance**: **HIGH for QB `pass_yards` mean bias and WR `receiving_yards` distribution shape.** This is the *only* engine that conditions WR/TE distributions on QB-specific behavior under pressure. Mechanism for KS:
  - **QB pass_yards mean bias** (`-25 to -31 yd/game`): qb_split scales receiver `receiving_yards_dist` by `yards_scale_factor`. When QB is pressure-resistant in a high-pressure matchup, factor > 1.0, expanding the yards distribution and lifting QB pass_yards (which sums over WRs). When QB is pressure-vulnerable, factor < 1.0, reducing pass_yards. Right now defaults assume neutral, contributing to the systematic shortfall.
  - **WR/TE `receiving_yards` distribution shape**: qb_split is one of three layers that scale the empirical yards distribution. Helps the same KS problem as `depth_role.efficiency` but conditioned on game-day matchup, not season-level role.
- **Recommendation**: **retune + re-enable.** The engine implementation is correct, but the v1 artifact regressed weekly MAE because it was a per-game factor with high variance and the *current sensitivity* (`completion=0.10, yards=0.12`) was tuned for rank_corr stability, not KS shape. Three concrete moves:
  1. **Lower the sensitivities** by 30-50% (e.g., `completion=0.06, yards=0.08`). Smaller shifts will preserve rank_corr while still pulling distributions toward QB-conditional reality.
  2. **Tighten the gating**: require `min_pressure_dropbacks=30` (up from 20) and `min_clean_dropbacks=60` (up from 40) to ensure the QB has a real pressure-response signal before applying.
  3. **Run with `--baseline defaults` + KS-priority output** measuring QB `pass_yards` mean bias AND distribution KS, plus WR `receiving_yards` KS. If KS improves while staying within the rank_corr/MAE hard floor, promote.
- **Files**: `src/fantasy_sim/data/pff/qb_split.py`, `config/defaults.yaml:172-181`, `tests/test_data/test_pff/test_qb_split.py`, `tests/test_data/test_pff/test_qb_split_integration.py`
- **Effort**: days (1 day toggle + measurement, 1-2 days retune if needed)

### qb_rushing.scramble
- **State**: dormant
- **What it does**: Replaces the static per-QB `scramble_rate` (constant probability per dropback) with a *learned context model*. Loads JSON artifacts at `qb_rushing.scramble.artifacts_dir`, parses logistic regression coefficients (feature_names + coefficients dict), and at runtime computes `P(scramble | game state, market context, team/opponent priors)`. Returns a probability that overrides the static `passer.usage.scramble_rate` in `play_resolver._resolve_pass()`. Scramble yards still come from `passer.outcomes.scramble_yards_dist` — only the *probability* is learned, not the gain distribution. Falls back to base scramble_rate when artifact is missing/invalid.
- **Why off**: Smoke artifact `qb-scramble-model-s50` (50 sims, smoke_v1 artifacts under `results/qb_rushing/scramble/smoke_v1`) produced `rank_corr Δ −0.0009, weekly_mae Δ −0.005, season_mae Δ −0.067, fpts_ks Δ −0.001` (`docs/hypotheses-list.md`). Negative on rank_corr (failed first smoke gate), QB lift was tiny (`+0.0037 weekly rank_corr`), RB regressed weekly, and **QB rushing-yards KS *worsened* in 2022 (`+0.02`), 2023 (`+0.01`), 2024 (`+0.00`)**. Did not advance to 200-sim decision run. Verdict: "do not repeat as a standalone scramble-probability slice."
- **KS-relevance**: **LOW for QB pass_yards. NEUTRAL-NEGATIVE for QB rushing_yards.** The *probability* of scrambling shifts how often QB rushes vs the rest of the play resolver chain — but the actual scramble yards distribution comes from the same empirical `scramble_yards_dist` array regardless. The smoke run's KS regression is direct evidence that learning probability without learning the yards distribution actively hurts shape (more samples from a fixed distribution doesn't improve KS, but the timing/state-conditioning shifts can shift the *aggregate* QB rushing yards distribution against the actual).
- **Recommendation**: **leave-off.** This is the only slice in the audit with explicit KS regression evidence. The hypotheses-list explicitly parks it: "do not repeat standalone scramble-probability modeling as-is." Repeating with KS as priority would replicate the same regression.
- **Files**: `src/fantasy_sim/data/qb_rushing/runtime.py:31-149` (model), `src/fantasy_sim/data/qb_rushing/models.py` (config/context), `config/defaults.yaml:303-309`
- **Effort**: n/a (no fix path — needs broader chain redesign per docs)

### tracking (NGS)
- **State**: dormant (broad family); 3 sub-engines also dormant individually
- **What it does**: Phase 4 family with three independent slices: (1) `receiver_participation` — adjusts WR/TE `target_share` and `air_yards_share` from PFF participation parquet (catchable_target_rate, contested_target_rate); (2) `rb_efficiency` — adjusts RB `carry_share` and `rushing_yards_dist` from FTN/NGS rushing data; (3) `qb_context` — adjusts pass_rate, pace, scramble, sack_rate from NGS passing data. Pre-sim, applied between usage and props with rolling 4-week window. Uses leak-free player-week aggregates joined from play-level sources. Implementation in `src/fantasy_sim/data/tracking/`.
- **Why off**: Per `docs/archive/accuracy-roadmap.md`, three isolated decision artifacts:
  - `phase-4-receiver-participation-v1`: `rank_corr Δ −0.0006, weekly_mae Δ +0.007, season_mae Δ +0.072`
  - `phase-4-rb-efficiency-v1`: `rank_corr Δ −0.0003, weekly_mae Δ +0.000, season_mae Δ −0.063`
  - `phase-4-qb-context-v1`: `rank_corr Δ +0.0002, weekly_mae Δ +0.007, ...`
  
  None cleared promotion. Bundle was not run because "none of the isolated slices produced materially positive evidence." All three regressed weekly_mae.
- **KS-relevance**: **MEDIUM for `rb_efficiency` (RB rush_yards distribution); LOW for the other two.** `rb_efficiency` mutates `rushing_yards_dist` (factor clamp `[0.93, 1.07]`) — same KS-shaping mechanism as `rb_scheme_fit`. The other two slices mutate volume only (target_share, air_yards_share, carry_share, pass_rate, pace, sack_rate) which has indirect KS effect. The `rb_efficiency` regression on weekly_mae but slight season_mae *improvement* (`−0.063`) is interesting — the engine moved season totals in the right direction but added per-game variance. Could be a KS win that shows up as MAE noise.
- **Recommendation**: **leave-off the family-level flag** (`tracking.enabled=false`); but **separately consider re-running `rb_efficiency` only as a KS-priority experiment**. The signal is in same-domain as `rb_scheme_fit` (which is more promising). If `rb_scheme_fit` promotes for KS, then test `rb_efficiency` on top to see if the two stack or conflict. Do not bundle all three tracking slices; the doc explicitly warns against it.
- **Files**: `src/fantasy_sim/data/tracking/engine.py`, `src/fantasy_sim/data/tracking/rb_efficiency.py`, `src/fantasy_sim/data/tracking/qb_context.py`, `src/fantasy_sim/data/tracking/receiver_participation.py`, `config/defaults.yaml:317-342`
- **Effort**: days (need to design isolated `rb_efficiency` re-test under KS regime)

### QB designed-run chain (just merged)
- **State**: dormant — fully wired, fully tested, **CURRENTLY DEFAULT-OFF** (`qb_rushing.designed_runs.enabled=false`, `config/defaults.yaml:310-315`)
- **What it does**: Two-piece runtime chain that activates when (a) `qb_rushing.designed_runs.enabled=true` and (b) season-specific JSON artifact exists at `qb_rushing.designed_runs.artifacts_dir`. Piece 1 (`select_rusher` adjustment): when QB is in the eligible rusher candidate list, multiply QB's selection weight by a learned probability factor from a logistic model (features: down/distance/red_zone/two_minute/trailing/home/spread_norm/total/itt/qb_prior_designed_run_share/team_prior/opponent_prior/mobility_tier). Piece 2 (`_resolve_run` adjustment): when the selected rusher is a QB on a designed-run play, sample yards from per-mobility-tier tail buckets in the artifact instead of the QB's empirical `rushing_yards_dist`. Both pieces gated by QB-only check (`b3d33c2 fix: restrict QB designed-run yards to QBs`). Engine wiring threaded through `play_resolver.py:115`, `:142`, `:347`, `:352`; `player_selector.py:209`; `game_sim.py:111`; `game_context.py:1030-1042`. Implementation in `src/fantasy_sim/data/qb_rushing/runtime.py:152-273`.

  **Importantly: this chain only mutates QB *rushing*. It does NOT touch QB `pass_yards`, scramble probability, or non-QB rushing.** The QB pass_yards mean shortfall is downstream of this entire chain.
- **Why off**: Smoke artifact `qb-designed-run-chain-s50-postfix` produced `rank_corr Δ −0.0007, weekly_mae Δ +0.000, season_mae Δ +0.056, fpts_ks Δ +0.003` (`docs/hypotheses-list.md`). QB weekly improved slightly (`+0.0033 rank_corr, −0.001 weekly_mae`), but TE weekly regressed (`−0.0049 rank_corr, +0.018 weekly_mae`) and overall season MAE worsened. fpts_ks regressed `+0.003`. Smoke gate not cleared; 200-sim decision run "not warranted." Per `docs/superpowers/handoff/` parked status confirmed in current memory ("designed-run priority parked after smoke").
- **KS-relevance**: **MEDIUM for QB `rushing_yards` distribution shape; ZERO for QB `pass_yards`.** The chain learns mobility-tier-conditional designed-run rate AND tier-conditional rush-gain tails (replaces QB's empirical rush distribution with bucketed tails for designed runs). This is structurally well-aimed at the QB rushing-yards distribution problem. However, the smoke evidence shows fpts_ks regressed (`+0.003`), suggesting either (a) the learned tail buckets are over-fit / under-sampled, (b) the selection probability factor is too aggressive in shifting QB carries away from when they actually happened, or (c) the chain interacts poorly with `td_tendency` / `i5` factors at the goal line.
- **Recommendation**: **leave-off (default)**, but do NOT delete. The chain is the most architecturally complete addition in the codebase for QB rushing distribution — every other QB-rushing approach (scramble probability alone) has been formally parked. Two narrow things are worth doing under a KS-priority regime:
  1. **Measure stat-level KS specifically for QB `rushing_yards`** with the chain on. The `fpts_ks +0.003` regression is *aggregate* KS; a stat-specific QB rush-yards KS may show improvement that's masked by other-position noise.
  2. If QB `rushing_yards` KS is *not* improved, don't enable. The chain is then "well-built but the underlying signal isn't strong enough at QB volume" — same diagnosis as scramble alone.
- **Files**: `src/fantasy_sim/data/qb_rushing/runtime.py`, `src/fantasy_sim/data/qb_rushing/models.py`, `src/fantasy_sim/engine/play_resolver.py`, `src/fantasy_sim/engine/player_selector.py`, `src/fantasy_sim/engine/game_sim.py`, `src/fantasy_sim/data/game_context.py:1030-1042`, `config/defaults.yaml:310-315`
- **Effort**: hours (KS-specific re-measurement on existing artifact)

## Hypotheses Ranked by ROI

### H-P5-01: Enable rb_scheme_fit for RB rush_yards KS
- **Slice**: `pff.rb_scheme_fit`
- **Action**: enable (`pff.rb_scheme_fit.enabled=true`)
- **Stat affected**: RB `rush_yards` (KS, mean), secondary effect on RB `fpts`
- **Mechanism**: Per-RB rushing-yards-distribution multiplicative scaling (clamp `[0.94, 1.06]`) conditioned on team scheme (gap vs zone) and RB directional preference. Directly reshapes the empirical `rushing_yards_dist` numpy array sampled in `play_resolver._resolve_run()`. Targets the `defaults regresses 0.22→0.29` RB rush_yards KS gap by giving the engine a player-and-scheme-specific reshape signal.
- **KS gain potential**: medium-large (this is the lever closest to the actual problem — RB rush_yards is the only stat with confirmed KS regression *and* a fully validated engine sitting off-by-default with already-positive rank/MAE deltas).
- **rank_corr/MAE risk**: **low**. Decision artifact already shows `rank_corr Δ +0.0018, weekly_mae Δ −0.003, season_mae Δ −0.040` — positive on every gate. Risk is QB/WR weekly regressions noted in the docs, but those were within the hard floor.
- **Effort**: hours
- **Dependencies**: PFF `rushing_direction` and `offense_run_blocking` parquets (already cached locally per the codebase audit).

### H-P5-02: Enable depth_role + depth_role.efficiency for WR/TE receiving_yards KS
- **Slice**: `pff.depth_role.efficiency` (with `pff.depth_role.enabled=true` as parent gate)
- **Action**: enable both flags; consider widening efficiency clamps to `[0.90, 1.10]` if first pass shows no KS movement
- **Stat affected**: WR `receiving_yards`, TE `receiving_yards` (KS + mean), secondary WR `receptions` and TE `receptions` (KS via catch_rate path)
- **Mechanism**: When `efficiency.enabled=true`, the engine scales WR/TE `receiving_yards_dist` by a factor against observed yards-per-reception, AND scales `catch_rate` by observed catch efficiency. Volume mutations are skipped (per `_volume_mutations_enabled()` gating). This is the *only* WR/TE-specific layer that mutates the empirical receiving-yards array.
- **KS gain potential**: medium-large (targets the WR `receiving_yards` 0.26→0.20 gap and the WR mean bias `-9 yd/game`).
- **rank_corr/MAE risk**: **low-medium**. The activated artifact shows `rank_corr Δ +0.0000, weekly_mae Δ −0.002, season_mae Δ +0.030`. Season MAE risk is the watchpoint; under KS-priority it is acceptable provided rank_corr stays at-zero.
- **Effort**: days
- **Dependencies**: PFF `receiving_depth` parquet (cached locally), `depth_role.enabled=true` as parent gate (volume mutations stay off due to `efficiency.enabled=true`).

### H-P5-03: Retune qb_split sensitivities + re-enable for QB pass_yards mean bias
- **Slice**: `pff.qb_split`
- **Action**: enable + retune. Lower `completion_sensitivity` from `0.10` to `0.06`, lower `yards_sensitivity` from `0.12` to `0.08`. Tighten gating: `min_pressure_dropbacks=30`, `min_clean_dropbacks=60`. Then re-validate.
- **Stat affected**: QB `pass_yards` (mean + KS), WR `receiving_yards` (mean + KS), TE `receiving_yards`. QB pass_yards is summed from per-receiver yards; qb_split scales those.
- **Mechanism**: Per-game `(pressure_environment − 1.0) × qb_pressure_response × sensitivity` factor multiplied into receiver `receiving_yards_dist` and `catch_rate`. When pressure-resistant QB plays a high-pressure defense, distribution scales *up*, lifting QB pass_yards (sum over receivers). Currently neutral by default — contributes to the QB pass_yards `−28 yd/game` mean shortfall.
- **KS gain potential**: medium (high if mean bias is partly QB-specific, low if mean bias is uniform across all QBs which would imply the engine already correctly assumes neutral).
- **rank_corr/MAE risk**: **medium**. Original v1 regressed weekly_mae by `+0.006`. The retune lowers sensitivities which should reduce variance contribution. Still riskier than rb_scheme_fit.
- **Effort**: days
- **Dependencies**: PFF `passing_detail` parquet (cached locally), matchup engine enabled (already on by default — qb_split gates on matchup availability per `qb_split.py` runtime).

### H-P5-04: Stat-specific KS re-measurement of QB designed-run chain
- **Slice**: QB designed-run chain (`qb_rushing.designed_runs`)
- **Action**: enable temporarily for one A/B run; measure stat-level KS specifically for QB `rushing_yards` (not aggregate fpts_ks); compare to current chain-off baseline.
- **Stat affected**: QB `rushing_yards` (KS via tier-bucketed tail samples + selection probability), secondary effect on QB `fpts`.
- **Mechanism**: Replaces QB's per-game `rushing_yards_dist` with mobility-tier-bucketed tail samples from the learned artifact when designed-run play. Tier-conditional rather than player-conditional, addressing low-sample QB rush distributions.
- **KS gain potential**: **small-medium** (smoke evidence already shows the aggregate fpts KS regressed `+0.003`, but QB-specific rush-yards KS was not isolated).
- **rank_corr/MAE risk**: **medium** — smoke already failed average-rank gate (`−0.0007`). Under KS-priority hard floor (`-0.005 rank_corr`) this is *inside* tolerance, but the TE weekly regression (`−0.0049`) is essentially at the floor already.
- **Effort**: hours (artifact exists, just need stat-KS-specific A/B output)
- **Dependencies**: `results/qb_rushing/designed_runs/smoke_v1/qb_designed_run_model_<season>.json` artifacts (already fitted).

### H-P5-05: Isolated rb_efficiency tracking re-test under KS regime
- **Slice**: `tracking.rb_efficiency` (with `tracking.enabled=true`, all other tracking slices off)
- **Action**: enable selectively (`tracking.enabled=true, tracking.receiver_participation.enabled=false, tracking.rb_efficiency.enabled=true, tracking.qb_context.enabled=false`); measure RB `rush_yards` KS.
- **Stat affected**: RB `rush_yards` (KS via `rushing_yards_dist` scaling), RB `carry_share` (volume).
- **Mechanism**: 4-week rolling window of NGS rushing data scales RB `carry_share` and `rushing_yards_dist` by clamped `[0.93, 1.07]` factor. Same KS-shaping mechanism as rb_scheme_fit but on a different signal (recent NGS performance vs scheme-fit).
- **KS gain potential**: medium (could stack with H-P5-01 or compete; needs measurement).
- **rank_corr/MAE risk**: medium. Original v1 had `weekly_mae Δ +0.000` (flat) but `season_mae Δ −0.063` (positive). Under KS-priority, the flat weekly MAE means it doesn't violate the hard floor.
- **Effort**: days
- **Dependencies**: NGS rushing parquet (cached for 2022-2024), H-P5-01 either resolved or run alongside to measure stack vs conflict.

## Open questions

- **Are the `pff.depth_role.efficiency` clamps `[0.94, 1.06]` / `[0.92, 1.08]` too tight to move WR/TE `receiving_yards` KS measurably?** The volume-only branch was tested with the same conservative clamps; KS may need more headroom. Worth running both at default and at `[0.90, 1.10]` to compare.
- **Does `rb_scheme_fit` interact with the post-sim `dynamic_blend` and `residual_calibration`?** Both ensemble layers operate on `fpts` at the projection level; they should not double-count rb_scheme_fit's distribution-level changes. But the V1 smoke run already had ensemble on, so the positive deltas are already inclusive of the interaction.
- **Did the QB designed-run chain's TE weekly regression (`−0.0049`) come from a real signal or from sim variance?** The chain only touches QB rushing — TE should be neutral. The regression suggests downstream ensemble/calibration is propagating QB-fpts changes into TE rankings via cross-position effects in `dynamic_blend` weights. Worth investigating before re-enabling.
- **Could `qb_split` retune help the QB `pass_yards` `−28 yd/game` mean bias if the bias is mostly from `CATCH_YARDS_BOOST=1` being too small?** The `play_resolver.py:32` boost is league-uniform; qb_split could add per-QB-per-matchup variance that closes individual gaps even if the aggregate shift comes from boost retune. They may be complementary, not substitutes.
- **Does the user's "QB designed-run priority parked after smoke" memory mean we should NOT re-test even for KS?** The memory says "parked after smoke" — implies the user has decided the chain is not worth additional engineering work. A KS-only re-measurement (no code changes) may still be valuable since it's cheap, but any retune is out of scope per memory.
- **Are there `team_context` re-test results in the Phase 6 ledger that contradict the "parked" status?** Per `docs/superpowers/plans/2026-04-14-phase-6-parked-levers.md`, four parked levers got isolated retests. The rb_scheme_fit decision artifact predates that retest cycle. Worth checking ledger for any newer rb_scheme_fit / qb_split / depth_role isolated runs before assuming the audit numbers are final.
