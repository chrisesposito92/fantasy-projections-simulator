---
phase: 02-structural-per-stat-calibration
plan: 03
subsystem: scoring/residual-calibration
tags: [ks-09, per-stat-calibration, residual-calibration, schema-v2, tdd, shipped-partial]
dependency_graph:
  requires: ["02-01 (schema_v2 loader)", "02-02 (KS-08 floor active)"]
  provides: ["corrected_<stat> columns", "schema-v2 artifacts with stat_corrections", "validate.py corrected_ routing"]
  affects: ["02-04 (KS-14)", "02-05 (KS-10)", "residual_calibration artifact schema"]
tech_stack:
  added: ["StatLevelConfig dataclass", "stat_clamp_adjustment() helper", "corrected_<stat> per-row columns", "stat_corrections artifact block", "actual_stats_by_player_week training param", "--set override support in fit_residual_calibration.py"]
  patterns: ["two-stage layered fpts (D-01)", "std-scaled clamp ±2*σ (D-04)", "phase2_ks_flags master toggle (D-02)", "corrected_ routing in validate.py (codex HIGH 1 fix)"]
key_files:
  created:
    - tests/test_validation/test_validate_corrected_stat_routing.py
  modified:
    - src/fantasy_sim/data/ensemble/models.py
    - src/fantasy_sim/data/ensemble/__init__.py
    - src/fantasy_sim/data/ensemble/config.py
    - src/fantasy_sim/scoring/residual_calibration.py
    - scripts/fit_residual_calibration.py
    - scripts/validate.py
    - config/defaults.yaml
    - tests/test_scoring/test_residual_calibration.py
    - tests/test_validation/test_config.py
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
decisions:
  - "KS-09 SHIPPED-PARTIAL: hard floor passes (+0.0001 rank_corr, +0.003 weekly_mae); KS Δ ≤ -0.03 bar not met (per-stat corrections too small at 200 sims vs full-stack existing calibration); architecture installed for Phase 3/4 levers"
  - "Two-stage layered fpts (D-01): corrected_<stat> columns are NEW/additive; row[fpts] unchanged from existing fpts-level correction"
  - "Codex HIGH 1 fix: validate.py _compute_distribution_ks prefers corrected_<stat> when KS-09 flag on — non-observability-only"
  - "Bare A/B failures informational per Phase 1 Gate Relaxation Decision (artifacts fit on full-stack residuals)"
metrics:
  duration: "61 minutes"
  completed: "2026-04-27"
  tasks: 5
  files_modified: 13
---

# Phase 2 Plan 03: KS-09 Per-Stat Residual Calibration Summary

**One-liner:** Two-stage per-stat residual calibration with std-scaled clamp writes `corrected_<stat>` columns and routes into validate.py KS metrics (codex HIGH 1 fix) — architecture SHIPPED-PARTIAL, hard floor passes, KS bar not yet met at 200 sims.

## What Was Built

### Architecture (D-01 Two-Stage Layered Approach)

KS-09 extends `residual_calibration` from fpts-only to per-stat correction while preserving the existing fpts-level correction unchanged. Per D-01:
- `adjust_week()` writes NEW `corrected_<stat>` columns (additive, do NOT propagate into `row["fpts"]`)
- `row["fpts"]` = max(raw_sim_fpts + existing_bucket_correction, 0) — UNCHANGED
- Per-stat and fpts corrections may diverge (documented per Pitfall 1)

### Per-Stat Correction Logic

1. `stat_clamp_adjustment(value, clamp_std)` — clamps per-stat residual to ±2*clamp_std (D-04)
2. `_per_stat_corrections()` in `adjust_week()` — for each covered stat, looks up `artifact["stat_corrections"][stat]["corrections"][bucket_key]` and applies clamped correction
3. Missing bucket → zero adjustment (corrected == raw)
4. 9 covered stats: pass_yards, pass_tds, interceptions, rush_yards, rush_tds, receiving_yards, receptions, receiving_tds, fumbles_lost

### Validate.py Output Contract (Codex HIGH 1 Fix)

`_compute_distribution_ks()` now routes `corrected_<stat>` into `stat_ks` / `stat_mean_bias` when the KS-09 flag is on:
- `_read_stat(row, stat)` helper: returns `row.get(f"corrected_{stat}")` when flag on + column present, else raw
- Arm A in bare A/B: no corrected_ columns → reads raw (byte-identical to legacy)
- Arm B with KS-09 active: reads corrected values

This resolves the observability-only failure mode codex identified — per-stat corrections now flow into the canonical ledger metric.

### Schema v2 Artifacts

`calibration_2023.json` and `calibration_2024.json` re-fit with `stat_corrections` block:
- schema_version: 2 (v1 artifacts continue to load via empty `stat_corrections: {}` normalization)
- 2023: 8 learned buckets, 11 fallback; 2024: 17 learned buckets, 34 fallback
- stat_corrections: 9 stats × 8-19 buckets each with correction + clamp_std

### Training Script Extension

- `source_row_for_projection()` + `source_rows_for_week()` extended with `actual_stats_by_player_week` parameter to capture projected stat values and actual_<stat> values for per-stat correction fitting
- `fit_residual_calibration_artifact()` extended with per-stat block computation when `stat_level.enabled`
- `fit_residual_calibration.py` gains `--set` override support (uses `apply_overrides` from validation.config)

## A/B Results

### p2.ks09.bare (ledger #114)
- Δ rank_corr: +0.0017 | Δ weekly_mae: +0.060 | Δ fpts_ks: +0.001
- Hard floor: FAIL (weekly_mae +0.060 > +0.05) — informational per Gate Relaxation Decision
- Note: artifacts fit on full-stack residuals; bare-mode isolation shows expected mismatch (bare QB pass_yards KS regresses +0.07-0.09 in bare mode)

### p2.ks09.full (ledger #115)
- Δ rank_corr: +0.0001 | Δ weekly_mae: +0.003 | Δ season_mae: -0.040
- Hard floor: PASS
- QB pass_yards KS Δ: avg +0.003 (within noise; 2022=-0.00, 2023=+0.00, 2024=+0.01)
- QB pass_yards mean bias in arm B: 2022=-39.1, 2023=-35.5, 2024=-35.9 yd/g

## D-14 Evaluation

| Condition | Result |
|-----------|--------|
| Hard floor (rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05) | **PASS** (+0.0001 / +0.003) |
| KS Δ ≤ -0.03 on QB pass_yards | **FAIL** (Δ ≈ +0.003, within noise) |
| QB pass_yards mean bias \|Δ\| ≤ 5 yd/g | Marginal improvement ~3-4 yd/g in arm B |

**Status: SHIPPED-PARTIAL.** Flag flips to true. Per D-14: BLOCKED requires hard floor regression; since hard floor passes, architecture stays active for Phase 3/4 levers (KS-10 per-position caps, KS-14 thin-bucket shrinkage) to layer on top. Per-stat corrections are small because the full-stack (market_history + ff_opportunity + fpts-level calibration) already handles most QB bias; incremental per-stat residuals are 1-5 yd/week per bucket.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan referenced `ResidualCalibrationLayer` (non-existent class name)**
- Found during: Task 1
- Issue: Plan's code snippets used `ResidualCalibrationLayer` but actual class is `ResidualCalibrationProjectionAdjuster`
- Fix: Used actual class name in all test code
- Files: tests/test_scoring/test_residual_calibration.py

**2. [Rule 2 - Missing Functionality] `source_row_for_projection` lacked stat capture for per-stat fitting**
- Found during: Task 4 (re-fit)
- Issue: The training script couldn't compute per-stat corrections because source rows didn't carry projected stat values or actual_<stat> values
- Fix: Extended `source_row_for_projection()` and `source_rows_for_week()` with `actual_stats_by_player_week` parameter; collect_source_rows_for_season passes `actual_stats_by_player_week` dict built from ActualPlayerWeek objects
- Files: src/fantasy_sim/scoring/residual_calibration.py, scripts/fit_residual_calibration.py

**3. [Rule 2 - Missing Functionality] `fit_residual_calibration.py` lacked `--set` override support**
- Found during: Task 4 (re-fit)
- Issue: No way to enable KS-09 flag for the re-fit without editing defaults.yaml directly
- Fix: Added `--set KEY=VALUE` CLI argument using existing `apply_overrides()` from validation.config
- Files: scripts/fit_residual_calibration.py

**4. [Rule 1 - Bug] `test_phase2_ks_flags_present_and_default_false` required KS-09 to remain `false`**
- Found during: Task 5
- Issue: Test had `ks09_per_stat_residual_calibration` in the "must be false" check; needed to add it to the `promoted` set after promotion commit
- Fix: Added `ks09_per_stat_residual_calibration` to `promoted` set in the test
- Files: tests/test_validation/test_config.py

### No architectural deviations (Rule 4 not triggered).

## Known Stubs

None. The per-stat correction fires on all populated buckets and falls back gracefully (zero correction = corrected == raw). The corrected_<stat> columns are always written when the flag is on and the stat is present in the row.

## Self-Check

**Checking created/modified files:**

- tests/test_scoring/test_residual_calibration.py: present (8 new ks09 tests)
- tests/test_validation/test_validate_corrected_stat_routing.py: created (2 routing tests)
- src/fantasy_sim/scoring/residual_calibration.py: modified (stat_clamp_adjustment, per-stat correction in adjust_week, stat_corrections in fit)
- src/fantasy_sim/data/ensemble/models.py: modified (StatLevelConfig, stat_level field)
- src/fantasy_sim/data/ensemble/config.py: modified (stat_level loading + KS-09 flag master toggle)
- scripts/validate.py: modified (_read_stat, _ks09_on, corrected_ routing)
- scripts/fit_residual_calibration.py: modified (--set support, actual_stats_by_player_week)
- config/defaults.yaml: modified (ks09 enabled=true, stat_level enabled=true)
- calibration_2023.json + calibration_2024.json: schema_version=2 with stat_corrections

**Commits (5 task commits):**
- 5f5e3e4: test(02-03): add 10 failing tests for KS-09 per-stat residual_calibration
- 92c942a: feat(02-03): KS-09 implement stat_clamp_adjustment() + per-stat correction
- 6a4a086: feat(02-03): route corrected_<stat> into validate.py stat_ks / stat_mean_bias
- 73ea95d: chore(02-03): KS-09 re-fit calibration artifacts (schema_v2) + run A/B
- 0fab517: feat(02-03): KS-09 SHIPPED-PARTIAL per D-14

## Self-Check: PASSED

All commits exist in git log. All key files present. 2152 tests pass. Ledger has 2 p2.ks09 entries. PROMOTION-NOTES.md has ## KS-09 section with D-14 evaluation and Final decision.
