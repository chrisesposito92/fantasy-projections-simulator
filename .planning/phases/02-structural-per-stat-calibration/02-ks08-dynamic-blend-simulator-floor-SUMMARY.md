---
phase: 02-structural-per-stat-calibration
plan: 02
subsystem: ensemble
tags: [dynamic_blend, simulator_weight_floor, post_sim, ensemble, calibration, tdd]

# Dependency graph
requires:
  - phase: 02-structural-per-stat-calibration
    plan: 01
    provides: "Phase 2 scaffolding, phase2_ks_flags block, bare_config_dict, entry baseline ledger entry"
provides:
  - "KS-08 simulator-weight floor (0.20) applied post-normalize in dynamic_blend._artifact_weights()"
  - "apply_simulator_weight_floor() helper in dynamic_blend.py"
  - "Re-fit weights_2023.json and weights_2024.json with floor=0.20"
  - "6-entry sweep ledger p2.ks08.s{020,030,040}.{bare,full} + 1 promoted entry p2.ks08.promoted"
affects:
  - "Phase 2 Plans 03-09 (all use dynamic_blend as a post-sim blending layer)"
  - "Any plan that reads weights_2023.json / weights_2024.json (artifact consumers)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Simulator-weight floor: apply_simulator_weight_floor(weights, floor) after normalize_weights() — floor lifts simulator weight and proportionally scales ff_opportunity + market_history to preserve sum=1.0"
    - "Sweep-then-promote: 3-point floor sweep with D-05 selection rule (smallest passing floor where hard floor passes AND KS improvement on TE/WR); Phase 1 Gate Relaxation applied (bare failures informational)"
    - "Artifact re-fit with floor constraint: fit_dynamic_blend_artifact() accepts simulator_weight_floor kw-arg; candidate grid filtered to compositions where simulator >= floor; floor recorded in artifact metadata"

key-files:
  created:
    - ".planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_sweep_table.txt"
    - ".planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_s{020,030,040}_{bare,full}.log (6 files)"
    - ".planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_refit.log"
    - ".planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_promoted.log"
  modified:
    - "src/fantasy_sim/scoring/dynamic_blend.py (apply_simulator_weight_floor helper + _artifact_weights floor gate + fit_dynamic_blend_artifact floor kw-arg)"
    - "scripts/fit_dynamic_blend_weights.py (--simulator-weight-floor CLI flag)"
    - "src/fantasy_sim/data/ensemble/config.py (load_ensemble_config reads floor from phase2_ks_flags)"
    - "src/fantasy_sim/data/ensemble/models.py (DynamicBlendConfig.simulator_weight_floor: float = 0.0)"
    - "config/defaults.yaml (ks08_dynamic_blend_simulator_floor.enabled=true, floor=0.20)"
    - "src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json (re-fit with floor=0.20)"
    - "src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json (re-fit with floor=0.20)"
    - "tests/test_scoring/test_dynamic_blend.py (6 new test_ks08_* tests)"
    - "tests/test_validation/test_config.py (updated to allow promoted flags)"
    - ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md (## KS-08 section added)"

key-decisions:
  - "floor=0.20 selected via D-05 rule: smallest floor passing hard floor (rank_corr -0.0008, weekly_mae +0.004) AND non-zero KS improvement (TE recv_yds -0.01 in all 3 seasons)"
  - "floor=0.40 eliminated: weekly_mae +0.051 exceeds +0.05 hard limit"
  - "floor=0.30 eliminated: passes hard floor but TE receptions KS regresses (+0.01) in 2022/2023, WR recv_yds regresses in 2023"
  - "Phase 1 Gate Relaxation applied: all bare runs fail weekly_mae (>+0.05) — consistent with KS-03/04/05/06/07/15 pattern; bare failures informational, full-stack gates promotion"
  - "Codex LOW 9 alignment: aggregate fpts_ks +0.004 (slight regression) vs TE recv_yds -0.01 improvement (all 3 seasons); primary stat-level target (TE recv_yds) overrides aggregate disagreement per plan spec"
  - "Sanity check A/B p2.ks08.promoted (#113): rank_corr -0.0004 (vs sweep -0.0008, diff=0.0004 < 1e-3 threshold) — no drift post-promotion"
  - "Artifact re-fit took 1162s (~19 min) with 12 workers/season; promoted A/B took 1636s (~27 min) with 4 workers/season"

patterns-established:
  - "Post-promote sanity check: null A/B (arm A = arm B = promoted defaults) confirms no drift between sweep and deployed artifact; criterion is rank_corr delta < 1e-3"
  - "Promoted flag tracking in test_config.py: promoted set lists flags that have flipped to enabled=true; separate from must-be-false set"

requirements-completed: [KS-08]

# Metrics
duration: 370min
completed: 2026-04-27
---

# Phase 02 Plan 02: KS-08 Dynamic Blend Simulator-Weight Floor Summary

**KS-08 SHIPPED: simulator-weight floor=0.20 applied post-normalize in dynamic_blend, with bundled artifacts re-fit at floor=0.20 and consistent TE receiving_yards KS improvement (-0.01) across all 3 seasons (2022-2024)**

## Performance

- **Duration:** ~370 min (6h 10m) — dominated by 6-sweep A/B runs (~71 min each) and 1 promoted A/B (~27 min); coding tasks <30 min
- **Started:** 2026-04-26T23:40:31-04:00 (Task 1 RED commit)
- **Completed:** 2026-04-27T05:53:06Z
- **Tasks:** 4 (TDD: RED → GREEN → sweep → promote)
- **Files modified:** 10

## Accomplishments

- Added `apply_simulator_weight_floor()` helper to `dynamic_blend.py` implementing floor-lift + proportional renormalize math (post-`normalize_weights()`); gated behind `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled`
- Extended `fit_dynamic_blend_weights.py` with `--simulator-weight-floor` CLI flag; candidate grid filtered to compositions with simulator >= floor; floor recorded in artifact metadata
- Ran 6-entry sweep (floors {0.20, 0.30, 0.40} × {bare, full}); selected floor=0.20 via D-05 rule; promoted with re-fit artifacts and sanity check A/B
- 2142 tests pass (2131 prior + 5 Phase 2 scaffolding + 6 new KS-08 tests)

## Task Commits

1. **Task 1: RED — 6 failing tests for KS-08 floor + renormalize** - `6c3063f` (test)
2. **Task 2: GREEN — implement apply_simulator_weight_floor() + CLI flag** - `a571a6c` (feat)
3. **Task 3: Sweep — 6 ledger entries + D-05 selection** - `fe4b826` (chore)
4. **Task 4: Promote — flip flag + re-fit artifacts + sanity check** - `7598d18` (feat)

## Files Created/Modified

- `src/fantasy_sim/scoring/dynamic_blend.py` — apply_simulator_weight_floor() helper, _artifact_weights() floor gate, fit_dynamic_blend_artifact() floor kw-arg
- `scripts/fit_dynamic_blend_weights.py` — --simulator-weight-floor CLI flag
- `src/fantasy_sim/data/ensemble/config.py` — load_ensemble_config reads floor from phase2_ks_flags
- `src/fantasy_sim/data/ensemble/models.py` — DynamicBlendConfig.simulator_weight_floor field
- `config/defaults.yaml` — ks08_dynamic_blend_simulator_floor.enabled=true, floor=0.20
- `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json` — re-fit, 7 learned + 14 fallback, simulator_weight_floor=0.2
- `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json` — re-fit, 17 learned + 55 fallback, simulator_weight_floor=0.2
- `tests/test_scoring/test_dynamic_blend.py` — 6 new test_ks08_* tests
- `tests/test_validation/test_config.py` — promoted flag tracking (KS-08 in promoted set)
- `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` — KS-08 sweep table + D-05 rationale + final decision

## Decisions Made

- **floor=0.20 selected** via D-05 rule: smallest floor passing hard floor AND showing non-zero KS improvement on TE/WR. See PROMOTION-NOTES.md ## KS-08 for full 6-row sweep table.
- **Phase 1 Gate Relaxation applied:** all 3 bare runs fail weekly_mae (s020 +0.063, s030 +0.059, s040 +0.064 — all > +0.05 limit). Consistent with Phase 1 pattern where bare isolation exposes underlying simulation calibration differences masked by the full stack.
- **Codex LOW 9 (aggregate fpts KS vs stat-level target disagreement):** s020.full shows fpts_ks +0.004 (slight regression) but TE receiving_yards shows consistent -0.01 improvement across all 3 seasons. Per plan spec, stat-level primary target overrides aggregate disagreement. Documented in PROMOTION-NOTES.md per Codex LOW 9 requirement.
- **Artifact re-fit required (D-06 Pitfall 7):** without re-fit, runtime floor fights against unconstrained-fit learned weights. Both the runtime floor change AND the artifact re-fit ship in this plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_phase2_ks_flags_present_and_default_false() failed after defaults.yaml promotion**
- **Found during:** Task 4 (flip defaults.yaml to enabled=true)
- **Issue:** The test asserted ALL phase2_ks_flags entries have `enabled=False`. After flipping KS-08 to `enabled: true`, the test failed with assertion error on `ks08_dynamic_blend_simulator_floor`.
- **Fix:** Modified test to separate promoted flags (assert `enabled=True`) from must-be-false flags (assert `enabled=False`). Added `promoted` set with inline comment showing ship date. Non-promoted flags still assert False.
- **Files modified:** `tests/test_validation/test_config.py`
- **Verification:** 59 config tests pass; `enabled=True` assertion for KS-08 passes
- **Committed in:** `7598d18` (Task 4 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test expected values after promotion state change)
**Impact on plan:** Auto-fix necessary for test correctness. The fix establishes a pattern for tracking promoted flags that subsequent plans will reuse.

## Issues Encountered

- The promoted A/B run took 1635.7 seconds (~27 min, vs expected ~70 min from prior sweep timing). Actual timing was much faster because the promoted run is a null A/B (arm A = arm B = same defaults); the cache hit rate was higher since both arms use identical configs. Prior sweep runs needed to compute two distinct arm configurations. This is expected and confirms the sanity check mechanism works correctly.
- Background monitors set to wait for the `p2.ks08.promoted` run to complete — the process used SN (low priority nice) scheduling throughout, requiring patience during the ~27-minute computation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- KS-08 is SHIPPED at floor=0.20. Plan 03 (KS-09 per-stat residual_calibration) may now proceed.
- The promoted artifacts (weights_2023.json, weights_2024.json) now carry `simulator_weight_floor=0.2` in metadata — any downstream tooling that reads artifact metadata should account for this field.
- Phase 2 Plans 03-09 use dynamic_blend as the post-sim blending layer; the floor=0.20 is now the baseline for all subsequent measurements.

---
*Phase: 02-structural-per-stat-calibration*
*Completed: 2026-04-27*

## Self-Check: PASSED

All key files verified present:
- `src/fantasy_sim/scoring/dynamic_blend.py` FOUND
- `config/defaults.yaml` FOUND
- `weights_2023.json` FOUND
- `weights_2024.json` FOUND
- SUMMARY.md FOUND
- `logs/p2_ks08_promoted.log` FOUND

All commits verified:
- `6c3063f` (task1: test RED) FOUND
- `a571a6c` (task2: feat GREEN) FOUND
- `fe4b826` (task3: chore sweep) FOUND
- `7598d18` (task4: feat promote) FOUND
