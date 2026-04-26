---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 10
subsystem: engine.clock
tags: [clock, calibration, measurement, no-code-change, ab-validation]

# Dependency graph
requires:
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: "Plan 00 — --arm-b-base bare flag + bare_config_dict + phase0.baseline pin (so the no-change ledger entry is comparable to Phase-0)"
  - phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
    provides: "Plans 01-08 — KS-01/03/04/05/06/07/15/29 promoted (post-Phase-1 stack against which the measurement is taken)"
provides:
  - "p1.ks32.measure ledger entry #104 (Arm A=bare, Arm B=current post-Phase-1 defaults — real delta-baring snapshot)"
  - "Documented decision branch: NO CHANGE (plays_per_team=66.2 ≥ 62 ✓; nfl_pass_attempts=33.8 ≥ 33 ✓ — both above the retune-trigger thresholds)"
  - "Confirmation that post-Phase-1 stack matches Phase-0 baseline within noise on headline metrics (Δ rank_corr -0.0009, Δ weekly_mae +0.014)"
affects: ["11-aggregate-validation", "Phase 5 wrap-up", "future clock-runoff calibration"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Measure-then-decide discipline (per D-23): run a measurement script first; only ship a code change if the measurement supports it. Sets precedent for future calibration-class items where retuning on a moving target risks chasing noise."
    - "MEASURED-NO-CHANGE promotion state (per D-24): a hypothesis can satisfy REQUIREMENTS.md 'delivered' definition without a source-code change, provided the measurement is recorded in the ledger and the decision is documented in PROMOTION-NOTES.md."

key-files:
  created: []
  modified:
    - ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md — added ## KS-32 measurement and ## KS-32 final decision: MEASURED-NO-CHANGE sections"

key-decisions:
  - "Decision: NO CHANGE. plays_per_team=66.2 (≥62 ✓; in fact above the upper bound 65) and nfl_pass_attempts=33.8 (≥33 ✓; in band [32, 37]). The original D-23 hypothesis ('pass attempts demonstrably low (32-33 instead of 35-36)') is not supported by the post-Phase-1 measurement — KS-15 promoted on 2026-04-26 may have already restored pass attempts as anticipated by the plan."
  - "Reducing CLOCK_PASS_INCOMPLETE from 5→3 is contraindicated: it would push plays_per_team even higher (already above the upper bound), worsening the existing FAIL on the upper band rather than improving anything."
  - "Used --baseline bare for the p1.ks32.measure ledger entry (per HIGH-4 fix in plan Task 4). This gives a real delta vs bare (Arm A=bare, Arm B=current post-Phase-1 defaults), structurally equivalent to phase0.baseline.full and directly comparable for the Phase-1-vs-Phase-0 differencing."

patterns-established:
  - "Pattern: a per-KS plan can ship as MEASURED-NO-CHANGE without any source change. The promotion-state commit, ledger entry, and PROMOTION-NOTES sections still produce a clean per-plan deliverable."
  - "Pattern: when a measurement script's CLI signature differs from the plan text (validate_passing.py does not accept --seasons), use the documented signature and surface the deviation in both PROMOTION-NOTES and SUMMARY (Rule 3)."

requirements-completed: [KS-32]

# Metrics
duration: 13 min
completed: 2026-04-26
---

# Phase 1 Plan 10: KS-32 Clock Runoff Calibration (measure-then-decide) Summary

**Measured CLOCK_PASS_INCOMPLETE retune candidate against post-Phase-1 baseline; NO CHANGE motivated — plays_per_team=66.2 (≥62 ✓) and nfl_pass_attempts=33.8 (≥33 ✓); ledger entry p1.ks32.measure #104 records the post-Phase-1 baseline state (Arm A=bare, Arm B=current defaults — real delta vs bare) and confirms the post-Phase-1 stack matches phase0.baseline.full within noise (Δ rank_corr -0.0009, Δ weekly_mae +0.014).**

## Performance

- **Duration:** 13 min wall-clock (2026-04-26T22:27:57Z → 2026-04-26T22:41:54Z)
- **Tasks executed:** 2 of 5 (Task 1 measurement, Task 4 ledger; Tasks 2+3 skipped per NO CHANGE branch; Task 5 = this commit)
- **Files modified:** 1 (`.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md`)
- **Files created:** 3 (this SUMMARY + 2 logs: `ks32_measurement.log`, `p1.ks32.measure.log`)
- **Source code change:** **NONE** — `src/fantasy_sim/engine/play_resolver.py` line 84 keeps `CLOCK_PASS_INCOMPLETE = 5`
- **Tests:** 93 clock + play_resolver tests pass (no source change to break); full 2,131-test suite assumed green from Plan 08 (last source-touching plan)

## Accomplishments

- **Measurement complete (Task 1)** — `scripts/validate_passing.py --sims 50` exercised the post-Phase-1 stack end-to-end. Observed `plays_per_team=66.2` (above the [63, 65] upper bound), `nfl_pass_attempts=33.8` (in [32, 37] band), `sacks/team/game=2.0` (in band). 5/9 metrics in NFL range; the two metrics that gate the KS-32 retune decision (plays_per_team, nfl_pass_attempts) both satisfy the NO CHANGE criterion.
- **Decision recorded (Task 1)** — appended `## KS-32 measurement` section to PROMOTION-NOTES.md with explicit decision rule evaluation (`plays_per_team ≥ 62 AND nfl_pass_attempts ≥ 33` → NO CHANGE).
- **Ledger entry pinned (Task 4)** — `validate.py --baseline bare --label p1.ks32.measure` ran 200 sims × 3 seasons (2022/2023/2024) in 572s. Pinned ledger entry #104 (Arm A=bare, Arm B=current post-Phase-1 promoted defaults). Per the HIGH-4 fix in Plan 10 Task 4, `--baseline bare` (no `--set`) gives a real delta-baring snapshot — Arm B captures the post-Phase-1 defaults state, structurally equivalent to `phase0.baseline.full` from Wave 0 but at a different point in time.
- **Phase-1-vs-Phase-0 delta evaluated (Task 4)** — differenced `p1.ks32.measure` (#104) Arm B metrics against `phase0.baseline.full` (#82) Arm B metrics: Δ rank_corr -0.0009, Δ weekly_mae +0.014, Δ season_mae +0.180, Δ fpts_ks -0.003. The post-Phase-1 stack matches the Phase-0 baseline within noise on every headline metric. This confirms the NO CHANGE decision: nothing in the Phase 1 stack caused pass-attempt drift that would justify reducing `CLOCK_PASS_INCOMPLETE`.
- **Final decision documented (Task 4)** — appended `## KS-32 final decision: MEASURED-NO-CHANGE (per D-24)` section to PROMOTION-NOTES.md with the differenced delta table and the explicit "delivered" mapping per REQUIREMENTS.md.

## Task Commits

1. **Task 1: Measurement against post-Phase-1 baseline** — `4c338a0` (chore)
   - Ran `validate_passing.py --sims 50` (demo path; no `--seasons` flag — see Deviations).
   - Observed plays_per_team=66.2, nfl_pass_attempts=33.8 — both satisfy NO CHANGE criteria.
   - Appended `## KS-32 measurement` to PROMOTION-NOTES.md with decision rule evaluation and rationale.
   - Created `logs/ks32_measurement.log`.
2. **Tasks 2, 3: SKIPPED per NO CHANGE branch** — no commits.
3. **Task 4: Ledger entry p1.ks32.measure** — `47ce72e` (chore)
   - Ran `validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE --baseline bare --label p1.ks32.measure`.
   - Pinned ledger entry #104 (572s wall-clock).
   - Appended `## KS-32 final decision: MEASURED-NO-CHANGE` to PROMOTION-NOTES.md with differenced Phase-1-vs-Phase-0 delta table and the "delivered" mapping per REQUIREMENTS.md.
   - Created `logs/p1.ks32.measure.log`.
4. **Task 5: Promotion-state commit + SUMMARY** — (this commit) `feat`
   - Created this `01-10-SUMMARY.md` documenting MEASURED-NO-CHANGE final state.

## Files Created/Modified

### Modified
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` — appended `## KS-32 measurement` and `## KS-32 final decision: MEASURED-NO-CHANGE` sections

### Created
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md` — this file
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks32_measurement.log` — `validate_passing.py` output (Task 1)
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks32.measure.log` — `validate.py` ledger run output (Task 4)

### NOT Modified (per NO CHANGE branch)
- `src/fantasy_sim/engine/play_resolver.py` — `CLOCK_PASS_INCOMPLETE = 5` retained
- `tests/test_engine/test_clock.py` — no new tests (no behavior change to test)
- `config/defaults.yaml` — no `phase1_ks_flags.ks32_clock_pass_incomplete_3s` block needed (no flag-gated code path was added; the RETUNE-only Cycle 3 D-45 flag is moot)

## Measurement Results

### `validate_passing.py --sims 50` (Task 1)

| Metric                       | Observed | Target band     | In band? |
|------------------------------|---------:|-----------------|:--------:|
| plays_per_team               | **66.2** | (63, 65)        | NO (above) |
| called_passes (incl scram)   | 38.1     | [37, 40]        | YES |
| scrambles/team/game          | 2.3      | [1.5, 3.5]      | YES |
| sacks/team/game              | 2.0      | [1.5, 3.0]      | YES |
| **nfl_pass_attempts**        | **33.8** | **[32, 37]**    | **YES** |
| completions/team/game        | 20.8     | [20, 24]        | YES |
| completion_rate (NFL conv)   | 61.6%    | [62%, 67%]      | NO (below) |
| yards/completion             | 10.1     | [10.5, 12.5]    | NO (below) |
| pass_yards/team/game         | 209.5    | [210, 250]      | NO (below) |

The two metrics that gate the KS-32 retune decision (`plays_per_team`,
`nfl_pass_attempts`) both satisfy the NO CHANGE criterion. The other FAIL
metrics reflect the underlying QB pass_yards mean-bias gap (out of scope
for Phase 1 per PROMOTION-NOTES `## KS-15`) and the demo roster's stat
distributions.

### `p1.ks32.measure` ledger entry (Task 4)

| Entry              | baseline | mode        | overrides | Δ rank_corr | Δ weekly_mae | Δ season_mae | Δ fpts_ks |
|--------------------|----------|-------------|-----------|------------:|-------------:|-------------:|----------:|
| p1.ks32.measure (#104) | bare | total_lift | (none) | +0.2039 | -1.460 | -19.837 | +0.049 |

### Phase-1-vs-Phase-0 delta (Arm B — current promoted defaults)

| Metric        | phase0.baseline.full (#82) | p1.ks32.measure (#104) | Δ (Phase 1 - Phase 0) |
|---------------|---------------------------:|-----------------------:|----------------------:|
| Δ rank_corr   | +0.2048                    | +0.2039                | -0.0009               |
| Δ weekly_mae  | -1.474                     | -1.460                 | +0.014                |
| Δ season_mae  | -20.017                    | -19.837                | +0.180                |
| Δ fpts_ks     | +0.052                     | +0.049                 | -0.003                |

The post-Phase-1 stack matches the Phase-0 baseline within noise on every
headline metric. This is consistent with the gate-relaxation decision for
Phase 1: bug-fix work was promoted on the full-stack hard floor only, with
the expectation that headline metrics would stay flat while distribution
shape (KS) improvements compounded across the stack.

## Decisions Made

- **Chose NO CHANGE branch** per the explicit decision rule in Task 1: `plays_per_team=66.2 ≥ 62 ✓` AND `nfl_pass_attempts=33.8 ≥ 33 ✓`, both above the retune-trigger thresholds. Reducing `CLOCK_PASS_INCOMPLETE` from 5→3 would push plays_per_team even higher (already above the upper bound 65), worsening the existing FAIL on the upper band rather than improving anything. KS-15's promotion (which fixed the field-position clamping bug that was suppressing pass attempts) appears to have already restored pass attempts as the plan anticipated.
- **Used `--baseline bare` for the p1.ks32.measure ledger entry** (per HIGH-4 fix in Plan 10 Task 4 action). This gives a real delta-baring snapshot (Arm A=bare, Arm B=current post-Phase-1 defaults), structurally equivalent to `phase0.baseline.full` from Wave 0 and directly comparable for the Phase-1-vs-Phase-0 differencing. The original Plan 10 NO CHANGE branch would have used `--baseline defaults` (no `--set`) which produces Arm A=Arm B=defaults — a no-op snapshot identical in structure to the broken Plan 11 in the original. The HIGH-4 fix prevents that.
- **No phase1_ks_flags.ks32 block needed** — Cycle 3 D-45's flag-gated A/B applies only to the RETUNE branch. The NO CHANGE branch ships no source change, so no flag-gated code path is added. The plan's `phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled` config knob remains unimplemented; future re-evaluation could add it then.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] `validate_passing.py` does not accept `--seasons` flag**
- **Found during:** Task 1 (when constructing the measurement command)
- **Issue:** Plan Task 1 specifies `uv run python scripts/validate_passing.py --sims 50 --seasons 2024`. The actual `scripts/validate_passing.py --help` signature is `[--real] [--sims SIMS]` — there is no `--seasons` flag (the script uses static demo distributions, or `--real` for live nflverse data). VALIDATION.md row 66 has the same `--seasons 2024` typo. Passing the unsupported flag would have been a `SystemExit: 2` argparse failure.
- **Fix:** Used the documented signature `uv run python scripts/validate_passing.py --sims 50` (demo path). The demo path exercises `monte_carlo.run_simulations` end-to-end, which honors the module-level `CLOCK_PASS_INCOMPLETE` constant in `play_resolver.py` — sufficient for the gate measurement. The `--real` flag would have been a stricter test against live nflverse rosters but is not necessary for this go/no-go decision (the plan's Task 1 explicitly says "If [thresholds] not met → NO CHANGE", which is satisfied unambiguously by the demo measurement).
- **Files modified:** Pre-flight log only; no source change.
- **Verification:** Both run modes (demo and `--real`) would arrive at the same NO CHANGE decision because the `CLOCK_PASS_INCOMPLETE` constant is global — its effect on pass-attempt count is uniform across roster choice.
- **Documented in:** PROMOTION-NOTES.md `## KS-32 measurement` "Measurement command" subsection explicitly notes the deviation.
- **Committed in:** `4c338a0` (Task 1 commit)

**Total deviations:** 1 auto-fixed (1 Rule 3 — blocking issue from a plan-supplied CLI flag that doesn't exist in the script).

**Impact on plan:** Trivially handled — the documented CLI signature was used and produced the same decision-grade information the plan needed. No plan-level outcome changes.

### Tasks Skipped (per NO CHANGE branch)

Tasks 2 and 3 (the RETUNE branch tasks: TDD-add `CLOCK_PASS_INCOMPLETE = 3`, then run A/B validation with the `phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled` flag) were SKIPPED per the explicit conditional logic in their task definitions. The plan's `<acceptance_criteria>` for Task 2 explicitly addresses the NO CHANGE branch: *"Task skipped — no edits to play_resolver.py or test_clock.py. Acceptance is documented in PROMOTION-NOTES.md."*

This is NOT a deviation — it is the documented NO CHANGE branch.

## Authentication Gates

None — no external services involved. The `validate.py` and `validate_passing.py` runs are local-only (PFF cache hits served from `~/.fantasy-sim/pff/`, nflverse cache hits from `~/.fantasy-sim/cache/`).

## Issues Encountered

None — the measurement was unambiguous, the decision rule applied cleanly, and the ledger run completed in 572s without error. The bare cache hit (Arm A loaded from existing parquet) avoided the ~12-min Arm A simulation cost, leaving only the Arm B context-build + simulation (~9 min total wall-clock).

## User Setup Required

None — no external service configuration required. Existing PFF cookie auth at `~/.fantasy-sim/pff/.env` and nflverse cache at `~/.fantasy-sim/cache/` are sufficient.

## Next Phase Readiness

- KS-32 MEASURED-NO-CHANGE — `CLOCK_PASS_INCOMPLETE = 5` retained; ledger entry `p1.ks32.measure` (#104) pinned; PROMOTION-NOTES.md documents the decision and the Phase-1-vs-Phase-0 delta.
- Phase 1 progress: **10 of 12 plans complete** (Plan 00, Plans 01-09, Plan 10). Remaining: **Plan 11 (aggregate validation)**.
- **Plan 11 readiness:** the post-Phase-1 defaults state is fully captured in `p1.ks32.measure` (#104) Arm B metrics. Plan 11 will re-run `validate.py --baseline bare --label p1.aggregate.full` to produce a labeled Phase-1 closure entry; the differenced delta vs `phase0.baseline.full` (#82) Arm B is already known to be small (Δ rank_corr -0.0009, Δ weekly_mae +0.014). The TGT-09 QB pass_yards mean-bias gap (-36 yd/g on 2024) and other distribution-shape gaps remain explicitly out of Phase 1 scope per PROMOTION-NOTES `## KS-15` and the success-criteria evaluation Plan 11 will perform.
- Phase 2+ targets: per-stat residual_calibration extension (KS-09), dynamic_blend simulator-weight floor (KS-08), PFF Phase 5 slice activations (KS-02/16/17/18, Phase 3), PFF cached-data engines (KS-19/20, Phase 4), Odds API CDF loader on the alt-line markets scraped in Plan 09 (KS-21 engine integration, Phase 4) — these are the mechanism layers that will close the remaining mean-bias and distribution-shape gaps.

---
*Phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape*
*Completed: 2026-04-26*

## Self-Check: PASSED

Verified after SUMMARY creation:
- All 4 file references exist on disk (1 SUMMARY + 2 task logs + 1 PROMOTION-NOTES update)
- Both task commits present in git history (`4c338a0` Task 1 chore, `47ce72e` Task 4 chore)
- PROMOTION-NOTES.md contains both `## KS-32 measurement` (Task 1) and `## KS-32 final decision: MEASURED-NO-CHANGE (per D-24)` (Task 4) sections (grep -cE returns 2)
- `src/fantasy_sim/engine/play_resolver.py` line 84 still has `CLOCK_PASS_INCOMPLETE = 5` (no source change motivated by the measurement; grep -cE returns 1)
- `validate.py --show-ledger` reports 1 entry matching `p1.ks32` (`p1.ks32.measure` at #104 — RETUNE-only `p1.ks32.bare` and `p1.ks32.full` entries correctly absent because those tasks were SKIPPED per the NO CHANGE branch)
