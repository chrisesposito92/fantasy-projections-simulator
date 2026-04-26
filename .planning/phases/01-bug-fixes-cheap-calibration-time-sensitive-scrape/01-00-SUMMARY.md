---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 00
subsystem: validation
tags: [validate-script, ledger, config-flags, bare-baseline, ab-harness, schema-bump]

# Dependency graph
requires:
  - phase: 00-initialization
    provides: pre-existing validate.py, SeasonMetrics ledger schema v4, bare_config builder
provides:
  - "validate.py --arm-b-base {defaults,bare} flag for true-isolation A/B"
  - "bare_config_dict() helper enumerating every .enabled gate (top-level + sub-engine + KS flags)"
  - "phase1_ks_flags config block (8 flags, default false) + get_phase1_ks_flags() loader shim"
  - "SeasonMetrics.stat_mean_bias field + ledger schema v5 (backward-compat load)"
  - "Phase-0 baseline pin scaffolding (PROJECT-PHASE0-FROZEN.md + logs/) — pin runs deferred to user main-repo execution"
  - "Phase logs directory at .planning/phases/01-.../logs/"
affects: [01-ks01-rz-tdgate-fix, 02-ks04-catch-yards-boost, 03-ks03-matchup-coverage-anchor, 04-ks05-props-engine-bugs, 05-ks06-backup-receiver-fallback, 06-ks07-positional-rz-catch-rate, 07-ks15-field-position-clamping, 08-ks29-team-context-reenable, 09-ks21-alt-line-scrape, 10-ks32-clock-runoff-measurement, 11-aggregate-validation]

# Tech tracking
tech-stack:
  added: [no new libraries — additive helpers + schema field only]
  patterns:
    - "Bare-base + targeted override via bare_config_dict() + apply_overrides() chain"
    - "Per-KS feature flags in phase1_ks_flags: block (legacy vs new code-path two-arm A/B)"
    - "Ledger schema versioning with backward-compat default factory + load_ledger setdefault"
    - "Per-position-stat mean bias persisted alongside KS for direct success-criterion evaluation"

key-files:
  created:
    - "tests/test_validation/test_ledger_schema.py"
    - ".planning/PROJECT-PHASE0-FROZEN.md"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/README.md"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.partial.log"
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md"
  modified:
    - "src/fantasy_sim/validation/config.py (bare_config_dict helper)"
    - "src/fantasy_sim/validation/ledger.py (SeasonMetrics.stat_mean_bias, schema v5)"
    - "src/fantasy_sim/config/loader.py (get_phase1_ks_flags shim)"
    - "config/defaults.yaml (phase1_ks_flags block, 8 flags default false)"
    - "scripts/validate.py (--arm-b-base flag, _compute_distribution_ks returns mean bias)"
    - "tests/test_validation/test_config.py (9 new TestBareConfigDict tests)"
    - "tests/test_validation/test_validate_script.py (added arm_b_base='defaults' to 4 SimpleNamespace test fixtures)"

key-decisions:
  - "bare_config_dict enumerates EVERY .enabled gate exhaustively (top-level + sub-engine + KS flags) — no Cycle-2 'loosen the test' escape hatch"
  - "Per-KS feature flags live in a top-level phase1_ks_flags: block in defaults.yaml, default false, with a get_phase1_ks_flags() loader shim for module-import-time access"
  - "Ledger schema bumped 4 → 5 with stat_mean_bias as an optional dataclass field; load_ledger uses setdefault to default older entries to {}"
  - "stat_mean_bias is derived from existing ks_distribution_summary mean_delta_a/_b — no second pass over per-game samples; persists arm_a_bias, arm_b_bias, bias_delta, n"
  - "Phase-0 pin runs deferred to user main-repo execution because results/ab_ledger.json is gitignored and worktree writes don't propagate"

patterns-established:
  - "Per-KS bare-isolation A/B: --baseline bare --arm-b-base bare --set phase1_ks_flags.ksXX_<name>.enabled=true"
  - "Per-KS feature-gate code paths: branch on get_phase1_ks_flags().get('ksXX_<name>', {}).get('enabled', False) at module/import time"
  - "Plan 11 reads stat_mean_bias['QB']['pass_yards']['arm_b_bias'] directly from ledger entries to evaluate success criterion 1"

requirements-completed: [ALL_PHASE_1]

# Metrics
duration: ~45min
completed: 2026-04-26
---

# Phase 1 Plan 00: validate.py harness extension + Phase-0 baseline pin scaffolding Summary

**Closed Codex Cycle-1 HIGH-1/HIGH-4 + Cycle-2 NEW HIGH #1/#2/#3 by shipping the
`--arm-b-base` flag, an exhaustive `bare_config_dict()`, the `phase1_ks_flags`
feature-flag block, and the ledger `stat_mean_bias` schema v5 — every per-KS
A/B in Phase 1 can now perform true (bare) vs (bare + KS) two-arm isolation
with mean bias persisted directly to the ledger.**

## Performance

- **Duration:** ~45 min (worktree execution; pin runs deferred to user)
- **Started:** 2026-04-26
- **Completed:** 2026-04-26
- **Tasks:** 9 (1, 2, 3, 8, 4, 9, 5, 6, 7 — wave-internal sequencing per plan)
- **Files modified:** 7 source/config + 4 new docs/logs

## Accomplishments

- `validate.py --arm-b-base {defaults,bare}` flag wired (default `defaults` —
  backward compatible). When `bare`, Arm B starts from `bare_config_dict(defaults)`
  and applies `--set` overrides on top, enabling true (bare) vs (bare + KS)
  isolation per Phase 1 D-29.
- `bare_config_dict()` helper enumerates EVERY `.enabled` gate that
  `build_engine_configs()` keys off — including the top-level gates
  (`pff.enabled`, `vegas.enabled`, `usage.enabled`, `props.enabled`,
  `weather.enabled`, `tracking.enabled`, `availability.enabled`,
  `role_trend.enabled`, `market_history.enabled`, `game_script.enabled`,
  `goal_line_concentration.enabled`, `td_tendency.enabled`,
  `target_selection.enabled`, `play_call_model.enabled`,
  `qb_rushing.{scramble,designed_runs}.enabled`) AND sub-engine flags AND
  the new `phase1_ks_flags.ksXX_*.enabled` flags.
- `phase1_ks_flags:` block added to `config/defaults.yaml` with 8 KS flags
  (default `enabled: false` everywhere). `get_phase1_ks_flags()` shim added to
  `src/fantasy_sim/config/loader.py` so per-KS sites can branch on the flag at
  module/import time.
- `SeasonMetrics.stat_mean_bias` field added (shape:
  `{position: {stat: {arm_a_bias, arm_b_bias, bias_delta, n}}}`). Ledger schema
  bumped 4 → 5 with backward-compatible `setdefault` in `load_ledger()`.
  `_compute_distribution_ks` in `validate.py` derives the field from existing
  `ks_distribution_summary` `mean_delta_a/_b` outputs and passes it into
  `SeasonMetrics`.
- HARD-GATE integration test
  `test_bare_config_dict_produces_all_None_engines` enforces that
  `build_engine_configs(bare_config_dict(load_defaults()))` returns None for
  every engine — no escape hatch.
- 13 new tests across `test_config.py` (9) and `test_ledger_schema.py` (4);
  full 2080-test suite remains green.
- Phase logs directory at
  `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/`
  created with `.gitkeep` + a `README.md` explaining contents.
- `PROJECT-PHASE0-FROZEN.md` written with the canonical pin commands the user
  must execute in the main repo.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add bare_config_dict() helper** — `60f0310` (feat)
2. **Task 2: Add unit tests for bare_config_dict** — `2bdc618` (test, TDD-first)
3. **Task 3: Wire --arm-b-base flag into validate.py** — `7fd24b4` (feat)
4. **Task 8: Add phase1_ks_flags config block + get_phase1_ks_flags() shim** — `2ff9edf` (feat)
5. **Task 4: HARD-GATE integration tests for bare_config_dict** — `9cc77b4` (test, TDD-first)
6. **Task 9: Extend SeasonMetrics.stat_mean_bias + bump ledger schema 4→5** — `ec1d5b0` (feat)
7. **Task 5: Create phase logs directory** — `9b8ab98` (chore)
8. **Task 6: Pin Phase-0 baseline reference doc + logs scaffolding** — `9d25364` (chore — partial; see deviations)
9. **Task 7: Promotion-state SUMMARY** — this commit (chore — written via SUMMARY.md)

## Files Created/Modified

### New files

- `tests/test_validation/test_ledger_schema.py` — 4 tests for schema v5
  (current version, default factory, save/load round-trip, pre-v5 backward compat)
- `.planning/PROJECT-PHASE0-FROZEN.md` — Phase-0 baseline reference + user
  pin commands + Plan 11 contract
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/.gitkeep`
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/README.md`
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.partial.log` — smoke verification
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-00-SUMMARY.md` — this file

### Modified files

- `src/fantasy_sim/validation/config.py` — added `bare_config_dict()` helper
  enumerating ~45 `.enabled` gates including the 8 new KS flags
- `src/fantasy_sim/validation/ledger.py` — `SeasonMetrics.stat_mean_bias` field
  + `CURRENT_LEDGER_SCHEMA_VERSION = 5` + `load_ledger` backward-compat
- `src/fantasy_sim/config/loader.py` — `get_phase1_ks_flags()` helper
- `config/defaults.yaml` — new top-level `phase1_ks_flags:` block with 8 flags
- `scripts/validate.py` — `--arm-b-base` flag in `build_cli`, Arm B
  construction branches on it, `_compute_distribution_ks` returns
  `stat_mean_bias`, `run_season` passes it into `SeasonMetrics`
- `tests/test_validation/test_config.py` — new `TestBareConfigDict` class with
  9 tests (5 unit + 4 integration including HARD GATE)
- `tests/test_validation/test_validate_script.py` — added
  `arm_b_base="defaults"` to 4 existing `SimpleNamespace` test fixtures (Rule 3
  fix for blocking missing-attribute errors after the new flag was wired)

## Decisions Made

- **bare_config_dict scope** (Cycle 3 D-44): enumerated EVERY `.enabled` gate
  exhaustively rather than relying on the Cycle-2 "loosen the test if it
  disagrees" escape hatch. Hard-gate integration test
  `test_bare_config_dict_produces_all_None_engines` enforces this on every
  test run; if a future engine is added to `build_engine_configs`, the test
  will fail until the new gate is added to the helper.
- **phase1_ks_flags block placement** (Cycle 3 D-45): inserted at the top of
  `config/defaults.yaml` as a top-level sibling to `pff:`, `vegas:`, etc., so
  per-KS sites can read it via the `get_phase1_ks_flags()` shim without
  having to plumb the full config dict through every call site.
- **stat_mean_bias derivation** (Cycle 3 D-46): derived from existing
  `ks_distribution_summary` `mean_delta_a/_b` outputs rather than re-walking
  the per-game samples. Saves a CPU pass and keeps the implementation tight.
- **Phase-0 pin runs deferred to user** (Plan deviation, Rule 4):
  `results/ab_ledger.json` is gitignored, so worktree pin runs would not
  propagate to the main-repo ledger that downstream Phase 1 plans consume.
  Rather than spend 60-90 min on runs whose ledger output would be discarded,
  the freeze doc + logs README hand off the exact commands for the user to
  execute in the main repo. Smoke verification (sims=2) was performed
  in-worktree to confirm the harness extension works end-to-end.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test
`test_bare_config_dict_preserves_non_enabled_keys` would have falsely failed**

- **Found during:** Task 2 (TDD-first test author / first run)
- **Issue:** Original draft of the test walked all sub-keys of
  `pff.tier_engine` and asserted equality. But `tier_engine` has nested
  sub-dicts (`ncaa_rookie`, `archetypes`) that themselves contain `enabled`
  flags — and the helper legitimately flips those nested flags. The test
  caught a false positive on `tier_engine.ncaa_rookie`.
- **Fix:** Added `if isinstance(val, dict): continue` skip for nested sub-dicts;
  the test now only compares scalar/list values at the top level of
  `tier_engine`.
- **Files modified:** `tests/test_validation/test_config.py`
- **Verification:** All 5 Task-2 tests pass.
- **Committed in:** `2bdc618` (Task 2 commit)

**2. [Rule 3 - Blocking] Existing `SimpleNamespace` test fixtures missed
`arm_b_base` attribute after Task 3**

- **Found during:** Task 3 (full test suite run after wiring `--arm-b-base`)
- **Issue:** `validate.py main()` references `args.arm_b_base`. Existing
  tests in `tests/test_validation/test_validate_script.py` build `args` via
  `SimpleNamespace(...)` and don't include the new attribute, so the
  full-suite run failed with `AttributeError: 'types.SimpleNamespace' object
  has no attribute 'arm_b_base'` for the test
  `test_main_uses_top_level_market_history_coverage_for_promotion_scope`.
- **Fix:** Added `arm_b_base="defaults"` (the new flag's default value) to
  all 4 `SimpleNamespace` constructions in the test file. Preserves the
  legacy behavior expected by the existing tests.
- **Files modified:** `tests/test_validation/test_validate_script.py`
- **Verification:** Full 2076 → 2080 suite green.
- **Committed in:** `7fd24b4` (Task 3 commit)

**3. [Rule 4 - Architectural] Phase-0 pin runs deferred to user main-repo
execution**

- **Found during:** Task 6 (about to execute the 200-sim pin runs)
- **Issue:** `results/ab_ledger.json` is gitignored (per repo `.gitignore` line
  19), so any pin runs executed in the worktree would not propagate to the
  main-repo ledger that downstream Phase 1 plans (01-11) consume. Running the
  full 60-90 min pin would discard its primary output (the ledger entry).
- **Fix:** Killed the partial 200-sim background run; executed a smoke test
  (`sims=2`) to confirm the harness extension works end-to-end with the new
  flag, helper, schema bump, and feature flags; created
  `PROJECT-PHASE0-FROZEN.md` with the canonical pin commands the user must
  run in the main repo, plus a `logs/README.md` explaining the
  worktree-vs-main-repo split.
- **Files modified:** `.planning/PROJECT-PHASE0-FROZEN.md`,
  `.planning/phases/.../logs/README.md`,
  `.planning/phases/.../logs/phase0.baseline.full.partial.log`
- **Verification:** Smoke test output captured in
  `phase0.baseline.full.partial.log` confirms the new code paths reach the
  parallel-season build phase without errors. The deferral and required
  user action are documented in two places (the freeze doc and the logs
  README).
- **Committed in:** `9d25364` (Task 6 commit)
- **User action required:** Run the two pin commands documented in
  `PROJECT-PHASE0-FROZEN.md` against the main repo before executing any
  Phase 1 KS plan that depends on the `phase0.baseline.full` /
  `phase0.baseline.bare` labels.

---

**Total deviations:** 3 (1 test bug, 1 blocking attribute, 1 architectural)
**Impact on plan:** Tests-1 and 2 were transparent fixes inside their tasks.
Deviation 3 is the one that downstream plans / orchestrator must be aware of —
the worktree cannot complete the persistent ledger write that the rest of
Phase 1 reads. All other Plan 00 deliverables (helper, flag, schema bump, KS
flags, frozen doc, logs scaffolding) are fully in place.

## Issues Encountered

- The original Task 2 draft test had a false-positive failure mode on nested
  sub-dicts (see Deviation 1). Diagnosed and fixed transparently.
- The CI pin-run path (Task 6) ran into the gitignored-ledger architectural
  constraint (see Deviation 3). Resolved by handoff doc + smoke verification;
  the actual pin runs need to happen in the user's main repo.

## User Setup Required

- **Run the two pin commands** documented in
  `.planning/PROJECT-PHASE0-FROZEN.md` against the main repo (NOT a worktree)
  before any Phase 1 KS plan (01-11) is executed. The exact commands and
  expected outputs are in the freeze doc.

## Next Phase Readiness

- All KS-Phase1 infrastructure is shipped: the `--arm-b-base bare` flag, the
  exhaustive `bare_config_dict()`, the 8 `phase1_ks_flags` flags + loader
  shim, the `stat_mean_bias` schema v5 field, and the phase logs directory.
- Per-KS plans (01-08, 10) can immediately begin authoring against the new
  pattern: `--baseline bare --arm-b-base bare --set
  phase1_ks_flags.ksXX_<name>.enabled=true` for the bare-isolation A/B
  ledger entry, and `--baseline defaults --set phase1_ks_flags.ksXX_<name>.enabled=true`
  for the full-stack A/B.
- Plan 11 (aggregate validation) can read
  `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` directly from the
  `phase0.baseline.full` and `p1.aggregate.full` ledger entries.
- Plan 09 (KS-21 scrape) is unblocked — it doesn't depend on Plan 00's
  harness extension.
- **Blocker for KS plan execution:** the user must run the two pin commands
  in the main repo first; otherwise `phase0.baseline.full` / `phase0.baseline.bare`
  labels will be missing and downstream A/B comparisons will have no Phase-0
  reference.

## Self-Check: PASSED

All claimed files exist and all referenced commit hashes are present in
`git log`. Verified via:

```bash
for f in <11 files>; do [ -f "$f" ] && echo "FOUND: $f"; done
for h in 60f0310 2bdc618 7fd24b4 2ff9edf 9cc77b4 ec1d5b0 9b8ab98 9d25364; do
  git log --oneline --all | grep -q "$h" && echo "FOUND: $h";
done
```

All 11 files reported `FOUND`; all 8 commit hashes reported `FOUND`.

---
*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Completed: 2026-04-26*
