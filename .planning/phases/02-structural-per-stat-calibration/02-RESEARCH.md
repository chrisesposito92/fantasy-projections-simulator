# Phase 2: Structural Per-Stat Calibration - Research

**Researched:** 2026-04-26
**Domain:** NFL fantasy projections simulator — structural per-stat residual calibration + dynamic_blend simulator-weight floor + tier_engine reliability cap retune + share-normalization residual + ff_opportunity prior width + thin-bucket Bayesian shrinkage
**Confidence:** HIGH (every claim grounded in current source files at `src/fantasy_sim/...` plus `.planning/research/HYPOTHESES.md` and the locked decisions in `.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md` D-01..D-15 / C-01..C-10)

## User Constraints

> Copied verbatim from `.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md` `<decisions>` (D-01..D-15) and `<carry-forward>` (C-01..C-10). Locked. Non-negotiable.

### KS-09 Per-Stat residual_calibration (architectural)

- **D-01:** fpts integration path = **two-stage layered**. Apply per-stat correction first (writes corrected stat columns); then apply the existing fpts-level `residual_calibration` on top of the simulator's raw `fpts` (unchanged). Final `fpts = raw_sim_fpts + existing_fpts_correction`, independent of stat-level corrections. Resolves HYPOTHESES.md Open Q 6 in favor of (b). Per-stat and fpts corrections may diverge slightly; documented and not chased in v1.
- **D-02:** Rollout = feature-flag gated via `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled` (continuing Phase 1 D-45 pattern). Default `false` during plan execution; promotion commit flips default to `true` in `config/defaults.yaml` after the per-KS A/B passes hard floor + KS-09 promotion bar (D-14). Rollback = flip flag back to `false`.
- **D-03:** Stat coverage = all scoring-impacting stats (~14 columns). QB: `pass_yards`, `pass_tds`, `interceptions`, `rush_yards`, `rush_tds`, `fumbles_lost`. RB: `rush_yards`, `rush_tds`, `receiving_yards`, `receptions`, `fumbles_lost`. WR/TE: `receiving_yards`, `receptions`, `receiving_tds`, `fumbles_lost`. Coverage list lives in `config/defaults.yaml` under `ensemble.residual_calibration.stat_level.covered_stats`.
- **D-04:** Per-row clamp = std-scaled at `±2 * sqrt(actual_var)` where `actual_var` is computed from the training-season hold-out distribution per `(position, usage_tier, stat)` bucket. Stored per-bucket in `stat_corrections.{stat}.clamp_std` in the calibration artifact. Adapts to stat scale (QB pass_yards std ~80 vs WR receptions std ~2).

### KS-08 dynamic_blend Simulator-Weight Floor

- **D-05:** Sweep = three-point `{0.20, 0.30, 0.40}`, smallest-passing selection. Run `validate.py` A/B at each floor value. Pick the SMALLEST floor that (a) clears hard floor `rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05` AND (b) shows non-zero KS Δ improvement on TE/WR fpts. Ledger labels: `p2.ks08.s020.{bare,full}`, `p2.ks08.s030.{bare,full}`, `p2.ks08.s040.{bare,full}`.
- **D-06:** Form = Option A (floor + renormalize). After the existing `normalize_weights(...)` call inside `_artifact_weights()` (`src/fantasy_sim/scoring/dynamic_blend.py:529-542`), clamp `weights[SIMULATOR_SOURCE] = max(weights[SIMULATOR_SOURCE], floor)` and renormalize the other sources (`ff_opportunity`, `market_history`) proportionally to sum to 1.0. Re-fit `scripts/fit_dynamic_blend_weights.py` with the floor as a training constraint so the bundled `decision_s200/weights_2024.json` and `weights_2023.json` artifacts train under the same floor.

### KS-10 Per-Position max_abs_adjustment + TE Elite Tier

- **D-07:** Ship the HYPOTHESES KS-10 values verbatim. Per-position caps in `config/defaults.yaml`:
  ```yaml
  ensemble.residual_calibration.max_abs_adjustment_by_position:
    QB: 2.5
    RB: 2.0
    WR: 1.5
    TE: 0.8
  ```
  Add a 4th `elite` tier above `14.0 fpts` for TE in `USAGE_TIER_THRESHOLDS` (`src/fantasy_sim/scoring/residual_calibration.py:25-30`); lower TE `min_bucket_rows` to `100` from `200`. Update `clamp_adjustment` lookup at `residual_calibration.py:109-111` to read per-position cap. Single A/B for the bundle.

### KS-11 tier_engine Reliability Cap Retune

- **D-08:** Position-specific cap raise (config-only). Add `pff.tier_engine.position_reliability` block in `config/defaults.yaml`:
  ```yaml
  pff.tier_engine.position_reliability:
    WR: { floor: 0.30, cap: 0.95, min_targets: 30 }
    TE: { floor: 0.30, cap: 0.95, min_targets: 30 }
    RB: { floor: 0.25, cap: 0.92, min_carries: 50 }
  ```
  QB stays at current `floor: 0.20, cap: 0.80`. The `compute_reliability(...)` method already reads `cfg.position_reliability` (`tier_engine.py:957-965`); the change is config-side plus an optional gate on `min_targets`/`min_carries` to confirm the player is "high-touch".

### KS-12 Share-Normalization Residual

- **D-09:** Compose with availability engine. In `src/fantasy_sim/data/player_builder.py:661-693` `_normalize_roster_shares`, normalize to `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` instead of exactly `1.0`. Small remainders go to a "league-default" residual not allocated to any roster player. Add backup-TE/WR equivalent of the existing `MIN_QB_CARRY_SHARE = 0.10` exclusion. New tests cover: (a) full-roster week (expected_active_shares ≈ 1.0, behavior unchanged); (b) multi-inactive week (residual non-zero, no over-redistribution); (c) interaction with `availability` engine on/off.

### KS-13 ff_opportunity Prior Width

- **D-10:** Probe-then-decide (single plan, two execution paths). Step 1: probe to verify `total_fantasy_points_exp_lo` and `total_fantasy_points_exp_hi` columns exist in the raw schema read by `src/fantasy_sim/data/ensemble/loader.py`. Path A (lo/hi found): build Gaussian prior with `mean = prior_fpts`, `std = (hi - lo) / (2 * 1.28)` (80% interval). When `dynamic_blend` uses ff_opportunity at high weight, sample N independent fpts shifts per player. Path B (lo/hi missing): fit per-bucket residual variance from training-season ff_opportunity_prior vs actual_fpts data. Either path ships behind `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled`.

### KS-14 Thin-Bucket Bayesian Shrinkage

- **D-11:** `MIN_BUCKET_PLAYS 10 → 5` + Bayesian shrinkage. Lower `MIN_BUCKET_PLAYS = 10 → 5` in `src/fantasy_sim/data/preprocessor.py:10`. When a `(play_type, GameStateBucket)` has `personal_plays` between 5 and 9, blend with team default at strength `5 * team_default_plays` so thin buckets shrink toward team default proportionally. Add audit metric `buckets_below_min_plays_pct` in `src/fantasy_sim/validation/coverage.py`.

### Sequencing & Plan Structure

- **D-12:** Within-phase order = **KS-08 → KS-09 → KS-14 → KS-10 → KS-11 → KS-13 → KS-12**. KS-08 + KS-09 lock first (critical-path); remaining 5 sort by ascending hard-floor risk per HYPOTHESES (KS-14, KS-10 → very low; KS-11, KS-13 → low; KS-12 → medium, last because `_normalize_roster_shares` fires 9+ times per game build).
- **D-13:** One plan per KS (Phase 1 cadence). Total 9 plans:
  - **Plan 01** — Entry baseline + flag scaffolding (`phase2_ks_flags:` block + `get_phase2_ks_flags()` shim + `bare_config_dict()` extension + `p2.entry.full` ledger pin + `stat_corrections` artifact-schema bump).
  - **Plan 02** — KS-08 (sim-weight floor sweep, 3 A/B, ship smallest-passing).
  - **Plan 03** — KS-09 (per-stat residual_calibration; biggest plan; artifact schema + training pipeline + runtime gating + A/B).
  - **Plan 04** — KS-14 (MIN_BUCKET_PLAYS + shrinkage).
  - **Plan 05** — KS-10 (per-position caps + TE elite tier).
  - **Plan 06** — KS-11 (tier_engine reliability cap raise).
  - **Plan 07** — KS-13 (ff_opportunity prior width; probe-then-decide).
  - **Plan 08** — KS-12 (share-normalization residual + availability composition).
  - **Plan 09** — Phase 2 aggregate validation (`p2.aggregate.full` vs `p1.aggregate.full` delta; walk-back trigger if hard floor regresses).
- **D-14:** KS-09 promotion bar = hard floor + KS Δ ≤ -0.03 on QB pass_yards + QB pass_yards mean bias `|Δ| ≤ 5 yd/g` vs Phase-1 baseline. If hard floor + KS Δ pass but bias `|Δ| > 5 yd/g`, mark `SHIPPED-PARTIAL`.
- **D-15:** End-of-phase aggregate mirrors Phase 1 Plan 11 pattern. Plan 09 runs `validate.py --baseline bare --label p2.aggregate.full` after all KS items have shipped to `defaults.yaml`. Compute Phase-2-vs-Phase-1 delta from ledger entries `p2.aggregate.full` Arm B vs `p1.aggregate.full` Arm B. Walk-back trigger = hard-floor regression on the Phase-2-vs-Phase-1 delta.

### Carry-Forward (locked from prior phases)

- **C-01:** Hard floor on every per-KS A/B: `rank_corr Δ ≥ -0.005` AND `MAE Δ ≤ +0.05` (PROJECT.md core constraint, `feedback_quality_over_simplicity.md`).
- **C-02:** Phase-2 entry baseline = ledger entry `p1.aggregate.full` (#105) Arm B.
- **C-03:** A/B mode per change = true isolation (`--baseline bare --arm-b-base bare --set <KS-X overrides>`) AND full-stack (`--baseline defaults --set <KS-X overrides>`).
- **C-04:** Validation set = all 2022-2024, 200 sims/season, PPR scoring.
- **C-05:** Agents execute `scripts/validate.py` directly per memory `feedback_ab_manual.md` (rule reversed 2026-04-26).
- **C-06:** Per-KS feature-flag pattern continues from Phase 1 D-45.
- **C-07:** Ledger label scheme: `p2.ksXX.{bare,full}`; KS-08 sweep `p2.ks08.s020.{bare,full}`/`s030`/`s040`; aggregate `p2.aggregate.full`.
- **C-08:** TDD-first for KS-08 and KS-09 (medium-large structural changes); test-after acceptable for KS-10/11/13/14; KS-12 requires TDD on the availability-composition tests per ROADMAP risk notes.
- **C-09:** Existing 1,200+ test suite (now 2,131 post-Phase-1) must stay green.
- **C-10:** PFF blending discipline: KS-11 `position_reliability` MUST NOT alter `feedback_qb_calibration` invariants (QB stays at `floor: 0.20, cap: 0.80`; no QB carry_share/scramble_rate/yards blending).

## Summary

Phase 2 is a **structural calibration phase** that addresses the architectural blocker exposed during Phase 1: `residual_calibration` and `dynamic_blend` adjust `fpts` only and leave the per-stat distributions un-calibrated, so stat-level KS regressions (especially QB pass_yards `bias` -39.29 yd/g and WR/TE receptions/yards distributions) have no remediation path. Phase 2 ships seven KS-XX items behind feature flags, validates each one through `scripts/validate.py` against the post-Phase-1 baseline (`p1.aggregate.full` Arm B), and then runs an aggregate A/B at end-of-phase to confirm the hard floor `rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05` and the headline criteria (TGT-04 TE receptions ≤ 0.27, TGT-08 fpts KS ≤ 0.18, WR receptions ≤ 0.24, TGT-09 QB pass_yards mean bias `|Δ| ≤ 5` yd/g).

The technical risk is concentrated in three places:

1. **KS-09 per-stat residual_calibration** is the architectural lift — it extends `src/fantasy_sim/scoring/residual_calibration.py:367-431` (`adjust_week`) to write per-stat columns BEFORE the existing `row["fpts"]` write at line 422, bumps the calibration artifact schema (`schema_version: 1 → 2`) to add a `stat_corrections` block, and extends `scripts/fit_residual_calibration.py` to fit per-stat residuals with std-scaled clamps. Two-stage layered fpts (D-01) keeps the existing fpts-level correction unchanged for safer rollback.

2. **KS-12 share-normalization** is the medium-risk integration. `_normalize_roster_shares` at `src/fantasy_sim/data/player_builder.py:661-693` is called by `build_team_roster()` (`player_builder.py:647-658`) which is invoked 9+ times per game build via `src/fantasy_sim/data/game_context.py`. Replacing the `1.0` target with `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` while composing with the `availability` engine without double-counting is the headline integration test target.

3. **KS-08 sim-weight floor** is the smallest mechanical change but the biggest blast radius for MAE — `ff_opportunity` is winning MAE in the post-Phase-1 stack precisely because it dominates the dynamic_blend weights. The smallest-passing sweep is conservative on MAE.

The validation infrastructure is already production-grade from Phase 1 — Plan 00 of Phase 1 shipped `--arm-b-base bare`, `bare_config_dict()` exhaustive enumeration, and `SeasonMetrics.stat_mean_bias` schema bump (v5). Phase 2's only validation work is to extend `bare_config_dict()` to include the new `phase2_ks_flags` plus the new top-level keys (`ensemble.residual_calibration.stat_level.enabled`, `ensemble.residual_calibration.max_abs_adjustment_by_position`, `ensemble.dynamic_blend.simulator_weight_floor`, `ensemble.ff_opportunity.prior_width.enabled`, `pff.tier_engine.position_reliability`), pin the `p2.entry.full` ledger entry (which equals `p1.aggregate.full` Arm B but recorded under the Phase-2 namespace for delta clarity), then run the same isolation + full-stack A/B pattern per KS as Phase 1.

**Primary recommendation:** treat each KS-XX as one plan (atomic commit) in dependency order from D-12; spawn the 7 KS plans plus Plan 01 (scaffolding) and Plan 09 (aggregate); run isolation + full-stack A/B per D-29/C-03 between commits; use the existing `phase1_ks_flags`-style pattern under a new `phase2_ks_flags` namespace. Total: **9 plans** (Plan 01 scaffolding, Plans 02-08 = 7 KS items in D-12 order, Plan 09 aggregate).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Per-stat post-sim correction (NEW) | `scoring/residual_calibration.py::adjust_week` | `scripts/fit_residual_calibration.py` (training); `data/ensemble/artifacts/residual_calibration/decision_s200/calibration_*.json` (artifacts) | KS-09 wires the per-stat write path BEFORE the existing fpts write; per-bucket clamps live in the artifact's new `stat_corrections` block |
| Sim-weight floor in dynamic_blend | `scoring/dynamic_blend.py::_artifact_weights` | `scripts/fit_dynamic_blend_weights.py` (re-fit with floor); `data/ensemble/artifacts/dynamic_blend/decision_s200/weights_*.json` | KS-08 clamps `weights[SIMULATOR_SOURCE] = max(..., floor)` AFTER `normalize_weights(...)` returns and renormalizes the rest |
| Per-position adjustment cap + TE elite tier | `scoring/residual_calibration.py` (`USAGE_TIER_THRESHOLDS`, `clamp_adjustment`) | `config/defaults.yaml` (`ensemble.residual_calibration.max_abs_adjustment_by_position`); calibration artifact (`min_bucket_rows` per-position) | KS-10 adds 4th tier > 14.0 fpts for TE; per-position cap lookup in `clamp_adjustment` |
| Tier-engine reliability ceiling | `data/pff/tier_engine.py::compute_reliability` | `data/pff/models.py::TierConfig.position_reliability`; `data/pff/config.py::_load_tier_config` | KS-11 leverages the existing `position_reliability` config block (already plumbed); only adds defaults for WR/TE/RB |
| Per-stat clamp std (NEW) | calibration artifact (`stat_corrections.{stat}.clamp_std`) | training pipeline (`fit_residual_calibration.py`) | KS-09 D-04 std-scaled clamp = ±2σ from training distribution per (pos, tier, stat) |
| Roster share normalization residual | `data/player_builder.py::_normalize_roster_shares` | `data/player_builder.py::_scale_shares` (helper); availability engine (composition) | KS-12 changes the normalization target from `1.0` to `expected_active_shares` |
| ff_opportunity prior width | `scoring/ensemble.py::FfOpportunityProjectionEnsembler.adjust_week` | `data/ensemble/loader.py` (probe target); `data/ensemble/normalizer.py` (lo/hi column passthrough) | KS-13 adds Gaussian prior `std = (hi - lo) / 2.56` (Path A) or fitted residual std (Path B) |
| Thin-bucket fallback handling | `data/preprocessor.py::compute_play_outcomes` (line 182 guard) | `validation/coverage.py` (audit metric `buckets_below_min_plays_pct`) | KS-14 lowers `MIN_BUCKET_PLAYS = 10 → 5` and adds Bayesian shrinkage when `n in [5,9]` |
| Phase-2 KS feature-flag plumbing | `config/defaults.yaml` (`phase2_ks_flags:` block) | `src/fantasy_sim/config/loader.py::get_phase2_ks_flags` (shim); `validation/config.py::bare_config_dict` (extension) | Plan 01 ships these; per-KS plans flip default `false → true` in promotion commits |
| Calibration artifact loading | `scoring/residual_calibration.py::ResidualCalibrationLayer._artifact` | `data/ensemble/artifacts/residual_calibration/decision_s200/calibration_*.json` | Schema v1 → v2 in Plan 03; artifact loader gracefully degrades when `schema_version > supported` (continue Phase 1 D-46 pattern for `SeasonMetrics.stat_mean_bias`) |
| A/B validation harness | `scripts/validate.py` | `validation/{config.py, ledger.py, cache.py, coverage.py}` | Already production-grade post-Phase-1; Plan 01 only extends `bare_config_dict()` |

## Standard Stack

This phase reuses the existing stack — no new dependencies.

### Core (already present)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | ≥1.26 | Random sampling, `np.std`, `np.sqrt`, `np.clip` (used in `compute_reliability`, `clamp_adjustment`) | All RNG passes through `rng: np.random.Generator` per project convention |
| polars | ≥1.0 | DataFrame ops (training-row aggregation in `fit_residual_calibration.py`, share normalization audits) | Project rule: polars not pandas |
| pytest | ≥8.0 | Test runner | TDD discipline per C-08; 2,131 existing tests post-Phase-1 |
| pytest-xdist | ≥3.0 | Parallel test execution | `uv run pytest tests/ -v` runs in parallel |
| hypothesis | ≥6.0 | Property-based statistical tests | KS-09 stat-coverage and KS-14 shrinkage formula benefit from hypothesis-style tests |
| click | ≥8.0 | CLI (`fantasy-sim` entry point) | No CLI changes in Phase 2 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `scipy.stats.kstest` (existing dependency) | ≥1.10 | Used in `validation/metrics.py::ks_distribution_summary` | Phase 2 plans surface stat-level KS in ledger entries (already wired via `SeasonMetrics.stat_ks` from Phase 1 D-46) |
| `scipy.stats.spearmanr` (existing) | ≥1.10 | Spearman rank correlation in `validation/metrics.py` | Hard-floor metric |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Per-stat correction in `residual_calibration.py` | `dynamic_blend.py` (per-stat blending) | Rejected — `dynamic_blend` already operates on `fpts` only; extending it to stats means re-architecting the blender's bucket-key scheme. KS-09 D-01 (two-stage layered fpts) keeps the change surgical and rollback-safe |
| Mixture-of-CDFs for KS-11 reliability cap | per-position floor/cap dict | Rejected — D-08 explicitly defers mixture-of-CDFs; would re-architect the blending core. Cap raise alone hits the elite-player compression issue per HYPOTHESES.md KS-11 |
| Option B (shrinkage center) for KS-08 | Option A (floor + renormalize) | Rejected per D-06 — Option A is surgical (~15 lines runtime + training-script update); Option B subsumed by KS-13 ff_opportunity prior width which addresses the same residual-variance idea |
| Path (a) re-derive fpts from corrected stats for KS-09 | Path (b) two-stage layered | Rejected per D-01 — Path (a) is architecturally cleaner but riskier (rollback breaks fpts ranking). HYPOTHESES.md Open Q 6 documents the tradeoff |
| Lower `MIN_BUCKET_PLAYS` only (no shrinkage) for KS-14 | `MIN_BUCKET_PLAYS = 5` + Bayesian shrinkage at n∈[5,9] | Rejected per D-11 — thin buckets without shrinkage produce noisy means; Bayesian formula provides the safety |

## Patterns to Mirror (from existing codebase + Phase 1)

### Pattern 1: Phase KS Feature-Flag Block (continues Phase 1 D-45)

`config/defaults.yaml` adds a top-level `phase2_ks_flags:` block, one entry per KS, default `enabled: false`:

```yaml
# config/defaults.yaml — at top of file alongside existing phase1_ks_flags
phase2_ks_flags:
  ks08_dynamic_blend_simulator_floor:
    enabled: false
    floor: 0.20  # promotion commit replaces with smallest-passing value from sweep
  ks09_per_stat_residual_calibration:
    enabled: false
  ks10_per_position_caps:
    enabled: false
  ks11_position_reliability:
    enabled: false
  ks12_share_normalization_residual:
    enabled: false
  ks13_ff_opportunity_prior_width:
    enabled: false
  ks14_thin_bucket_shrinkage:
    enabled: false
```

`src/fantasy_sim/config/loader.py` adds `get_phase2_ks_flags()`:

```python
def get_phase2_ks_flags() -> dict:
    """Return the phase2_ks_flags block from the loaded defaults.yaml.
    Mirrors get_phase1_ks_flags() (loader.py:99-111).
    Returns {} if the block is absent (graceful degradation for older configs).
    """
    defaults = load_defaults()
    return defaults.get("phase2_ks_flags", {})
```

### Pattern 2: bare_config_dict() Exhaustive Enumeration (continues Phase 1 D-44)

`src/fantasy_sim/validation/config.py::bare_config_dict()` adds the new Phase-2 flags + new top-level keys to the disabled-set list. The Phase 1 list is at `validation/config.py:262-267`; Phase 2 plans append:

```python
# Phase 2 KS code-change feature flags (D-45/D-02 pattern continued from Phase 1)
"phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled",
"phase2_ks_flags.ks09_per_stat_residual_calibration.enabled",
"phase2_ks_flags.ks10_per_position_caps.enabled",
"phase2_ks_flags.ks11_position_reliability.enabled",
"phase2_ks_flags.ks12_share_normalization_residual.enabled",
"phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled",
"phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled",
```

The Phase 1 hard-gate test `test_bare_config_dict_produces_all_None_engines` already enforces "every flag with `enabled: true` in defaults must be flipped off in `bare_config_dict()`"; Plan 01's Task 4 extends it with the Phase 2 flags.

### Pattern 3: Per-KS Promotion-State Commit (continues Phase 1 D-25/D-40)

Each per-KS plan ends with a single commit message of the form:

```
feat(02-XX): KS-XX <SHIPPED|SHIPPED-NO-OP|SHIPPED-PARTIAL|BLOCKED> per D-31/D-14 — <one-sentence rationale>

Δ rank_corr <delta>, Δ weekly_mae <delta>, Δ <primary-target-KS> <delta>

Defaults: phase2_ks_flags.ksXX_<name>.enabled=<true|false>

Refs: <CONTEXT.md decisions touched>
```

`SHIPPED` = full-stack passes hard floor + KS Δ on primary target; flag flipped to `true`. `SHIPPED-NO-OP` = hard floor passes but KS Δ doesn't move (per D-31); flag stays `false`. `SHIPPED-PARTIAL` = KS-09 specifically — hard floor + KS Δ pass but bias `|Δ| > 5 yd/g` per D-14; flag flipped to `true` and the bias gap documented in PROMOTION-NOTES.md. `BLOCKED` = hard floor regressed; flag stays `false`, code path stays in tree but dormant.

### Pattern 4: Std-Scaled Clamp from Training Distribution (NEW for KS-09)

KS-09's `±2 * sqrt(actual_var)` per-bucket clamp matches the existing project pattern of "factors clamped to configurable range" (CONVENTIONS.md `## Numerical & RNG Patterns`) but with the bound derived from data instead of constant:

```python
# scoring/residual_calibration.py — new helper (Plan 03)
def stat_clamp_adjustment(value: float, clamp_std: float) -> float:
    """Clamp a per-stat residual to ±2 * clamp_std (per-bucket std from training).

    clamp_std comes from artifact["stat_corrections"][stat]["clamp_std"][bucket_key].
    Caller falls back to max_abs_adjustment_by_position[stat-position] if clamp_std is
    None / missing (graceful degradation when artifact has no data for the bucket).
    """
    limit = max(2.0 * float(clamp_std), 0.0)
    return min(max(float(value), -limit), limit)
```

Bucket key continues the existing `(position, usage_tier, source_confidence_bucket)` triple from `bucket_key_for_projection()` (`residual_calibration.py:97-106`); KS-09 stores `clamp_std` per-stat per-bucket inside `stat_corrections.{stat}.clamps[bucket_key]` so a single artifact carries both the existing fpts correction AND the per-stat corrections without re-keying.

### Pattern 5: Bayesian Shrinkage Formula (existing project-wide; KS-14 reuses)

The project-wide convention `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)` (CONVENTIONS.md `## Numerical & RNG Patterns`) is used by KS-14:

```python
# data/preprocessor.py::compute_play_outcomes — new shrinkage branch (Plan 04)
# When n in [5, 9] (between MIN_BUCKET_PLAYS=5 and "robust" threshold of 10)
if 5 <= len(yards_list) < 10 and team_default_yards is not None:
    n = len(yards_list)
    prior_strength = 5 * len(team_default_yards)
    observed = float(np.mean(yards_list))
    prior = float(np.mean(team_default_yards))
    shrunk_mean = (n * observed + prior_strength * prior) / (n + prior_strength)
    # Synthesize a length-n distribution with the shrunk mean (preserves the
    # observed shape but pulls the location toward the team default proportional
    # to data thinness)
    yards_arr = np.array(yards_list) - observed + shrunk_mean
else:
    yards_arr = np.array(yards_list)
```

The shape preservation matters because the play_resolver downstream samples from these arrays via `rng.choice(arr)` (CONCERNS.md `## Empirical distributions`); replacing observed yards entirely with a constant would erase the variance the simulator needs.

### Pattern 6: Probe-Then-Decide (NEW pattern for KS-13)

Plan 07 ships both Path A and Path B in the same plan body, and chooses at execution time based on a one-shot probe of the loader output. The probe is a tiny script that loads one (season, week) of ff_opportunity data and asserts the lo/hi columns are present (or absent). The probe outcome is recorded in the plan summary; the plan body has both code branches pre-coded so it doesn't stall.

### Pattern 7: Two-Script Pipeline for Artifact Re-Fits (continues Phase 1 D-08 pattern)

KS-08 + KS-09 both bump the bundled `decision_s200/*.json` artifacts. The training scripts (`scripts/fit_dynamic_blend_weights.py`, `scripts/fit_residual_calibration.py`) run AFTER the runtime code change lands so the re-fit incorporates the new constraint (KS-08) or new schema (KS-09). Both scripts already exist and use the same `--test-seasons --min-source-season --sims --training-years --scoring --output-dir` CLI; Phase 2 plans only add `--simulator-weight-floor <value>` to fit_dynamic_blend_weights.py (KS-08) and pass through `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true` to fit_residual_calibration.py (KS-09) so the training run produces the per-stat block.

### Pattern 8: Roster Share Composition with availability (NEW for KS-12)

Plan 08 introduces a coordination point with the existing availability engine. The pattern:

```python
# data/player_builder.py — new helper (Plan 08)
def _expected_active_share_factor(roster: TeamRoster, typical_roster_size: int = 22) -> float:
    """Compute the share-normalization target accounting for inactive players.

    Returns active_players / typical_roster_size. Default 22 = NFL standard active +
    backup mix at skill positions (QB+RB+WR+TE+kicker+defense). When all players are
    active, this returns ≈1.0 and behavior matches the legacy normalization.
    """
    active = sum(1 for p in roster.players if p.usage.is_active)  # availability engine
    if typical_roster_size <= 0 or active == 0:
        return 1.0
    return min(active / typical_roster_size, 1.0)
```

The composition with availability is order-sensitive: KS-12 reads `p.usage.is_active` AFTER the availability engine has set it (the post-sim adjustment pipeline order in `AGENTS.md` confirms availability runs before usage normalization in `GameContextBuilder.build_game()`). Tests must cover the order: (a) availability OFF → all `is_active = True` → factor = 1.0 → legacy behavior; (b) availability ON, full roster → factor = 1.0 → legacy behavior; (c) availability ON, multi-inactive → factor < 1.0 → residual non-zero.

## Pitfalls & Gotchas

### Pitfall 1: Two-Stage Layered fpts is NOT pure-additive

Per D-01, `final fpts = raw_sim_fpts + existing_fpts_correction`. The per-stat corrections write `corrected_pass_yards`, `corrected_receiving_yards`, etc. as NEW columns; they do NOT mutate the in-place `pass_yards` field that the simulator computed nor do they propagate into the fpts via the scoring formula. This means downstream consumers reading projection rows will see TWO sets of stat columns (raw + corrected) and ONE set of fpts (the existing fpts-level correction applied on top of raw_sim_fpts). Plan 03 must document this in the artifact + projection-row schema and add explicit tests that `corrected_pass_yards != pass_yards` for non-fallback rows.

### Pitfall 2: Sim-Weight Floor Renormalization Ordering

KS-08's floor + renormalize pattern (D-06) MUST happen AFTER `normalize_weights(...)` because:

1. `normalize_weights()` already enforces non-negative + sum-to-1.0;
2. Floor + renormalize swaps the simulator weight upward and pulls down the others proportionally;
3. If we floor BEFORE normalize, the artifact-level zeros for simulator stay zero (artifact dict has `weights["simulator"] = 0.0` and `max(0.0, 0.20) = 0.20` but the renormalize then divides by `sum = 0.20 + ff + market` which DOES give 0.20 / sum, but this is mathematically identical only when ff + market sum to 0.80 in the artifact — which is true after `normalize_weights()` but NOT before).

So the implementation order is:

```python
# scoring/dynamic_blend.py::_artifact_weights (Plan 02)
normalized = normalize_weights(raw_weights, context.sources)
if normalized is None:
    return None
floor = float(self.config.simulator_weight_floor or 0.0)
if floor > 0 and SIMULATOR_SOURCE in normalized:
    sim = normalized[SIMULATOR_SOURCE]
    if sim < floor:
        # Lift sim to floor; pull down others proportionally to preserve sum=1.0
        slack = floor - sim
        other_total = sum(w for s, w in normalized.items() if s != SIMULATOR_SOURCE)
        if other_total > 0:
            scale = max(0.0, (other_total - slack) / other_total)
            for source in normalized:
                if source != SIMULATOR_SOURCE:
                    normalized[source] *= scale
            normalized[SIMULATOR_SOURCE] = floor
return normalized
```

This is post-`normalize_weights()` (sum stays 1.0). Plan 02 Task 1 RED tests cover both the unchanged case (sim ≥ floor) and the lift case (sim < floor).

### Pitfall 3: Re-Fitting `decision_s200` Artifacts Requires Holdout Discipline

The `fit_dynamic_blend_weights.py` training script asserts `season >= _HOLDOUT_SEASON` is reserved (line 194-198). Phase 2 KS-08 re-fits `weights_2024.json` and `weights_2023.json`; the training data is `seasons in [2022..2023]` for `weights_2024` and `[2022]` for `weights_2023` per the existing min_source_season logic. We MUST NOT include 2024 in the training set when re-fitting `weights_2024.json`. Same applies to KS-09 re-fitting `calibration_2024.json` / `calibration_2023.json` via `fit_residual_calibration.py`.

### Pitfall 4: TE Elite Tier Interacts with `_merge_thin_tiers`

KS-10 D-07 lowers TE `min_bucket_rows` to 100 from 200 (so TE buckets need fewer rows to be retained). The existing `_merge_thin_tiers` logic in `tier_engine.py:441-477` is a SEPARATE concern (it merges thin TIERS within a position, not thin BUCKETS within `residual_calibration`). Plan 05 verifies via test that the artifact written by `fit_residual_calibration.py` after the KS-10 retune contains a non-empty `TE|elite|*` bucket — proving the elite tier is being populated and not collapsed. The KS-10 test plan does NOT touch `_merge_thin_tiers`; that is mixture-of-CDFs territory deferred per D-08.

### Pitfall 5: KS-12 `expected_active_shares` Floor

KS-12's `expected_active_shares` factor `active / typical_roster_size` could theoretically drop to 0 (every player inactive) or above 1 (more active players than typical). The implementation MUST clamp:

- Lower bound: `max(active / typical_roster_size, _MIN_ACTIVE_FRACTION)` where `_MIN_ACTIVE_FRACTION = 0.5` so a multi-inactive week never collapses the carry/target totals to 0.
- Upper bound: `min(active / typical_roster_size, 1.0)` so an unusually deep roster doesn't OVER-allocate beyond the share-sums-to-1.0 invariant.

Without these bounds, `_scale_shares()` (line 683-693) could produce negative or > 1.0 effective shares, breaking `select_rusher` / `select_receiver` downstream.

### Pitfall 6: KS-13 Path A vs Path B Decision is Lazy

The KS-13 probe (Plan 07) checks the FF Opportunity loader's raw schema for `total_fantasy_points_exp_lo` and `total_fantasy_points_exp_hi`. Both columns must be present AND non-null for at least 80% of training rows to qualify for Path A. If either is missing or sparse, the plan branches to Path B (fitted residual std from training data). The probe outcome is documented in Plan 07's summary; the plan body has both branches pre-coded.

### Pitfall 7: KS-14 Cache Invalidation

`MIN_BUCKET_PLAYS = 10 → 5` is a `data/preprocessor.py` change that DOES invalidate the PBP-stats cache (one of the three cache layers per `AGENTS.md` `## Three-Layer Cache`). Plan 04 must trigger cache regeneration; the test path is verifying that `compute_play_outcomes(...)` produces strictly more buckets when run with the lower threshold (the `len(distributions)` count goes up). KS-09 / KS-08 / KS-10 / KS-11 / KS-12 / KS-13 do NOT invalidate the PBP-stats cache (they touch post-sim layers or per-game runtime config).

### Pitfall 8: `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor` Promotion Value

The KS-08 sweep produces three floor candidates {0.20, 0.30, 0.40}; the smallest passing is the promotion value. The promotion commit MUST update both `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled = true` AND `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor = <chosen>`. The runtime code reads `floor` directly from the flag block (NOT from a separate `ensemble.dynamic_blend.simulator_weight_floor` field) so the two-line change keeps the flag block self-contained per the Phase 1 D-45 pattern.

## Validation Architecture

Phase 2's validation strategy is **identical to Phase 1 post-Plan-00**: extend `bare_config_dict()` with the new Phase-2 flags, run `validate.py --baseline bare --arm-b-base bare --set <KS-X overrides>` for true isolation A/B and `validate.py --baseline defaults --set <KS-X overrides>` for full-stack overlay per change. Hard floor `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05` per C-01.

### Validation Touchpoints

- **Plan 01 (scaffolding):** ships the `phase2_ks_flags:` block + `get_phase2_ks_flags()` shim + `bare_config_dict()` extension + integration test extension (`test_bare_config_dict_produces_all_None_engines` continues to be a HARD GATE; the Phase 1 Cycle-2 escape hatch stayed REMOVED). Pins `p2.entry.full` ledger entry via `validate.py --baseline bare --label p2.entry.full` (no `--set`) — equals `p1.aggregate.full` Arm B but recorded under Phase-2 namespace for delta clarity. Bumps `residual_calibration` artifact `schema_version: 1 → 2` (the per-stat block lives under the new schema; loader gracefully handles v1 artifacts as fpts-only).
- **Plan 02 (KS-08):** runs `validate.py --baseline bare --arm-b-base bare --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=<v> --label p2.ks08.s<v>.bare` for `v in {0.20, 0.30, 0.40}`; same for full-stack. Pick smallest-passing and re-fit `decision_s200/weights_*.json` with the chosen floor; promotion commit flips flag default + sets `floor` value.
- **Plan 03 (KS-09):** runs `validate.py --baseline bare --arm-b-base bare --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true --label p2.ks09.bare` and full-stack. Promotion bar `D-14` evaluated from ledger: `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"] - stat_mean_bias["QB"]["pass_yards"]["arm_a_bias"]` AND `stat_ks["QB"]["pass_yards"]["arm_b"] - stat_ks["QB"]["pass_yards"]["arm_a"]`. Re-fit `decision_s200/calibration_*.json` with the new `stat_corrections` block.
- **Plan 04 (KS-14):** standard A/B; primary target = `validation/coverage.py::buckets_below_min_plays_pct` audit metric drops; KS Δ on RB/WR rush_yards and receiving_yards as a secondary gate.
- **Plan 05 (KS-10):** standard A/B; primary target = TE receptions KS Δ ≤ -0.02 (per HYPOTHESES KS-10 expectation); secondary = artifact `TE|elite|*` bucket non-empty after re-fit.
- **Plan 06 (KS-11):** standard A/B; primary target = WR/TE receiving_yards KS Δ ≤ -0.01; QB pass_yards must NOT regress (C-10 invariant — verified via existing `tests/test_data/test_pff/test_tier_engine.py:848` QB-untouched test reused as preflight).
- **Plan 07 (KS-13):** standard A/B; primary target depends on probe outcome (Path A → fpts KS Δ ≤ -0.01; Path B → fpts KS Δ ≤ -0.005 because residual-fit path is weaker than schema-derived width per HYPOTHESES.md).
- **Plan 08 (KS-12):** standard A/B; primary target = WR target_share variance retention (measured in coverage metrics); secondary = no MAE regression on the multi-inactive test fixture.
- **Plan 09 (aggregate):** `validate.py --baseline bare --label p2.aggregate.full`; computes Phase-2-vs-Phase-1 delta from `p1.aggregate.full` Arm B (`#105`) and `p2.aggregate.full` Arm B; walk-back trigger if hard floor regresses on the differenced delta per D-15.

### Per-KS Test Distribution

| Plan | TDD Required (C-08) | Estimated New Tests | Existing Tests Touched |
|------|---------------------|---------------------|------------------------|
| 01 (scaffolding) | No (config-only) | 4 (loader shim, bare_config_dict extension, schema-v2 artifact loader, p2.entry.full ledger pin) | `test_validation/test_config.py` (extends Phase 1 hard-gate test) |
| 02 (KS-08) | Yes | 6 (floor+renormalize math, no-floor path unchanged, sim<floor lift, training-script floor flag, artifact has floor in schema, A/B isolation passes hard floor) | `test_scoring/test_dynamic_blend.py` |
| 03 (KS-09) | Yes | 8 (per-stat correction writes new columns, fpts unchanged when stat_level disabled, std-scaled clamp applies, missing-bucket fallback, schema-v2 artifact has stat_corrections, training-script writes per-stat block, integration order with dynamic_blend, integration test that corrected ≠ raw) | `test_scoring/test_residual_calibration.py` |
| 04 (KS-14) | No (test-after acceptable) | 4 (MIN_BUCKET_PLAYS lowered, n in [5,9] applies shrinkage, n ≥ 10 unchanged, audit metric `buckets_below_min_plays_pct` decreases) | `test_data/test_preprocessor.py` |
| 05 (KS-10) | No | 5 (per-position cap lookup, TE elite tier exists, lower min_bucket_rows for TE, artifact post-refit has TE\|elite\|* bucket, behavior matches HYPOTHESES verbatim values) | `test_scoring/test_residual_calibration.py` |
| 06 (KS-11) | No | 5 (WR/TE/RB position_reliability defaults, QB unchanged at 0.20/0.80, min_targets/min_carries gate, reliability range expands per position, behavior preflight: existing QB-untouched test passes) | `test_data/test_pff/test_tier_engine.py` |
| 07 (KS-13) | No | 6 (probe script existence, probe outcome correctly identifies Path A vs B, Path A Gaussian sampling, Path B fitted std, prior-width disabled = legacy point estimate, A/B isolation) | `test_scoring/test_ensemble.py` |
| 08 (KS-12) | Yes (per C-08) | 7 (full-roster week unchanged, multi-inactive week residual non-zero, availability OFF graceful degradation, _MIN_ACTIVE_FRACTION lower bound, upper bound = 1.0, backup-TE/WR exclusion threshold, integration with `select_receiver`) | `test_data/test_player_builder.py`, `test_data/test_game_context.py` |
| 09 (aggregate) | No | 1 (delta computation script reads stat_mean_bias from `p1.aggregate.full` and `p2.aggregate.full` — mirrors Phase 1 Plan 11 Task 2) | `test_validation/test_aggregate.py` (new test file) |

**Total new tests:** ~46 across 9 plans. Existing 2,131-test suite stays green per C-09.

## Sequencing & Dependency Graph

Per D-12, within-phase order is **KS-08 → KS-09 → KS-14 → KS-10 → KS-11 → KS-13 → KS-12**, with Plan 01 (scaffolding) at Wave 0 and Plan 09 (aggregate) at Wave 7.

| Plan | Wave | Depends On | Runtime Code | Training Script | Re-Fit Artifact |
|------|------|------------|--------------|-----------------|-----------------|
| 01 — Entry baseline + flag scaffolding | 0 | — | `config/loader.py` (shim), `validation/config.py` (bare_config_dict ext), `scoring/residual_calibration.py` (schema-v2 artifact loader) | None | Schema bump only (no re-fit yet) |
| 02 — KS-08 sim-weight floor | 1 | 01 | `scoring/dynamic_blend.py::_artifact_weights` | `scripts/fit_dynamic_blend_weights.py` (--simulator-weight-floor flag) | `decision_s200/weights_2023.json`, `weights_2024.json` |
| 03 — KS-09 per-stat residual_calibration | 2 | 01, 02 (KS-08 floor active during KS-09 fit so the corrections account for the new sim weights) | `scoring/residual_calibration.py::adjust_week`, `clamp_adjustment` | `scripts/fit_residual_calibration.py` (writes stat_corrections block) | `decision_s200/calibration_2023.json`, `calibration_2024.json` |
| 04 — KS-14 thin-bucket shrinkage | 3 | 01 | `data/preprocessor.py::compute_play_outcomes`, `validation/coverage.py` | None | None (PBP-stats cache regenerates on next run) |
| 05 — KS-10 per-position caps + TE elite tier | 4 | 01, 03 (KS-10 needs the schema-v2 artifact's stat_corrections to coexist with new per-position cap lookup) | `scoring/residual_calibration.py::USAGE_TIER_THRESHOLDS, clamp_adjustment` | `scripts/fit_residual_calibration.py` (TE min_bucket_rows=100, elite tier in fit) | `decision_s200/calibration_2023.json`, `calibration_2024.json` (re-fit on top of Plan 03) |
| 06 — KS-11 tier_engine reliability cap | 4 (parallel with 05) | 01 | `data/pff/tier_engine.py::compute_reliability` already plumbed; only `config/defaults.yaml` adds `position_reliability` block | None | None |
| 07 — KS-13 ff_opportunity prior width | 5 | 01, 02 (KS-13 prior width matters most when sim weight is low, which the KS-08 floor counteracts; Plan 07 measures the residual KS gap after KS-08 lands) | `scoring/ensemble.py::FfOpportunityProjectionEnsembler.adjust_week`, optional probe script `scripts/probe_ff_opportunity_quantiles.py` | None (Path A) or new `scripts/fit_ff_opportunity_residual_std.py` (Path B) | None (Path A) or new artifact `data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/std_*.json` (Path B) |
| 08 — KS-12 share-normalization residual | 6 | 01 | `data/player_builder.py::_normalize_roster_shares`, `_scale_shares` | None | None |
| 09 — Phase 2 aggregate validation | 7 | 02, 03, 04, 05, 06, 07, 08 (every per-KS plan must have shipped to defaults — promoted or rolled back) | None (read-only; computes ledger delta) | None | None |

The Plan 05 / Plan 06 parallel waveable group (Wave 4) reflects: KS-10 modifies `residual_calibration.py` and re-fits the calibration artifact; KS-11 modifies only `config/defaults.yaml` and `tier_engine.py` (no artifact re-fit needed because the existing `position_reliability` config block is already plumbed). The two changes touch disjoint files and are independently A/B-testable.

## Approval

- Research scope: **Phase 2** structural calibration items KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14 (7 of 23 v1 hypotheses)
- Phase boundary: respects ROADMAP.md "out of scope for Phase 2" carve-outs (KS-02 / KS-16-18 = Phase 3, KS-19-21 = Phase 4 with KS-21 scrape complete in Phase 1, v2 long-tail KS-22..KS-33 = follow-up initiative)
- Hard floor + KS-09 promotion bar: enforced via Plan 09 aggregate per D-15 walk-back trigger
- Validation infrastructure: reuses Phase 1 Plan 00 deliverables (`--arm-b-base bare`, `bare_config_dict()` exhaustive enumeration, `SeasonMetrics.stat_mean_bias` schema v5)
- Ledger labels: namespace-clean (`p2.*`); Phase-2-vs-Phase-1 delta computed via difference of `p2.aggregate.full` and `p1.aggregate.full` (#105) Arm B entries
- All 7 Phase 2 KS-XX requirements traceable: each gets one plan with the corresponding `phase2_ks_flags.ksXX_<name>.enabled` flag and one ledger pair `p2.ksXX.{bare,full}`
- D-12 within-phase order respected; D-13 plan-count = 9 plans; D-14 KS-09 promotion bar elevated; D-15 walk-back trigger = hard-floor regression on Phase-2-vs-Phase-1 delta

**Approved 2026-04-26.**
