---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 06
subsystem: engine+data
tags: [ks07, positional-rz-catch-rate, play-resolver, player-builder, bug-fix, feature-flag, ab-validation, promoted, tdd]

# Dependency graph
requires:
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: "Plan 00 phase1_ks_flags scaffolding (ks07_positional_rz_catch_rate flag block with rates {WR:0.92, TE:0.95, RB:0.85}), bare-isolation A/B harness (--arm-b-base bare), and gate-relaxation decision (mid-phase 2026-04-26 — bare hard-floor failures on bug-fix work are informational, full-stack hard floor is operative)"
provides:
  - "src/fantasy_sim/engine/play_resolver.py: D-20 positional `RZ_CATCH_RATE_MODIFIERS` dict {WR:0.92, TE:0.95, RB:0.85} replacing the single 0.92 scalar (kept for backward compat as `RZ_CATCH_RATE_MODIFIER = MODIFIERS['WR']`). Per-play RZ catch rate fallback in `_resolve_pass` looks up `receiver.position` in the dict (with WR fallback for unknown positions) when `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` is on; else uses the legacy scalar. Config rates can be overridden via `--set phase1_ks_flags.ks07_positional_rz_catch_rate.rates.<POS>=<rate>` for runtime sweeps."
  - "src/fantasy_sim/data/player_builder.py: D-20 per-player RZ catch rate fallback in `_assemble_models` (when `rs['rz_targets'] < MIN_RZ_TARGETS = 10`) now uses the position-aware modifier when the flag is on, legacy 0.92 when off. Lazy module-attribute lookup of `_KS07_POSITIONAL_RZ_CATCH_RATE` so monkeypatch in tests applies cleanly."
  - "config/defaults.yaml: phase1_ks_flags.ks07_positional_rz_catch_rate.enabled = true (PROMOTED 2026-04-26)."
  - "tests/test_engine/test_play_resolver.py: 7 new KS-07 tests (dict literal, backward-compat scalar, 3 flag-on behavior tests for WR/TE/RB, 2 flag-off legacy parity tests for TE/RB)."
  - "tests/test_data/test_player_builder.py: 6 new TestKs07PositionalRzCatchRateFallback tests (TE/RB/WR flag-on, TE/RB flag-off, lookup-key smoke test). Plus updated `test_rz_catch_rate_fallback_below_threshold` to read the live flag (TE TK87 now uses 0.95 under flag-on, 0.92 under flag-off)."
  - "PROMOTION-NOTES.md ## KS-07 section: full ledger evaluation, primary-target detail, mechanism diagnosis of the bare-mode QB pass_yards regression, and PROMOTED decision under the relaxed full-stack-only gate."
affects:
  - "Production simulator: per-player RZ catch rate fallback (when player has < 10 RZ targets) and per-play RZ catch rate fallback (when receiver has zero rz_catch_rate stat) both now use the position-aware modifier. TE players catch slightly more RZ targets (0.95 vs 0.92); RB players catch fewer RZ targets (0.85 vs 0.92, reflecting checkdowns under pressure). WR players unchanged."
  - "rookie_builder.py NOT touched per plan scope — continues to use the legacy `RZ_CATCH_RATE_MODIFIER = 0.92` scalar for all rookie archetypes (lines 96, 103). Tracked as a deferred enhancement: extending positional rates to rookie archetypes is a small follow-up that could ship in a later cleanup commit."
  - "Phase 1 Plan 11 aggregate validation: post-Phase-1 defaults now include the KS-07 fix; Plan 11 will compare p1.aggregate.full Arm B against phase0.baseline.full Arm B, and the Δ will include this PROMOTED change alongside KS-01/KS-03/KS-04/KS-05/KS-06/KS-21."
  - "All future per-KS plans in this phase (Plan 07 KS-15, Plan 08 KS-29, Plan 10 KS-32) will run on top of the KS-07-promoted defaults — their A/B Arm B is `defaults + KS-XX-flag` and `defaults` already includes KS-07 promotion."

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level flag-gated code paths via get_phase1_ks_flags() at import (mirrors KS-01/03/04/05/06 conventions)."
    - "Backward-compat scalar pointing into the canonical dict (`RZ_CATCH_RATE_MODIFIER = RZ_CATCH_RATE_MODIFIERS['WR']`) so legacy callers and the flag-off branch get one shared 0.92 value without copy-paste drift."
    - "Lazy module-attribute lookup in player_builder.py (`from fantasy_sim.engine import play_resolver as _pr; if _pr._KS07_POSITIONAL_RZ_CATCH_RATE: ...`) so test monkeypatch on the source module applies to the consumer's read. Avoids the import-time-snapshot pitfall where `from ... import _KS07_POSITIONAL_RZ_CATCH_RATE` would freeze the boolean at import time."
    - "Config-driven dict literal: the canonical dict has hardcoded values (`{WR:0.92, TE:0.95, RB:0.85}`) and a runtime override loop reads `phase1_ks_flags.ks07_positional_rz_catch_rate.rates` to allow `--set` overrides without source edits. Source remains the source of truth for defaults; config is the runtime knob."

key-files:
  created:
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md (this file)"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.bare.log (~12 KB, ~1 min wall — Arm A loaded from bare cache)"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.full.log (~30 KB, ~30 min wall)"
  modified:
    - "src/fantasy_sim/engine/play_resolver.py: +56 lines (flag block + RZ_CATCH_RATE_MODIFIERS dict + config override loop + backward-compat scalar + flag-gated call site at line ~319)"
    - "src/fantasy_sim/data/player_builder.py: +18 lines (import update + flag-gated rz_modifier branch at line ~549)"
    - "tests/test_engine/test_play_resolver.py: +146 lines (7 KS-07 tests)"
    - "tests/test_data/test_player_builder.py: +205 lines (TestKs07PositionalRzCatchRateFallback class with 6 tests + 17-line update to legacy test_rz_catch_rate_fallback_below_threshold to read live flag)"
    - "config/defaults.yaml: 1 line (flag default false → true)"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md: +148 lines (## KS-07 section)"

key-decisions:
  - "PROMOTED via flag-default flip in config/defaults.yaml under the relaxed full-stack-only gate (mid-phase 2026-04-26 gate-relaxation decision in PROMOTION-NOTES). Bare hard-floor failure (+0.064 weekly_mae) is informational only per the gate-relaxation rationale; full-stack hard floor PASSES (Δ rank_corr -0.0012, Δ weekly_mae +0.003, Δ fpts_ks +0.000)."
  - "Primary-target non-regression bar (D-30 small-gain) met: WR receiving_yards full Δ ≈ 0 across all 3 seasons (flat). TE receiving_yards full Δ flat in 2 of 3 seasons (+0.01 in 2023 only). TE receptions full Δ flat in 2 of 3 seasons (+0.01 in 2023 only). Aggregate fpts_ks Δ = +0.000."
  - "Plan success criterion #3 (RB rush_yards Δ ≥ 0): full RB rush_yards ΔKS = +0.00 / +0.01 / -0.00 — non-negative across all 3 seasons ✓."
  - "Bare-mode QB pass_yards regression (+0.07 to +0.09 ΔKS, mean drop ~5 yd/g) diagnosed in PROMOTION-NOTES: RB modifier 0.85 (was 0.92) increases RB checkdown incompletions in the RZ → more 0-yd plays charged to QB pass_yards in bare mode where no compensating engines absorb the per-play delta. Same unmasking pattern as KS-03/04/05/06; not attributable to any defect in the KS-07 mechanism."
  - "Test fix-up for `test_rz_catch_rate_fallback_below_threshold` (Rule 1 deviation): the pre-existing test hardcoded `0.92` for TK87 (a TE). With the flag now on by default, TK87 uses 0.95. Updated the assertion to read the live `_KS07_POSITIONAL_RZ_CATCH_RATE` flag and look up the position-aware modifier so the test stays correct under both flag states."
  - "rookie_builder.py NOT updated per plan scope (only play_resolver.py:319 and player_builder.py:549 were in scope per the must_haves frontmatter). The legacy `RZ_CATCH_RATE_MODIFIER = 0.92` scalar continues to be exported for the rookie builder's two call sites (lines 96, 103). All 4 rookie archetype tests (lines 619-635) still pass. Extending the positional rates to rookie archetypes is a small follow-up enhancement that could ship in a later cleanup commit."
  - "TDD-first executed for both tasks per D-33/D-34 (test-after acceptable for KS-07, but TDD chosen for consistency with the per-flag pattern established in KS-01/04/15 and the rigor preference per `feedback_quality_over_simplicity.md`): 7 RED tests in play_resolver + 6 RED tests in player_builder committed first; GREEN code paths added second; refactor-style cleanup not needed."
  - "Doc-string trim commit (3a8bc7d) to remove duplicated dict literal from the explanatory comment so each `\"WR\": 0.92` / `\"TE\": 0.95` / `\"RB\": 0.85` string appears exactly once. Plan acceptance criterion `grep -c '\"WR\": 0.92'` literally requires return value 1 — the explanatory comment was duplicating the literal and inflating the count to 2."

patterns-established:
  - "Backward-compat scalar pointing into a canonical dict: `SCALAR = DICT['<canonical_key>']` is a clean way to introduce a dict-of-rates without breaking existing callers that imported the scalar. Prevents copy-paste drift between the dict default and the scalar."
  - "Lazy attribute lookup for cross-module flag reads in test contexts: `from module import name as _alias; if _alias._FLAG: ...` keeps test monkeypatch semantics (the assignment to `pr._FLAG` actually affects `_pr._FLAG` because they point to the same module object). Useful for any future flag-gated code that's read from one module and gated by a constant defined in another."

requirements-completed: [KS-07]

# Metrics
duration: 40min
completed: 2026-04-26
---

# Phase 1 Plan 06: KS-07 Positional RZ Catch Rate Summary

**Per D-20, replaces the single `RZ_CATCH_RATE_MODIFIER = 0.92` scalar with the per-position dict `RZ_CATCH_RATE_MODIFIERS = {"WR": 0.92, "TE": 0.95, "RB": 0.85}`. Two call sites updated (play_resolver.py:319 per-play fallback, player_builder.py:549 per-player fallback). Both gated behind `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled` per Cycle 3 D-45 (legacy code preserved for the flag-off A/B Arm A; new code is the flag-on Arm B and the production default after promotion). KS-07 is the SECOND plan in Phase 1 to clear the relaxed full-stack hard floor cleanly with the new code path active (KS-06 was first; KS-01 SHIPPED-NO-OP; KS-03/04/05 RETROACTIVELY PROMOTED under the relaxed gate). Full-stack hard floor PASSES (Δ rank_corr -0.0012, Δ weekly_mae +0.003, Δ fpts_ks +0.000); D-30 small-gain primary-target non-regression bar met on WR/TE receiving_yards; success criterion #3 (RB rush_yards Δ ≥ 0) met across all 3 seasons.**

## Performance

- **Duration:** ~40 min wall (most spent on the ~30-min full-stack A/B validation run; bare A/B was ~1 min via warm bare cache; code+tests ~8 min)
- **Started:** 2026-04-26T19:46:57Z
- **Completed:** 2026-04-26T20:30Z (approx)
- **Tasks:** 4 (Task 1 RED+GREEN+doc, Task 2 RED+GREEN, Task 3 A/B + ledger, Task 4 promotion + SUMMARY)
- **Commits:** 6 task commits + 1 final promotion+SUMMARY commit
- **Files created:** 3 (SUMMARY.md, p1.ks07.bare.log, p1.ks07.full.log)
- **Files modified:** 6 (2 source, 2 test, 1 config, 1 PROMOTION-NOTES)
- **Tests added:** 13 new (7 play_resolver + 6 player_builder)
- **Test suite:** 2122 passed (up from 2109 baseline + 13 new) → 2122 / 2122 green

## Accomplishments

- D-20 positional RZ catch rate dict implemented as flag-gated branches per Cycle 3 D-45 (legacy 0.92 scalar preserved for the flag-off A/B Arm A; new positional dict is the flag-on Arm B and the production default after promotion)
- 13 new TDD tests cover both flag states for both call sites; all pass
- A/B validation completed with both bare and full-stack arms; results recorded as ledger entries `p1.ks07.bare` (#94) and `p1.ks07.full` (#95)
- PROMOTION decision: full hard floor PASSES (Δ rank_corr -0.0012, Δ weekly_mae +0.003); primary-target WR/TE receiving_yards non-regressive (Δ ≈ 0 across most seasons); success criterion #3 (RB rush_yards Δ ≥ 0) met across all 3 seasons
- Flag default flipped from `false` to `true` in `config/defaults.yaml` — production simulator now applies the per-position RZ catch rate modifiers
- Bare-mode QB pass_yards regression (informational only under relaxed gate) diagnosed in PROMOTION-NOTES as a cross-stat interaction of the RB 0.85 rate driving more RZ checkdown incompletions in the absence of compensating engines — not a defect in the KS-07 mechanism
- Pre-existing `test_rz_catch_rate_fallback_below_threshold` (which hardcoded 0.92 for the TE TK87) updated to read the live flag and look up the position-aware modifier, so the test stays correct under both flag states (Rule 1 auto-fix)
- 1,200+ test budget intact and growing (2122 passing); no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 RED:** `96dc664` — `test(01-06): add failing tests for KS-07 positional RZ_CATCH_RATE_MODIFIERS`
2. **Task 1 GREEN:** `f25b63b` — `feat(01-06): KS-07 positional RZ_CATCH_RATE_MODIFIERS dict in play_resolver.py per D-20`
3. **Task 1 doc:** `3a8bc7d` — `docs(01-06): trim KS-07 docstring duplication so literal grep returns 1`
4. **Task 2 RED:** `9906c35` — `test(01-06): add failing tests for KS-07 positional RZ modifier in player_builder`
5. **Task 2 GREEN:** `68cd753` — `feat(01-06): KS-07 player_builder.py uses positional RZ_CATCH_RATE_MODIFIERS per D-20`
6. **Task 3 ledger:** `d39d862` — `chore(01-06): record KS-07 A/B ledger entries (p1.ks07.{bare,full})`
7. **Task 4 promotion + SUMMARY:** (this commit) — `feat(01-06): KS-07 PROMOTED — positional RZ catch rate (WR 0.92, TE 0.95, RB 0.85)`

## Files Created/Modified

### Source

- `src/fantasy_sim/engine/play_resolver.py` — Adds `_KS07_POSITIONAL_RZ_CATCH_RATE` flag (read at module load via `get_phase1_ks_flags()`); declares `RZ_CATCH_RATE_MODIFIERS: dict[str, float] = {"WR": 0.92, "TE": 0.95, "RB": 0.85}` with literal canonical defaults; reads any `phase1_ks_flags.ks07_positional_rz_catch_rate.rates.<POS>` config overrides and applies them on top of the literal defaults; declares `RZ_CATCH_RATE_MODIFIER = RZ_CATCH_RATE_MODIFIERS["WR"]` for backward compat (legacy callers + flag-off branch); inside `_resolve_pass`, when `effective_catch_rate <= 0` and `receiver.outcomes.catch_rate > 0` (the per-play fallback branch), looks up `receiver.position` in the dict when flag-on (with WR fallback for unknown positions) or uses the legacy scalar when flag-off.
- `src/fantasy_sim/data/player_builder.py` — Updates the `play_resolver` import to bring in both `RZ_CATCH_RATE_MODIFIERS` and the legacy scalar `RZ_CATCH_RATE_MODIFIER`; inside `_assemble_models`, when `rs["rz_targets"] < MIN_RZ_TARGETS` (the per-player fallback branch at the per-roster `position` row), reads `_pr._KS07_POSITIONAL_RZ_CATCH_RATE` lazily (so test monkeypatch on the live module applies) and either looks up the position-aware modifier (flag-on) or uses the legacy scalar (flag-off); applies the resulting modifier to `outcomes.catch_rate` to produce `outcomes.red_zone_catch_rate`.

### Tests

- `tests/test_engine/test_play_resolver.py` — Adds 7 KS-07 tests at end of file:
  - `test_ks07_rz_catch_rate_modifiers_dict` — literal dict contents per D-20
  - `test_ks07_backward_compat_scalar_unchanged` — `RZ_CATCH_RATE_MODIFIER == RZ_CATCH_RATE_MODIFIERS["WR"] == 0.92`
  - `test_ks07_flag_on_te_uses_higher_rate` — behavioural: 4000-trial RZ pass with TE receiver, flag-on, observed completion rate centers on 0.95
  - `test_ks07_flag_on_rb_uses_lower_rate` — behavioural: same with RB receiver, observed rate centers on 0.85
  - `test_ks07_flag_on_wr_unchanged_from_legacy` — behavioural: WR receiver, observed rate centers on 0.92 (no behavior change)
  - `test_ks07_flag_off_te_uses_legacy_scalar` — behavioural: TE receiver under flag-off uses 0.92 (Arm A bit-for-bit parity)
  - `test_ks07_flag_off_rb_uses_legacy_scalar` — behavioural: same for RB under flag-off
  - Two helpers: `_make_ks07_roster(position)` (single-receiver roster with `red_zone_catch_rate=0.0` to force the fallback branch) and `_measure_rz_catch_rate(roster)` (4000-trial RZ pass measurement loop)
- `tests/test_data/test_player_builder.py` — Adds `TestKs07PositionalRzCatchRateFallback` class with 6 tests (all using `monkeypatch.setattr(pr, "_KS07_POSITIONAL_RZ_CATCH_RATE", True/False)`):
  - `test_ks07_player_builder_te_uses_positional_modifier_when_flag_on` (TE, expect 0.5 * 0.95 fallback)
  - `test_ks07_player_builder_rb_uses_positional_modifier_when_flag_on` (RB, expect 0.5 * 0.85)
  - `test_ks07_player_builder_wr_unchanged_when_flag_on` (WR, expect 0.5 * 0.92)
  - `test_ks07_player_builder_te_uses_legacy_scalar_when_flag_off` (TE under flag-off, expect 0.5 * 0.92)
  - `test_ks07_player_builder_rb_uses_legacy_scalar_when_flag_off` (RB under flag-off, expect 0.5 * 0.92)
  - `test_ks07_player_builder_modifier_lookup_uses_position_string` (smoke test asserting dict keys contain WR/TE/RB and the lookup uses the position string from roster)
  - Two helpers: `_make_pbp_for_position(player_id)` (10 outside-RZ targets — 5 catches, 5 incompletions — so catch_rate=0.5 and rz_targets=0 forces the fallback branch) and `_make_roster(player_id, position)` (single-skill-position roster with QB)
  - Updates pre-existing `test_rz_catch_rate_fallback_below_threshold` to read the live `_KS07_POSITIONAL_RZ_CATCH_RATE` flag and look up the position-aware modifier dynamically (TK87 is a TE per `tests/conftest.py:81` — under flag-on uses 0.95, under flag-off uses 0.92)

### Config

- `config/defaults.yaml` — `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled: false → true`. Comment updated to record the PROMOTED decision and the relaxed-gate result summary.

### Planning artifacts

- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` — New `## KS-07` section (148 lines) with full ledger evaluation, primary-target detail (per-season per-stat KS for WR/TE recv, RB rush, QB pass), mechanism diagnosis of the bare-mode QB pass_yards regression (RB checkdown incompletions in the RZ), and PROMOTED decision rationale.
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.bare.log` — Bare-isolation A/B run output (~12 KB, ~1 min wall — Arm A loaded from warm bare cache, only Arm B simulated).
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.full.log` — Full-stack overlay A/B run output (~30 KB, ~30 min wall).

## Decisions Made

### Promotion State: PROMOTED

Per the relaxed full-stack-only gate established mid-phase 2026-04-26 (PROMOTION-NOTES.md `## Gate Relaxation Decision`):

| Gate | Threshold | KS-07 result | Pass? |
|------|-----------|--------------|-------|
| Full Δ rank_corr | ≥ -0.005 | -0.0012 | ✓ |
| Full Δ weekly_mae | ≤ +0.05 | +0.003 | ✓ |
| Full Δ fpts_ks | (none, observational) | +0.000 | (n/a) |
| D-30 primary-target non-regression (WR recv_yds) | flat or improved | WR Δ ≈ 0 (3 seasons, all flat) | ✓ |
| D-30 primary-target non-regression (TE recv_yds) | flat or improved | TE Δ flat in 2 of 3 seasons (+0.01 in 2023 only) | ✓ |
| Plan success criterion #3 (RB rush_yards Δ ≥ 0) | non-negative | +0.00 / +0.01 / -0.00 (all non-negative) | ✓ |
| Bare Δ rank_corr (informational) | ≥ -0.005 | +0.0013 | ✓ |
| Bare Δ weekly_mae (informational) | ≤ +0.05 | +0.064 | INFORMATIONAL FAIL — see PROMOTION-NOTES diagnosis |

KS-07 is the SECOND plan in Phase 1 to clear the relaxed full-stack hard floor cleanly with the new code path active (KS-06 was the first). The bare-mode regression is diagnosed as the RB-modifier-driven increase in RZ checkdown incompletions in the absence of compensating engines — not a defect in the positional-rate mechanism.

### Action

Flipped `phase1_ks_flags.ks07_positional_rz_catch_rate.enabled: false → true` in `config/defaults.yaml`. Production simulator now applies the per-position RZ catch rate modifiers by default (WR=0.92 unchanged, TE=0.95 up from 0.92, RB=0.85 down from 0.92).

### Mechanism Diagnosis (Bare-Mode QB pass_yards Regression)

Bare-mode QB pass_yards Arm B mean drops by ~5 yd/g vs Arm A, and KS deteriorates by +0.07 to +0.09 across all 3 seasons. The mechanism:

- **TE 0.95 (was 0.92):** more TE catches in the RZ. Per-receiver effect: small. Net QB effect: small (TE catches are a subset of total RZ targets).
- **RB 0.85 (was 0.92):** RB checkdown completions in the RZ drop from ~92% to ~85%. Each missed checkdown is an incompletion (yards=0, clock_runoff=5s vs 30s). Net QB effect: more incompletions per RZ pass attempt, dragging the QB's pass_yards distribution down by ~5 yd/g per game in bare mode.
- **WR 0.92 (unchanged):** baseline behavior preserved.

In bare mode the engines that normally smooth distributional shifts (tier_engine, props, ensemble post-sim layers) are all off, so the per-play yard delta from RB checkdown incompletions propagates straight through to the QB pass_yards aggregate. In full mode (`p1.ks07.full`), the active engines absorb the per-play delta cleanly — full QB pass_yards Δ is -0.01/+0.00/+0.00, and weekly MAE moves only +0.003.

This is the **same bare-mode unmasking pattern** documented in PROMOTION-NOTES `## KS-04`, `## KS-03`, `## KS-05`, `## KS-06` and codified in the `## Gate Relaxation Decision`. The bug fix is correct; the bare gate is structurally noisy on bug-fix work; full-stack hard floor is the operative gate going forward.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing test hardcoded legacy 0.92 for TE player**

- **Found during:** Task 4 (after flipping flag default to `true` in `config/defaults.yaml`)
- **Issue:** `tests/test_data/test_player_builder.py::TestRedZoneCatchRate::test_rz_catch_rate_fallback_below_threshold` asserted `tk.outcomes.red_zone_catch_rate == pytest.approx(tk.outcomes.catch_rate * 0.92, abs=0.01)` for TK87. TK87 is a TE per `tests/conftest.py:81`. Flipping the flag default to `true` made TK87 use 0.95 (the new TE rate), breaking the assertion.
- **Fix:** Updated the assertion to read the live `_KS07_POSITIONAL_RZ_CATCH_RATE` flag and look up the position-aware modifier dynamically (flag-on → use `RZ_CATCH_RATE_MODIFIERS.get(tk.position, MODIFIERS["WR"])`; flag-off → use `RZ_CATCH_RATE_MODIFIER`). Test now passes under both flag states.
- **Files modified:** tests/test_data/test_player_builder.py
- **Verification:** Full test suite green (2122 passing). The 4 rookie archetype tests at lines 619-635 were intentionally NOT updated because `rookie_builder.py` was NOT touched per plan scope and continues to use the legacy 0.92 scalar.
- **Committed in:** Task 4 promotion commit (this commit)

**2. [Rule 2 - Missing Critical] Doc-string trim to satisfy literal grep AC**

- **Found during:** Task 1 GREEN (post-implementation acceptance check)
- **Issue:** The plan acceptance criterion `grep -c '"WR": 0.92' src/fantasy_sim/engine/play_resolver.py` literally requires return value 1 (the dict literal definition). My initial GREEN commit included an explanatory comment that ALSO contained the literal `{"WR": 0.92, "TE": 0.95, "RB": 0.85}`, inflating the grep count to 2 for each per-position literal.
- **Fix:** Trimmed the explanatory comment to `\`RZ_CATCH_RATE_MODIFIERS\` (defined below)` so the literal text appears exactly once (in the canonical dict definition). Doc-only change; behavior unchanged.
- **Files modified:** src/fantasy_sim/engine/play_resolver.py
- **Verification:** All three `grep -c '"WR": 0.92'`, `'"TE": 0.95'`, `'"RB": 0.85'` now return 1.
- **Committed in:** `3a8bc7d` (separate doc commit between Task 1 GREEN and Task 2 RED)

**3. [Discretion] PROMOTED outcome via D-30 small-gain non-regression bar (under relaxed gate)**

- **Found during:** Task 4 promotion decision
- **Issue:** Plan 06 was originally drafted assuming the strict D-31 hard floor on BOTH ledger entries (the pre-relaxation rule). Under that rule, KS-07 would have been BLOCKED on bare weekly_mae +0.064 > +0.05. But the gate was relaxed mid-phase (PROMOTION-NOTES `## Gate Relaxation Decision`, established after KS-04/03/05 BLOCKED) to full-stack hard floor only.
- **Fix:** Applied the relaxed gate per the documented mid-phase decision. KS-07 passes full-stack hard floor (Δ rank_corr -0.0012, Δ weekly_mae +0.003) AND meets D-30 small-gain primary-target non-regression bar (WR Δ ≈ 0 across all 3 seasons; TE flat in 2 of 3 with one +0.01; RB rush_yards Δ ≥ 0 across all 3 seasons per success criterion #3). Promoted.
- **Files modified:** config/defaults.yaml (flag default false → true), PROMOTION-NOTES.md (## KS-07 section), tests/test_data/test_player_builder.py (Rule 1 fix above)
- **Verification:** PROMOTION-NOTES `## KS-07` section documents the full evaluation; ledger entries `p1.ks07.bare` (#94) and `p1.ks07.full` (#95) preserve the raw data.
- **Committed in:** Task 4 promotion commit (this commit)

**4. [Out-of-scope, deferred] rookie_builder.py NOT updated**

- **Found during:** Task 1 (initial scope review)
- **Issue:** `src/fantasy_sim/data/rookie_builder.py` lines 96 and 103 also use `RZ_CATCH_RATE_MODIFIER` to compute rookie archetype `red_zone_catch_rate = archetype["catch_rate"] * RZ_CATCH_RATE_MODIFIER`. Logically this should also become position-aware (rookie TEs should use 0.95, rookie RBs should use 0.85). But the plan must_haves frontmatter explicitly scopes KS-07 to `play_resolver.py:319` and `player_builder.py:549` — rookie_builder.py is NOT in scope.
- **Fix:** Left rookie_builder.py untouched. Backward-compat scalar `RZ_CATCH_RATE_MODIFIER = RZ_CATCH_RATE_MODIFIERS["WR"]` (= 0.92) preserved so the rookie builder continues to use 0.92 for all rookie archetypes. All 4 rookie archetype tests at `test_player_builder.py:619-635` still pass.
- **Files modified:** None
- **Verification:** `uv run pytest tests/test_data/test_player_builder.py::TestRookieArchetypeDefaults -v` shows all 4 tests pass.
- **Committed in:** N/A (no change). Tracked as a deferred enhancement: extending positional rates to rookie archetypes is a small follow-up that could ship in a later cleanup commit.

---

**Total deviations:** 4 — 1 Rule 1 test fix-up (broken-by-this-plan; consistent with prior plans' patterns), 1 Rule 2 doc-string trim (grep AC literal), 1 promotion under relaxed gate (discretion per established mid-phase decision), 1 explicitly out-of-scope item documented for follow-up.
**Impact on plan:** All deviations consistent with Cycle 3 D-45 design intent and the gate-relaxation decision documented in PROMOTION-NOTES. No scope creep beyond the explicit must_haves frontmatter. The literal acceptance grep checks are met.

## Issues Encountered

- **Pre-existing test broken by flag-default flip (Task 4):** see Deviation #1 above. Single test (`test_rz_catch_rate_fallback_below_threshold`) hardcoded the legacy 0.92 modifier for a TE player. Updated to read the live flag and look up the position-aware modifier dynamically.
- **Doc-string literal duplication (Task 1):** see Deviation #2 above. Initial comment included a copy of the dict literal which inflated the AC grep count. Trimmed in a follow-up doc commit.
- **Bare-mode QB pass_yards regression (Task 3):** see Mechanism Diagnosis above. Diagnosed as RB-modifier-driven increase in RZ checkdown incompletions; informational only under the relaxed gate.

## User Setup Required

None — no external service configuration required. Production behavior changes per PROMOTION (TE players now have 0.95 RZ catch rate fallback, RB players now have 0.85 RZ catch rate fallback, WR unchanged at 0.92). No restart, no migration, no key rotation needed.

## Next Phase Readiness

- KS-07 is **delivered and PROMOTED** per REQUIREMENTS.md: implemented + tested + ledgered + promotion decision documented + flag default flipped + production behavior updated.
- KS-15 (Plan 07), KS-29 (Plan 08), KS-32 (Plan 10) are all unblocked and operate on different mechanisms.
- All future per-KS A/Bs in this phase will have the KS-07-promoted behavior in their `defaults` baseline (Arm A for full A/B, Arm B for bare A/B per the bare_config_dict pattern).
- Plan 11 aggregate validation (Wave 7) will compare `p1.aggregate.full` Arm B against `phase0.baseline.full` Arm B, and the Δ will include the KS-07 PROMOTED change (alongside KS-01 SHIPPED-NO-OP, KS-03/04/05 RETROACTIVELY PROMOTED, KS-06 PROMOTED, KS-21 PROMOTED for the data-acquisition portion).
- Phase 1 progress: 6 PROMOTED (KS-21, KS-03, KS-04, KS-05, KS-06, KS-07) + 1 SHIPPED-NO-OP (KS-01) + 0 BLOCKED. Remaining: KS-15, KS-29, KS-32, then aggregate validation.

---
*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Plan: 06*
*Completed: 2026-04-26*

## Self-Check: PASSED

Files verified present:
- src/fantasy_sim/engine/play_resolver.py (modified)
- src/fantasy_sim/data/player_builder.py (modified)
- tests/test_engine/test_play_resolver.py (modified)
- tests/test_data/test_player_builder.py (modified)
- config/defaults.yaml (modified)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-06-SUMMARY.md (created)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (modified)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.bare.log (created)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks07.full.log (created)

Commits verified present in git log:
- 96dc664 (Task 1 RED — test)
- f25b63b (Task 1 GREEN — feat)
- 3a8bc7d (Task 1 doc — trim docstring duplication)
- 9906c35 (Task 2 RED — test)
- 68cd753 (Task 2 GREEN — feat)
- d39d862 (Task 3 — chore: ledger)
- (Task 4 promotion + SUMMARY commit will be the final commit of this plan)
