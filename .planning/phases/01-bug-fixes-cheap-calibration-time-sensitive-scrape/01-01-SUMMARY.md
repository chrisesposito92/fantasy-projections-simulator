---
phase: 01
plan: 01
subsystem: engine.play_resolver
tags: [ks-01, rz-stack, bug-fix, distribution-preservation, phase1-ks-flag]
dependency-graph:
  requires: ["00 — validation harness + Phase-0 baseline + phase1_ks_flags scaffolding"]
  provides: ["RZ TD-gate failure path that preserves the sampled distribution (D-09); flag-promoted phase1_ks_flags.ks01_preserve_distribution=true"]
  affects: ["02-ks04-catch-yards-boost (depends_on: KS-01); 07-ks15-clamping-fix (depends_on: KS-01); 11-phase1-aggregate-validation (reads p1.ks01.* ledger entries)"]
tech-stack:
  added: []
  patterns: ["Cycle 3 D-45 feature-flag-gated per-KS code change (read at module import via get_phase1_ks_flags shim)"]
key-files:
  created: []
  modified:
    - "src/fantasy_sim/engine/play_resolver.py"
    - "tests/test_engine/test_play_resolver.py"
    - "config/defaults.yaml"
decisions:
  - "Helper signature: _tackled_short_preserve_distribution(yard_line, sampled_yards_pre_clamp) returns max(1, min(yard_line - 1, sampled_yards_pre_clamp)) per D-09"
  - "Flag-gated implementation per Cycle 3 D-45: legacy _tackled_short preserved as the else-branch in both _resolve_pass and _resolve_run; flag flip in defaults.yaml is the rollback knob"
  - "Pre-clamp source for _resolve_pass = `player_yards` (post-boost, pre-clamp, pre-home-field, line 267/271); for _resolve_run = `raw_yards` (post-home-field, pre-clamp, line 362)"
  - "Test 5/6 monkeypatch _KS01_PRESERVE_DIST + _red_zone_td_gate to deterministically force the flag-on, gate-fail branch; mixed [1, 1, 1, 8, 10, 12, 15, 20] receiving distribution exercises the safe band [1, 2]"
  - "PROMOTED as SHIPPED-NO-OP (D-31): hard floor passes both A/B entries, KS Δ doesn't cleanly clear the -0.01 promotion bar at 200 sims/season; bug fix is correct, KS-04/KS-15 will stack on top"
metrics:
  duration: "28.5 min (1711 sec)"
  completed: "2026-04-26"
  tasks_total: 4
  tasks_completed: 4
  ledger_entries: 2
  promotion_state: "SHIPPED-NO-OP"
---

# Phase 1 Plan 01: KS-01 RZ TD-gate truncation fix — Summary

**Promotion state:** SHIPPED-NO-OP
**Phase:** 1
**Wave:** 1
**Final commit (Task 4):** see commits table

Replaced the punitive `_tackled_short()` rewrite (which overwrote realistic catch / run yardage with `rng.integers(1, max(2, yard_line // 3))` whenever the RZ TD gate denied a touchdown) with a distribution-preserving variant per D-09: `yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))`. Gated behind `phase1_ks_flags.ks01_preserve_distribution.enabled` per Cycle 3 D-45 so the per-KS A/B is a genuine two-arm comparison; promoted to default `true` after the A/B passed hard floor.

## What shipped

1. New helper `_tackled_short_preserve_distribution(yard_line, sampled_yards_pre_clamp) -> int` in `src/fantasy_sim/engine/play_resolver.py` (D-09 semantics: floor at 1, cap at yard_line - 1).
2. Module-level `_KS01_PRESERVE_DIST` sentinel read once from `phase1_ks_flags.ks01_preserve_distribution.enabled` at import time (Cycle 3 D-45).
3. Both `_resolve_pass` (RZ pass-TD-gate failure branch) and `_resolve_run` (RZ run-TD-gate failure branch) now choose between the new helper (flag on) and the legacy `_tackled_short` (flag off) — the legacy path is preserved as the else-branch in both call sites, so emergency rollback is just flipping the flag back to `false`.
4. RED→GREEN test pair (TDD per D-33): 6 new tests under `# === KS-01: RZ TD-gate distribution preservation ===` covering the helper directly (Tests 1, 2), PASS_TD_GATE / RUN_TD_GATE calibration regression guards (Tests 3, 4), and end-to-end forced-fail-gate behavior in `_resolve_pass` / `_resolve_run` (Tests 5, 6).
5. `config/defaults.yaml` flag default flipped from `false` → `true` in the promotion-state commit (per D-45). The flag block remains in `defaults.yaml` so emergency rollback is a single-line edit.

## Tasks

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | RED — failing tests for KS-01 distribution preservation + PASS/RUN gate calibration regression guards | `80d8d11` | `tests/test_engine/test_play_resolver.py` |
| 2 | GREEN — implement `_tackled_short_preserve_distribution` per D-09 + flag-gated rewire of both call sites | `9f7b588` | `src/fantasy_sim/engine/play_resolver.py`, `tests/test_engine/test_play_resolver.py` |
| 3 | A/B validate KS-01 in isolation and full-stack; commit ledger entries + PROMOTION-NOTES | `5d9bcf4` | `.planning/phases/01-…/logs/p1.ks01.bare.log`, `.../p1.ks01.full.log`, `.../PROMOTION-NOTES.md` |
| 4 | Promotion-state commit + SUMMARY (flag default flipped to `true`) | (this commit) | `config/defaults.yaml`, `.planning/phases/01-…/01-01-SUMMARY.md` |

## Ledger results

| Entry | Δ rank_corr | Δ weekly_mae | Δ season_mae | Δ fpts_ks | QB pass_yards KS Δ (max season) | Hard floor (D-31)? | Promotion bar (D-31 medium-large)? |
|-------|-------------|--------------|--------------|-----------|----------------------------------|--------------------|------------------------------------|
| p1.ks01.bare | +0.0011 | -0.002 | -0.063 | +0.000 | ~0 (no movement) | PASS | NOT MET (no movement) |
| p1.ks01.full | +0.0004 | +0.003 | +0.046 | +0.000 | -0.01 (2024 only) | PASS | BARELY MET (2024 only) |

Phase-0 reference (`phase0.baseline.full` Arm B, frozen): QB pass_yards KS = 0.353, mean bias = -28.32 yd/g.

QB pass_yards mean bias (Arm B) is essentially unchanged across both runs:
- bare: 187.0 / 193.5 / 189.5 vs actual 215.5 / 209.5 / 216.5 → -28.5 / -16.0 / -27.0 yd/g
- full: 189.7 / 192.0 / 196.0 vs actual 217.8 / 217.0 / 218.5 → -28.0 / -25.0 / -22.5 yd/g

Mechanism explanation: KS-01 fires only on RZ TD-gate failures, which is a small fraction of plays per game. The per-game stat impact at 200 sims/season is below the detection threshold of the A/B harness. KS-04 (CATCH_YARDS_BOOST retune) and KS-15 (clamping fix) will compound on this foundation per the dependency-mandatory order in D-26.

## Promotion decision

Hard floor passes BOTH ledger entries (D-31). Promotion bar (KS Δ ≤ -0.01 on QB pass_yards) is not cleanly met across all seasons — only 2024 in the full overlay shows a -0.01 movement; bare-isolation shows zero movement; mean bias is unchanged. Per D-31 "shipped no-op" clause: "If hard floor passes but KS doesn't move, mark as 'shipped no-op' and continue — the bug fix is correct even if KS doesn't budge."

**Decision: SHIPPED-NO-OP** — flip `phase1_ks_flags.ks01_preserve_distribution.enabled` to `true` so downstream defaults runs (Plan 11 `p1.aggregate.full`) automatically pick up the new code path. Bug fix is correct and required as a precondition for KS-04 / KS-15.

See `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` `## KS-01` section.

## Deviations from Plan

**1. [Rule 1 — TDD test authoring bug] Test 5 distribution had no values inside the safe band**
- **Found during:** Task 2 GREEN run (Test 5 failed with `mean=2.0`)
- **Issue:** The plan's stated WR `receiving_yards_dist=np.array([8, 10, 12, 15, 20])` produced ALL samples > yard_line - 1 = 2, so the helper always returned 2 (the cap). The plan's assertion `1.0 < mean < 2.0` was unsatisfiable for that input.
- **Fix:** Changed the distribution to `[1, 1, 1, 8, 10, 12, 15, 20]` so the sampling band is actually exercised (some plays return 1, others return 2), making the assertion meaningful as a "is it sampling, or always saturating?" probe.
- **Files modified:** `tests/test_engine/test_play_resolver.py` (KS-01 Test 5 only)
- **Commit:** `9f7b588` (Task 2 GREEN — bundled with the fix)

**2. [Rule 3 — blocking issue] RED-state test guard pattern**
- **Found during:** Task 1 RED initial run
- **Issue:** The plan's RED tests imported `_tackled_short_preserve_distribution` at module top, which made the whole test file uncollectable (ImportError at collection time). That blocked the calibration regression-guard tests (Tests 3 & 4) from running, and Task 1's acceptance criterion required `ks01_pass_td_gate_calibration` to PASS in RED.
- **Fix:** Replaced the top-level import with a `_ks01_helper()` dynamic accessor that does `_pr._tackled_short_preserve_distribution` lazily inside each helper-dependent test. The file collects in RED; helper-dependent tests fail (Rule-1 RED behavior); calibration tests pass (Rule-3 acceptance criterion satisfied).
- **Files modified:** `tests/test_engine/test_play_resolver.py`
- **Commit:** `80d8d11` (Task 1 RED — bundled with the test additions)

No other deviations from plan. Tests 5 & 6 (resolve_pass/resolve_run forced-fail-gate band check) ran with full coverage — no need for the plan's `pytest.mark.skip` fallback.

## Threat-model verification

Per the plan's `<threat_model>`:
- **T-01-01-01 (Tampering — RZ TD-gate calibration constants):** mitigated by `test_ks01_pass_td_gate_calibration_unchanged_after_fix` and `test_ks01_run_td_gate_calibration_unchanged_after_fix` (100k-trial rate check ±0.01). Both passing post-Task-2.
- **T-01-01-02 (Information disclosure — ledger):** accepted (no PII).
- **T-01-01-03 (DoS — A/B wall-clock):** accepted; bare run took 65.6s, full run took 1142.2s (~19 min) — both bounded by `--sims 200`.

No new threat surface introduced; no `## Threat Flags` section needed.

## Authentication gates

None.

## Self-Check: PASSED

Verified each claim:

**Files exist:**
- `src/fantasy_sim/engine/play_resolver.py` → FOUND
- `tests/test_engine/test_play_resolver.py` → FOUND
- `config/defaults.yaml` → FOUND
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks01.bare.log` → FOUND
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks01.full.log` → FOUND
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` → FOUND

**Commits exist:**
- `80d8d11` (Task 1 RED) → FOUND
- `9f7b588` (Task 2 GREEN) → FOUND
- `5d9bcf4` (Task 3 ledger + notes) → FOUND
- (Task 4 promotion commit appended after this SUMMARY is written.)

**Code-shape acceptance criteria (Task 2):**
- `_tackled_short_preserve_distribution(yard_line: int, sampled_yards_pre_clamp: int) -> int` — present in play_resolver.py
- `return max(1, min(yard_line - 1, sampled_yards_pre_clamp))` — present
- `_KS01_PRESERVE_DIST` — present (line 27)
- `if _KS01_PRESERVE_DIST:` — present (lines 301, 400)
- `yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)` — present (line 302, _resolve_pass)
- `yards = _tackled_short_preserve_distribution(state.yard_line, raw_yards)` — present (line 401, _resolve_run)
- Legacy path preserved: `grep -c "yards = _tackled_short(state.yard_line, rng)" src/fantasy_sim/engine/play_resolver.py` → 2

**Test outcomes:**
- KS-01 selector: 6/6 PASSED, 0 SKIPPED, 0 FAILED
- Full suite: 2086 passed (up from prior 1,200+ baseline; matches D-35 requirement)

**Ledger:**
- `uv run python scripts/validate.py --show-ledger | grep p1.ks01 | wc -l` → 2 (both entries present)
