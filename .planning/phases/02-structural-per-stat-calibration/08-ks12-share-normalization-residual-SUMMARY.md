---
phase: 02-structural-per-stat-calibration
plan: 08
subsystem: simulation
tags: [share-normalization, availability, player-builder, ks-calibration, distribution-shape]

# Dependency graph
requires:
  - phase: 02-structural-per-stat-calibration
    provides: Plan 01 scaffolding (phase2_ks_flags gating pattern, bare config, validation harness)
  - phase: 02-structural-per-stat-calibration
    provides: Plan 06 (KS-11 position_reliability SHIPPED — full stack baseline includes it)
provides:
  - "_expected_active_share_factor() in player_builder.py: clips active/typical_roster_size to [0.5, 1.0]"
  - "_scale_shares_with_factor() in _normalize_roster_shares: scales to factor instead of 1.0 when KS-12 flag is on"
  - "MIN_BACKUP_RECEIVING_SHARE = 0.05: backup TE/WR exclusion threshold for eligibility computation"
  - "phase2_ks_flags.ks12_share_normalization_residual.enabled=true (SHIPPED)"
affects: [02-structural-per-stat-calibration/09-phase2-aggregate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Active-roster share scaling: normalize to fraction-of-active-roster rather than always 1.0"
    - "Backup exclusion threshold: MIN_BACKUP_RECEIVING_SHARE guards against classifying low-share players as 'missing'"

key-files:
  created:
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks12_bare.log
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks12_full.log
  modified:
    - src/fantasy_sim/data/player_builder.py
    - tests/test_data/test_player_builder.py
    - tests/test_data/test_game_context.py
    - tests/test_validation/test_config.py
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md

key-decisions:
  - "KS-12 SHIPPED: hard floor PASS (rank_corr +0.0006, weekly_mae -0.009); WR/TE receptions KS non-regressive all 3 seasons (2022-2024)"
  - "MIN_BACKUP_RECEIVING_SHARE = 0.05 selected per planner's discretion (D-09 CONTEXT.md)"
  - "Bare arm failure (wk_mae +0.454) treated as informational per Phase 1 Gate Relaxation Decision — bare mode with availability ON exposes expected noise amplification without corrective signal stack"
  - "Two p2.ks12.bare (#125, #127) and two p2.ks12.full (#126, #128) ledger entries; authoritative pair: #127 and #128 (most recent)"

patterns-established:
  - "Share-normalization target: normalize to active-roster fraction rather than always 1.0 prevents over-concentration when starters are on bye/injured"

requirements-completed: []

# Metrics
duration: ~95min (Task 3 only; Tasks 1+2 from prior session)
completed: 2026-04-27
---

# Phase 2 Plan 08: KS-12 Share-Normalization Residual Summary

**`_expected_active_share_factor` clips active/roster-size to [0.5,1.0] in `_normalize_roster_shares`, preventing over-concentration when players are missing — SHIPPED with hard floor PASS (+0.0006 rank_corr, -0.009 weekly_mae)**

## Performance

- **Duration:** ~95 min (Task 3 A/B + promotion; Tasks 1+2 completed in prior session)
- **Started:** 2026-04-27T (Tasks 1+2 in prior session; Task 3 resumed)
- **Completed:** 2026-04-27
- **Tasks:** 3/3 (1=RED TDD, 2=GREEN, 3=A/B promotion)
- **Files modified:** 6

## Accomplishments

- 7 KS-12 unit/integration tests (RED → GREEN TDD cycle) — all passing
- `_expected_active_share_factor(players, positions)`: computes active/typical_roster_size, clips to [0.5, 1.0]
- `_scale_shares_with_factor(players, positions, factor)`: scales sum to `factor` instead of 1.0 in `_normalize_roster_shares`
- `MIN_BACKUP_RECEIVING_SHARE = 0.05`: excludes very-low-share TE/WR from "active" count to prevent false "inactive" classification
- A/B with `availability.enabled=true`: full-stack #128 rank_corr +0.0006, weekly_mae -0.009 — SHIPPED
- PROMOTION-NOTES.md `## KS-12` block fully populated; previously untracked Plan 06 logs staged

## Task Commits

1. **Task 1: TDD RED — 7 failing KS-12 tests** - `b579c34` (test)
2. **Task 2: GREEN — implement _expected_active_share_factor + scale-with-factor** - `ead3e1f` (feat)
3. **Task 3: A/B promotion + defaults.yaml SHIPPED** - `fb9a81d` (feat)

**Plan metadata:** (this SUMMARY commit — see final_commit below)

## Files Created/Modified

- `src/fantasy_sim/data/player_builder.py` - Added `_KS12_SHARE_NORM_RESIDUAL` flag check, `_expected_active_share_factor()`, `_scale_shares_with_factor()`, `MIN_BACKUP_RECEIVING_SHARE = 0.05`; wired into `_normalize_roster_shares()`
- `tests/test_data/test_player_builder.py` - `TestKS12ShareNormalizationResidual` (5 unit tests)
- `tests/test_data/test_game_context.py` - `TestKS12NormalizeRosterSharesIntegration` (2 integration tests)
- `config/defaults.yaml` - `phase2_ks_flags.ks12_share_normalization_residual.enabled: true` (flipped SHIPPED)
- `tests/test_validation/test_config.py` - Added ks12 to `promoted` set in `test_phase2_ks_flags_present_and_default_false`
- `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` - `## KS-12` block with full A/B table + D-30 evaluation + decision

## Decisions Made

- **KS-12 SHIPPED**: Full hard floor passes (rank_corr +0.0006, weekly_mae -0.009); WR/TE receptions KS non-regressive across 2022, 2023, 2024.
- **MIN_BACKUP_RECEIVING_SHARE = 0.05**: Threshold prevents the factor from treating very-low-share backup TE/WR as "missing" active receivers. Selected per D-09 planner's discretion.
- **Bare arm informational**: Bare isolation with `availability.enabled=true` shows expected amplified noise (wk_mae +0.454) because corrective signal stack (PFF tiers, market_history, etc.) is absent in bare mode. Gate Relaxation Decision applies.
- **Two-run ledger**: Both bare (#125, #127) and full (#126, #128) have duplicate entries; authoritative pair is most-recent (#127 bare, #128 full) since first pair was from the interrupted prior session.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_phase2_ks_flags_present_and_default_false assertion failure after promotion**
- **Found during:** Task 3 (post-promotion pytest run)
- **Issue:** The test asserted `ks12_share_normalization_residual.enabled` must be `false` but flag was just promoted to `true`. Test did not include `ks12` in the `promoted` exclusion set.
- **Fix:** Added `"ks12_share_normalization_residual": # SHIPPED 2026-04-27 (Plan 08)` to the `promoted` set and updated the docstring accordingly.
- **Files modified:** `tests/test_validation/test_config.py`
- **Committed in:** `fb9a81d` (Task 3 promotion commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - test update required after promotion)
**Impact on plan:** Necessary correctness fix — the promotion gate test must track every new promotion. No scope creep.

## Issues Encountered

- Session SSE-stream timeout during prior execution — Tasks 1+2 were complete (commits b579c34, ead3e1f) but Task 3 was not started. The first A/B bare run (p2.ks12.bare #125) and full run (p2.ks12.full #126) from the interrupted session were already in the ledger. Task 3 was resumed cleanly; additional bare (#127) and full (#128) runs added. Authoritative results are the most recent pair.

## Known Stubs

None — all KS-12 functionality is fully wired. `_expected_active_share_factor` is live in `_normalize_roster_shares` when flag is enabled.

## Threat Flags

None — no new network endpoints, auth paths, file access, or schema changes introduced.

## Next Phase Readiness

- KS-12 promoted. All 8 Phase 2 per-KS plans (KS-08 through KS-14) now have a promotion decision.
- Plan 09 (Phase 2 aggregate A/B) is unblocked — all flags set to their shipped state.
- 2191 tests passing.

---
*Phase: 02-structural-per-stat-calibration*
*Completed: 2026-04-27*
