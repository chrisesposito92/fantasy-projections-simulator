# Phase 5 RB Scheme-Fit Engine Design

Date: 2026-04-14
Status: Approved design
Phase: 5
Topic: RB scheme-fit engine using PFF `rushing_direction` and `offense_run_blocking`

## Objective

Add a new default-off Phase 5 RB slice that uses PFF `rushing_direction` plus
`offense_run_blocking` to model whether a runner's directional profile fits his
offense's gap-versus-zone personality, then translate that fit into a bounded
pre-sim rushing-efficiency adjustment without reopening usage, TD, or
play-calling ownership.

This slice is intentionally narrow:

- RB only
- offense-side only
- pre-sim only
- rushing efficiency only
- isolated marginal validation only

The first promotable slice adjusts only:

- RB `rushing_yards_dist`

It does not adjust:

- `carry_share`
- `red_zone_carry_share`
- `outer_rz_carry_share`
- `goal_line_carry_share`
- `rushing_td_factor`
- `i5_rushing_td_factor`
- team `play_calling.default`
- team `pace_factor`
- any pass-catcher fields

## Verified Current State

This design is based on a code-and-data verification pass on branch
`codex/phase-5-depth-role-v1`, not just the companion docs.

### Still true in code

- Phase 5A `pff.depth_role`, Phase 5B `pff.depth_role.efficiency`, and Phase
  5C `pff.qb_split` are all implemented, validated, and still default-off in
  `config/defaults.yaml`
- no `pff.rb_scheme_fit` config family or runtime engine exists yet
- `GameContextBuilder` runtime order in code is:
  - vegas
  - availability
  - usage
  - tracking
  - props
  - matchup
  - tier with optional team context
  - qb-split
  - depth-role
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
  - runtime game script
  - overrides
- the repo-level `AGENTS.md` adjustment-order summary is stale relative to the
  code and the audit document; the audit currently matches the runtime
- `_ensure_pff_crosswalk()` still builds the shared PFF player mapping from the
  summary trio:
  - `receiving_summary`
  - `rushing_summary`
  - `passing_summary`
- that crosswalk is roster-season aware, includes `target_season` when needed,
  and already has tests covering the recent qb-split fixes around transferred
  players and stale cache invalidation
- existing RB mutation ownership is already split across other layers:
  - `usage` and `tracking.rb_efficiency` can touch `carry_share`
  - `td_tendency` owns rushing TD conversion factors
  - `vegas.props` can touch RB rushing shares and red-zone shares
  - `matchup` and `tier/team_context` already touch generic rushing-yards
    environment

### Still true in local data

- local NFL PFF processed coverage exists for `2022-2024` for:
  - `rushing_direction`
  - `offense_run_blocking`
  - `rushing_summary`
- local support caches needed for season-aware backtests exist for
  `2022-2024`:
  - `rosters_weekly`
  - `pbp`
- `rushing_direction` exists locally but is still stored as a nested
  `directions: list[struct]` column rather than flat player-week directional
  columns
- `offense_run_blocking` already exposes the useful team OL split columns:
  - `gap_grades_run_block`
  - `zone_grades_run_block`
  - `gap_snap_counts_run_block`
  - `zone_snap_counts_run_block`
  - `gap_snap_counts_run_play`
  - `zone_snap_counts_run_play`

### Verified useful `rushing_direction` shape

Verified locally in `rushing_direction_2024.parquet`:

- player rows are still weekly rows with nested directional summaries
- the nested structs expose:
  - `attempts`
  - `direction`
  - `yards`
  - `ypa`
  - `yards_after_contact`
  - `yco_attempt`
  - `explosive`
  - `first_downs`
  - `touchdowns`
  - `fumbles`
  - `missed_tackles`
- the main RB direction codes present locally are:
  - `ML`
  - `MR`
  - `LG`
  - `RG`
  - `LE`
  - `RE`
  - `LT`
  - `RT`
- there are also rare gadget or broken-play buckets such as:
  - `JS-L`
  - `JS-R`
  - `EA-L`
  - `EA-R`
  - occasional QB-coded buckets

### Current Phase 5 branch state this design must respect

- Phase 5A, 5B, and 5C are all implemented and non-promotable on current
  evidence
- the handoff, roadmap, and audit all treat `RB scheme-fit engine` as the
  remaining major deferred Phase 5 follow-on
- the branch already has working coverage-reporting infrastructure for
  feature-family-specific PFF slices, so RB scheme-fit should follow that same
  pattern instead of inventing a separate validation contract

## Selected Approach

Use a new offense-side pre-sim PFF `rb_scheme_fit` engine that:

1. flattens RB `rushing_direction` rows into an RB directional profile
2. computes the offense's gap-versus-zone personality from
   `offense_run_blocking`
3. combines runner profile plus offensive scheme/blocking personality into one
   bounded RB-specific fit factor
4. applies that factor only to `rushing_yards_dist`

This was chosen over:

- a broader RB layer that also mutates `carry_share`, which would overlap
  usage-style responsibility and make marginal attribution noisier
- a broader layer that also mutates TD factors, which would overlap
  `td_tendency`
- a raw full-taxonomy direction model, which has more theoretical fidelity but
  too much surface area for the first isolated Phase 5 RB slice
- a blocking-only layer, which would underuse the runner-specific data and stop
  being meaningfully "scheme fit"

## Scope

This slice owns:

- a new `pff.rb_scheme_fit` config family under `pff`
- flattening and aggregating nested `rushing_direction` rows
- RB-only directional runner profiling
- team scheme and blocking profiling from `offense_run_blocking`
- same-season rolling windows with early-season blend behavior
- bounded pre-sim mutation of RB `rushing_yards_dist`
- explicit validation coverage reporting for `pff.rb_scheme_fit`
- roadmap and audit updates after the validation decision

This slice does not own:

- team play-calling mutation
- RB carry-share redistribution
- red-zone or goal-line share mutation
- rushing TD factor mutation
- explicit defensive front or run-fit modeling
- any post-sim projection layer
- combined Phase 5 bundle validation

## Architecture

### New config family

Add a new nested PFF family under `pff`:

```yaml
pff:
  rb_scheme_fit:
    enabled: false
    rush_yards_sensitivity: 0.10
    factor_clamp: [0.94, 1.06]
    min_attempts: 20
    min_games: 4
    early_season_blend: true
    scheme_usage_weight: 0.65
    blocking_alignment_weight: 0.35
```

Reasoning:

- it belongs with the other PFF refinement layers
- it follows the existing `--pff/--no-pff` master switch
- it needs its own enable flag and validation lifecycle, separate from
  `qb_split` and `depth_role`
- the config surface stays intentionally small in v1:
  - no per-direction sensitivities
  - no share weights
  - no TD-related knobs
- `scheme_usage_weight` and `blocking_alignment_weight` are relative weights,
  not independent clamps; the engine should normalize them to sum to `1.0`
  when both are positive and return neutral if both are non-positive

### Modules

- `src/fantasy_sim/data/pff/rb_scheme_fit.py`
  - `RbSchemeFitEngine`
  - direction flattening helpers
  - runner-profile helpers
  - team-scheme helpers
  - fit-factor helpers
- `src/fantasy_sim/data/pff/models.py`
  - `RbSchemeFitConfig`
  - compact result dataclass for runtime factors
- `src/fantasy_sim/data/pff/config.py`
  - parse `pff.rb_scheme_fit`
- `src/fantasy_sim/data/game_context.py`
  - instantiate and wire the engine
- `src/fantasy_sim/validation/coverage.py`
  - `pff.rb_scheme_fit` coverage reporting

`GameContextBuilder` owns runtime ordering and application, while feature
extraction and factor calculation stay inside `data/pff/`.

### Runtime placement

Runtime placement in `GameContextBuilder`:

1. matchup
2. tier with optional team context
3. RB scheme-fit
4. qb-split
5. depth-role
6. coverage

Reasoning:

- `tier/team_context` establishes the offense's generic RB baseline first
- RB scheme-fit then adds a player-specific offense-fit refinement
- `qb_split`, `depth_role`, and `coverage` remain later pass-game layers and do
  not overlap this RB-only slice

### Runtime gating

`rb_scheme_fit` should activate only when:

- `pff.enabled` is true
- `pff.rb_scheme_fit.enabled` is true
- `target_season` and `week` are available

Unlike `qb_split`, this engine should not depend on `pff.matchup.enabled`
because it is an offense-side fit layer, not an opponent-pressure layer.

## Factor Model

### RB eligibility

For the active offense:

- consider only players with `position == "RB"`
- require `carry_share > 0`
- require a non-empty `rushing_yards_dist`

If no eligible RBs exist, the engine returns neutral and does nothing.

### Direction flattening

Flatten `rushing_direction` from nested rows into one RB-direction-week row set.

V1 should ignore QB rows and keep only RB-relevant player rows after the normal
position normalization path.

### Runner family mapping

Collapse the raw direction taxonomy into two runner families:

- `interior`
  - `ML`
  - `MR`
  - `LG`
  - `RG`
- `edge`
  - `LE`
  - `RE`
  - `LT`
  - `RT`

Rare gadget or broken-play buckets stay out of scope in v1:

- `JS-L`
- `JS-R`
- `EA-L`
- `EA-R`
- `R-L`
- `R-R`
- any QB-coded directions

These buckets should be ignored rather than coerced into a family.

### RB runner profile

For each RB, aggregate the no-leakage historical window:

- all prior seasons in the training set
- current season rows only where `week < target_week`

Build an RB runner profile with:

- total classified attempts
- classified attempts by family
- family attempt share
- yards by family
- YPA by family
- games represented

Sample gates:

- require at least `min_attempts` classified attempts after ignored rare
  buckets are removed
- require at least `min_games`

If current-season support is below threshold and `early_season_blend` is true,
blend current season with the immediate previous season only. If the blended
profile still misses thresholds, return neutral for that RB.

### Team scheme and blocking profile

For each offense, aggregate `offense_run_blocking` over the same no-leakage
window and compute:

- `gap_share = gap_run_play / (gap_run_play + zone_run_play)`
- `zone_share = zone_run_play / (gap_run_play + zone_run_play)`
- `gap_grade`
- `zone_grade`

Grades should be snap-weighted by the run-block snap counts, not simple player
means.

If current-season support is below threshold and `early_season_blend` is true,
blend with the immediate previous season only.

Team support gate:

- require at least `min_games` represented in the aggregated team sample
- require non-zero total `gap_run_play + zone_run_play`

### Usage-side scheme fit

Map offense-side scheme share to the RB's family profile using the explicit
heuristic:

- gap maps to `interior`
- zone maps to `edge`

Compute:

- `runner_usage_score = (gap_share * interior_ypa) + (zone_share * edge_ypa)`
- `runner_baseline_score = overall classified YPA`
- `usage_delta = (runner_usage_score / runner_baseline_score) - 1.0`

This is the RB's usage-side fit signal before final weighting.

This captures whether the offense tends to call the kinds of runs that the RB
historically handles best.

### Blocking-alignment fit

Use the offense's relative split strength as a smaller residual signal:

- compare `gap_grade` versus `zone_grade`
- reward an interior-leaning RB more when gap blocking is relatively stronger
- reward an edge-leaning RB more when zone blocking is relatively stronger

Use the explicit v1 formulation:

- `family_preference = interior_attempt_share - edge_attempt_share`
- `blocking_delta = family_preference * ((gap_grade - zone_grade) / 100.0)`

This is intentionally a smaller second-order term, controlled by
`blocking_alignment_weight`, so the engine does not simply reapply generic OL
quality already modeled elsewhere.

### Final factor

Combine the two neutral-centered sub-signals with the normalized config
weights:

- `combined_delta = (scheme_usage_weight * usage_delta) + (blocking_alignment_weight * blocking_delta)`

Then translate that into the final bounded rushing factor:

- `rush_yards_factor = clamp(1.0 + (combined_delta * rush_yards_sensitivity), factor_clamp)`

Neutral conditions should yield exactly `1.0`.

## Runtime Mutation Rules

Apply the weekly factor only to eligible RBs on the offense.

### Rushing efficiency translation

Apply the RB-specific fit factor to:

- `rushing_yards_dist`

Rule:

- scale the existing empirical distribution multiplicatively
- do not replace it with a new synthetic curve
- keep the runtime representation aligned with existing RB efficiency patterns

### Explicit non-goals

Do not mutate:

- `carry_share`
- `red_zone_carry_share`
- `outer_rz_carry_share`
- `goal_line_carry_share`
- `rushing_td_factor`
- `i5_rushing_td_factor`
- `play_calling.default`
- `pace_factor`
- any pass-game fields

## Data Flow

End-to-end flow:

1. `GameContextBuilder` computes matchup
2. `GameContextBuilder` computes and applies tier/team-context
3. `GameContextBuilder` calls `RbSchemeFitEngine` for each offense, passing:
   - roster
   - `target_season`
   - `week`
   - shared `pff_crosswalk`
4. `RbSchemeFitEngine` loads and flattens `rushing_direction`
5. `RbSchemeFitEngine` builds per-RB runner profiles
6. `RbSchemeFitEngine` builds the offense's gap-versus-zone profile from
   `offense_run_blocking`
7. `RbSchemeFitEngine` combines runner profile plus scheme/blocking profile
   into compact RB fit factors
8. `GameContextBuilder` applies those factors only to RB
   `rushing_yards_dist`
9. downstream PFF pass-game layers continue normally

## Coverage Rules

Add a new validation signal:

- `pff.rb_scheme_fit`

It reports `full`, `partial`, `none`, or `disabled` using required historical
inputs for each test season.

Required paths per season:

- `rushing_direction_<season>.parquet`
- `offense_run_blocking_<season>.parquet`
- `rushing_summary_<season>.parquet`
- `rosters_weekly_<season>.parquet`

Reasoning:

- `rushing_direction` is the primary runner-profile source
- `offense_run_blocking` is the primary scheme/blocking source
- `rushing_summary` keeps the signal aligned with the existing shared PFF
  crosswalk construction path
- `rosters_weekly` is required to map PFF rows back to the active roster

Coverage should appear explicitly in:

- validation run headers
- saved ledger metadata
- any future Phase 5 handoff summary

## Error Handling

The runtime policy is neutral fallback, never speculative inference.

- if any required dataset is missing, return neutral
- if no eligible RBs exist on the roster, do nothing
- if an RB cannot be resolved through the shared PFF crosswalk, that RB stays
  neutral
- if an RB has too few classified attempts or games, that RB stays neutral
- if the offense lacks stable team scheme/blocking support, all RBs on that
  offense stay neutral
- if all classified attempts for an RB fall into ignored rare buckets, that RB
  stays neutral
- if any computed score or factor is non-finite, fall back to `1.0`

Do not silently degrade to:

- carry-share mutation
- TD-factor mutation
- opponent defensive front inference
- a blocking-only fallback that ignores runner profile

That would blur what the validation artifact actually tested.

## Testing

### Config tests

Add config coverage for:

- default `pff.rb_scheme_fit` parsing
- custom-value parsing
- validation override propagation

Suggested files:

- `tests/test_data/test_pff/test_config.py`
- `tests/test_validation/test_config.py`

### Engine unit tests

Add targeted unit tests for:

- flattening nested `directions`
- mapping raw direction codes into `interior` and `edge`
- ignoring rare/unmapped buckets
- runner-profile aggregation
- team scheme/blocking aggregation from `offense_run_blocking`
- early-season blending with current season plus immediate previous season only
- low-sample neutral fallback for RBs
- low-sample neutral fallback for teams
- bounded factor calculation and clamping

Suggested file:

- `tests/test_data/test_pff/test_rb_scheme_fit.py`

### Integration tests

Add runtime tests verifying:

- the engine is created when enabled
- runtime placement is after `tier/team_context` and before `qb_split`
- only RB `rushing_yards_dist` mutates
- `carry_share`, red-zone/goal-line shares, TD factors, and pass-game fields do
  not mutate

Suggested file:

- `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`

### Coverage tests

Add explicit `pff.rb_scheme_fit` coverage assertions in:

- `tests/test_validation/test_coverage.py`

Required cases:

- `full`
- `partial`
- `none`
- `disabled`

### Validation script tests

Add validation-header and ledger assertions showing the new family appears in
printed coverage summaries and saved metadata.

Suggested file:

- `tests/test_validation/test_validate_script.py`

## Validation Plan

After implementation:

1. run narrow config and engine tests first
2. run integration and coverage tests
3. run one isolated marginal validation artifact against `baseline=defaults`
4. require the validation header to print explicit
   `pff.rb_scheme_fit=...` coverage
5. update both source-of-truth docs with the actual result:
   - `docs/accuracy-roadmap.md`
   - `docs/accuracy-stack-audit.md`

First validation target:

- test seasons `2022-2024`
- comparison mode `marginal_lift`
- baseline `defaults`
- label shape like `phase-5-rb-scheme-fit-v1`
- leave the rest of the default stack unchanged

## Promotion Gate

This slice is promotable only if its isolated marginal artifact shows:

- RB weekly improvement as the phase-specific win condition
- no material QB/WR regression
- no material season-level regression across the rest of the core position
  groups
- trustworthy `pff.rb_scheme_fit` coverage in the run header

If the result is flat or regressive, keep `pff.rb_scheme_fit.enabled: false`
and carry the real verdict into the roadmap, audit, and the next handoff.
