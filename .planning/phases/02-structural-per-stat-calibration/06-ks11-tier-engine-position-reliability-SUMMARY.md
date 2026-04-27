---
phase: 02-structural-per-stat-calibration
plan: 06
subsystem: pff
tags: [position-reliability, tier-engine, config, feature-flag, codex-medium-6]
dependency_graph:
  requires: [02-01-phase2-scaffolding]
  provides: [ks11_position_reliability, position_reliability_loader_gate]
  affects: [tier_engine.compute_reliability, plans-07-08-09]
tech_stack:
  added: []
  patterns: [phase2-d45-feature-flag-pattern, codex-medium-6-loader-gate]
key_files:
  created:
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks11_bare.log
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks11_full.log
  modified:
    - config/defaults.yaml
    - src/fantasy_sim/data/pff/config.py
    - tests/test_data/test_pff/test_tier_engine.py
    - tests/test_data/test_pff/test_config.py
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
    - tests/test_validation/test_config.py
decisions:
  - "KS-11 SHIPPED — hard floor PASSES (+0.0004 rank_corr, -0.002 weekly_mae); KS Δ within noise at 200 sims (expected for cap raise affecting elite players only)"
  - "Codex MEDIUM 6 fix implemented: _ks11_position_reliability_enabled() helper gates loader; flag=false → passes {} regardless of defaults.yaml content"
  - "position_reliability populated with D-08 values: WR/TE {floor: 0.30, cap: 0.95, min_targets: 30}, RB {floor: 0.25, cap: 0.92, min_carries: 50}; QB stays at global {0.20, 0.80} per C-10"
  - "Flag default flipped to enabled=true after A/B passes; promoted set updated in test_phase2_ks_flags_present_and_default_false"
metrics:
  duration: 40m
  completed_date: "2026-04-27"
  tasks_completed: 3
  files_changed: 6
---

# Phase 2 Plan 06: KS-11 Tier Engine Position Reliability Summary

KS-11 per-position reliability cap raise via config-only change. Populates `pff.tier_engine.position_reliability` with D-08 values (WR/TE floor=0.30/cap=0.95, RB floor=0.25/cap=0.92), adds Codex MEDIUM 6 flag-gate in the loader, ships 7 tests, and promotes to enabled=true after A/B clears the hard floor.

## What Was Built

### Task 1: 5 unit tests for compute_reliability per-position behavior

Added to `tests/test_data/test_pff/test_tier_engine.py`:
- `test_ks11_wr_position_reliability_uses_per_position_floor_cap` — WR cap=0.95, floor=0.30 override
- `test_ks11_te_position_reliability_uses_per_position_floor_cap` — TE cap=0.95, floor=0.30 override
- `test_ks11_rb_position_reliability_uses_per_position_floor_cap` — RB cap=0.92, floor=0.25 override
- `test_ks11_qb_unchanged_at_global_values` — QB has no entry → falls back to global 0.20/0.80
- `test_ks11_position_reliability_unknown_position_uses_global` — K and None fall back to global cap

Reused existing `TestApplyTeamContext::test_qb_unchanged` as QB-untouched preflight gate.

### Task 1b: Codex MEDIUM 6 loader gate (src/fantasy_sim/data/pff/config.py)

Added `_ks11_position_reliability_enabled()` helper below `_SUPPORTED_DEPTH_ROLE_POSITIONS`. Replaced the unconditional `tier_raw.get("position_reliability", {})` assignment with a flag-gated conditional:
- When `phase2_ks_flags.ks11_position_reliability.enabled=false`: loader passes `{}` regardless of defaults.yaml content
- When flag is `true`: loader passes the populated dict

This ensures per-KS A/B isolation is real — the populated dict cannot leak into the bare arm.

Added to `tests/test_data/test_pff/test_config.py`:
- `test_ks11_loader_passes_empty_when_flag_off` — monkeypatches `_ks11_position_reliability_enabled` → False, verifies loader returns `{}`
- `test_ks11_loader_passes_populated_dict_when_flag_on` — monkeypatches flag → True, verifies dict passes through

### Task 2: A/B validation + promotion-state commit

Populated `pff.tier_engine.position_reliability` in defaults.yaml with D-08 values (safe because Codex MEDIUM 6 gate ensures the populated dict is no-op while flag=false). Ran two A/B arms:

**p2.ks11.bare (#120):** Δ rank_corr +0.0496, Δ weekly_mae -0.243 (bare informational)

**p2.ks11.full (#121):**
| Metric | Δ |
|--------|---|
| rank_corr | +0.0004 |
| weekly_mae | -0.002 |
| WR receiving_yards KS (avg) | ≈ 0.00 |
| TE receiving_yards KS (avg) | ≈ 0.00 |
| QB pass_yards KS (avg) | ≤ 0.00 (C-10 PASS) |

Hard floor: **PASS**. KS Δ within 200-sim noise (expected: cap raise affects elite players only, small fraction of player-weeks). C-10 QB invariant: **PASS**.

Flipped `phase2_ks_flags.ks11_position_reliability.enabled` to `true` in defaults.yaml. Updated `test_phase2_ks_flags_present_and_default_false` to include `ks11_position_reliability` in promoted set. PROMOTION-NOTES.md `## KS-11` block populated with full A/B table + D-30 + C-10 evaluations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_phase2_ks_flags_present_and_default_false promoted set**
- **Found during:** Task 2
- **Issue:** After flipping `ks11_position_reliability.enabled` to `true` in defaults.yaml, the hard-gate test `test_phase2_ks_flags_present_and_default_false` failed because `ks11_position_reliability` was not in the promoted set.
- **Fix:** Added `"ks11_position_reliability"` to the `promoted` set in the test. Also updated the docstring to list all currently promoted flags.
- **Files modified:** `tests/test_validation/test_config.py`
- **Commit:** 8a7de41

**2. [Rule 2 - Config] Populated defaults.yaml position_reliability block pre-A/B**
- **Found during:** Task 2
- **Issue:** `_parse_value` in `validation/config.py` does not support JSON dict syntax, so `--set pff.tier_engine.position_reliability={...}` cannot be used as the plan suggested.
- **Fix:** Populated the dict directly in defaults.yaml before running A/B (per fallback procedure in plan: "edit defaults.yaml in a TEMPORARY commit"). This is safe because Codex MEDIUM 6 gate (Task 1b) ensures the populated dict is no-op when flag=false. The populated dict stays in defaults.yaml as the promoted value.
- **Files modified:** `config/defaults.yaml`
- **Commit:** 8a7de41 (combined with promotion)

## Self-Check

Files exist:
- `config/defaults.yaml`: `position_reliability:` block with WR/TE/RB entries — FOUND
- `src/fantasy_sim/data/pff/config.py`: `_ks11_position_reliability_enabled` function — FOUND
- `tests/test_data/test_pff/test_tier_engine.py`: 5 `def test_ks11_*` functions — FOUND
- `tests/test_data/test_pff/test_config.py`: `test_ks11_loader_passes_empty_when_flag_off` + `test_ks11_loader_passes_populated_dict_when_flag_on` — FOUND
- `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md`: `## KS-11` section — FOUND

Commits:
- af93a0c: test(02-06) — FOUND
- ad51774: feat(02-06) Codex MEDIUM 6 gate — FOUND
- 8a7de41: feat(02-06) KS-11 SHIPPED — FOUND

Ledger entries:
- p2.ks11.bare (#120): FOUND
- p2.ks11.full (#121): FOUND

Test suite: 2173 passed (all KS-11 tests green)

## Self-Check: PASSED
