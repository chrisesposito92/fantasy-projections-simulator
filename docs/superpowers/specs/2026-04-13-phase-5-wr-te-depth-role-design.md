# Phase 5 WR/TE Depth-Role V1 Design

Date: 2026-04-13
Status: Approved design
Phase: 5
Topic: WR/TE depth-role v1 using PFF `receiving_depth`

## Objective

Add a new pre-sim PFF depth-role engine that uses `receiving_depth` to improve
WR and TE weekly opportunity calibration without silently rewriting unrelated
positions, conflating role with efficiency, or making Phase 5 validation too
noisy to trust.

Phase 5A is intentionally narrow:

- WR and TE only
- role/volume only
- pre-sim only
- marginal validation only

The first promotable slice should adjust `target_share` and
`air_yards_share` only. It should not touch `catch_rate`,
`yards_per_reception`, or receiving-yards outcome distributions in v1.

## Verified Current State

This design is based on a code-and-data verification pass against the current
repo and local stores, not just the companion docs.

### Still true in code

- `config/defaults.yaml` still matches the current audit for active defaults:
  - `ensemble.ff_opportunity.enabled: true`
  - `availability.enabled: true`
  - `availability.injuries.enabled: false`
  - `market_history.enabled: true`
  - `tracking.enabled: false`
  - `role_trend.enabled: false`
  - `pff.team_context.enabled: false`
  - `pff.talent.enabled: false`
- `GameContextBuilder` runtime order is still, in substance:
  - vegas
  - availability
  - usage
  - tracking
  - props
  - matchup
  - tier with optional team context
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
- Shared post-sim ordering is still:
  - `role_trend`
  - `market_history`
  - `ensemble.ff_opportunity`
- Non-detail `week`, `season`, `game`, validation, and backtest flows still
  use the shared post-sim projection-layer path.
- `player` and `--detail` flows still bypass post-sim layers.
- `passing_detail`, `receiving_depth`, and `rushing_direction` are still not
  meaningfully used by current runtime PFF engines.

### Still true in local data

- local PFF processed coverage exists under `~/.fantasy-sim/pff/processed/nfl/`
  for:
  - `receiving_depth_2018-2025.parquet`
  - `passing_detail_2018-2025.parquet`
  - `rushing_direction_2018-2025.parquet`
  - `offense_run_blocking_2018-2025.parquet`
  - `offense_pass_blocking_2018-2025.parquet`
- local NCAA processed coverage exists under
  `~/.fantasy-sim/pff/processed/ncaa/` for `2021-2025`
- local `ff_opportunity` cache exists for `2022-2024`
- local market-history processed player markets exist for `2023-2025`
- local props parquet exists for `2025` only
- no local props parquet exists for `2022-2024`

### Verified useful Phase 5 columns

Verified locally in `receiving_depth_2024.parquet`:

- overall role/use fields such as:
  - `routes`
  - `targets`
  - `targets_percent`
  - `route_rate`
- depth-bucket fields such as:
  - `short_targets`
  - `medium_targets`
  - `deep_targets`
  - `deep_targets_percent`
  - `deep_avg_depth_of_target`
- alignment and direction fields such as:
  - `left_*`
  - `center_*`
  - `right_*`
  - `behind_los_*`
  - `short_*`
  - `medium_*`
  - `deep_*`

Verified locally in `passing_detail_2024.parquet`:

- pressure / no-pressure splits
- blitz / no-blitz splits
- screen / no-screen splits
- depth and field-side splits

Verified locally in `rushing_direction_2024.parquet`:

- the data exists and is rich enough for future RB work, but it is stored as a
  nested `directions: List[Struct]` column rather than a flat player-week row
  shape

That means the Phase 5 premise is still valid, but the WR/TE slice is the
cleanest first implementation.

### Audit wording that is already stale

The companion docs should be updated during Phase 5 to reflect:

- local injuries parquet now exists for `2022-2024`
- legacy `market_history_weekly_2023.parquet` and
  `market_history_weekly_2024.parquet` exist locally, even though the current
  market-history runtime path uses `player_markets_*`
- `rushing_direction` is available locally but structurally nested, so RB
  scheme-fit is real future work, not just a trivial config follow-up

## Recommended Approach

Use a new pre-sim PFF `depth_role` engine for WR and TE only, and restrict v1
to role/volume adjustments.

This was chosen over:

- a full WR/TE depth-role + efficiency engine in one pass, which has more
  upside but makes marginal validation too noisy
- a post-sim WR/TE blend, which would be simpler but would underuse the role
  information and would not fix upstream opportunity assumptions
- a QB-first Phase 5 slice, which is lower priority because current QB
  rank-correlation is already strong relative to WR/TE improvement headroom

## Phase 5 Breakdown

### Current priority

- `Phase 5A: WR/TE Depth-Role V1`

### Next, if 5A validates cleanly

- `Phase 5B: WR/TE efficiency v2`

### Explicitly deferred within Phase 5

- `Phase 5C: QB split engine` from `passing_detail`
- `Phase 5D: RB scheme-fit engine` from `rushing_direction` plus
  `offense_run_blocking`

These deferrals are part of the plan. They should be carried in the roadmap,
audit, and validation handoff language so they are not forgotten.

## Phase 5A Scope

Phase 5A owns:

- a new PFF `depth_role` config family under `pff`
- WR/TE-only pre-sim factor computation from `receiving_depth`
- same-season rolling-window feature extraction with early-season blending
- bounded role/volume adjustments for:
  - `target_share`
  - `air_yards_share`
- share re-normalization after mutation
- coverage-aware validation and ledger reporting for `pff.depth_role`
- roadmap and audit updates as part of the phase definition

Phase 5A does not own:

- `catch_rate` adjustments
- receiving-yards distribution rewrites
- `yards_per_reception` or YAC efficiency work
- QB split-dependent passing efficiency
- RB direction / line-fit modeling
- multi-slice Phase 5 bundles

## Architecture

### New config family

Add a new nested PFF family under `pff`, for example:

```yaml
pff:
  depth_role:
    enabled: false
    positions: [WR, TE]
    wr:
      target_share_sensitivity: 0.10
      air_yards_share_sensitivity: 0.12
      factor_clamp: [0.94, 1.06]
    te:
      target_share_sensitivity: 0.08
      air_yards_share_sensitivity: 0.06
      factor_clamp: [0.95, 1.05]
    min_routes: 15
    min_targets: 6
    min_games: 4
    early_season_blend: true
```

Reasoning:

- it belongs with the other PFF intelligence layers
- it should follow the existing `--pff/--no-pff` master switch
- it should not be mixed into `usage` or `tracking`, because the source is PFF
  and the modeling purpose is finer-grained receiving role, not snap or
  charting context

### Recommended modules

- `src/fantasy_sim/data/pff/depth_role.py`
  - main engine and feature extraction
- `src/fantasy_sim/data/pff/models.py`
  - typed config and result dataclasses
- `src/fantasy_sim/data/pff/config.py`
  - config parsing
- `src/fantasy_sim/data/game_context.py`
  - engine wiring and runtime placement
- `src/fantasy_sim/validation/coverage.py`
  - `pff.depth_role` coverage reporting

`GameContextBuilder` should only orchestrate the engine. Feature engineering
and application logic should stay inside PFF modules so the main pipeline
remains readable.

## Runtime Placement

Recommended placement in `GameContextBuilder`:

1. matchup
2. tier with optional team context
3. depth-role
4. coverage
5. DST baseline / kicker / TD / weather

Reasoning:

- `tier_engine` owns the broader talent baseline
- `depth_role` refines WR/TE role shape on top of that baseline
- `coverage` should stay after it because coverage is a per-opponent,
  per-matchup modifier rather than a stable same-season role estimate

After `depth_role` mutates roster players, the builder should re-normalize
shares before continuing.

## Data Window And Coverage Rules

Phase 5A should follow the same evidence discipline used in later phases:

- use same-season rolling windows with `week < max_week`
- blend current-season evidence with prior-season evidence when samples are
  below threshold
- return neutral factors when no trustworthy player-week profile is available
- never treat no-data seasons as neutral signal in phase promotion logic

Coverage reporting should distinguish:

- `pff.depth_role`
- `pff.depth_role.wr`
- `pff.depth_role.te`

That allows later evidence to say whether a run exercised only WR, only TE, or
both.

## Factor Logic

### V1 inputs

The engine should derive WR/TE role shape from `receiving_depth` using fields
that directly describe route and target deployment.

Use cases for v1:

- overall route participation and target ownership
- depth mix across behind/short/medium/deep
- vertical role evidence from deep-target and deep-route signals
- short-area possession usage that matters for TE and certain WR archetypes

### Recommended derived signals

Compute interpretable signals, not one opaque composite score:

- `target_role_signal`
  - how much target ownership the player commands relative to team peers
- `air_role_signal`
  - how much vertical opportunity the player commands relative to team peers
- `depth_shape_signal`
  - whether the player is primarily short-area, intermediate, or vertical
- `role_stability_signal`
  - whether the current same-season shape is trustworthy enough to act on

### V1 outputs

The engine should emit:

- `target_share_factor`
- `air_yards_share_factor`

Both factors should be:

- centered on `1.0`
- tightly clamped
- position-specific
- conservative in the presence of thin samples

### Recommended application behavior

- apply factors only to players whose fantasy position is `WR` or `TE`
- leave RB and QB target roles untouched in v1
- mutate current roster player usage fields rather than replacing them with raw
  PFF values
- re-normalize affected team shares after mutation
- keep uncovered players neutral

### Explicit v1 non-goals

Do not change:

- `catch_rate`
- `red_zone_catch_rate`
- receiving-yards empirical distributions
- YAC or YPR efficiency
- alignment-specific per-play outcome distributions

That work belongs to the deferred WR/TE efficiency slice.

## Validation Strategy

Phase 5A should be evaluated as a narrow marginal-lift test against current
defaults.

Required comparison:

- `defaults` vs `defaults + pff.depth_role.enabled=true`

Required evidence discipline:

- no combined Phase 5 bundles
- explicit season coverage reporting
- explicit WR and TE position-level readouts
- fresh post-Phase-0 ledger rows only

### Promotion gate

Promote only if:

- at least one of WR or TE improves materially on weekly metrics and/or
  season-total MAE
- the other of WR or TE holds without material regression
- overall weekly MAE does not regress materially
- QB and RB do not regress materially
- the result is explainable as isolated marginal lift

For this phase, "material regression" should use the existing validation
thresholds already enforced by the current harness. Phase 5A should not invent
looser exception rules just because WR/TE is the priority slice.

If the engine is mixed or flat:

- keep it implemented
- keep it default-off
- record whether the next move should be retuning role-volume or moving on to
  the deferred efficiency slice

## Testing Plan

Required tests:

- unit tests for `receiving_depth` feature extraction
- unit tests for early-season blending and neutral fallback
- unit tests for position-specific clamps
- integration tests for `game_context` ordering and post-mutation
  re-normalization
- validation coverage tests for `pff.depth_role`
- validation pipeline tests showing `defaults` and `defaults + depth_role`
  thread into the harness correctly

Do not claim success without fresh A/B evidence.

## Documentation Requirements

This phase is not complete without updating the two canonical docs.

### `docs/accuracy-roadmap.md`

Phase 5 updates must include:

- mark Phase 5 as in progress
- identify `WR/TE Depth-Role V1` as the current Phase 5 priority
- identify the next follow-on candidate as `WR/TE efficiency v2`
- explicitly list deferred sub-slices:
  - `QB split engine`
  - `RB scheme-fit engine`
- record whether the next priority after Phase 5 remains:
  - market-history `2022` backfill
  - Phase 4 retune
  - or additional Phase 5 follow-on work

### `docs/accuracy-stack-audit.md`

Phase 5 updates must include:

- current defaults and parked flags
- current status of `pff.depth_role`
- local `receiving_depth` coverage and shape
- local injuries-cache note for `2022-2024`
- local legacy `market_history_weekly` inventory note
- the `rushing_direction` nested-shape caveat
- the explicit list of Phase 5 deferrals still not started

## Deferral Ledger

This section should remain visible in the design, roadmap, and audit until the
items are either implemented or intentionally de-scoped.

### Deferred after Phase 5A by design

- `WR/TE efficiency v2`
  - catch-rate and receiving-efficiency adjustments from `receiving_depth`
- `QB split engine`
  - clean-pocket, pressure, blitz, and depth splits from `passing_detail`
- `RB scheme-fit engine`
  - run-direction and blocker-fit work from `rushing_direction` and
    `offense_run_blocking`

### Deferred validation work

- any combined Phase 5 multi-slice bundle
- any promotion of WR/TE efficiency before role-volume v1 is isolated

## Success Definition

Phase 5A is successful if it produces a clean, coverage-aware marginal lift in
WR/TE projection quality without creating new uncertainty about where the gain
came from.

The design is intentionally narrower than the full Phase 5 opportunity. That is
the right trade-off for the first slice because it preserves attribution, keeps
the deferrals visible, and gives later Phase 5 work a stable baseline.
