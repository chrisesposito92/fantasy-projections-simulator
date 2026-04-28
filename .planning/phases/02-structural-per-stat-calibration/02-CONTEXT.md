# Phase 2: Structural Per-Stat Calibration - Context

**Gathered:** 2026-04-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Address the architectural blocker that `residual_calibration` and `dynamic_blend` adjust `fpts` only, leaving stat distributions un-calibrated. Ship 7 KS-XX items: per-stat residual_calibration extension (KS-09), dynamic_blend simulator-weight floor (KS-08), per-position max_abs_adjustment + TE elite-tier override (KS-10), tier_engine reliability cap raise for high-touch positions (KS-11), share-normalization residual fix coordinated with availability (KS-12), ff_opportunity prior width via lo/hi quantiles or fitted residual std (KS-13), thin-bucket Bayesian shrinkage (KS-14). With Phase 1 bug noise removed, structural-fix measurements are now interpretable. Phase-2 entry baseline = ledger entry `p1.aggregate.full` (#105) Arm B (post-Phase-1 promoted defaults).

Out of scope for this phase (belongs in later phases):
- KS-02, KS-16, KS-17, KS-18 — Phase 5 PFF slice activations (Phase 3)
- KS-19, KS-20, KS-21 — new-signal integration including Odds API alt-line CDF engine (Phase 4)
- v2 long-tail items KS-22..KS-33 — deferred to follow-up initiative

</domain>

<decisions>
## Implementation Decisions

### KS-09 Per-Stat residual_calibration (architectural)

- **D-01:** **fpts integration path = two-stage layered.** Apply per-stat correction first (writes corrected stat columns); then apply the existing fpts-level `residual_calibration` on top of the simulator's raw `fpts` (unchanged). Final `fpts = raw_sim_fpts + existing_fpts_correction`, independent of stat-level corrections. Resolves HYPOTHESES.md Open Q 6 in favor of (b). Rationale: safer rollback — if stat corrections misfire, fpts ranking/MAE wins still hold. Accepted cost: corrected stats and corrected fpts can diverge slightly (e.g., corrected `pass_yards * 0.04 ≠` corrected fpts contribution); this is documented and not chased in v1.
- **D-02:** **Rollout = feature-flag gated** via `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled` (continuing Phase 1 D-45 pattern). Default `false` during plan execution; promotion commit flips default to `true` in `config/defaults.yaml` after the Phase 2 aggregate A/B passes hard floor + KS-09 promotion bar (D-14). Rollback = flip flag back to `false`; existing fpts-level calibration continues to work. Resolves HYPOTHESES.md Open Q 5.
- **D-03:** **Stat coverage = all scoring-impacting stats (~14 columns).** QB: `pass_yards`, `pass_tds`, `interceptions`, `rush_yards`, `rush_tds`, `fumbles_lost`. RB: `rush_yards`, `rush_tds`, `receiving_yards`, `receptions`, `fumbles_lost`. WR/TE: `receiving_yards`, `receptions`, `receiving_tds`, `fumbles_lost`. Matches HYPOTHESES KS-09 framing ("no remediation path for stat-level KS"). Per-stat coverage list goes into `config/defaults.yaml` under `ensemble.residual_calibration.stat_level.covered_stats` so downstream agents can audit and modify without touching code.
- **D-04:** **Per-row clamp = std-scaled** at `±2 * sqrt(actual_var)` where `actual_var` is computed from the training-season hold-out distribution per `(position, usage_tier, stat)` bucket. Stored per-bucket in `stat_corrections.{stat}.clamp_std` in the calibration artifact. Adapts to stat scale (QB pass_yards std ~80 vs WR receptions std ~2). Same Bayesian-shrinkage spirit used elsewhere in the project. Per HYPOTHESES KS-09 verbatim.

### KS-08 dynamic_blend Simulator-Weight Floor

- **D-05:** **Sweep = three-point {0.20, 0.30, 0.40}, smallest-passing selection.** Run `validate.py` A/B at each floor value. Pick the SMALLEST floor that (a) clears hard floor `rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05` AND (b) shows non-zero KS Δ improvement on TE/WR fpts. Conservative on MAE — `ff_opportunity` is winning MAE precisely because it dominates, so larger floors cost more MAE. Ledger labels: `p2.ks08.s020.{bare,full}`, `p2.ks08.s030.{bare,full}`, `p2.ks08.s040.{bare,full}`. Resolves HYPOTHESES.md Open Q 2.
- **D-06:** **Form = Option A (floor + renormalize).** In `src/fantasy_sim/scoring/dynamic_blend.py` after the existing `normalize_weights(...)` call inside `_artifact_weights()`, clamp `weights[SIMULATOR_SOURCE] = max(weights[SIMULATOR_SOURCE], floor)` and renormalize the other sources (`ff_opportunity`, `market_history`) proportionally to sum to 1.0. Re-fit `scripts/fit_dynamic_blend_weights.py` with the floor as a training constraint so the bundled `decision_s200/weights_2024.json` artifact (and any future season artifacts) train under the same floor. Surgical change (~15 lines runtime + training-script update); preserves existing artifact schema, dynamic_blend semantics, and ff_opportunity weight auditing. Option B (shrinkage center) deferred — KS-13 (ff_opportunity prior width) covers similar mechanism with simpler architecture.

### KS-10 Per-Position max_abs_adjustment + TE Elite Tier

- **D-07:** **Ship the HYPOTHESES KS-10 values verbatim.** Per-position caps in `config/defaults.yaml` under `ensemble.residual_calibration.max_abs_adjustment_by_position`: `QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8`. Add a 4th "elite" tier above `14.0 fpts` for TE in `USAGE_TIER_THRESHOLDS` (`src/fantasy_sim/scoring/residual_calibration.py:25-30`); lower TE `min_bucket_rows` to `100` from `200`. Update lookup at `residual_calibration.py:109-111` to read per-position cap. Single A/B for the bundle (no per-position sweep — small-medium gain doesn't justify ~12 sweep runs). Ship behind `phase2_ks_flags.ks10_per_position_caps.enabled`.

### KS-11 tier_engine Reliability Cap Retune

- **D-08:** **Position-specific cap raise (config-only).** Add `pff.tier_engine.position_reliability` block in `config/defaults.yaml`:
  ```yaml
  pff.tier_engine.position_reliability:
    WR: { floor: 0.30, cap: 0.95, min_targets: 30 }
    TE: { floor: 0.30, cap: 0.95, min_targets: 30 }
    RB: { floor: 0.25, cap: 0.92, min_carries: 50 }
  ```
  QB stays at current `floor: 0.20, cap: 0.80`. Update `_blend_yards()` at `src/fantasy_sim/data/pff/tier_engine.py:1034-1052` and `position_reliability` at `tier_engine.py:961-965` to look up per-position values, gated by min targets/carries threshold. Mixture-of-CDFs approach explicitly deferred — would re-architect the blending core, larger code surface, deferred to v2 backlog if KS-11 cap raise underdelivers. Ship behind `phase2_ks_flags.ks11_position_reliability.enabled`.

### KS-12 Share-Normalization Residual

- **D-09:** **Compose with availability engine.** In `src/fantasy_sim/data/player_builder.py:618-693` `_normalize_roster_shares`, normalize to `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` instead of exactly `1.0`. Small remainders go to a "league-default" residual not allocated to any roster player. Coordinates with `availability` engine so weeks with multiple inactives don't artificially redistribute their shares onto starters. Add backup-TE/WR equivalent of the existing `MIN_QB_CARRY_SHARE = 0.10` exclusion (currently no equivalent for non-QB pocket players). Ship behind `phase2_ks_flags.ks12_share_normalization_residual.enabled`. New tests cover: (a) full-roster week (expected_active_shares ≈ 1.0, behavior unchanged); (b) multi-inactive week (residual non-zero, no over-redistribution); (c) interaction with `availability` engine on/off. **Risk-flag for planner:** ROADMAP risk note explicitly says "coordinate so the residual doesn't double-count availability-driven share reductions" — this is the planner's primary integration concern.

### KS-13 ff_opportunity Prior Width

- **D-10:** **Probe-then-decide (single plan, two execution paths).** Step 1: 1-day probe to verify `total_fantasy_points_exp_lo` and `total_fantasy_points_exp_hi` columns exist in the raw schema read by `src/fantasy_sim/data/ensemble/loader.py`. **Path A (lo/hi found):** Build Gaussian prior with `mean = prior_fpts`, `std = (hi - lo) / (2 * 1.28)` (80% interval). When `dynamic_blend` uses ff_opportunity at high weight, sample N independent fpts shifts per player. **Path B (lo/hi missing):** Reduce to fitting our own per-bucket residual variance model from training-season ff_opportunity_prior vs actual_fpts data. Use per-bucket fpts std as the prior std. Either path ships behind `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled`. Probe outcome documented in plan summary; decision made within the plan, not pre-committed here.

### KS-14 Thin-Bucket Bayesian Shrinkage

- **D-11:** **MIN_BUCKET_PLAYS 10 → 5 + Bayesian shrinkage.** Lower `MIN_BUCKET_PLAYS = 10 → 5` in `src/fantasy_sim/data/preprocessor.py:9`. Add Bayesian shrinkage formula: when a `(play_type, GameStateBucket)` has `personal_plays` between 5 and 9, blend with team default at strength `5 * team_default_plays` so thin buckets shrink toward team default proportionally to their data thinness, instead of falling back hard. Add audit metric in `src/fantasy_sim/validation/coverage.py` reporting per-position fallback rate (`buckets_below_min_plays_pct`). Ship behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled`. Per HYPOTHESES KS-14 verbatim — confidence high.

### Sequencing & Plan Structure

- **D-12:** **Within-phase order = KS-08 → KS-09 → KS-14 → KS-10 → KS-11 → KS-13 → KS-12.** KS-08 and KS-09 lock first per ROADMAP critical path (KS-08 simpler grid-search; KS-09 layers per-stat correction on top of restored simulator variance). The remaining 5 sort by ascending hard-floor risk per HYPOTHESES: KS-14 (very low) → KS-10 (very low) → KS-11 (low) → KS-13 (low) → KS-12 (medium, last because `_normalize_roster_shares` fires 9+ times per game build, biggest blast radius if it regresses).
- **D-13:** **One plan per KS (Phase 1 cadence).** Total 9 plans:
  - **Plan 01** — Entry baseline + flag scaffolding: pin `p2.entry.full` ledger entry (Arm A bare, Arm B = current post-Phase-1 defaults), add `phase2_ks_flags:` block to `config/defaults.yaml` with 7 flags (one per KS), add `get_phase2_ks_flags()` shim in `src/fantasy_sim/config/loader.py`, extend `bare_config_dict()` per Phase 1 D-44 pattern to enumerate the new flags. KS-09 also requires calibration artifact schema bump; that lives in Plan 03.
  - **Plan 02** — KS-08 (sim-weight floor sweep, 3 A/B, ship smallest-passing).
  - **Plan 03** — KS-09 (per-stat residual_calibration; biggest single plan; artifact schema + training pipeline + runtime gating).
  - **Plan 04** — KS-14 (MIN_BUCKET_PLAYS + shrinkage).
  - **Plan 05** — KS-10 (per-position caps + TE elite tier).
  - **Plan 06** — KS-11 (tier_engine reliability cap raise).
  - **Plan 07** — KS-13 (ff_opportunity prior width; probe-then-decide).
  - **Plan 08** — KS-12 (share-normalization residual + availability composition).
  - **Plan 09** — Phase 2 aggregate validation (`p2.aggregate.full` vs `p1.aggregate.full` delta; walk-back trigger if hard floor regresses).
- **D-14:** **KS-09 promotion bar = hard floor + KS Δ ≤ -0.03 on QB pass_yards + QB pass_yards mean bias |Δ| ≤ 5 yd/g vs Phase-1 baseline.** Phase 1 D-31 promotion bar for medium-large items was `hard floor + KS Δ ≤ -0.01 on primary target`; KS-09 is rated "very large" by HYPOTHESES, so raise the bar. PROJECT.md flags QB pass_yards mean bias as the headline Phase 1 miss (-39.29 yd/g; TGT-09 target ±5) — KS-09 is the architectural lever for closure, so the bar must include explicit bias closure. If KS-09 lands hard floor + KS Δ on QB pass_yards but bias |Δ| > 5 yd/g, mark `SHIPPED-PARTIAL` and document the residual gap; the architecture stays for Phase 3/4 levers (depth_role, qb_split, Odds API alt-line) to layer on top.
- **D-15:** **End-of-phase aggregate mirrors Phase 1 Plan 11 pattern.** Plan 09 runs `validate.py --baseline bare --label p2.aggregate.full` after all KS items (08, 09, 14, 10, 11, 13, 12) have shipped to `defaults.yaml`. Compute Phase-2-vs-Phase-1 delta from ledger entries `p2.aggregate.full` Arm B vs `p1.aggregate.full` Arm B. Hard floor + headline criteria (TGT-09 QB bias, TGT-01 QB pass_yards KS, TGT-08 fpts KS, TGT-04 TE receptions KS) evaluated against this delta. **Walk-back trigger** = hard-floor regression on the Phase-2-vs-Phase-1 delta (NOT Phase-2-vs-Phase-0). Cumulative tracking deferred to Phase 5 wrap-up. PROJECT.md `Current` column updates after Plan 09 success.

### Carry-Forward (no re-ask, locked from prior phases)

- **C-01:** Hard floor on every per-KS A/B: `rank_corr Δ ≥ -0.005` AND `MAE Δ ≤ +0.05` (per `feedback_quality_over_simplicity.md`, PROJECT.md core constraint).
- **C-02:** Phase-2 entry baseline = ledger entry `p1.aggregate.full` (#105) Arm B per Phase 1 closure note in `PROJECT.md` and `STATE.md`.
- **C-03:** A/B mode per change = true isolation (`--baseline bare --arm-b-base bare --set <KS-X overrides>`) AND full-stack (`--baseline defaults --set <KS-X overrides>`) per Phase 1 D-29 (revised post-Codex review).
- **C-04:** Validation set = all 2022-2024, 200 sims/season, PPR scoring per Phase 1 D-28.
- **C-05:** Agents execute `scripts/validate.py` directly per Phase 1 D-29 + memory `feedback_ab_manual.md` (rule reversed 2026-04-26).
- **C-06:** Per-KS feature-flag pattern continues from Phase 1 D-45: each per-KS code change behind `phase2_ks_flags.ksXX_<name>.enabled` (default `false`, promotion commit flips to `true`). Plan 01 adds the new flag block + `get_phase2_ks_flags()` shim.
- **C-07:** Ledger label scheme: `p2.ksXX.{bare,full}` per change; KS-08 sweep uses `p2.ks08.s020.{bare,full}`/`s030`/`s040`; aggregate is `p2.aggregate.full`.
- **C-08:** TDD-first for KS-08 and KS-09 (medium-large structural changes per HYPOTHESES; 6-10 unit tests each); test-after acceptable for KS-10/11/13/14; KS-12 requires TDD on the availability-composition tests per the integration risk in ROADMAP risk notes.
- **C-09:** Existing 1,200+ test suite (now 2,131 post-Phase-1) must stay green throughout; per Phase 1 D-35.
- **C-10:** PFF blending discipline carries forward per `feedback_qb_calibration.md`: KS-11 `pff.tier_engine.position_reliability` MUST NOT alter the existing `feedback_qb_calibration` rules (no QB carry_share / scramble_rate / yards blending).

### Claude's Discretion

- KS-09 calibration artifact filename + path layout (`src/fantasy_sim/data/ensemble/artifacts/residual_calibration/...`) — planner picks based on existing `decision_s200` convention.
- KS-09 training-pipeline season iteration (which seasons train artifact, which holds out for validation) — planner mirrors existing `fit_residual_calibration.py` season-folding logic.
- KS-12 backup-TE/WR exclusion threshold (mirror `MIN_QB_CARRY_SHARE = 0.10` or pick a different value for receiving roles) — planner picks based on per-position empirical share floor.
- KS-13 probe execution mechanics (whether to add a one-off `scripts/probe_ff_opportunity_quantiles.py` or do it inline in the loader) — planner picks based on whether the probe outcome reusable downstream.
- Specific `phase2_ks_flags` flag-name suffixes (e.g., `ks08_simulator_weight_floor` vs `ks08_dynamic_blend_floor`) — planner picks consistent with Phase 1 naming convention; documented in Plan 01.
- Test-case enumeration for KS-08/KS-09 TDD — planner derives from HYPOTHESES.md mechanism descriptions plus `feedback_qb_calibration.md` invariants.
- `validate.py` `--show-ledger` integration for the Phase-2-vs-Phase-1 delta surfacing (helper script vs PROMOTION-NOTES.md table) — planner mirrors Phase 1 Plan 11 choice.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Initiative documents
- `.planning/PROJECT.md` — Initiative scope, hard floor, post-Phase-1 baseline values for TGT-XX, Phase 1 closure note flagging QB pass_yards bias regression as Phase 2 KS-09 lever
- `.planning/PROJECT-PHASE0-FROZEN.md` — Original Phase-0 baseline preserved for cumulative tracking
- `.planning/REQUIREMENTS.md` — All 23 KS-XX hypotheses; Phase 2 owns KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14
- `.planning/ROADMAP.md` §"Phase 2" — Goal, dependencies, requirements, success criteria, risk notes including KS-09 feature-flag and integration-path recommendation
- `.planning/STATE.md` — Current position; updated after each phase transition
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` — Phase 1 decisions (especially D-44/D-45/D-46 — feature-flag + bare_config_dict + ledger schema patterns that Phase 2 inherits)

### Hypothesis backlog (definitive mechanism + file:line refs)
- `.planning/research/HYPOTHESES.md` §KS-08 (lines 175-187) — `dynamic_blend` zeros simulator weight; Option A/B mechanisms
- `.planning/research/HYPOTHESES.md` §KS-09 (lines 189-201) — per-stat `residual_calibration` extension; tactical vs deep variants
- `.planning/research/HYPOTHESES.md` §KS-10 (lines 203-224) — per-position max_abs_adjustment + TE elite tier; verbatim values
- `.planning/research/HYPOTHESES.md` §KS-11 (lines 226-245) — tier_engine reliability cap; position_reliability config block
- `.planning/research/HYPOTHESES.md` §KS-12 (lines 247-259) — share-normalization residual; availability composition
- `.planning/research/HYPOTHESES.md` §KS-13 (lines 261-273) — ff_opportunity prior width via lo/hi quantiles
- `.planning/research/HYPOTHESES.md` §KS-14 (lines 275-287) — thin-bucket Bayesian shrinkage
- `.planning/research/HYPOTHESES.md` §"Open Questions" (lines 658-680) — Open Q 2 (resolved D-05 + D-06), Open Q 5 (resolved D-02), Open Q 6 (resolved D-01)
- `.planning/research/HYPOTHESES.md` §"KS Budget Sanity Check" (lines 595-654) — fpts budget allocation (KS-08: -0.04 to -0.07; KS-13: -0.02 to -0.03; KS-09: -0.02 to -0.03)

### Supporting research
- `.planning/research/DISTRIBUTION_SHAPE.md` — Direct evidence for KS-08, KS-09, KS-10, KS-11, KS-13, KS-14
- `.planning/research/MEAN_BIAS.md` — Evidence for KS-09 (H-MB-09 stat-level mean bias)
- `.planning/research/SIGNAL_COVERAGE.md` — Background for ff_opportunity composition (KS-13)
- `.planning/research/PHASE5_SLICES.md` — Background; not directly Phase 2 but informs cap-raise stack interactions

### Codebase brownfield map (refreshed 2026-04-26)
- `.planning/codebase/STRUCTURE.md` — Directory layout, three-layer cache structure
- `.planning/codebase/CONVENTIONS.md` — Naming, RNG patterns, factor patterns, Bayesian blending formula
- `.planning/codebase/ARCHITECTURE.md` — GameContextBuilder facade, post-sim `role_trend → dynamic_blend → residual_calibration` order (Phase 2 modifies this)
- `.planning/codebase/INTEGRATIONS.md` — Cache directories, ensemble artifact locations
- `.planning/codebase/CONCERNS.md` — Field-position clamping fragility (informs KS-09 stat coverage)
- `.planning/codebase/STACK.md` — Python 3.12+, polars (NOT pandas), numpy, uv, pytest
- `.planning/codebase/TESTING.md` — TDD discipline, fixtures, statistical/integration markers

### Project guidance
- `AGENTS.md` — Project architecture, post-sim adjustment pipeline order, A/B testing approach, PFF blending discipline

### Source files (will be read/modified — primary surfaces per KS)

**KS-08 (`dynamic_blend` floor)**
- `src/fantasy_sim/scoring/dynamic_blend.py:700` — `dynamic_blend_simulator_weight` field write
- `src/fantasy_sim/scoring/dynamic_blend.py:795-799` — `row["fpts"]` blend assignment (the compression site)
- `src/fantasy_sim/scoring/dynamic_blend.py` — `_artifact_weights()` (target for floor + renormalize logic)
- `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json` — Bundled artifact (sample bucket: `simulator: 0.0, ff_opportunity: 0.85, market_history: 0.15`)
- `scripts/fit_dynamic_blend_weights.py` — Re-fit with floor constraint
- `config/defaults.yaml` — `ensemble.dynamic_blend.simulator_weight_floor` knob

**KS-09 (per-stat `residual_calibration`)**
- `src/fantasy_sim/scoring/residual_calibration.py:25-30` — `USAGE_TIER_THRESHOLDS` (target for TE elite tier in KS-10, also referenced for KS-09 bucket keys)
- `src/fantasy_sim/scoring/residual_calibration.py:109-111` — `clamp_adjustment` (extend for per-stat clamps)
- `src/fantasy_sim/scoring/residual_calibration.py:367-431` — `adjust_week()` adjuster
- `src/fantasy_sim/scoring/residual_calibration.py:422` — Current `row["fpts"]` write (target — extend with per-stat writes BEFORE this line)
- `src/fantasy_sim/scoring/projections.py:7-60` — Stat aggregations with no post-sim hook (KS-09 wires per-stat correction here OR after `dynamic_blend`)
- `scripts/fit_residual_calibration.py` — Training pipeline; extend artifact schema for `stat_corrections` block
- `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/.../calibration_*.json` — Calibration artifacts (schema bump)

**KS-10 (per-position caps + TE elite tier)**
- `src/fantasy_sim/scoring/residual_calibration.py:25-30` — `USAGE_TIER_THRESHOLDS` (add 4th tier > 14.0 fpts for TE)
- `src/fantasy_sim/scoring/residual_calibration.py:109-111` — `clamp_adjustment` lookup (extend per-position lookup)
- `config/defaults.yaml:374` — `max_abs_adjustment` (replace with `max_abs_adjustment_by_position`)
- `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/.../calibration_2024.json:125-170` — Empty `TE|high|*` bucket (artifact evidence for the elite-tier need)

**KS-11 (tier_engine reliability)**
- `src/fantasy_sim/data/pff/tier_engine.py:961-965` — `position_reliability` (current grade-derived value)
- `src/fantasy_sim/data/pff/tier_engine.py:982` — `np.clip(raw, floor, cap)` (target for per-position lookup)
- `src/fantasy_sim/data/pff/tier_engine.py:1034-1052` — `_blend_yards()` (uses reliability)
- `src/fantasy_sim/data/pff/tier_engine.py:441-477` — `_merge_thin_tiers()` (related — KS-10 elite tier interaction)
- `config/defaults.yaml:82-84` — Existing tier_engine clamps + pool_size (add new `position_reliability` block)

**KS-12 (share-normalization residual)**
- `src/fantasy_sim/data/player_builder.py:618-693` — `_normalize_roster_shares` (the rescale function)
- `src/fantasy_sim/data/player_builder.py:683-693` — `_scale_shares` helper
- `src/fantasy_sim/data/player_builder.py:630` — `MIN_QB_CARRY_SHARE = 0.10` (the existing position-specific exclusion; pattern for backup-TE/WR equivalent)
- `src/fantasy_sim/data/game_context.py:1073-1259` — 9+ call sites per game build (audit for double-normalize)
- `src/fantasy_sim/engine/availability.py` (or equivalent — verify path) — Availability engine integration point

**KS-13 (ff_opportunity prior width)**
- `src/fantasy_sim/scoring/ensemble.py:97-105` — `prior_fpts = float(prior["prior_fpts"])` (the point-estimate site)
- `src/fantasy_sim/data/ensemble/normalizer.py` — Probe target for lo/hi column existence
- `src/fantasy_sim/data/ensemble/loader.py` — Raw schema verification (Path A/B branch decision)

**KS-14 (thin-bucket shrinkage)**
- `src/fantasy_sim/data/preprocessor.py:9` — `MIN_BUCKET_PLAYS = 10` (target → 5)
- `src/fantasy_sim/data/preprocessor.py:100, 137` — Bucket guards (extend with shrinkage)
- `src/fantasy_sim/engine/play_resolver.py:303, 393` — Fallback chain (consumer)
- `src/fantasy_sim/validation/coverage.py` — Add `buckets_below_min_plays_pct` audit metric

### Validation infrastructure
- `scripts/validate.py` — Main A/B harness; agents run with `p2.ksXX.{bare,full}` labels
- `scripts/validate.py` extension from Phase 1 — `--arm-b-base {defaults,bare}` flag (Plan 01 confirms it still works for Phase 2)
- `src/fantasy_sim/validation/ledger.py` — Persistent A/B cache; `SeasonMetrics.stat_mean_bias` (added in Phase 1 D-46) used directly by KS-09 success bar (D-14)
- `src/fantasy_sim/validation/coverage.py` — KS distribution metrics (KS-09 surfaces stat-level KS; KS-14 adds fallback-rate audit)
- `src/fantasy_sim/validation/config.py:118-138` — `build_engine_configs()` keys (Plan 01 extends `bare_config_dict()` per D-44 pattern)

### Phase 1 ledger entries (baseline + reference)
- `phase0.baseline.full` (entry #82) — Original Phase-0 baseline (Arm A bare, Arm B current pre-Phase-1 defaults)
- `p1.aggregate.full` (entry #105) — Post-Phase-1 baseline (Arm A bare, Arm B = post-Phase-1 promoted defaults). **THIS is Phase-2's entry baseline** per C-02.
- `phase0.baseline.bare` — Sanity-check no-op (Arm A == Arm B = bare)

### User memory (carries forward, do not contradict)
- Memory `feedback_ab_manual.md` — REVERSED 2026-04-26: agents run A/B validation directly
- Memory `feedback_ab_testing_approach.md` — Each change tested in isolation (`baseline+X`) AND full-stack (`all_engines+X`)
- Memory `feedback_qb_calibration.md` — PFF layers must NOT blend QB `carry_share`, `scramble_rate`, or yards (binds KS-11 position_reliability — QB stays at current values per D-08)
- Memory `feedback_quality_over_simplicity.md` — Always pick higher quality/accuracy over simpler approaches (binds D-03 stat coverage = full not yards-only)
- Memory `feedback_workflow.md` — Subagent-driven dev validated; phased plans; update docs after each phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`src/fantasy_sim/scoring/residual_calibration.py:367-431`** (`adjust_week`) — Existing fpts adjuster. KS-09 extends this in-place to write per-stat columns BEFORE the existing `row["fpts"]` write at line 422. The fpts-level correction logic stays unchanged per D-01.
- **`src/fantasy_sim/scoring/residual_calibration.py:25-30`** (`USAGE_TIER_THRESHOLDS`) — Defines `low/mid/high` thresholds per position. KS-10 adds 4th `elite` tier > 14.0 fpts for TE; reused by KS-09 for `(position, usage_tier, stat)` clamp_std lookup keys.
- **`src/fantasy_sim/scoring/dynamic_blend.py:795-799`** — Single-line blend assignment `row["fpts"] = (...)`. KS-08 floor takes effect upstream in `_artifact_weights()`; this line is unchanged. Useful as a reference site to verify the floor flowed through.
- **`src/fantasy_sim/data/pff/tier_engine.py:1034-1052`** (`_blend_yards`) — Existing proportional resample. KS-11 swaps the `np.clip(raw, floor, cap)` lookup for a per-position dict. Mixture-of-CDFs deferred per D-08.
- **`src/fantasy_sim/data/player_builder.py:683-693`** (`_scale_shares`) — Existing rescale helper used by `_normalize_roster_shares`. KS-12 wraps this with the `expected_active_shares` calculation per D-09.
- **`src/fantasy_sim/data/preprocessor.py:9, 100, 137`** — Existing `MIN_BUCKET_PLAYS` constant + guards. KS-14 lowers the constant + adds shrinkage formula at the guards.
- **`scripts/fit_residual_calibration.py`** — Existing training script for fpts-only calibration artifacts. KS-09 extends it to also fit per-stat residuals with std-scaled clamp parameters.
- **`scripts/fit_dynamic_blend_weights.py`** — Existing dynamic_blend training script. KS-08 D-06 adds the floor as a training constraint so future-season artifacts ship with the floor baked in.
- **Phase 1 `phase1_ks_flags` pattern** — Plan 01 extends with `phase2_ks_flags` block in `config/defaults.yaml` + `get_phase2_ks_flags()` shim mirroring Phase 1's `get_phase1_ks_flags()` shim. `bare_config_dict()` per Phase 1 D-44 also gets the new flags enumerated.
- **Phase 1 `SeasonMetrics.stat_mean_bias` field** (added in Phase 1 D-46) — KS-09 success bar (D-14) reads `stat_mean_bias["QB"]["pass_yards"]` directly from the persisted ledger; no side script needed.

### Established Patterns

- **Engine pattern** — `class XEngine: __init__(config, loader); compute() → context/result object`. KS-12's availability composition reuses the existing availability engine API; no new engine.
- **Factor pattern** — Multiplicative factors centered on 1.0, clamped to configurable range. KS-08 floor is a sub-pattern (clamp from below, renormalize remainder).
- **Bayesian blending** — `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`. KS-14 uses this formula explicitly with `prior_strength = 5 * team_default_plays`.
- **Std-scaled clamp** — KS-09's `±2 * sqrt(actual_var)` matches the existing PROJECT-wide pattern of "factors clamped to configurable range" but with the bound derived from data instead of constant.
- **Feature-flag toggles per KS** — `phase1_ks_flags.ksXX_<name>.enabled` (Phase 1 D-45). Phase 2 reuses with `phase2_ks_flags.ksXX_<name>.enabled`.
- **Ledger label conventions** — Phase + change identifier; bare vs full-stack suffix (`p2.ksXX.{bare,full}`).
- **A/B isolation + full-stack** — Per change, run both true-isolation (`--baseline bare --arm-b-base bare --set X`) and full-stack (`--baseline defaults --set X`). Both must pass hard floor for promotion.
- **Re-fit training scripts on schema bump** — KS-08 re-fits `fit_dynamic_blend_weights.py` with floor; KS-09 re-fits `fit_residual_calibration.py` with stat_corrections; both ship a re-generated `decision_s200` artifact.

### Integration Points

- **Post-sim layer order** (`AGENTS.md` §"Adjustment Pipeline Order"): `role_trend → dynamic_blend → residual_calibration`. KS-08 changes the WEIGHT inside `dynamic_blend`. KS-09 inserts per-stat correction INSIDE `residual_calibration.adjust_week()` BEFORE the existing fpts-level correction (per D-01). The order itself doesn't change; the work each layer does does.
- **`src/fantasy_sim/data/ensemble/artifacts/`** — Bundled artifact directory. Phase 2 ships re-fit artifacts:
  - `dynamic_blend/decision_s200/weights_2024.json` — KS-08 (sim-weight floor baked in)
  - `residual_calibration/decision_s200/calibration_*.json` — KS-09 (new `stat_corrections` block) + KS-10 (per-position cap baked in)
  - These are loaded by the production runtime; Phase 2 plans must regenerate AND commit them alongside the code changes.
- **`config/defaults.yaml`** — Multiple top-level sites for Phase 2:
  - `ensemble.dynamic_blend.simulator_weight_floor` (KS-08)
  - `ensemble.residual_calibration.stat_level.{enabled, covered_stats, clamp_std_multiplier}` (KS-09)
  - `ensemble.residual_calibration.max_abs_adjustment_by_position` (KS-10)
  - `ensemble.ff_opportunity.prior_width.{enabled}` (KS-13)
  - `pff.tier_engine.position_reliability` (KS-11)
  - `phase2_ks_flags.{ks08, ks09, ks10, ks11, ks12, ks13, ks14}.enabled` (top-level KS flags)
- **Three-layer cache** — KS-08 / KS-09 changes invalidate post-sim ensemble caches automatically; pipeline-output and PBP-stats caches unchanged. KS-14's `MIN_BUCKET_PLAYS` change DOES invalidate the PBP-stats cache (one of the three cache layers); planner must verify cache regeneration in tests.
- **`scripts/validate.py`** — A/B harness already in place; Phase 2 reuses Phase 1's `--arm-b-base bare` flag. Plan 01 verifies the existing flag still works for Phase 2 KS-flags (no scope changes assumed).
- **`SeasonMetrics.stat_mean_bias`** — Added in Phase 1 D-46. KS-09 success bar (D-14) reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` directly from ledger entries (`p1.aggregate.full` + `p2.ks09.full` + `p2.aggregate.full`). No new schema bump required for KS-09 success measurement.

</code_context>

<specifics>
## Specific Ideas

- **D-01 two-stage layered fpts:** ROADMAP risk note explicitly recommends path (b) for safer rollback; user confirmed. Architecture cleanliness of path (a) deferred — if Phase 2 closes the targets cleanly, path (a) becomes a future "consolidation" plan, not a current blocker.
- **D-02 feature flag:** continues Phase 1 D-45 explicitly. Plan 01 must enumerate ALL 7 new Phase 2 flags in `bare_config_dict()` per Phase 1 D-44 (the Codex Cycle-2 fix). Existing Phase-1-flag enumeration is reused as the pattern.
- **D-04 std-scaled clamp:** matches HYPOTHESES KS-09 literally (`±2 * sqrt(actual_var)`). Per-bucket `clamp_std` lives inside the artifact, not in `defaults.yaml` — config stays clean, artifact contains data-derived values.
- **D-05 smallest-passing floor:** matches ROADMAP risk note "pick the smallest floor that recovers KS while staying within MAE +0.05". Conservative on MAE because ff_opportunity is winning MAE.
- **D-06 Option A:** prefer surgical change. Option B (shrinkage center) deferred unless Option A underperforms — KS-13 (ff_opp prior width) covers the same residual-variance idea with simpler architecture.
- **D-07 KS-10 verbatim values:** "Ship the HYPOTHESES values directly" — no per-position cap sweep. HYPOTHESES KS-10 rates this `small-medium gain, very low risk`; sweep ROI is poor.
- **D-08 KS-11 config-only:** mixture-of-CDFs is bigger architectural lift; deferred. Position cap raise alone hits the elite-player compression issue. QB stays at floor 0.20, cap 0.80 per `feedback_qb_calibration.md` — this is the binding constraint, not an oversight.
- **D-09 KS-12 availability composition:** ROADMAP risk note flags this as the planner's primary integration concern. Plan 08 must document the integration test cases explicitly: full roster (no change), multi-inactive (residual non-zero), availability off (graceful degradation). Backup-TE/WR exclusion threshold left to planner discretion.
- **D-10 KS-13 probe-then-decide:** single plan with branch logic. Probe outcome (lo/hi present or absent) goes into the plan summary; both Path A and Path B are pre-coded so the plan doesn't stall on probe outcome.
- **D-11 KS-14 with shrinkage:** the Bayesian shrinkage is the safety. "Lower threshold only, no shrinkage" was rejected because thin buckets (5-9 plays) without shrinkage produce noisy means.
- **D-12 risk-graded order:** KS-12 last is deliberate — `_normalize_roster_shares` fires 9+ times per game build, biggest blast radius if it regresses. Putting low-risk items first means cumulative budget is preserved if a late item misfires.
- **D-13 one plan per KS:** matches Phase 1 cadence. Plan 01 + 7 KS plans + Plan 09 aggregate = 9 plans total.
- **D-14 KS-09 elevated bar:** `KS Δ ≤ -0.03 on QB pass_yards` AND `mean bias |Δ| ≤ 5 yd/g`. Phase 1 D-31 was `≤ -0.01` for medium-large items; KS-09 is "very large" per HYPOTHESES so the bar tightens. PROJECT.md flags QB pass_yards bias as the headline Phase 1 miss (-39.29 yd/g) — KS-09 is the architectural lever.
- **D-15 mirror Phase 1 Plan 11:** Plan 09 records `p2.aggregate.full` ledger entry; computes Phase-2-vs-Phase-1 delta; walk-back trigger is hard-floor regression on the differenced delta. Two-pivot tracking deferred to Phase 5 wrap-up (cumulative initiative summary).
- **C-06 flag default policy:** every per-KS flag defaults to `false` during plan execution. Promotion commit per plan flips default to `true` after the per-KS A/B clears its bar. This means at any commit during Phase 2 execution, only the KS items that have promoted have flags `true`; the active stack matches the persisted ledger.

</specifics>

<deferred>
## Deferred Ideas

- **KS-09 path (a) "re-derive fpts from corrected stats"** — D-01 selects path (b) for safety. If Phase 2 lands cleanly, a future "consolidation" plan can revisit path (a) for architectural cleanliness. Logged in v2 backlog candidate list.
- **KS-08 Option B "shrinkage center" form** — D-06 selects Option A. If Option A's smallest-passing floor underdelivers (KS Δ > -0.04 on TE/WR fpts), Option B becomes a Phase 2 follow-up plan or v2 backlog item. KS-13 may subsume this need.
- **KS-09 path expansion to TDs/fumbles only if needed** — D-03 covers all scoring-impacting stats up front. If artifact-fitting reveals certain columns (e.g., `interceptions`, `fumbles_lost`) lack sufficient bucket data, planner may scope-reduce; documented in plan.
- **KS-11 mixture-of-CDFs architecture** — D-08 selects config-only cap raise. Full mixture-of-CDFs (band-targeted blending) deferred to v2 backlog if cap raise underdelivers.
- **KS-12 alternative simpler "relax sum-to-1.0" approach** — D-09 selects availability composition. If the composition test cases (full roster / multi-inactive / availability-off) prove too brittle in implementation, planner may fall back to simpler relax approach in-plan; documented in plan summary.
- **KS-13 path "fit our own residual variance up front"** — D-10 selects probe-then-decide. The fitting path is Path B inside the same plan; not deferred outside Phase 2.
- **Per-stat residual_calibration cumulative ledger entries** — D-15 selects mirror-Phase-1 aggregate (single end-of-phase entry). Per-KS-cumulative tracking (`p2.cumulative.through_ksXX.full` after each promotion) is deferred to Phase 5 wrap-up.
- **KS-09 "deep variant" (per-sim fpts arrays through dynamic_blend)** — HYPOTHESES KS-09 mentions this as a deeper architectural option. Out of scope for v1 of KS-09; explicit deferral to v2 backlog or future "Hybrid ML Fork" initiative (referenced in user memory `project_hybrid_ml_fork.md`).
- **End-of-initiative Phase-2-vs-Phase-0 cumulative ledger entry** — D-15 defers two-pivot aggregate. Phase 5 wrap-up plan computes cumulative initiative progress from `p2.aggregate.full` vs `phase0.baseline.full`.

</deferred>

---

*Phase: 02-structural-per-stat-calibration*
*Context gathered: 2026-04-26*
