# Phase 1 FF Opportunity Ensemble Design

## Problem

The current simulator stack has already accumulated substantial contextual lift,
but the next high-probability weekly improvement path does not require another
deep engine rewrite.

The verified opportunity is narrower:

- `nflreadpy.load_ff_opportunity(seasons=..., stat_type="weekly")` is a real,
  historical weekly source
- it exposes expected-opportunity and expected-fantasy style signals at the
  player-week level
- those signals can be evaluated as a clean marginal layer against current
  defaults without changing upstream simulation behavior

The design goal for Phase 1 is not "use every available external prior."
It is to isolate the value of `ff_opportunity` as cleanly as possible.

That means Phase 1 v1 must avoid:

- upstream share mutation
- multi-source attribution noise
- schema-risk coupling to `ff_rankings`
- any success criteria that depend on unverified historical rankings coverage

## Goals

- add a new top-level `ensemble` modeling family
- make `ff_opportunity` the required Phase 1 v1 prior source
- make Phase 1 v1 cover QB/RB/WR/TE by default
- blend `ff_opportunity` into weekly player projections only after simulation
- keep uncovered player-weeks strictly neutral
- make the ensemble layer source-agnostic enough that `ff_rankings` can be
  plugged in later without restructuring callers
- keep weekly QB/WR results as the primary success metrics and tie-breaker for
  the first promotion decision
- validate the phase as a marginal comparison:
  - `baseline=defaults`
  - versus `defaults + ensemble`
- update the source-of-truth docs as part of the phase:
  - [`docs/accuracy-roadmap.md`](../../../docs/accuracy-roadmap.md)
  - [`docs/accuracy-stack-audit.md`](../../../docs/accuracy-stack-audit.md)

## Non-Goals

- no upstream usage, target-share, or carry-share mutation
- no changes inside [`GameContextBuilder`](../../../src/fantasy_sim/data/game_context.py)
- no learned weight fitting in v1
- no requirement that `ff_rankings` be historically usable in Phase 1
- no new paid data vendor
- no attempt to make final fantasy-point priors internally consistent with
  stat-level detail columns in v1

Phase 1 v1 is a post-sim projection blend, not a simulator rewrite.

## Recommended Approach

Use a **post-sim opportunity ensemble**.

1. run the current simulator and projection pipeline unchanged
2. load and normalize `ff_opportunity` into a player-week prior table
3. blend the prior onto weekly player projections at the final fantasy-point
   layer
4. recompute ranks after blending
5. treat `ff_rankings` as a disabled future plug-in under the same
   `ensemble` family

This is the smallest approach that:

- preserves clean attribution
- lowers lift and regression risk
- keeps A/B interpretation simple
- leaves a clean insertion point for future prior sources

## Scope Boundary

### In scope

- new `ensemble` config family in [`config/defaults.yaml`](../../../config/defaults.yaml)
- a new loader/normalizer stack under `src/fantasy_sim/data/ensemble/`
- a new post-sim blender under `src/fantasy_sim/scoring/`
- validation coverage, config, and ledger plumbing for the new family
- roadmap and audit updates that reflect current defaults, coverage, and
  Phase 1 sequencing

### Out of scope

- touching existing PFF, usage, vegas, weather, game-script, or TD-tendency
  math
- changing detailed stat columns produced by
  [`build_player_projections`](../../../src/fantasy_sim/scoring/projections.py)
- historical rankings ingestion as part of the v1 promotion gate
- adding a general multi-provider abstraction beyond the minimum needed for the
  future `ff_rankings` plug-in point

## Architecture

### Keep the simulator path unchanged

The existing simulation path should continue to run exactly as it does today:

- build game context
- simulate games
- build weekly player projections

Phase 1 attaches after that path, not inside it.

That means the ensemble layer should operate on the outputs of
[`build_player_projections`](../../../src/fantasy_sim/scoring/projections.py),
not on team distributions or roster shares.

### Add a new `ensemble` family

The new family should parallel the existing config-loader pattern used for
`usage`, `weather`, `vegas`, and `pff`.

At minimum, the family should support:

- `ensemble.enabled`
- `ensemble.ff_opportunity.enabled`
- `ensemble.ff_opportunity.cache_dir`
- `ensemble.ff_opportunity.positions`
- `ensemble.ff_opportunity.feature`
- `ensemble.ff_opportunity.weights`
- `ensemble.ff_opportunity.min_coverage_weeks`
- `ensemble.ff_rankings.enabled`

`ff_rankings` should exist in config from day one so the family shape does not
need to change later, but it should default to disabled and remain outside the
v1 success criteria.

## Components

### 1. `data/ensemble/loader.py`

Responsibility:

- wrap `nflreadpy.load_ff_opportunity(...)`
- cache the raw weekly dataset locally
- expose a small load API for the requested seasons

It should not:

- blend projections
- perform final player matching decisions
- decide promotion eligibility

### 2. `data/ensemble/normalizer.py`

Responsibility:

- convert raw `ff_opportunity` rows into a normalized player-week prior table
- key the normalized output by `(season, week, player_id)`
- filter to the configured position set
- derive the compact prior feature set used by v1
- produce coverage and mapping audit metadata

Recommended v1 prior fields:

- `prior_fpts`
- optional component priors such as receiving or rushing expected points only
  if they are needed for debugging or future extension
- source coverage flags
- source row count and mapping status where useful

The normalized output must be designed so future sources can target the same
join contract.

### 3. `scoring/ensemble.py`

Responsibility:

- join normalized priors onto weekly player projection rows
- apply the configured blend
- recompute rank after blending
- preserve pass-through behavior for uncovered rows

It should not:

- mutate detailed stat columns in v1
- infer missing priors
- silently overwrite simulator output without coverage metadata

### 4. validation integration

[`scripts/validate.py`](../../../scripts/validate.py) and
[`src/fantasy_sim/validation`](../../../src/fantasy_sim/validation) should
treat `ensemble` like other feature families:

- config snapshot records whether it is enabled
- coverage reporting states whether historical data existed for tested seasons
- marginal validation compares `defaults` against `defaults + ensemble`

## Data Flow

The Phase 1 v1 flow should be:

1. simulator builds weekly player projections as normal
2. ensemble loader fetches historical `ff_opportunity` rows for requested
   seasons
3. normalizer maps rows onto nflverse `player_id` keys and emits a compact
   prior table
4. blender joins the prior table to weekly projection rows
5. covered rows are blended
6. uncovered rows pass through unchanged
7. ranks are recomputed after blending
8. season aggregation consumes the blended weekly outputs

This architecture keeps the intervention localized to one clean hook while
letting season-level metrics change naturally through weekly projections.

## Mapping Strategy

Phase 1 should reuse existing repo matching patterns rather than introduce a
second unrelated resolver design.

Recommended policy:

- prefer direct `player_id` joins whenever the source already carries nflverse
  IDs
- if normalization is needed, reuse the repo's existing normalized
  name-and-team matching patterns as the basis for controlled fallback
- if a player-week cannot be mapped cleanly, skip it and mark it uncovered

Guardrails:

- no silent fuzzy match with no audit trail
- no attaching priors to multiple players
- no coercing uncovered rows into pseudo-covered data

If mapping ambiguity remains after normalized matching, the row should be
excluded from v1 blending and counted in coverage diagnostics.

## Blend Policy

Phase 1 v1 should use a fixed, explicit blend at the final fantasy-point layer.

For a covered player-week:

`blended_fpts = sim_fpts * (1 - w_pos) + prior_fpts * w_pos`

Where:

- `w_pos` is position-specific
- `prior_fpts` comes from normalized `ff_opportunity`

For an uncovered player-week:

- `blended_fpts = sim_fpts`

After blending:

- recompute weekly rank
- preserve original detailed stat fields unchanged in v1

### Why not blend stat columns in v1

`ff_opportunity` is being used as a fantasy prior first, not as a fully
resolved stat-distribution source. Mutating stat columns in v1 would create
false precision and make the first A/B result harder to interpret.

## Config Policy

The v1 config should be conservative and explicit.

Recommended defaults:

- `ensemble.enabled: false` until the phase is implemented and validated
- `ensemble.ff_opportunity.enabled: false` by default until promoted
- position-specific weights rather than one global weight
- default position scope is `QB`, `RB`, `WR`, and `TE`
- initial weights stay conservative: `QB 0.35`, `WR 0.25`, `RB 0.15`,
  `TE 0.15`
- weekly `QB` and `WR` remain the primary success metrics and tie-breaker for
  the first promotion decision
- `ensemble.ff_rankings.enabled: false`

### Weight policy

Do not fit weights in v1.

Start with fixed weights that are easy to reason about and tune later only if
the first clean marginal result justifies follow-up work.

### Future `ff_rankings` plug-in contract

The ensemble API should be shaped so that `ff_rankings` can later contribute
another prior table into the same blender without changing:

- the projection caller contract
- the validation entrypoint
- the ledger schema shape

That future work may combine multiple priors internally, but Phase 1 v1 should
not depend on it.

## Coverage And Validation Semantics

Phase 1 must report whether the new source was actually exercised.

Validation coverage should answer:

- was `ensemble.ff_opportunity` enabled?
- did the requested backtest seasons have source rows?
- how much of the tested player-week surface mapped cleanly?
- which rows were skipped as uncovered?

Coverage states should follow the same reporting philosophy as the existing
validation stack:

- `disabled`
- `full`
- `partial`
- `none`

The design should be explicit that `ff_rankings` is:

- present in config
- disabled in v1
- not part of the v1 promotion gate

## Error Handling

Phase 1 should fail closed on ambiguous source semantics and fail neutral on
missing rows.

Rules:

- if `ff_opportunity` cannot be loaded for a requested season set, coverage
  should report `none` or `partial`, not pretend the feature was exercised
- if a source row lacks the required expected-fantasy field, skip it and mark
  it uncovered
- if a row cannot be mapped cleanly to a simulator `player_id`, skip it and
  mark it uncovered
- uncovered player-weeks must pass through unchanged
- do not let one malformed row fail the entire season-level run if the rest of
  the source is usable

The system should prefer honest partial coverage over fragile all-or-nothing
behavior.

## Testing Strategy

### Loader tests

Add focused tests for:

- cached versus uncached `ff_opportunity` loads
- minimal schema expectations for the required v1 fields
- season-scoped loading behavior

### Normalizer tests

Add focused tests for:

- position filtering
- direct player-id mapping
- normalized fallback matching where allowed
- ambiguous mapping resulting in uncovered rows
- missing required source fields resulting in uncovered rows

### Blender tests

Add projection-layer tests for:

- covered rows blend to the expected `fpts`
- uncovered rows remain unchanged
- ranks recompute correctly after blending
- detailed stat columns remain unchanged in v1

### Validation tests

Extend existing validation test patterns to cover:

- `ensemble.ff_opportunity` coverage reporting
- config snapshot inclusion for the new family
- marginal `baseline=defaults` runs recording the new coverage metadata

## Promotion Gate

Phase 1 should be evaluated only as:

- `defaults`
- versus `defaults + ensemble`

The promotion gate is:

- clear weekly `QB` and/or `WR` improvement
- no material season-level regression across the broader QB/RB/WR/TE default
  scope
- documented historical coverage for the exercised backtest seasons

The v1 gate is explicitly **not**:

- "any tiny positive delta"
- "works only when rankings are also added"
- "improves uncovered rows through indirect side effects"

`ff_rankings` should not be part of the v1 success criteria even if the config
surface exists.

## Documentation Requirements

Phase 1 includes mandatory source-of-truth updates.

### `docs/accuracy-roadmap.md`

At phase close, update:

- Phase 1 status
- the v1 scope statement that Phase 1 used `ff_opportunity` only
- any unlocked next-priority work
- any sequencing note about `ff_rankings` being deferred from the first
  promotion decision

### `docs/accuracy-stack-audit.md`

At phase close, update:

- current `ensemble` defaults and parked flags
- actual `ff_opportunity` coverage for backtest seasons
- mapping caveats discovered during implementation
- the fact that `ff_rankings` remains optional/future pending historical
  coverage and schema checks

These doc updates are part of the phase definition, not cleanup work.

## Acceptance Criteria

- a new `ensemble` config family exists with `ff_opportunity` and future
  `ff_rankings` sections
- `ff_opportunity` is the only required v1 prior source
- the simulator path remains unchanged upstream of final weekly projections
- covered player-weeks blend at the final fantasy-point layer
- uncovered player-weeks remain neutral
- weekly ranks recompute after blending
- validation reports historical `ensemble.ff_opportunity` coverage explicitly
- marginal `defaults` versus `defaults + ensemble` validation is the primary
  promotion path
- `ff_rankings` is pluggable later without restructuring the phase interface
- the roadmap and audit docs are updated as part of implementation

## Implementation Notes For The Next Planning Step

The implementation plan should decompose Phase 1 into a small number of
independent work items:

1. config + models for `ensemble`
2. `ff_opportunity` loader/cache
3. normalization + mapping
4. post-sim blending hook
5. validation coverage/ledger integration
6. tests
7. roadmap + audit updates

That breakdown preserves clean attribution and keeps the first A/B result
focused on the value of `ff_opportunity`.
