# Phase 3 Market History Design

Date: 2026-04-12
Status: Approved design
Phase: 3
Topic: Historical market intelligence v1

## Objective

Add a new `market_history` layer that uses historical market inputs where
coverage is real, improves weekly projection accuracy, and does not let
uncovered seasons silently distort conclusions.

Phase 3 v1 is explicitly coverage-gated around `2023-2024` historical market
inputs. `2022` is not a blocker for the phase, but it must never be treated as
fake neutral evidence for the market layer.

## Verified Current State

This design was based on a code-and-data verification pass against the current
repo and local stores, not just the audit docs.

### Still true in code

- Phase 2 defaults are live:
  - `availability.enabled: true`
  - `availability.injuries.enabled: false`
  - `availability.depth_charts.enabled: true`
  - `availability.usage_fallback.enabled: true`
  - `role_trend.enabled: false`
- `role_trend` is a post-sim layer that runs before `ensemble` when enabled.
- `GameContextBuilder` order is still, in substance:
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
  - runtime game script attachment
- Non-detail `week`, `season`, `game`, validation, and backtest flows use the
  shared post-sim projection-layer path.
- `player` and `--detail` flows still bypass post-sim layers.
- `DataLoader` wraps `injuries` and `depth_charts`.
- `DataLoader` does not yet wrap `participation` or `ftn_charting`.

### Still true in local data

- `ff_opportunity` cache exists for `2022-2024`.
- Local props parquet exists for `2025` only.
- Historical props parquet does not exist locally for `2022-2024`.
- NFL processed PFF coverage is present for the currently relevant core tables
  from `2018-2025`.
- High-granularity NFL PFF tables such as `passing_detail`,
  `receiving_depth`, `rushing_direction`, `offense_run_blocking`, and
  `offense_pass_blocking` are present from `2018-2025`.
- The weather cache exists locally, but validation still treats weather as an
  API-backed covered input rather than a purely local-file requirement.

### Audit wording that should be updated later

- The audit should explicitly list:
  - `availability.depth_charts.enabled: true`
  - `availability.usage_fallback.enabled: true`
- Phase 3 wording should reflect that `2023-2024` is the minimum in-scope
  backfill for v1, not a hidden `2022-2024` hard requirement.
- PFF inventory wording should use the current local counts:
  - `190` NFL parquet files
  - `105` NCAA parquet files
  - one stray `.DS_Store`

## Phase 3 v1 Scope

Phase 3 v1 adds a new `market_history` layer for historical player-market
inputs used in backtests and validation.

It owns:

- a new top-level `market_history` config family
- `2023-2024` historical market ingestion and local caching
- canonical player-week market rows keyed to nflverse `player_id`
- richer historical market-derived features than the current single-consensus
  props prior, limited to fields that truly exist in stored history
- covered-season-only market evaluation
- explicit coverage reporting and ledger metadata
- required roadmap and audit updates at phase close

It does not own:

- `2022` backfill as a prerequisite for phase completion
- a `GameContextBuilder` rewrite
- replacement of the current `vegas.props` path
- any design that hides uncovered seasons inside blended promotion averages

## Evidence Contract

These rules are part of the phase definition, not optional reporting polish.

- Market-specific readouts are evaluated only on covered seasons.
- `2022` must be reported as `no-data` / `uncovered`.
- `2022` must not be treated as neutral market evidence.
- `2022` must not be folded into covered-season averages for the market layer.
- Stack-wide validation can still show the normal season set.
- Promotion decisions for the market layer must be based on covered-season
  evidence only.
- `2022` backfill should be recorded as follow-on work, not as a hidden blocker
  for Phase 3 v1.

The practical result is that Phase 3 v1 may ship if the covered-season evidence
for `2023-2024` is strong and trustworthy, even while `2022` remains uncovered
for the market layer.

## Recommended Approach

Use a coverage-gated `2023-2024` market-history v1 with explicit
partial-coverage evaluation.

This was chosen over:

- a stricter split-regime design that would add more evaluation overhead
- an ingestion-only phase that would avoid risk but delay actual accuracy lift

This approach preserves momentum while keeping the evidence honest.

## Architecture

### New top-level family

Add a new top-level `market_history` family instead of overloading
`vegas.props`.

Rationale:

- `vegas.props` assumes a single per-week consensus line and mutates player
  models during context build.
- Phase 3 needs coverage-gated historical evaluation and should remain easy to
  isolate in marginal A/B runs.
- A separate family makes it possible to reason about market evidence without
  conflating it with live/forward props behavior.

### Recommended modules

- `src/fantasy_sim/data/market_history/config.py`
  - load config into typed models
- `src/fantasy_sim/data/market_history/models.py`
  - define config and canonical row/feature types
- `src/fantasy_sim/data/market_history/loader.py`
  - read season/week keyed historical market parquet
  - return canonical player-week rows
  - expose coverage by season, week, and market type
- `src/fantasy_sim/data/market_history/features.py`
  - convert raw stored history into canonical features
- `src/fantasy_sim/scoring/market_history.py`
  - apply the covered-player-week market adjustment post-sim

### v1 feature surface

Only features with reliable historical coverage should be enabled in v1.
Candidate features include:

- closing line
- opening line
- open-to-close movement
- book dispersion or disagreement
- anytime-TD implied probability

Do not fabricate features that are absent from the stored history. Missing raw
inputs should downgrade coverage, not trigger synthetic neutral values.

## Runtime Placement

Keep `vegas.props` unchanged for now.

Phase 3 v1 should be a post-sim layer, not a pre-sim roster mutation inside
`GameContextBuilder`.

Recommended shared ordering:

1. `role_trend`
2. `market_history`
3. `ensemble.ff_opportunity`

Why:

- `role_trend` reflects same-season role drift from internal data.
- `market_history` adds week-specific external market intelligence on top of
  that simulated baseline.
- `ensemble.ff_opportunity` remains the final broad fantasy prior unless later
  evidence justifies changing the order.

This ordering must be shared across:

- validation
- backtest
- non-detail `week`
- non-detail `season`
- non-detail `game`

`player` and `--detail` flows should continue to bypass post-sim layers in v1
unless a later phase intentionally changes that behavior.

## Data Contract

### Coverage target

Required for Phase 3 v1:

- historical market coverage for `2023`
- historical market coverage for `2024`

Not required for Phase 3 v1:

- historical market coverage for `2022`

### Storage shape

Store historical market snapshots in a new local store separate from the
current live-style props cache. The shape should support reproducible backtests
and easy coverage inspection.

Recommended properties:

- parquet files keyed by `season` and `week`
- canonical player identity resolved to nflverse `player_id`
- explicit storage of source coverage fields needed to judge whether a feature
  is usable

### Relationship to current props cache

The current props path remains a separate runtime surface for existing
`vegas.props` behavior. Phase 3 v1 should not repurpose `~/.fantasy-sim/pff/props`
as if it were already a suitable historical market-history store.

## Validation Design

### Stack-wide summary

The existing stack-wide validation output can still show the normal season set.
For standard validation runs that means the usual backtest seasons may still
appear together.

However, the market layer must be reported as partially covered, not implicitly
active for all displayed seasons.

### Market-specific readout

Add a separate market-layer readout computed only on covered seasons.

Required behavior:

- covered seasons are listed explicitly
- uncovered seasons are listed explicitly
- market-layer averages are computed only from covered seasons
- the run is clearly marked as partial coverage when uncovered seasons exist

Required v1 example semantics:

- covered seasons: `2023, 2024`
- uncovered seasons: `2022`
- promotion evidence scope: `covered_only`

### Forbidden behavior

The validation path must not:

- include `2022` inside market-specific averages
- treat `2022` as an implied zero-delta season
- suppress uncovered-season status from headers, summaries, or ledger metadata

### Promotion rule

Promotion decisions for `market_history` are based on covered-season evidence
only.

That means the phase can be promoted if:

- `2023-2024` covered-season evidence is positive and trustworthy
- no material regressions appear in the relevant covered-season metrics
- uncovered `2022` is reported clearly rather than hidden

## Ledger And Coverage Metadata

Extend validation coverage and ledger recording so Phase 3 runs can be
interpreted correctly.

Required additions:

- `market_history.coverage_status`
- `market_history.covered_seasons`
- `market_history.uncovered_seasons`
- feature-specific coverage where needed
- a flag or metadata field equivalent to:
  - `promotion_evidence_scope=covered_only`

The run header and ledger should make it obvious whether a market-layer result
is:

- fully covered
- partially covered
- uncovered and therefore not exercised

## Testing

### Loader tests

- missing files return an empty or explicit no-data state
- `2023-2024` season/week discovery is correct
- canonical player identity resolves to nflverse `player_id`

### Feature tests

- only historically backed raw fields produce enabled features
- missing raw fields downgrade coverage rather than fabricating values
- feature-specific coverage is surfaced correctly

### Projection-layer tests

- shared post-sim ordering is `role_trend -> market_history -> ensemble`
- non-detail flows use the shared ordering
- `player` and `--detail` continue to bypass post-sim layers in v1

### Validation tests

- market-specific readouts use covered seasons only
- `2022` is reported as `no-data` / `uncovered`
- `2022` is excluded from covered-only averages
- ledger metadata records covered and uncovered seasons correctly

### Regression evidence

At least one labeled Phase 3 marginal validation artifact should exist after
implementation, and its output must explicitly call out covered-only promotion
evidence.

## Documentation Close-Out

Phase 3 is not complete until both source-of-truth docs are updated.

### `docs/accuracy-roadmap.md`

Update with:

- Phase 3 status
- the next priority after Phase 3
- the covered-season promotion rule for `market_history`
- `2022` backfill listed as follow-on work rather than a blocker

### `docs/accuracy-stack-audit.md`

Update with:

- current defaults and parked status for `market_history`
- runtime placement relative to `role_trend` and `ensemble`
- current data coverage and uncovered-season caveats
- the verified local data counts and any wording corrections from this design

## Follow-On Work

Not part of Phase 3 v1, but should be documented as future work:

- `2022` historical market backfill if a credible source is found
- expansion beyond the v1 market feature set
- any decision to merge or reconcile `market_history` with live `vegas.props`
- any later decision to move market logic upstream into simulation inputs

## Success Criteria

Phase 3 v1 is successful if it delivers all of the following:

- a new isolated `market_history` family
- reliable `2023-2024` historical market coverage
- explicit partial-coverage validation behavior
- no fake-neutral treatment of uncovered `2022`
- covered-only promotion evidence for the market layer
- roadmap and audit docs updated at phase close

## Out of Scope

- using `2022` absence as a blocker for v1
- blending uncovered seasons into market-layer promotion metrics
- broad tracking or participation expansion
- PFF granularity v2 work
- refactoring `GameContextBuilder` beyond what is required to preserve shared
  projection-layer ordering
