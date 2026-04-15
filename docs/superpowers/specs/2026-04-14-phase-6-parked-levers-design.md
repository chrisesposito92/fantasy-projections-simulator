# Phase 6 Re-open Parked Levers Design

Date: 2026-04-14
Status: Approved design
Phase: 6
Topic: Re-open truly parked default-off levers under the post-Phase-5 stack

## Objective

Run Phase 6 as a measurement-first phase that:

- corrects stale roadmap and audit assumptions
- makes coverage reporting truthful for Phase 6 candidate levers
- fixes any data-path mismatch that would make a parked lever look uncovered when
  local data actually exists
- retests only the truly parked default-off levers, one at a time, against the
  current default stack

Phase 6 should not be treated as a generic rerun of old sweeps. It should be a
post-Phase-5 retest phase with cleaner documentation, cleaner coverage
reporting, and isolated marginal evidence.

## Verified Current State

This design is based on a direct verification pass against current code, local
data, and current ledger artifacts.

### Still true in code

- `config/defaults.yaml` currently ships with:
  - `ensemble.enabled: true`
  - `ensemble.ff_opportunity.enabled: true`
  - `market_history.enabled: true`
  - `availability.enabled: true`
  - `availability.injuries.enabled: false`
  - `availability.depth_charts.enabled: true`
  - `availability.usage_fallback.enabled: true`
  - `tracking.enabled: false`
  - `role_trend.enabled: false`
  - `usage.ngs.enabled: false`
  - `usage.route_rate.enabled: false`
  - `pff.team_context.enabled: false`
  - `pff.depth_role.enabled: false`
  - `pff.depth_role.efficiency.enabled: false`
  - `pff.qb_split.enabled: false`
  - `pff.rb_scheme_fit.enabled: false`
  - `goal_line_concentration.enabled: false`
  - `td_tendency.enabled: true`
  - `td_tendency.i5_enabled: true`
- `GameContextBuilder` runtime order is currently:
  - vegas
  - availability
  - usage
  - tracking
  - props
  - matchup
  - tier with optional team-context integration
  - RB scheme-fit
  - QB split
  - depth-role
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
  - runtime game-script attachment
  - user overrides
- shared post-sim ordering is still:
  - `role_trend`
  - `market_history`
  - `ensemble.ff_opportunity`
- non-detail validation, backtester, and non-detail `week` / `season` /
  `game` CLI flows still use that shared post-sim ordering
- `player` and `--detail` flows still bypass those post-sim layers
- Phase 5 artifacts are present in `results/ab_ledger.json`:
  - `phase-5-depth-role-v1`
  - `phase-5-depth-role-efficiency-v2-activated`
  - `phase-5-qb-split-v1-postfix`
  - `phase-5-rb-scheme-fit-v1`

### Still true in local data

- local `ff_opportunity` cache exists for `2022-2024`
- local injuries cache exists for `2022-2024`
- local depth-chart cache exists for `2022-2024`
- local participation cache exists for `2022-2024`
- local FTN charting cache exists for `2022-2024`
- local NGS receiving, passing, and rushing caches exist for `2022-2024`
- local market-history processed data exists for `2023-2025`
- local props parquet still exists for `2025` only
- no local props parquet exists for `2022-2024`
- local PFF processed inventory currently includes:
  - `190` NFL parquet files
  - `105` NCAA parquet files
- NFL PFF facet coverage for the key parked and active slices is present for
  `2018-2025`
- NCAA PFF coverage is present for `2021-2025`

### Still true in validation

- `baseline=defaults` marginal validation is implemented in `scripts/validate.py`
- ledger entries carry schema version, comparison mode, and coverage summary
- market-history evidence is still covered-only for `2023-2024`
- Phase 4 remains slice-by-slice evidence only; no combined bundle result exists

### Verified stale assumptions

- Phase 6 in `docs/accuracy-roadmap.md` still lists `td_tendency` and `i5` in
  the retest queue, but both are already default-on
- the roadmap still frames Phase 5 / Phase 3 / Phase 4 as the immediate next
  planning targets instead of making Phase 6 the active next priority
- the audit still frames recent planning through the Phase 5D result, but it
  does not yet explicitly recast Phase 6 around only the truly parked levers

### Verified Phase 6 measurement gaps

- `collect_signal_coverage()` does not expose explicit signals for:
  - `pff.team_context`
  - `goal_line_concentration`
  - `td_tendency`
  - `td_tendency.i5_enabled`
- `usage.route_rate` currently reports as uncovered even though the local NFL
  PFF data exists
- that mismatch is caused by the current route-rate path assumption:
  - `UsageEngine._load_pff_route_rate()` uses `DataLoader.load_pff_facet()`
  - `DataLoader.load_pff_facet()` defaults to `~/.fantasy-sim/pff/processed/`
  - actual NFL route-rate source files live under
    `~/.fantasy-sim/pff/processed/nfl/`

The consequence is that Phase 6 cannot cleanly interpret some parked-lever
results until the evaluation path is corrected.

## Recommended Approach

Use a strict two-slice Phase 6:

1. measurement cleanup
2. isolated parked-lever retests

This was chosen over:

- a lever-first retest pass, which would generate faster artifacts but weaker
  evidence
- a docs-only pass, which would correct wording but would not fix the signal
  coverage gaps that Phase 6 depends on

The recommended design keeps Phase 6 practical. Slice A fixes the evidence
surface. Slice B uses that evidence surface to run clean marginal retests.

## Phase 6 Scope

### In scope

- explicit coverage reporting for the Phase 6 candidate levers
- route-rate path correction so runtime and coverage see the real NFL PFF store
- roadmap updates that mark:
  - Phase 5 complete as implemented and not promoted
  - Phase 6 as the active next priority
  - the corrected parked-lever queue
- audit updates that record:
  - current defaults
  - current local data coverage
  - the route-rate caveat and its resolution
  - any coverage-helper limitations that were fixed
- isolated retests for the still-parked default-off levers:
  - `pff.team_context`
  - `usage.ngs`
  - `goal_line_concentration`
  - `usage.route_rate`

### Out of scope

- re-parking or re-testing `td_tendency`
- re-parking or re-testing `td_tendency.i5_enabled`
- bundled multi-lever Phase 6 experiments before an isolated lever wins
- new Phase 4 redesign work
- new Phase 5 PFF slice development
- vague `coverage v2 ideas` without a concrete, named lever or data source

## Architecture And Components

### Slice A: measurement cleanup

Slice A should not change default production projections. Its job is to make
the validation and documentation path truthful.

Recommended component work:

- `src/fantasy_sim/validation/coverage.py`
  - add explicit coverage signals for:
    - `pff.team_context`
    - `goal_line_concentration`
    - `td_tendency`
    - `td_tendency.i5_enabled`
  - keep the coverage notes explicit when a signal is enabled but only partial
    or missing
- `src/fantasy_sim/data/loader.py` and/or the route-rate loading path
  - make route-rate use the actual NFL PFF processed root
  - ensure the coverage helper and runtime path agree on the same filesystem
    assumption
- `docs/accuracy-roadmap.md`
  - rewrite the Phase 6 queue around only truly parked levers
  - mark Phase 6 as the next priority
- `docs/accuracy-stack-audit.md`
  - update current defaults and current caveats from verified code/data state

### Slice B: isolated retests

Slice B should reuse the existing validation harness rather than inventing a
Phase 6-specific runner.

Recommended retest order:

1. `pff.team_context`
2. `usage.ngs`
3. `goal_line_concentration`
4. `usage.route_rate`

Rationale:

- `pff.team_context` already sits in the current runtime architecture and has
  full local PFF coverage
- `usage.ngs` has real local receiving NGS coverage and is already wired as a
  parked lever
- `goal_line_concentration` is fully wired in runtime and validation config,
  but lacks explicit signal coverage reporting
- `usage.route_rate` should go last because its data-path assumption must be
  corrected before any retest evidence is trustworthy

## Validation Rules

Every Phase 6 retest should:

- use `baseline=defaults`
- be interpreted as `marginal_lift`
- record explicit coverage in the run header and ledger row
- be evaluated one lever at a time
- avoid bundle inference unless at least one isolated retest first produces a
  clearly positive result

Phase 6 should keep the existing project-wide success preference:

- weekly QB/WR lift first
- then no material season-level regression across the broader stack

## Documentation Rules

Phase 6 is not complete unless both source-of-truth docs are updated.

### `accuracy-roadmap.md` must reflect

- Phase 5 status: implemented, validated, not promoted
- Phase 6 status: active next planning and execution priority
- corrected queue membership:
  - keep `pff.team_context`
  - keep `usage.ngs`
  - keep `goal_line_concentration`
  - keep `usage.route_rate`
  - remove `td_tendency`
  - remove `i5`
- measurement-first sequencing inside Phase 6

### `accuracy-stack-audit.md` must reflect

- current defaults with `td_tendency.enabled: true` and `td_tendency.i5_enabled: true`
- the current local coverage inventory for the parked Phase 6 levers
- the route-rate path caveat if still unresolved
- any coverage-helper gaps that were fixed in Slice A

## Error Handling And Guardrails

- If a lever is enabled but historical coverage is missing, validation output
  must say that directly rather than making the result look neutral.
- If coverage is partial, the run header and docs must preserve that caveat.
- If a runtime path and coverage path disagree about where data lives, fix that
  mismatch before treating any Phase 6 retest as evidence.
- Do not treat an old pre-Phase-6 run as the decision artifact for a parked
  lever once the measurement path has changed.

## Testing And Verification

Phase 6 Slice A should include:

- coverage tests for the new explicit Phase 6 signals
- a route-rate regression test proving that the route-rate path resolves the
  real NFL PFF processed store
- verification that the docs match current defaults, current queue membership,
  and current local coverage claims

Phase 6 Slice B should include:

- per-lever validation artifacts recorded in the unified ledger
- no promotion claim without an isolated marginal result

## Completion Criteria

Phase 6 planning is complete when:

- the written docs no longer claim that `td_tendency` and `i5` are parked
- the coverage helper can explicitly report the real Phase 6 candidate levers
- route-rate coverage reflects the real local data layout
- the roadmap makes Phase 6 the active next priority
- the audit records the corrected defaults, coverage inventory, and resolved
  caveats

Only after that should the implementation plan branch into the individual
Phase 6 retests.
