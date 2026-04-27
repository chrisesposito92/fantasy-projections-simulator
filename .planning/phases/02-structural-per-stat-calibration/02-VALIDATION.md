---
phase: 2
slug: structural-per-stat-calibration
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Hard floor: any change must NOT regress rank_corr by > 0.005 OR MAE by > 0.05 vs `p1.aggregate.full` Arm B (the post-Phase-1 promoted defaults). KS-09 promotion bar elevated per D-14.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-xdist + hypothesis |
| **Config file** | `pyproject.toml` (project-managed via uv) |
| **Quick run command** | `uv run pytest tests/test_scoring/test_dynamic_blend.py tests/test_scoring/test_residual_calibration.py tests/test_scoring/test_ensemble.py tests/test_data/test_player_builder.py tests/test_data/test_preprocessor.py tests/test_data/test_pff/test_tier_engine.py -v` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Statistical-only command** | `uv run pytest tests/ -v -m statistical` |
| **Estimated runtime** | ~30s (quick), ~6 min (full), ~12 min (statistical) |
| **A/B harness — true isolation (per-KS bare)** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare [--set k=v ...] --label "p2.ksXX.bare"` |
| **A/B harness — full-stack overlay (per-KS full)** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults [--set k=v ...] --label "p2.ksXX.full"` |
| **A/B harness — Wave 0 entry baseline pin** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label "p2.entry.full"` (no `--set`) |
| **A/B harness — end-of-phase aggregate** | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label "p2.aggregate.full"` (no `--set`; Phase-2-vs-Phase-1 delta = `p2.aggregate.full` Arm B − `p1.aggregate.full` Arm B) |
| **A/B inspection** | `uv run python scripts/validate.py --show-ledger \| grep -E "^p2\."` |
| **Training script — KS-08 re-fit** | `uv run python scripts/fit_dynamic_blend_weights.py --test-seasons 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200 --simulator-weight-floor <chosen>` |
| **Training script — KS-09 re-fit** | `uv run python scripts/fit_residual_calibration.py --test-seasons 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200 --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true` |
| **Coverage audit (KS-14)** | `uv run python scripts/validate.py --sims 50 --seasons 2024 --baseline defaults --label p2.ks14.coverage_audit --show-coverage` (surfaces `buckets_below_min_plays_pct`) |

---

## Sampling Rate

- **After every task commit:** Run quick command — must be green.
- **After every plan completes (each KS-XX):** Run full suite — must be green.
- **After every plan completes (each KS-XX):** Run BOTH `validate.py --baseline bare --arm-b-base bare --set <KS-X overrides> --label p2.ksXX.bare` (true isolation) AND `validate.py --baseline defaults --set <KS-X overrides> --label p2.ksXX.full` (full-stack overlay). Both must pass hard floor.
- **End of phase (after all 7 KS plans + Plan 01 ship):** Run `validate.py --baseline bare --label p2.aggregate.full` (no `--set`) — captures post-Phase-2 promoted defaults' metrics in Arm B; Plan 09 differences this against `p1.aggregate.full` Arm B per D-15.
- **Max feedback latency per task:** ~30s (quick suite); ~30 min (per A/B run at 200 sims/season × 3 seasons).

---

## Per-Plan Verification Map

| Plan ID | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-phase2-scaffolding-and-entry-baseline | 0 | (prerequisite for all KS plans) | — | `phase2_ks_flags:` block in defaults.yaml; `get_phase2_ks_flags()` shim in loader.py; `bare_config_dict()` extended with 7 new flags + 5 new top-level keys; `test_bare_config_dict_produces_all_None_engines` HARD GATE extended for Phase 2; `residual_calibration` artifact `schema_version: 2` accepted; `p2.entry.full` ledger entry pinned (no `--set`; equals `p1.aggregate.full` Arm B numerically but Phase-2 namespace) | unit + integration + ledger | `uv run pytest tests/test_validation/test_config.py -v -k "bare_config_dict or all_None or phase2_ks" && uv run pytest tests/test_scoring/test_residual_calibration.py -v -k "schema_v2 or schema_version" && uv run python -c "from fantasy_sim.config.loader import get_phase2_ks_flags; assert len(get_phase2_ks_flags())>=7" && uv run python scripts/validate.py --help \| grep arm-b-base && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p2.entry.full` | ✅ scripts/validate.py exists | ⬜ pending |
| 02-ks08-dynamic-blend-simulator-floor | 1 | KS-08 | — | Floor + renormalize after `normalize_weights(...)` in `_artifact_weights`; smallest-passing floor selected from sweep {0.20, 0.30, 0.40}; `decision_s200/weights_*.json` re-fit with `--simulator-weight-floor <chosen>`; D-45/D-02 Cycle 3 pattern: gated behind `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` | unit + statistical + sweep | `uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k "floor or ks08 or simulator_weight" && for v in 0.20 0.30 0.40; do uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=$v --label p2.ks08.s$(echo $v \| sed 's/\.//').bare; uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=$v --label p2.ks08.s$(echo $v \| sed 's/\.//').full; done && uv run python scripts/fit_dynamic_blend_weights.py --test-seasons 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200 --simulator-weight-floor <chosen>` | ✅ test_dynamic_blend.py exists | ⬜ pending |
| 03-ks09-per-stat-residual-calibration | 2 | KS-09 | — | Per-stat correction writes corrected_<stat> columns BEFORE existing fpts write at `residual_calibration.py:422`; std-scaled clamp ±2σ from artifact `stat_corrections.{stat}.clamp_std`; calibration artifact `schema_version: 2` with `stat_corrections` block; gated behind `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled`; KS-09 promotion bar D-14 elevated (KS Δ ≤ -0.03 on QB pass_yards AND `\|bias Δ\| ≤ 5 yd/g`) | unit + statistical + integration | `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k "stat_level or per_stat or clamp_std or ks09 or schema_v2" && uv run python scripts/fit_residual_calibration.py --test-seasons 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200 --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true --label p2.ks09.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true --label p2.ks09.full` | ✅ test_residual_calibration.py exists | ⬜ pending |
| 04-ks14-thin-bucket-shrinkage | 3 | KS-14 | — | `MIN_BUCKET_PLAYS = 10 → 5` in preprocessor.py:10; Bayesian shrinkage formula at n ∈ [5, 9] blends with team default at strength `5 * len(team_default_yards)`; new `buckets_below_min_plays_pct` audit metric in coverage.py; gated behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` | unit + statistical | `uv run pytest tests/test_data/test_preprocessor.py tests/test_validation/test_coverage.py -v -k "min_bucket or shrinkage or ks14 or buckets_below" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true --label p2.ks14.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true --label p2.ks14.full` | ✅ test_preprocessor.py exists | ⬜ pending |
| 05-ks10-per-position-caps-te-elite-tier | 4 | KS-10 | — | Per-position caps in defaults.yaml `ensemble.residual_calibration.max_abs_adjustment_by_position` = `{QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8}`; 4th `elite` tier in `USAGE_TIER_THRESHOLDS` for TE > 14.0 fpts; TE `min_bucket_rows: 100` (down from 200); `clamp_adjustment` lookup reads per-position cap; gated behind `phase2_ks_flags.ks10_per_position_caps.enabled`; calibration artifact re-fit on top of Plan 03 v2 schema | unit + statistical | `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k "per_position_caps or elite_tier or ks10 or USAGE_TIER" && uv run python scripts/fit_residual_calibration.py --test-seasons 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200 --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true --set phase2_ks_flags.ks10_per_position_caps.enabled=true && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase2_ks_flags.ks10_per_position_caps.enabled=true --label p2.ks10.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks10_per_position_caps.enabled=true --label p2.ks10.full` | ✅ test_residual_calibration.py exists | ⬜ pending |
| 06-ks11-tier-engine-position-reliability | 4 | KS-11 | — | `pff.tier_engine.position_reliability` block added to defaults.yaml: WR/TE `{floor: 0.30, cap: 0.95, min_targets: 30}`, RB `{floor: 0.25, cap: 0.92, min_carries: 50}`; QB stays at global `{floor: 0.20, cap: 0.80}` per C-10; `compute_reliability(...)` already plumbed (`tier_engine.py:957-965`); gated behind `phase2_ks_flags.ks11_position_reliability.enabled` | unit + statistical + behavior preflight | `uv run pytest tests/test_data/test_pff/test_tier_engine.py -v -k "position_reliability or qb_unchanged or ks11 or min_targets or min_carries" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set pff.enabled=true --set pff.tier_engine.enabled=true --set phase2_ks_flags.ks11_position_reliability.enabled=true --label p2.ks11.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks11_position_reliability.enabled=true --label p2.ks11.full` | ✅ test_tier_engine.py exists (incl. existing QB-untouched test at line 848) | ⬜ pending |
| 07-ks13-ff-opportunity-prior-width | 5 | KS-13 | — | Probe verifies `total_fantasy_points_exp_lo`/`_hi` columns; Path A: Gaussian prior `std = (hi - lo) / (2 * 1.28)`; Path B: fitted residual std from training data; gated behind `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled`; probe outcome documented in plan summary | unit + statistical + probe | `uv run python scripts/probe_ff_opportunity_quantiles.py --season 2024 --week 1 \| tee logs/p2_ks13_probe.json && uv run pytest tests/test_scoring/test_ensemble.py tests/test_data/test_ensemble/test_loader.py -v -k "prior_width or quantile or ks13 or path_a or path_b" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true --label p2.ks13.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true --label p2.ks13.full` | ✅ test_ensemble.py exists | ⬜ pending |
| 08-ks12-share-normalization-residual | 6 | KS-12 | — | `_normalize_roster_shares` normalizes to `expected_active_shares = sum_of_shares * factor` where `factor = clip(active / typical_roster_size, _MIN_ACTIVE_FRACTION=0.5, 1.0)`; backup-TE/WR exclusion threshold (planner picks; TDD-first per C-08); composes with availability engine without double-counting; gated behind `phase2_ks_flags.ks12_share_normalization_residual.enabled` | unit + statistical + integration | `uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k "normalize_roster_shares or expected_active_shares or availability or ks12 or _MIN_ACTIVE_FRACTION" && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --arm-b-base bare --set availability.enabled=true --set phase2_ks_flags.ks12_share_normalization_residual.enabled=true --label p2.ks12.bare && uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --set phase2_ks_flags.ks12_share_normalization_residual.enabled=true --label p2.ks12.full` | ✅ test_player_builder.py exists | ⬜ pending |
| 09-phase2-aggregate-validation | 7 | (covers all KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14) | — | `p2.aggregate.full` ledger entry uses `--baseline bare` (NOT `--baseline defaults`); Phase-2-vs-Phase-1 delta computed from `p1.aggregate.full` Arm B (#105) and `p2.aggregate.full` Arm B; D-14 promotion bar evaluated per-stat from `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` and `stat_ks["QB"]["pass_yards"]["arm_b"]`; D-15 walk-back trigger if hard floor regresses on Phase-2-vs-Phase-1 delta | aggregate validation | `uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p2.aggregate.full && uv run python scripts/validate.py --show-ledger \| grep -E "p1.aggregate.full\|p2.aggregate.full"` (then Task 2 delta-computation script reads stat_mean_bias and stat_ks from both entries) | ✅ harness exists (post-Plan-00 of Phase 1) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Hard floor enforcement: each `--label p2.ksXX.{bare,full}` ledger entry must show `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05`. Promotion bar layered on top: KS-09 elevated (D-14: KS Δ ≤ -0.03 on QB pass_yards AND `|bias Δ| ≤ 5 yd/g`); KS-08 sweep picks smallest-passing; KS-10/11/13/14 use Phase 1 D-30 small-gain bar (any non-regression KS Δ on primary target); KS-12 D-30 small-gain bar with WR target_share variance retention as primary target.

---

## Wave 0 Requirements

- [x] `tests/test_scoring/test_dynamic_blend.py` — exists, receives new tests for KS-08 floor + renormalize math (Plan 02 RED→GREEN)
- [x] `tests/test_scoring/test_residual_calibration.py` — exists, receives new tests for KS-09 per-stat correction + KS-10 per-position caps + TE elite tier (Plan 03 + Plan 05 RED→GREEN)
- [x] `tests/test_scoring/test_ensemble.py` — exists, receives new tests for KS-13 prior width Path A and Path B (Plan 07)
- [x] `tests/test_data/test_preprocessor.py` — exists, receives new tests for KS-14 MIN_BUCKET_PLAYS lowering + shrinkage formula (Plan 04)
- [x] `tests/test_data/test_player_builder.py` — exists, receives new tests for KS-12 share-normalization residual + availability composition (Plan 08 RED→GREEN)
- [x] `tests/test_data/test_game_context.py` — exists, receives new tests for KS-12 integration with `select_receiver` (Plan 08 integration tests)
- [x] `tests/test_data/test_pff/test_tier_engine.py` — exists, receives new tests for KS-11 position_reliability defaults + QB-untouched preflight reuses existing line 848 test (Plan 06)
- [x] `tests/test_data/test_ensemble/` — directory exists, receives new tests for KS-13 loader probe (Plan 07)
- [x] `tests/test_validation/test_config.py` — exists from Phase 1, EXTENDED in Plan 01 to enumerate the 7 new Phase-2 flags + 5 new top-level keys in `bare_config_dict()`
- [x] `tests/test_validation/test_aggregate.py` — NEW file in Plan 09 (delta-computation script tests)
- [x] `tests/test_validation/test_coverage.py` — NEW file in Plan 04 (`buckets_below_min_plays_pct` audit metric tests)
- [x] `tests/conftest.py` — exists with `sample_pbp` (20 plays, KC/BUF), `sample_rosters`, `expanded_pbp` (60 plays/team) fixtures — sufficient for new tests; Plan 08 adds `multi_inactive_roster` fixture if needed
- [x] pytest framework — installed via `uv` (project uses `uv run pytest`)
- [x] hypothesis property-based testing — installed via `uv` (used in `tests/test_engine/test_statistical_validation.py`)
- [x] `scripts/validate.py` — A/B harness present with `--baseline {bare,defaults}`, `--arm-b-base {defaults,bare}`, `--set`, `--label`, `--show-ledger` (post-Phase-1 Plan 00)
- [x] `scripts/fit_residual_calibration.py` — present (267 LOC); Plan 03 extends with stat_corrections fitting block
- [x] `scripts/fit_dynamic_blend_weights.py` — present (268 LOC); Plan 02 extends with `--simulator-weight-floor` flag
- [ ] `scripts/probe_ff_opportunity_quantiles.py` — NEW one-off probe script in Plan 07 Wave 5 (created during plan execution; planner discretion per CONTEXT.md "Claude's Discretion")
- [x] `src/fantasy_sim/validation/ledger.py` — Persistent A/B ledger with schema versioning + `format_ledger_table` (verified post-Phase-1; `SeasonMetrics.stat_mean_bias` field at schema v5)
- [x] `src/fantasy_sim/validation/coverage.py` — KS distribution metrics; Plan 04 extends with `buckets_below_min_plays_pct`
- [x] `src/fantasy_sim/data/pff/tier_engine.py` — `compute_reliability(position=...)` already plumbed (line 957-965); KS-11 only adds config-side defaults
- [x] `src/fantasy_sim/data/pff/models.py` — `TierConfig.position_reliability: dict[str, dict[str, float]]` field already exists at line 162
- [x] `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_*.json` — bundled artifacts at schema_version: 1; Plan 01 bumps to schema_version: 2 in loader (graceful degradation: v1 = fpts-only, v2 = fpts + stat_corrections); Plan 03 + Plan 05 re-fit
- [x] `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_*.json` — bundled artifacts at schema_version: 1; Plan 02 re-fits with floor baked in
- [x] `.planning/phases/02-structural-per-stat-calibration/logs/` — created in Plan 01 with .gitkeep (mirrors Phase 1 D-43 pattern)

> All testing infrastructure is in place from Phase 1. Wave 0 stubbing IS required for Plan 01 only (loader shim, bare_config_dict extension, schema-v2 artifact loader, p2.entry.full ledger pin). New tests added inline within each KS plan as the first task (TDD-first per C-08 for KS-08, KS-09, KS-12; test-after acceptable per C-08 for KS-10/11/13/14).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KS-08 sweep "smallest-passing" floor selection | KS-08 D-05 | The smallest-passing decision requires reading 6 ledger rows (3 floors × {bare, full}) holistically — "clears hard floor AND non-zero KS Δ" is operator-evaluated against the full row vector, not a single threshold | After Plan 02 Task 3 produces all 6 ledger entries, agent prints the comparative table and explicitly evaluates D-05 "(a) clears hard floor AND (b) non-zero KS Δ improvement on TE/WR fpts" per floor, then selects smallest-passing in plan summary |
| KS-09 promotion-bar judgment (D-14) | KS-09 D-14 | D-14 has THREE conditions stacked: hard floor + KS Δ ≤ -0.03 on QB pass_yards + bias `|Δ| ≤ 5 yd/g`. Outcome is one of {SHIPPED, SHIPPED-PARTIAL, BLOCKED}, not a binary pass/fail | After Plan 03 ledger A/B completes, agent reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` and `stat_ks["QB"]["pass_yards"]["arm_b"]` from both `p1.aggregate.full` and `p2.ks09.full`, computes the deltas, and explicitly evaluates each of the three D-14 conditions in the promotion-state commit message |
| KS-13 Path A vs Path B branch decision | KS-13 D-10 | The probe outcome (lo/hi columns present and non-null for ≥80% of training rows) is a one-shot data-dependent measurement, not a code-detected condition | Plan 07 Task 1 runs `scripts/probe_ff_opportunity_quantiles.py`; agent reads JSON output and selects Path A or Path B branch in the plan body, documents the outcome in the plan summary |
| KS-12 backup-TE/WR exclusion threshold | KS-12 (Claude's Discretion in CONTEXT.md) | Threshold value is left to planner discretion based on per-position empirical share floor; requires reading historical share distributions and choosing a value | Plan 08 Task 1 includes a one-shot script that prints the empirical 10th percentile target_share for backup TE/WR; agent picks a threshold (e.g., 0.05 or 0.08) based on the histogram and documents the choice in the plan summary |
| Phase 2 walk-back judgment | Plan 09 D-15 | If aggregate fails hard floor on Phase-2-vs-Phase-1 delta, "smallest-gain promotion candidate first" requires reading per-KS ledger entries holistically | Plan 09 Task 2 surfaces walk-back candidate; operator decides whether to revert per D-15 |

---

## Validation Sign-Off

- [x] All plans have `<automated>` verify blocks per the Per-Plan Verification Map above
- [x] Sampling continuity: every plan ends with quick test pass + true-isolation A/B + full-stack A/B + ledger inspection
- [x] Wave 0 covers all MISSING references: Plan 01 ships `phase2_ks_flags:` block + `get_phase2_ks_flags()` shim + `bare_config_dict()` extension + `p2.entry.full` ledger pin + `residual_calibration` schema-v2 artifact loader
- [x] No watch-mode flags (pytest runs to completion; A/B runs are bounded by `--sims 200`)
- [x] Feedback latency < 30s per quick test pass; < 30 min per per-KS A/B pair
- [x] `nyquist_compliant: true` set in frontmatter
- [x] HARD FLOOR enforced via `validate.py` ledger entries + Plan 09 Phase-2-vs-Phase-1 delta script (D-15 walk-back trigger)
- [x] KS-09 ELEVATED PROMOTION BAR (D-14) wired through `stat_mean_bias` + `stat_ks` reads from `SeasonMetrics` schema v5 (already in place from Phase 1 D-46)
- [x] PFF QB INVARIANTS (C-10) protected via existing `tests/test_data/test_pff/test_tier_engine.py:848` QB-untouched test reused as KS-11 preflight (mirrors Phase 1 D-22 / LOW-2 pattern)
- [x] PHASE 2 ENTRY BASELINE (C-02) explicit: `p2.entry.full` ledger entry pinned in Plan 01 Task 3; Plan 09 differences `p2.aggregate.full` against `p1.aggregate.full` (#105) NOT `p2.entry.full` per D-15 (the latter is a sanity-check pin only, the delta is computed against the canonical Phase 1 closing entry)

**Approval:** approved 2026-04-26 (initial)
