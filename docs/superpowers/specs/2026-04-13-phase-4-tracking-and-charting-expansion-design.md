# Phase 4 Tracking And Charting Expansion Design

Date: 2026-04-13
Status: Approved design
Phase: 4
Topic: Tracking and charting expansion for QB/RB/WR/TE

## Objective

Add a new pre-sim `tracking` family that uses verified non-PFF tracking and
charting feeds to improve weekly projection accuracy across QB, RB, WR, and TE
without introducing silent no-data behavior, duplicate responsibility with
existing layers, or hard-to-attribute validation results.

Phase 4 is promotable only if at least one of the four core positions improves
materially while the others hold without material regression. A pure "nothing
got worse" result is not enough to justify default-on promotion.

## Verified Current State

This design is based on a code-and-data verification pass against the current
repo and local stores, not just the audit documents.

### Still true in code

- `config/defaults.yaml` still matches the current audit for active defaults:
  - `ensemble.ff_opportunity.enabled: true`
  - `market_history.enabled: true`
  - `availability.enabled: true`
  - `availability.injuries.enabled: false`
  - `availability.depth_charts.enabled: true`
  - `availability.usage_fallback.enabled: true`
  - `role_trend.enabled: false`
  - `usage.ngs.enabled: false`
  - `usage.route_rate.enabled: false`
  - `pff.team_context.enabled: false`
  - `pff.talent.enabled: false`
  - `goal_line_concentration.enabled: false`
- `GameContextBuilder` runtime order is still, in substance:
  - vegas
  - availability
  - usage
  - props
  - matchup
  - tier with optional team context
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
  - runtime game-script attachment
- Shared post-sim ordering is still:
  - `role_trend`
  - `market_history`
  - `ensemble.ff_opportunity`
- Non-detail `week`, `season`, `game`, validation, and backtest flows still
  use the shared projection-layer path.
- `player` and `--detail` flows still bypass post-sim layers.
- `DataLoader` wraps:
  - `load_injuries`
  - `load_depth_charts`
  - `load_nextgen_stats`
- `DataLoader` does not yet wrap:
  - `load_participation`
  - `load_ftn_charting`
- The only existing "tracking-style" runtime logic today lives in parked
  `usage.ngs` and `usage.route_rate`, both of which remain default-off.

### Still true in local data

- local `ff_opportunity` cache exists for `2022-2024`
- local `market_history` processed store exists for `2023-2025`
- local props parquet exists for `2025` only
- no local props parquet exists for `2022-2024`
- local cache currently includes:
  - `ngs_receiving_2022.parquet`
  - `ngs_receiving_2023.parquet`
  - `ngs_receiving_2024.parquet`
- there is no current local cache for:
  - participation
  - FTN charting
  - NGS passing
  - NGS rushing
- PFF processed inventory currently totals:
  - `190` NFL parquet files
  - `105` NCAA parquet files
  - one stray `.DS_Store`

### Verified upstream data surfaces

Verified in the installed `nflreadpy` package:

- `load_participation()` exists and is available since `2016`
- `load_ftn_charting()` exists and is available since `2022`
- `load_nextgen_stats(..., stat_type='passing')` exists
- `load_nextgen_stats(..., stat_type='rushing')` exists
- `load_nextgen_stats(..., stat_type='receiving')` exists

Verified useful column surfaces:

- participation:
  - `was_pressure`
  - `time_to_throw`
  - `route`
  - `offense_formation`
  - `offense_personnel`
  - `defense_personnel`
  - `number_of_pass_rushers`
  - `defenders_in_box`
- FTN charting:
  - `is_no_huddle`
  - `is_play_action`
  - `is_rpo`
  - `is_catchable_ball`
  - `is_contested_ball`
  - `n_blitzers`
  - `n_pass_rushers`
- NGS passing:
  - `avg_time_to_throw`
  - `aggressiveness`
  - `completion_percentage_above_expectation`
- NGS rushing:
  - `rush_yards_over_expected`
  - `rush_yards_over_expected_per_att`
  - `rush_pct_over_expected`

### Audit wording that is already stale

The companion docs should be updated during Phase 4 to reflect:

- there is not yet a `tracking` family in code
- `load_participation` and `load_ftn_charting` are still upstream-only, not
  wrapped in `DataLoader`
- `market_history_weekly_2023.parquet` and `market_history_weekly_2024.parquet`
  now exist locally and should be reflected in the audit inventory
- local tracking coverage today is limited to receiving NGS cache; Phase 4 must
  backfill its own feeds before claiming validation coverage

## Recommended Approach

Use a dedicated pre-sim `tracking` family with position-scoped sub-engines and
staged marginal validation artifacts.

This was chosen over:

- a post-sim-only tracking layer, which would be easier but would underuse
  game-generation inputs such as pressure, blitz, catchable-ball quality, and
  rushing-over-expected
- a hybrid pre-sim/post-sim tracking design, which would increase overlap risk
  with `role_trend`, `market_history`, and `ensemble`

The design keeps Phase 4 coherent as a real tracking/charting expansion while
still remaining low-risk through strict clamps, coverage gating, and staged
sub-engine promotion.

## Phase 4 Scope

Phase 4 owns:

- a new top-level `tracking` config family
- new `DataLoader` wrappers and cache paths for:
  - participation
  - FTN charting
  - NGS passing
  - NGS rushing
- `2022-2024` local backfill for any feed used in validation
- a new tracking input loader that composes leak-free season/week windows
- position-scoped pre-sim tracking sub-engines covering QB, RB, WR, and TE
- coverage-aware validation and ledger reporting for tracking slices
- required roadmap and audit updates after each promoted Phase 4 slice

Phase 4 does not own:

- hard inactive or starter-out decisions
- a new post-sim projection layer
- a rebrand of parked `usage.ngs` / `usage.route_rate` into tracking v1
- PFF depth-role, scheme-fit, or split-granularity work that belongs in
  Phase 5
- opaque composite scores that blend unrelated signals into one uninterpretable
  factor

## Architecture

### New top-level family

Add a new top-level `tracking` family rather than overloading `usage`,
`role_trend`, or `market_history`.

Rationale:

- `availability` already owns explicit inactive / limited / starter logic
- `usage` already owns snap counts, CPOE, and its parked NGS / route-rate
  experiments
- `role_trend`, `market_history`, and `ensemble` already own post-sim
  projection cleanup
- Phase 4 needs a coherent home for pre-sim tracking/charting context that is
  independent, coverage-reportable, and easy to disable slice-by-slice

### Recommended modules

- `src/fantasy_sim/data/tracking/config.py`
  - load typed tracking config from YAML
- `src/fantasy_sim/data/tracking/models.py`
  - config dataclasses and canonical feature row types
- `src/fantasy_sim/data/tracking/loader.py`
  - compose leak-free player-week and team-week tracking inputs
- `src/fantasy_sim/data/tracking/engine.py`
  - orchestrate per-slice application to rosters and distributions
- `src/fantasy_sim/data/tracking/qb_context.py`
  - QB-specific feature computation and application
- `src/fantasy_sim/data/tracking/receiver_participation.py`
  - WR/TE route and target-quality feature computation
- `src/fantasy_sim/data/tracking/rb_efficiency.py`
  - RB efficiency-over-expected feature computation

`GameContextBuilder` should only orchestrate the family. Feature engineering
and application logic should stay inside tracking modules so the pipeline stays
readable.

## Runtime Placement

Recommended `GameContextBuilder` ordering:

1. vegas
2. availability
3. usage
4. tracking
5. props
6. matchup
7. tier with optional team context
8. coverage
9. DST baseline
10. kicker
11. TD tendency
12. weather

Why this slot:

- `availability` stays first for explicit inactive / limited decisions
- `usage` keeps ownership of the current snap/CPOE branch
- `tracking` then refines stabilized player-week context before external props
  and PFF layers compound it
- `tracking` remains pre-sim only, preserving the current post-sim layer stack
  and avoiding overlap with `role_trend` or `market_history`

## Sub-Engine Design

### `tracking.receiver_participation`

Primary targets:

- WR
- TE

Primary inputs:

- participation
- FTN charting

Candidate signals:

- route involvement and route consistency
- catchable-ball quality
- contested-ball profile
- participation-derived route presence and passing-game involvement

Allowed effects:

- `target_share`
- `air_yards_share`
- small receiving quality modifiers such as bounded catch-rate or
  receiving-yards-quality refinements

TE policy:

- TE uses the same engine as WR but with separate config sensitivities and
  clamps
- TE is an explicit Phase 4 target because it is the current weakest core
  position by backtest performance

### `tracking.rb_efficiency`

Primary target:

- RB

Primary inputs:

- NGS rushing
- FTN charting

Candidate signals:

- rushing-over-expected
- rushing-over-expected per attempt
- box-count context where it is cleanly recoverable
- motion / no-huddle / play-action environment only if the effect is
  interpretable and does not collapse into generic team context

Allowed effects:

- bounded rushing efficiency adjustments
- modest carry-share quality refinements if justified by the signal design

Explicit non-goals:

- gap/zone line-fit logic
- run-direction scheme fit

Those belong to Phase 5 PFF granularity work.

### `tracking.qb_context`

Primary target:

- QB

Primary inputs:

- participation
- FTN charting
- NGS passing

Candidate signals:

- pressure exposure
- blitz exposure
- no-huddle context
- play-action context
- passing quality context such as time to throw and aggressiveness

Allowed effects:

- modest QB passing-quality refinements
- bounded scramble tendency adjustments
- optional small team-level pass-rate or pace context factor only if the signal
  is stable, leak-free, and clearly attributable to the QB context slice

Explicit non-goals:

- replacing the existing CPOE path
- duplicating PFF matchup pass-rush logic

### Family-level policy

- each slice is independently enableable
- each slice has its own clamps and sensitivity blocks
- all factors remain multiplicative and centered on `1.0`
- any share mutation must be followed by share normalization
- no slice may create hard inactive decisions or starter promotion logic

## Data Contract

### Required loaders and cache paths

Add new `DataLoader` wrappers for:

- `load_participation`
- `load_ftn_charting`
- `load_nextgen_stats(..., stat_type='passing')`
- `load_nextgen_stats(..., stat_type='rushing')`

Recommended cache behavior:

- same parquet-on-first-load pattern as the current loader
- separate cache keys per stat type and season set
- neutral empty-data behavior when upstream fetch returns empty

### Required historical backfill

For any feed used in a promotable Phase 4 slice:

- local backfill must exist for `2022`
- local backfill must exist for `2023`
- local backfill must exist for `2024`

If a feed cannot be backfilled cleanly for `2022-2024`, that slice must either:

- remain non-promotable, or
- be evaluated with explicit covered-only evidence and an explicit caveat in
  both source-of-truth docs

It must never be treated as if uncovered years were neutral.

### Leak-free windowing

All tracking slices must use strict historical windows:

- `season == target season`
- `week < target week`

No slice may read current-week rows during feature computation.

## Degradation Semantics

- every slice must be neutral when its required inputs are missing
- partial source availability degrades only the affected slice, not the whole
  tracking family
- validation coverage must report both slice-level and family-level state
- uncovered seasons remain explicit `no-data`
- no signal may be treated as exercised evidence unless the coverage helper
  reports it as covered

Recommended coverage keys:

- `tracking.qb_context`
- `tracking.receiver_participation`
- `tracking.rb_efficiency`
- `tracking`

## Validation Design

Phase 4 should be executed as staged sub-phases inside one parent phase.

### Internal order

Recommended order:

1. `tracking.receiver_participation`
2. `tracking.rb_efficiency`
3. `tracking.qb_context`
4. optional combined `tracking` bundle

Why:

- WR/TE participation and catchable-ball context maps most directly to the
  weakest current position group, TE
- RB efficiency has a clean, verified non-PFF signal surface
- QB is already the strongest position and should be handled as upside without
  regression pressure, not as the first rescue target

### Required A/B paths

Every slice gets:

- `bare` vs current defaults
- `defaults` vs `defaults + slice`

Combined-bundle validation is optional and only runs after isolated slice
artifacts exist.

### Promotion rule

Phase 4 is promotable when:

- at least one of QB, RB, WR, or TE improves materially
- the other positions hold without material regression

Phase 4 is not promotable when:

- all four positions merely hold with no meaningful improvement

TE should be treated as an explicit target in artifact interpretation, but not
as the only acceptable winner.

## Documentation And Audit Maintenance

Documentation updates are part of the phase definition, not optional cleanup.

### `docs/accuracy-roadmap.md` must be updated after each promoted slice with:

- Phase 4 status
- current active slice
- next internal slice priority
- any newly deferred or unlocked follow-on work
- whether the combined bundle remains pending, promoted, or rejected

### `docs/accuracy-stack-audit.md` must be updated after each promoted slice with:

- current `tracking` defaults and parked flags
- wrapped loaders now implemented in code
- current local cache coverage for participation, FTN charting, NGS passing,
  and NGS rushing
- caveats fixed by the slice
- any newly discovered coverage or schema caveats
- any stale audit assumptions removed

## Testing Requirements

Required test surfaces:

- loader/cache tests for new tracking sources
- tracking config parsing tests
- unit tests per sub-engine
- pipeline-order tests proving `tracking` runs between `usage` and `props`
- normalization tests after share mutations
- validation coverage tests for slice-level and family-level reporting
- validation/backtest integration tests proving config loading and
  dual-arm wiring work correctly

No tracking slice should be promoted without:

- passing the existing suite
- passing new slice-specific tests
- producing a trustworthy marginal validation artifact

## Promotion And Rollback Semantics

- each slice should be independently disableable
- each slice should be independently promotable
- a rejected slice should not block the rest of Phase 4 from proceeding
- the combined bundle should only be attempted if the isolated slice evidence
  makes double-counting risk manageable

This keeps Phase 4 interpretable and avoids a monolithic "tracking on/off"
decision that hides which sub-engine actually created lift.

## Acceptance Criteria

Phase 4 planning is complete when the implementation plan can execute against
these concrete requirements:

- a new pre-sim `tracking` family exists in design, not as a post-sim patch
- participation, FTN charting, and required NGS variants have loader/caching
  support and documented coverage expectations
- QB, RB, WR, and TE all have explicit Phase 4 ownership
- TE is an explicit target, but not the only valid source of promotion lift
- slice-by-slice validation artifacts are required before any combined bundle
- roadmap and audit maintenance are built into the phase definition

## Next Step

After this spec is approved by the user, the next step is to write a detailed
implementation plan for Phase 4. That plan should preserve the staged slice
structure and should treat roadmap/audit updates as required deliverables for
every promoted slice.
