---
phase: 02-structural-per-stat-calibration
plan: 01
subsystem: config, validation, scoring
tags: [scaffolding, feature-flags, schema-bump, ledger-pin]
dependency_graph:
  requires: [phase-01-all-plans]
  provides: [phase2_ks_flags, get_phase2_ks_flags, bare_config_dict_phase2, schema_v2_loader, p2.entry.full]
  affects: [plans-02-through-08, plan-09-aggregate]
tech_stack:
  added: []
  patterns: [phase1-D45-feature-flag-pattern, phase1-D46-schema-bump-pattern, phase1-D44-hard-gate-test]
key_files:
  created:
    - .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  modified:
    - config/defaults.yaml
    - src/fantasy_sim/config/loader.py
    - src/fantasy_sim/validation/config.py
    - src/fantasy_sim/scoring/residual_calibration.py
    - tests/test_validation/test_config.py
    - tests/test_scoring/test_residual_calibration.py
decisions:
  - "phase2_ks_flags block added with 7 flags (KS-08..KS-14) all default false, continuing D-45 pattern"
  - "get_phase2_ks_flags() shim mirrors get_phase1_ks_flags() — graceful degradation on missing block"
  - "bare_config_dict() extended with 7 Phase 2 KS flags + 2 sub-engine boolean gates (stat_level.enabled, prior_width.enabled)"
  - "ARTIFACT_SCHEMA_VERSION bumped 1->2; ARTIFACT_SCHEMA_VERSIONS_SUPPORTED=(1,2) loader accepts both; v1 artifacts get empty stat_corrections:{} normalized in"
  - "p2.entry.full ledger #106 pinned; delta vs p1.aggregate.full (#105) within Monte Carlo stochastic variation at 200 sims"
metrics:
  duration: ~30m
  completed_date: "2026-04-27"
  tasks_completed: 4
  files_changed: 6
---

# Phase 2 Plan 01: Phase 2 Scaffolding and Entry Baseline Summary

Phase 2's foundational scaffolding. Ships the `phase2_ks_flags:` config block with 7 feature flags (all default false), the `get_phase2_ks_flags()` loader shim, extended `bare_config_dict()` hard-gate coverage, schema-v2-aware residual calibration artifact loader, and pins the `p2.entry.full` ledger entry. Zero runtime behavior change — all flags default false.

## What Was Built

### Task 1: `phase2_ks_flags:` block + new config keys

Added to `config/defaults.yaml`:
- `phase2_ks_flags:` block at file head (after `phase1_ks_flags:`) with 7 flags, all `enabled: false`:
  - `ks08_dynamic_blend_simulator_floor` (Plan 02)
  - `ks09_per_stat_residual_calibration` (Plan 03)
  - `ks10_per_position_caps` (Plan 05)
  - `ks11_position_reliability` (Plan 06)
  - `ks12_share_normalization_residual` (Plan 08)
  - `ks13_ff_opportunity_prior_width` (Plan 07)
  - `ks14_thin_bucket_shrinkage` (Plan 04)
- `ensemble.dynamic_blend.simulator_weight_floor: 0.0` (KS-08 placeholder)
- `ensemble.residual_calibration.max_abs_adjustment_by_position:` (KS-10 placeholder, all positions 1.5)
- `ensemble.residual_calibration.stat_level:` (KS-09, enabled: false, 9 covered stats)
- `ensemble.ff_opportunity.prior_width:` (KS-13, enabled: false)
- `pff.tier_engine.position_reliability: {}` (KS-11 placeholder, empty dict)

### Task 2: `get_phase2_ks_flags()` shim + `bare_config_dict()` extension + tests

- Added `get_phase2_ks_flags()` to `src/fantasy_sim/config/loader.py` mirroring `get_phase1_ks_flags()` exactly
- Extended `bare_config_dict()` disabled-set in `src/fantasy_sim/validation/config.py` with 9 new entries (7 KS flags + 2 sub-engine boolean gates)
- Added `test_phase2_ks_flags_present_and_default_false` (hard gate: all 7 flags exist with enabled=false)
- Added `test_phase2_bare_config_disables_all_new_flags` (hard gate: bare config disables all new flags)

### Task 3: Schema-v2-aware artifact loader

- `ARTIFACT_SCHEMA_VERSION: 1 → 2` (writer side uses 2 for new artifacts)
- `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED = (1, 2)` (reader accepts both)
- `_artifact()` loader updated: checks `schema not in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED`; normalizes v1 artifacts with empty `stat_corrections: {}` so KS-09 sees uniform shape
- Fixed `test_bundled_decision_artifacts_are_available` to use `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED` (bundled artifacts remain v1 until Plan 03/05 re-fit)
- Added 3 new tests: `test_artifact_loader_accepts_schema_v1`, `test_artifact_loader_accepts_schema_v2`, `test_artifact_loader_rejects_schema_v3`

### Task 4: Logs directory + PROMOTION-NOTES.md + ledger pin + full suite

- Created `.planning/phases/02-structural-per-stat-calibration/logs/` with `.gitkeep` and `PROMOTION-NOTES.md` stub (KS-08..KS-14 + Phase 2 Aggregate sections)
- `p2.entry.full` (ledger #106) pinned: rank_corr_delta=+0.2036, weekly_mae_delta=-1.459
  - Δ vs `p1.aggregate.full` (#105): rank_corr_delta +0.0008, weekly_mae_delta +0.001
  - Within Monte Carlo stochastic variation at 200 sims/season
  - Confirms: zero runtime behavior change from Plan 01 scaffolding
- Full suite: 2136 passed (2131 prior + 5 new Phase 2 scaffolding tests), zero regressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `test_bundled_decision_artifacts_are_available` to use `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED`**
- **Found during:** Task 3
- **Issue:** After bumping `ARTIFACT_SCHEMA_VERSION` to 2, the test asserted `artifact["schema_version"] == ARTIFACT_SCHEMA_VERSION`. Bundled artifacts remain at schema_version 1 until Plan 03/05 re-fits them. This caused the test to fail.
- **Fix:** Updated assertion to `artifact["schema_version"] in ARTIFACT_SCHEMA_VERSIONS_SUPPORTED` — correct because the loader now accepts both v1 and v2.
- **Files modified:** `tests/test_scoring/test_residual_calibration.py`
- **Commit:** 92cf114

## Self-Check

**Files exist:**
- config/defaults.yaml: `phase2_ks_flags:` block confirmed present
- src/fantasy_sim/config/loader.py: `def get_phase2_ks_flags()` confirmed present
- src/fantasy_sim/validation/config.py: `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` confirmed present
- src/fantasy_sim/scoring/residual_calibration.py: `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED` confirmed present
- .planning/phases/02-structural-per-stat-calibration/logs/.gitkeep: exists
- .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md: exists with `## Phase 2 Entry Baseline`

**Commits:**
- 68c9933: config(02-01): add phase2_ks_flags block + Phase-2 placeholder config keys
- c980b75: feat(02-01): add get_phase2_ks_flags() shim + extend bare_config_dict() with 7 KS flags + 2 sub-engine gates
- 92cf114: feat(02-01): bump residual_calibration artifact loader to schema_version: 2 (graceful v1 + v2 support)
- 1d1e486: docs(02-01): pin p2.entry.full ledger entry + create logs/ directory + initialize PROMOTION-NOTES.md

## Self-Check: PASSED

All 4 tasks committed. 2136 tests pass. p2.entry.full pinned at ledger #106.
