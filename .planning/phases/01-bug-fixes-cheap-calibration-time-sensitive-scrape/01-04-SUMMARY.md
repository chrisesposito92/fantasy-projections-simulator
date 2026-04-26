---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 04
subsystem: data
tags: [props, vegas, ks05, bug-fix, feature-flag, ab-validation, blocked]

# Dependency graph
requires:
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: "Plan 00 phase1_ks_flags scaffolding (ks05_props_recv_yds_fix flag + get_phase1_ks_flags shim) and bare-isolation A/B harness (--arm-b-base bare)"
provides:
  - "src/fantasy_sim/data/vegas/props_engine.py: D-17/D-18 bug-fix code path gated behind phase1_ks_flags.ks05_props_recv_yds_fix.enabled (default false). Flag-on path uses _DEFAULT_TEAM_PASS_YDS = 240.0 + corrected _apply_recv_yds magnitude formula. Flag-off path keeps legacy 230.0 + buggy magnitude — production bit-for-bit identical to pre-Phase-1."
  - "tests/test_data/test_vegas/test_props_engine.py: 6 new TestKs05PropsEngineFixes tests covering both flag states + edge cases."
  - "PROMOTION-NOTES.md ## KS-05 section: full ledger evaluation, mechanism diagnosis (props:none discovery), and BLOCKED-via-flag-rollback decision rationale."
affects:
  - "Phase 4 KS-21 OddsApiCdfLoader integration: when alt-line CDF data flows through props_engine, the KS-05 flag should be re-evaluated against the new data path. The fix is correct math — only the validation context (no historical PFF props parquet) prevented promotion in Phase 1."
  - "Future per-team rolling-mean plumbing (D-18 sub-fix 3): when pipeline exposes per-team rolling pass yards, the proxy `target_share * 32.0 * catch_rate` should be replaced with the real signal."

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level flag-gated code paths via get_phase1_ks_flags() + importlib.reload pattern in tests (mirrors KS-01/KS-04/KS-03 conventions)."

key-files:
  created: []
  modified:
    - "src/fantasy_sim/data/vegas/props_engine.py: +38 lines flag-gated KS-05 fix"
    - "tests/test_data/test_vegas/test_props_engine.py: +182 lines (6 new tests under TestKs05PropsEngineFixes)"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md: +156 lines KS-05 section"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.bare.log: new (18.3 KB)"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.full.log: new (37.2 KB)"

key-decisions:
  - "BLOCKED via flag-rollback per Cycle 3 D-45 (same precedent as KS-04 / KS-03): flag stays false in defaults.yaml; production behavior unchanged."
  - "Bare-isolation hard-floor failure (+0.154 weekly_mae) is collateral from required `--set vegas.enabled=true --set vegas.props.enabled=true` activation per D-44 bare_config_dict pattern, NOT from KS-05's logic — both A/B runs report `props:none` (no historical PFF props parquet for 2022/2023/2024 per forward-only PFF endpoint contract)."
  - "Full-stack overlay passes hard floor (Δ rank_corr +0.0001, Δ weekly_mae -0.004) but shows no KS movement on WR/TE receiving_yards primary targets because the props_engine never fires (no parquet)."
  - "D-18 sub-fix 3 (per-team rolling mean from pipeline) deferred per discretion + RESEARCH.md Pitfall 4; v1 proxy `target_share * 32.0 * catch_rate` ships in the flag-on path."

patterns-established:
  - "Test-after acceptable per D-34 for KS-05: existing test suite + 6 new dedicated unit tests cover the changed branches; no need for new TDD-RED cycle when the bug fix is one-line magnitude correction."
  - "Module-import-time flag read with importlib.reload + unittest.mock.patch in tests: flag is read once at module load, so test isolation requires reloading the module after each patch context exits (the flag-off-by-default state is restored automatically)."

requirements-completed: [KS-05]

# Metrics
duration: 27min
completed: 2026-04-26
---

# Phase 1 Plan 04: KS-05 Props Engine Bug Fixes Summary

**Two D-17/D-18 bug fixes (`_DEFAULT_TEAM_PASS_YDS = 230 → 240` constant and `_apply_recv_yds` magnitude bug) shipped flag-gated; BLOCKED at promotion via Cycle 3 D-45 flag-rollback because bare-isolation A/B fails hard floor on collateral `vegas.enabled` activation while full-stack A/B can't measure the fix (no historical PFF props parquet — `props:none` in both runs).**

## Performance

- **Duration:** 27 min
- **Started:** 2026-04-26T18:16:23Z
- **Completed:** 2026-04-26T18:44:03Z
- **Tasks:** 3 implementation tasks + 1 promotion-state task = 4 task commits + 1 final SUMMARY commit
- **Files modified:** 5 (1 source, 1 test, 1 PROMOTION-NOTES, 2 ledger logs)

## Accomplishments

- Two real bugs identified by HYPOTHESES.md KS-05 are correctly fixed in `src/fantasy_sim/data/vegas/props_engine.py`:
  1. `_DEFAULT_TEAM_PASS_YDS` flag-on default = 240.0 (matches NFL ~240 yd/team/game; was 230.0)
  2. `_apply_recv_yds` historical_season_yds = `dist_mean * catches_per_game * games_played` (was `dist_mean * games_played` — treating per-catch yards as per-game yards, off by ~3-7×)
- v1 proxy for `catches_per_game` plumbed via new module constant `_PROXY_TEAM_TARGETS_PER_GAME = 32.0` (per RESEARCH.md Pitfall 4)
- 6 new unit tests under `TestKs05PropsEngineFixes` covering both flag states, edge cases, and a regression test that documents the legacy buggy shift magnitude
- Full A/B validation completed: both `p1.ks05.bare` (#90) and `p1.ks05.full` (#91) ledger entries pinned with full diagnostic detail
- Mechanism diagnosis (`props:none` discovery) documented in PROMOTION-NOTES.md `## KS-05` section — explains why neither A/B can validate the fix in the current data state and what conditions would unblock re-evaluation
- All 2101 existing tests stay green; flag default false preserves bit-for-bit production parity

## Task Commits

Each task was committed atomically:

1. **Task 1: Patch `_DEFAULT_TEAM_PASS_YDS` and `_apply_recv_yds` magnitude bug** — `237dbbd` (fix)
2. **Task 2: Add KS-05 tests** — `bd199c6` (test)
3. **Task 3: A/B validate KS-05 (bare + full) and record ledger** — `6f4841a` (chore)
4. **Task 4: Promotion-state commit + SUMMARY** — (this commit)

## Files Created/Modified

- `src/fantasy_sim/data/vegas/props_engine.py` — Imports `get_phase1_ks_flags`; reads `phase1_ks_flags.ks05_props_recv_yds_fix.enabled` at module load; branches on flag for `_DEFAULT_TEAM_PASS_YDS` (240.0 flag-on, 230.0 flag-off) and `_apply_recv_yds` historical formula (corrected vs legacy buggy). Adds `_PROXY_TEAM_TARGETS_PER_GAME = 32.0` constant.
- `tests/test_data/test_vegas/test_props_engine.py` — Adds `TestKs05PropsEngineFixes` class with 6 tests:
  - `test_ks05_default_team_pass_yds_flag_on_is_240`
  - `test_ks05_default_team_pass_yds_flag_off_is_230`
  - `test_ks05_proxy_team_targets_per_game_is_32`
  - `test_ks05_apply_recv_yds_uses_catches_per_game_in_historical`
  - `test_ks05_apply_recv_yds_legacy_inflates_historical_by_design`
  - `test_ks05_apply_recv_yds_skips_zero_targets_no_crash`
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` — New `## KS-05` section (156 lines) with full ledger evaluation, mechanism diagnosis, and BLOCKED-via-flag-rollback decision
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.bare.log` — Bare-isolation A/B run output (18.3 KB, 80.5s wall)
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.full.log` — Full-stack overlay A/B run output (37.2 KB, 1185.5s wall)

## Decisions Made

### Promotion State: BLOCKED

Per D-31 hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05 on BOTH ledger entries):

| Entry | Δ rank_corr | Δ weekly_mae | Hard floor? |
|-------|-------------|--------------|-------------|
| p1.ks05.bare (#90) | +0.0014 | **+0.154** | **FAIL** |
| p1.ks05.full (#91) | +0.0001 | -0.004 | PASS |

Per Plan 04 Task 3 literal: "If hard floor fails on either entry → revert Task 1 ... mark `## PLAN BLOCKED`."

### Mechanism Diagnosis (Critical)

Both A/B runs report `props:none Forward-only unless season parquet files exist in ~/.fantasy-sim/pff/props` in the coverage line. PFF player props are current-season-only (per project memory `project_pff_props_endpoint.md`). No 2022/2023/2024 historical parquet exists. The KS-05 `_apply_recv_yds` code path therefore does NOT fire in either A/B — there are no prop rows to consume.

The bare-isolation MAE delta of +0.154 is NOT attributable to KS-05's logic. It is collateral from the required `--set vegas.enabled=true --set vegas.props.enabled=true` activation per D-44 (Cycle-3 `bare_config_dict` correctly disables top-level engine gates per Pattern 7). Top-level `vegas.enabled` activates VEG-01 (ITT pace scaling) and VEG-02 (spread-based pass-rate conditioning) which DO change game environment in bare mode. Same diagnostic pattern as KS-04 (collateral activation masks intended A/B target).

### Action: Flag-Rollback per D-45

Per Cycle 3 D-45 (same precedent as KS-04 PROMOTION-NOTES lines 119-123 and KS-03 lines 224-251): the new code path STAYS in `props_engine.py` (gated behind module-level `_KS05_PROPS_RECV_YDS_FIX = False`), and `phase1_ks_flags.ks05_props_recv_yds_fix.enabled` STAYS at its Plan-00 default of `false` in `config/defaults.yaml`. Production behavior is bit-for-bit identical to pre-Phase-1.

This is functionally equivalent to a literal revert of Task 1 but preserves the experiment, the 6 new unit tests, and the implementation for future re-evaluation. Future unblock conditions:
- Phase 4 `OddsApiCdfLoader` consumes the alt-line market data scraped in Plan 09 → would let props blending fire on historical seasons
- Historical PFF props parquet becomes available (currently forward-only)
- D-18 sub-fix 3 (per-team rolling mean from pipeline) is plumbed through `props_engine.apply()` arguments, replacing the v1 proxy

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Cycle 3 D-45 flag-gating not in original Task 1 acceptance criteria**

- **Found during:** Task 1 (Patch `_DEFAULT_TEAM_PASS_YDS` and `_apply_recv_yds`)
- **Issue:** Plan 04 Task 1 acceptance criteria literal grep checks (`grep -c "_DEFAULT_TEAM_PASS_YDS = 240.0"` returns 1) assume an unconditional flag-flipped-on implementation, but the must_haves frontmatter (per D-45) requires flag-gated coexistence so the per-KS A/B is genuinely two-arm.
- **Fix:** Implemented flag-gated coexistence per D-45: `_DEFAULT_TEAM_PASS_YDS = float(_KS05_FLAGS.get("default_team_pass_yds", 240.0))` when flag-on, else `230.0`. Same for `_apply_recv_yds` magnitude formula. The literal grep check fails but the equivalent flag-gated assertions pass; D-45 takes precedence over the literal acceptance grep per the plan's own must_haves block.
- **Files modified:** src/fantasy_sim/data/vegas/props_engine.py
- **Verification:** Runtime check confirms flag-off path uses 230.0 and flag-on path uses 240.0; 6 new unit tests cover both branches.
- **Committed in:** 237dbbd (Task 1 commit)

**2. [Rule 3 - Blocking] Test-isolation pattern for module-import-time flag read**

- **Found during:** Task 2 (Add tests)
- **Issue:** First-pass test code reloaded the props_engine module INSIDE the patch context, but the `finally` cleanup also ran inside that context, leaving the module stuck in flag-on state and contaminating subsequent tests in the same module.
- **Fix:** Restructured the patch + reload sequence: `with patch(...): importlib.reload(pe_mod)` (reload while patched), then `try: ... finally: importlib.reload(pe_mod)` (reload AFTER patch exits, restoring the flag-off default). This is the canonical pattern for testing module-import-time-flag-read code.
- **Files modified:** tests/test_data/test_vegas/test_props_engine.py
- **Verification:** All 6 KS-05 tests pass; full 2101-test suite stays green.
- **Committed in:** bd199c6 (Task 2 commit)

**3. [Discretion] BLOCKED outcome via D-45 flag-rollback rather than literal revert**

- **Found during:** Task 3 (A/B validation)
- **Issue:** Task 3 literal instruction is "If hard floor fails → revert Task 1's commit". But Cycle 3 D-45 introduced flag-gated rollback as the explicit knob for exactly this situation (per KS-04 / KS-03 precedent in PROMOTION-NOTES).
- **Fix:** Used flag-rollback (flag default stays false in defaults.yaml; new code stays in source for future re-evaluation). Production behavior bit-for-bit identical to pre-Phase-1; experiment preserved for follow-up.
- **Files modified:** None (the flag was already false from Plan 00; no defaults.yaml change required)
- **Verification:** `phase1_ks_flags.ks05_props_recv_yds_fix.enabled: false` in `config/defaults.yaml` (line 17); `_KS05_PROPS_RECV_YDS_FIX = False` at runtime when defaults are loaded.
- **Committed in:** 6f4841a (Task 3 commit, documented in PROMOTION-NOTES)

---

**Total deviations:** 3 — 1 D-45 flag-gating (must_have-driven), 1 test-isolation fix (blocking), 1 D-45 flag-rollback in BLOCKED branch (discretion per established KS-04 / KS-03 precedent)
**Impact on plan:** All deviations consistent with D-45 design intent and the established KS-04 / KS-03 BLOCKED precedent. No scope creep. The literal Task 1 acceptance grep check was superseded by D-45 must_haves; the literal Task 3 revert instruction was superseded by D-45 flag-rollback knob.

## Issues Encountered

- **`props:none` discovery (Task 3 mid-run):** the diagnostic line in both A/B run outputs revealed that PFF player props are forward-only with no historical parquet for 2022/2023/2024. This means neither A/B can directly validate KS-05's logic — the code path never fires. Documented in PROMOTION-NOTES `## KS-05` mechanism diagnosis. Does not block the plan but reframes the BLOCKED outcome as "fix is correct, but cannot be validated in current data state" rather than "fix regresses metrics".
- **Test isolation regression on first attempt (Task 2):** initially used wrong patch+reload ordering; second test run revealed flag-on state leaked into flag-off test. Fixed before commit.

## User Setup Required

None — no external service configuration required. Production behavior unchanged.

## Next Phase Readiness

- KS-05 is **delivered** per REQUIREMENTS.md "delivered" definition (implemented + tested + ledgered + promotion decision documented). Promotion state: BLOCKED.
- KS-15 (Plan 07), KS-06 (Plan 05), KS-07 (Plan 06) — all unblocked. KS-05 doesn't share files with these plans (different mechanisms entirely).
- Phase 4 `OddsApiCdfLoader` integration should treat the KS-05 flag as a re-evaluation candidate when alt-line CDF data flows through `props_engine.apply()`. The math is correct; only the no-historical-data condition is blocking promotion.
- Wave 3 progresses: of {KS-04, KS-03, KS-05}, all three landed BLOCKED-via-flag-rollback. The pattern of "correctness fix exposes bare-mode under-projection that legacy bug was masking" is now documented across three KS plans and is a known phenomenon for Plan 11 aggregate evaluation.

---
*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Plan: 04*
*Completed: 2026-04-26*

## Self-Check: PASSED

Files verified present:
- src/fantasy_sim/data/vegas/props_engine.py (modified)
- tests/test_data/test_vegas/test_props_engine.py (modified)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-04-SUMMARY.md (created)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (modified)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.bare.log (created)
- .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.full.log (created)

Commits verified present in git log:
- 237dbbd (Task 1 — fix)
- bd199c6 (Task 2 — test)
- 6f4841a (Task 3 — chore: ledger)
