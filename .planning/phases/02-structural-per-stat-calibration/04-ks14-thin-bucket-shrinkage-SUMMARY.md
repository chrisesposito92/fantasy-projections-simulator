---
phase: 02-structural-per-stat-calibration
plan: "04"
subsystem: data/preprocessor + validation/coverage
tags: [ks14, thin-bucket, bayesian-shrinkage, flag-gate, codex-high-2]
dependency_graph:
  requires: ["02-01"]  # scaffolding (get_phase2_ks_flags)
  provides: ["_effective_min_bucket_plays", "_apply_bayesian_shrinkage", "buckets_below_min_plays_pct"]
  affects: ["02-05", "02-06"]  # KS-10 and KS-11 can now run (Wave 4 per D-12)
tech_stack:
  added: []
  patterns:
    - "Flag-gated threshold via module-level helper (mirrors Phase 1 KS-06 D-45 pattern)"
    - "Shape-preserving Bayesian shrinkage: location shift without scale change (Pattern 5)"
    - "final_defaults moved before bucket loop so shrinkage can access team defaults"
key_files:
  created: []
  modified:
    - src/fantasy_sim/data/preprocessor.py
    - src/fantasy_sim/validation/coverage.py
    - tests/test_data/test_preprocessor.py
    - tests/test_validation/test_coverage.py
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
decisions:
  - "KS-14 SHIPPED: full hard floor passes (Δ rank_corr +0.0000, Δ weekly_mae -0.000); bare regression (+0.068) informational per Gate Relaxation Decision"
  - "Flag flipped to enabled=true in defaults.yaml per D-30 SHIPPED criteria"
  - "codex HIGH 2 fix honored: MIN_BUCKET_PLAYS = 10 constant unchanged; _effective_min_bucket_plays() helper implements the threshold change"
metrics:
  duration: "~90 minutes execution"
  completed_date: "2026-04-27"
  tasks: 3
  files_modified: 7
---

# Phase 2 Plan 04: KS-14 Thin-Bucket Bayesian Shrinkage Summary

KS-14 implements a flag-gated threshold reduction (10 → 5) with Bayesian shrinkage for thin buckets (n∈[5,9]) in the preprocessor. The codex HIGH 2 fix ensures flag-off behavior is byte-identical to pre-KS-14 via the `_effective_min_bucket_plays()` helper pattern.

## What Was Built

**Task 1: Preprocessor — flag-gated threshold + Bayesian shrinkage helper**

- `MIN_BUCKET_PLAYS = 10` kept UNCHANGED at module scope (codex HIGH 2 fix)
- `_KS14_THIN_BUCKET_SHRINKAGE` flag read from `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` at import time
- `_effective_min_bucket_plays()` helper: returns 10 (flag off, legacy) or 5 (flag on)
- `_apply_bayesian_shrinkage(personal, team_default)`: shape-preserving location shift using project-wide Pattern 5 formula. `prior_strength = 5 * len(team_default)`, output = `personal_arr - observed_mean + adjusted_mean`
- `compute_play_calling`: threshold guard updated to use `_effective_min_bucket_plays()`
- `compute_play_outcomes`: `final_defaults` moved before bucket loop; flag-gated shrinkage branch fires for n∈[5,9] when flag is on; robust (n≥10) always retained
- 6 unit tests including the codex-required `test_ks14_legacy_min_bucket_plays_when_flag_off`

**Task 2: Coverage audit metric**

- `buckets_below_min_plays_pct(pbp_buckets, position, threshold=10)` added to `validation/coverage.py`
- Reports fraction of buckets with `n < threshold` (coarse per-position fallback rate)
- 3 unit tests covering all-robust, mixed-thin, and empty inputs

**Task 3: A/B validation + promotion**

- Bare A/B (`--baseline bare --arm-b-base bare`): Δ rank_corr +0.0015, Δ weekly_mae +0.068
- Full A/B (`--baseline defaults`): Δ rank_corr +0.0000, Δ weekly_mae -0.000
- Full hard floor PASSES; bare regression informational per Gate Relaxation Decision
- `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` flipped to `true`
- PROMOTION-NOTES.md `## KS-14` section populated with A/B results + D-30 evaluation
- `test_phase2_ks_flags_present_and_default_false` updated to include ks14 in promoted set

## A/B Results

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[RB][rush_yards] | Δ stat_ks[WR][receiving_yards] | Hard Floor |
|------|-------------|--------------|---------------------------|--------------------------------|-----------|
| bare | +0.0015     | +0.068       | -0.00                     | +0.00                          | FAIL (MAE > +0.05) |
| full | +0.0000     | -0.000       | -0.00                     | -0.00                          | PASS |

Decision: **SHIPPED** — full hard floor PASSES, primary targets non-regressive.

## Deviations from Plan

**1. [Rule 2 - Missing Functionality] Fixed test suite tracking of promoted flags**

- **Found during:** Task 3 post-promotion test run
- **Issue:** `test_phase2_ks_flags_present_and_default_false` correctly checked that KS-14 defaulted to `false`; after promotion the flag became `true` and the test failed
- **Fix:** Added `"ks14_thin_bucket_shrinkage"` to the `promoted` set in the test (same pattern used for KS-08 and KS-09)
- **Files modified:** `tests/test_validation/test_config.py`
- **Commit:** 10e845f (included in Task 3 commit)

**2. [Rule 1 - Bug] Added 1 extra test (6 instead of plan's 5)**

- The plan specified 5 unit tests. The implementation naturally produced 6 tests when `test_ks14_no_shrinkage_when_team_default_empty` covered both `None` and `[]` cases (2 assertions in 1 test body) and `test_ks14_no_shrinkage_when_n_above_threshold` was kept as a separate test covering the n≥10 fast path. All 6 pass.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1    | 6e3a9a3 | feat(02-04): KS-14 add _effective_min_bucket_plays() flag gate + Bayesian shrinkage helper |
| 2    | c079a43 | feat(02-04): KS-14 add buckets_below_min_plays_pct audit metric |
| 3    | 10e845f | feat(02-04): KS-14 SHIPPED per D-30 |

## Self-Check: PASSED

- [x] `src/fantasy_sim/data/preprocessor.py` contains `MIN_BUCKET_PLAYS = 10` (UNCHANGED)
- [x] `src/fantasy_sim/data/preprocessor.py` contains `def _effective_min_bucket_plays(`
- [x] `src/fantasy_sim/data/preprocessor.py` contains `def _apply_bayesian_shrinkage(`
- [x] `src/fantasy_sim/data/preprocessor.py` contains `_KS14_THIN_BUCKET_SHRINKAGE`
- [x] `src/fantasy_sim/validation/coverage.py` contains `def buckets_below_min_plays_pct(`
- [x] `tests/test_data/test_preprocessor.py` has 6 `def test_ks14_*` functions
- [x] `tests/test_validation/test_coverage.py` has `TestKs14BucketsBelowMinPlaysPct` class (3 tests)
- [x] `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` contains `## KS-14`
- [x] Ledger has 2 rows: `p2.ks14.bare` (#116) and `p2.ks14.full` (#117)
- [x] Full test suite: 2161 tests passing (2152 pre-plan + 9 new)
- [x] Commits 6e3a9a3, c079a43, 10e845f exist and are prefixed `(02-04)`
