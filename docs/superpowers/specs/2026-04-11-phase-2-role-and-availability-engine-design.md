# Phase 2 Role And Availability Engine Design

## Problem

The next major weekly accuracy gap is same-season role drift rather than another
pure talent refinement.

The verified miss classes are concrete:

- inactive or limited players still carrying stale role assumptions
- starter changes at QB and other skill positions
- same-season share drift that season-level priors do not catch quickly enough
- depth-chart promotion or demotion not reaching weekly projections fast enough

The codebase already has part of the needed substrate:

- pre-sim roster/share mutation inside
  [`GameContextBuilder`](../../../src/fantasy_sim/data/game_context.py)
- post-sim weekly projection blending via the Phase 1 ensemble layer
- coverage-aware validation and ledger metadata in
  [`scripts/validate.py`](../../../scripts/validate.py) and
  [`src/fantasy_sim/validation`](../../../src/fantasy_sim/validation)

The data picture is mixed and needs to be reflected accurately in the design:

- weekly player stats, weekly rosters, snap counts, and `ff_opportunity`
  history are locally cached for the main backtest seasons
- `load_injuries()`, `load_participation()`, and `load_depth_charts()` are
  verified upstream loaders, but injuries/participation/depth charts are not yet
  locally cached or integrated in the repo today
- props historical parquet still exists only for 2025, and the correct path is
  `~/.fantasy-sim/pff/props`

Phase 2 should improve weekly role handling without pretending that every
verified upstream source is already a trusted local historical input.

## Goals

- add a new pre-sim `availability` family for hard role eligibility decisions
- add a new post-sim `role_trend` family for bounded same-season weekly role
  correction
- support QB/RB/WR/TE in v1
- support per-position gating through `positions` lists rather than separate
  booleans for each position
- keep Phase 2 conservative when explicit availability signals are absent
- extend coverage-aware validation so the phase can distinguish:
  - explicit-signal coverage
  - fallback-only coverage
  - neutral/no-data behavior
- update the source-of-truth docs as part of the phase:
  - [`docs/accuracy-roadmap.md`](../../../docs/accuracy-roadmap.md)
  - [`docs/accuracy-stack-audit.md`](../../../docs/accuracy-stack-audit.md)

## Non-Goals

- no monolithic rewrite of the existing `usage` family
- no requirement that participation or injuries be historically backfilled in v1
- no full simulator-side re-learning of every committee or route tree
- no hard inactive/starter-out decisions based on usage-only evidence
- no automatic A/B execution by the agent in this phase

Phase 2 v1 should improve role handling with bounded new logic, not become a
second simulator.

## Verified Baseline

The current repo and local data state should be treated as the Phase 2 starting
point.

### Still true from the audit

- default-on families in [`config/defaults.yaml`](../../../config/defaults.yaml)
  still include ensemble, PFF core engines, weather, vegas, usage,
  `game_script.trailing_late`, and `td_tendency`
- parked or disabled defaults still include `pff.team_context`,
  `pff.talent`, `usage.ngs`, `usage.route_rate`, and
  `goal_line_concentration`
- the runtime order in
  [`src/fantasy_sim/data/game_context.py`](../../../src/fantasy_sim/data/game_context.py)
  is still materially:
  - vegas
  - usage
  - props
  - matchup
  - tier and optional team context
  - coverage
  - DST baseline
  - kicker
  - TD tendency
  - weather
  - runtime game script
  - overrides
- ensemble is still post-sim and still bypassed by `player` and `--detail`
  CLI flows in [`src/fantasy_sim/cli.py`](../../../src/fantasy_sim/cli.py)

### Audit corrections Phase 2 must carry forward

- `ff_opportunity` local cache coverage is stronger than the current audit text:
  local parquet exists for 2022, 2023, and 2024 under
  `~/.fantasy-sim/cache/ff_opportunity_weekly_<season>.parquet`
- props historical coverage is still absent for 2022-2024, but the correct
  cache path is `~/.fantasy-sim/pff/props`
- injuries, participation, and depth charts should be described as
  "verified upstream loaders" until this phase actually adds local caching and
  validation coverage for them

## Recommended Approach

Use a **hybrid Phase 2 design**.

1. `availability` runs pre-sim and mutates roster eligibility and shares before
   downstream modeling
2. `role_trend` runs post-sim and applies bounded same-season weekly projection
   correction
3. both families cover QB/RB/WR/TE, but each family supports per-position
   disable via a `positions` list

This is the best balance of:

- weekly upside
- regression containment
- validation clarity
- compatibility with the current architecture

### Rejected alternatives

#### Pre-sim only

Pushing both availability and trend logic into pre-sim roster/share mutation
would maximize internal consistency, but it would also maximize regression risk
and make marginal attribution harder.

#### Post-sim only

Keeping everything post-sim would be simpler, but it would fail the key use
case where inactive or benched players should affect the simulation itself.

## Scope Boundary

### In scope

- a new `availability` config family and engine
- a new `role_trend` config family and post-sim projection modifier
- local caching wrappers for Phase 2 inputs as needed
- coverage reporting for the new families
- validation and ledger plumbing needed to interpret partial-data and fallback
  behavior
- roadmap and audit updates as part of the phase closeout

### Out of scope

- re-using `usage` as the container for Phase 2 families
- participation-heavy route-role modeling that depends on future Phase 4 work
- historical market backfill
- deeper PFF split modeling from Phase 5
- automatic experiment execution by the agent

## Hard Rules

These are mandatory v1 rules.

- hard availability changes require explicit signals
- usage-only evidence can down-weight confidence or slightly damp projections
- usage-only evidence should not create inactive or starter-out decisions by
  itself in v1

Operationally, that means:

- only injuries, depth-chart movement, roster presence, or similar explicit
  sources can trigger hard inactive, starter swap, or sharp role removal
  decisions
- snaps, weekly stats, and recent opportunity can support a soft downgrade,
  soft upgrade, or uncertainty penalty
- when explicit and fallback evidence disagree, v1 resolves conservatively

## Architecture

### Add two new top-level families

In [`config/defaults.yaml`](../../../config/defaults.yaml), add:

- `availability`
- `role_trend`

Each family should support:

- `enabled`
- `positions: [QB, RB, WR, TE]`

This matches the existing design pattern used by Phase 1 for
`ensemble.ff_opportunity.positions` and avoids a boolean explosion.

### Runtime order

The pre-sim order in
[`src/fantasy_sim/data/game_context.py`](../../../src/fantasy_sim/data/game_context.py)
should become:

1. base team distributions and player models
2. vegas
3. availability
4. usage
5. props
6. matchup
7. tier and optional team context
8. coverage
9. DST baseline
10. kicker
11. TD tendency
12. weather
13. runtime game script
14. overrides

The post-sim weekly projection order should become:

1. projection rows from simulation
2. role_trend
3. ensemble

`availability` belongs in `GameContextBuilder`.
`role_trend` does not.

## Components

### 1. `data/availability/`

Responsibility:

- load and cache explicit availability signals
- synthesize a bounded per-player decision context
- apply pre-sim roster/share mutation when explicit evidence justifies it

Suggested pieces:

- `models.py`
- `config.py`
- `loader.py`
- `engine.py`

The engine output should be explicit and debuggable:

- inactive
- limited
- promoted
- demoted
- starter certainty
- confidence penalty
- share redistribution hints

### 2. `scoring/role_trend.py`

Responsibility:

- apply bounded same-season weekly projection adjustments after simulation
- use recent evidence to damp or boost weekly projections by position
- stay neutral when required data is absent

This layer should not:

- declare players inactive
- override a hard availability decision
- mutate detailed stat columns in v1 unless the implementation can keep them
  internally consistent

### 3. Validation integration

[`scripts/validate.py`](../../../scripts/validate.py) and the validation package
should treat `availability` and `role_trend` as first-class families for:

- config snapshots
- coverage reporting
- ledger interpretation
- marginal A/B comparison

## Signal Set

### `availability` explicit-signal tier

Priority inputs:

- `load_injuries()`
- `load_depth_charts()`
- weekly roster presence
- current-week roster status where available

These are the only signal types allowed to drive hard availability moves in v1.

### `availability` fallback tier

Soft-only support inputs:

- recent snap counts
- recent weekly player stats
- recent same-team opportunity share

These can:

- reduce certainty
- slightly suppress projected role
- support a promotion already hinted at by explicit evidence

These cannot:

- mark a player inactive
- declare a starter out
- force a hard starter swap by themselves

### `role_trend` inputs by position

- QB:
  - recent pass attempts
  - recent rush attempts
  - recent fantasy opportunity
  - participation/snap data when available
- RB:
  - recent carries
  - recent targets
  - recent snap share
  - red-zone opportunity proxies from weekly stats where available
- WR:
  - recent targets
  - recent receiving usage
  - recent snap share
  - route participation later when participation support lands
- TE:
  - recent targets
  - recent receiving usage
  - recent snap share
  - route participation later when participation support lands

## Behavior By Family

### `availability`

- QB:
  - resolve likely starter conservatively
  - suppress backup-only QBs when explicit evidence supports it
  - redistribute QB rush share only when needed
- RB:
  - remove explicit inactives
  - reduce limited backs
  - promote next backs only when explicit signal and recent usage agree
- WR and TE:
  - remove explicit inactives
  - demote buried players conservatively
  - promote depth-chart risers conservatively

### `role_trend`

- QB:
  - adjust final weekly projection for starter changes and rushing role shifts
- RB:
  - adjust for committee drift rather than trying to fully relearn the
    backfield pre-sim
- WR and TE:
  - adjust for target-share and snap-share drift
  - use stronger effect when multiple recent weeks point in the same direction

## Config Shape

Recommended v1 config surface:

- `availability.enabled`
- `availability.positions`
- `availability.injuries.enabled`
- `availability.depth_charts.enabled`
- `availability.roster_presence.enabled`
- `availability.snap_fallback.enabled`
- `availability.factor_clamp`
- `availability.confidence_thresholds`
- `role_trend.enabled`
- `role_trend.positions`
- `role_trend.window_weeks`
- `role_trend.position_weights`
- `role_trend.factor_clamp`

The exact parameter names can shift slightly in implementation if the structure
stays narrow and coverage-reportable.

## Data Flow

### Pre-sim

1. build base team distributions and rosters
2. apply vegas
3. build per-player availability context
4. apply hard explicit availability decisions
5. apply soft confidence/share damping where allowed
6. normalize shares
7. continue through the existing pre-sim stack

### Post-sim

1. simulate games
2. build weekly player projections
3. apply bounded `role_trend`
4. apply Phase 1 ensemble
5. compute downstream weekly and season metrics

## Coverage And Validation

Phase 2 should extend the Phase 0 coverage model rather than invent a parallel
reporting path.

Recommended coverage entries:

- `availability`
- `availability.injuries`
- `availability.depth_charts`
- `availability.usage_fallback`
- `role_trend`

Coverage output should distinguish:

- full explicit-signal coverage
- partial explicit-signal coverage
- fallback-only execution
- neutral/no-data behavior

## Validation Policy

### A/B execution ownership

Any A/B validation runs are executed manually by the user.

This phase may add config plumbing, coverage reporting, helper docs, and
recommended commands, but the agent should not run Phase 2 validation commands
as part of planning or implementation signoff.

### Recommended validation matrix

The user should manually run:

- `defaults` vs `defaults + availability`
- `defaults` vs `defaults + role_trend`
- `defaults` vs `defaults + availability + role_trend`

Optional follow-up ablations:

- per-position enable runs
- "all positions except one" runs

### Promotion gate

- weekly QB and/or WR improvement remains the primary decision driver
- no material season-level regression across QB/RB/WR/TE
- no claim of lift from sub-signals that had `none` or materially `partial`
  historical coverage
- run notes must say clearly when explicit-signal coverage was sparse and the
  family mostly operated in fallback or neutral mode

## Error Handling And Neutral Behavior

- missing injuries data:
  - no hard inactive decisions from injuries
- missing depth-chart data:
  - no hard promotion/demotion from depth charts
- missing participation data:
  - neutral for that sub-signal in v1
- missing usage fallback data:
  - skip soft trend adjustments rather than guessing
- conflicting explicit signals:
  - choose the less aggressive action unless the conflict is deterministic
- position removed from `positions`:
  - family stays fully neutral for that position

## Documentation Requirements

Phase 2 is not complete until both source-of-truth docs are updated.

### `accuracy-roadmap.md`

Update:

- Phase 2 status
- next priority after Phase 2
- that Phase 2 chose a hybrid design
- that per-position gating is supported through `positions`
- any scope explicitly deferred to later phases

### `accuracy-stack-audit.md`

Update:

- current defaults after Phase 2
- actual runtime ordering with `availability` and `role_trend`
- corrected `ff_opportunity` local coverage note
- corrected props cache path
- verified-loader versus locally-cached distinction for injuries,
  participation, and depth charts
- the v1 caveat that usage-only evidence is soft-only and cannot create hard
  inactive or starter-out decisions

## Risks

- explicit availability sources may be too sparse or noisy for strong backtest
  exercise in early v1
- pre-sim availability logic can create unintended share redistribution effects
  if normalization rules are not carefully bounded
- post-sim role trend can become a hidden second ensemble if the clamps are too
  loose

The implementation plan should keep both families narrow enough that failed
ideas can be disabled or rolled back independently.

## Recommended Implementation Sequence

1. add config models and coverage plumbing for `availability` and `role_trend`
2. add local caching and loader wrappers for explicit availability sources
3. implement conservative `availability` pre-sim mutation
4. implement bounded `role_trend` post-sim correction
5. update roadmap and audit docs
6. hand the final validation command set to the user for manual A/B execution

## Success Definition

Phase 2 is successful if it produces repeatable marginal weekly lift from
same-season role handling while staying honest about which sub-signals had real
historical coverage and while preserving season-level behavior across all four
core positions.
