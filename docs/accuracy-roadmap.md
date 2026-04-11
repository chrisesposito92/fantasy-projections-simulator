# Accuracy Roadmap

Roadmap built from the 2026-04-10 audit and research session.

Companion audit:

- [`docs/accuracy-stack-audit.md`](./accuracy-stack-audit.md)

## Goal

Improve:

- `rank_corr`
- weekly MAE
- season MAE

Primary tie-breaker:

- weekly QB/WR accuracy first

Guardrails:

- no material season-level regression in any position
- no promotion without trustworthy data coverage and marginal validation

## Operating Rules

Every future phase should follow these rules:

1. Validate both `bare` vs current defaults and `defaults` vs `defaults + change`.
2. Record data coverage by season and week for every external signal.
3. Promote only after weekly QB/WR metrics improve or hold while season metrics do not regress materially.
4. Keep 2025 as the eventual frozen promotion holdout after the evaluation path is fixed.
5. Re-open previously parked levers only after the phase-0 measurement fixes land.
6. At the end of every phase, update both:
   - [`docs/accuracy-roadmap.md`](./accuracy-roadmap.md)
   - [`docs/accuracy-stack-audit.md`](./accuracy-stack-audit.md)
7. Those doc updates are part of the phase definition, not optional cleanup.

## Documentation Maintenance

Every implementation phase should close with a documentation pass that keeps the
two source-of-truth docs current.

### `accuracy-roadmap.md` must be updated with:

- phase status
- any change in priority ordering
- newly unlocked or de-scoped follow-up work
- any revised promotion gates or sequencing notes

### `accuracy-stack-audit.md` must be updated with:

- current defaults and parked flags
- runtime ordering changes
- newly available local data or backfilled history
- resolved or newly discovered validation caveats
- any changes to which evidence is considered trustworthy

### Rule For Future Sessions

Fresh phase-planning sessions should assume these two docs are the canonical
handoff. That only works if each completed phase leaves both docs current.

## Ranked Phases

Scoring:

- `Lift`: implementation effort/cost, `1` easiest and `10` hardest
- `Accuracy Upside`: expected impact on `rank_corr`, weekly MAE, season MAE
- `Eval Leverage`: how much the phase improves trust in future experiments

| Rank | Phase | Lift | Accuracy Upside | Eval Leverage |
|---|---:|---:|---:|---:|
| 0 | Validation Integrity And Data Completeness | 3 | 2 | 10 |
| 1 | External Fantasy Priors And Opportunity Ensemble | 4 | 9 | 7 |
| 2 | Same-Season Role And Availability Engine | 5 | 9 | 8 |
| 3 | Historical Market Intelligence | 6 | 8 | 8 |
| 4 | Tracking And Charting Expansion | 7 | 8 | 6 |
| 5 | PFF Granularity V2 | 8 | 7 | 6 |
| 6 | Re-open Parked Levers Under The New Data Regime | 3 | 5 | 7 |

## Phase 0: Validation Integrity And Data Completeness

### Status

Implemented.

The Phase 0 validation path now:

- threads `td_tendency_config` through bare dual-arm validation
- treats `baseline=defaults` as a first-class marginal validation path
- records schema/comparison metadata and coverage summaries on new labeled runs
- prints coverage-aware run headers so no-data and partial-data cases are explicit

What Phase 0 did **not** do:

- regenerate or backfill historical ledger rows
- add repeated-seed or confidence-summary execution

### Why First

The current measurement path can overstate or misclassify gains because:

- `td_tendency` is not threaded through bare dual-arm validation
- historical props do not exist for 2022-2024
- the unified ledger has no `baseline=defaults` entries
- config snapshots span multiple schema eras

### Deliverables

- Thread `td_tendency_config` through the bare dual-arm path in `validate.py`
- Treat `baseline=defaults` as a first-class marginal validation path, alongside bare-vs-defaults comparisons
- Add explicit per-run coverage reporting for:
  - props
  - PFF inputs
  - weather
  - usage signals
  - any new external data source
- Record config-schema version in the unified ledger
- Record comparison metadata in the unified ledger so each row can be interpreted as:
  - total-lift evidence
  - marginal-lift evidence
  - coverage-aware evidence
  - schema-era evidence
- Update both source-of-truth docs as part of the phase:
  - [`docs/accuracy-roadmap.md`](./accuracy-roadmap.md)
  - [`docs/accuracy-stack-audit.md`](./accuracy-stack-audit.md)

### Deferred From This Phase

- repeated seeds
- multi-run confidence summaries

### Planning Notes

- This phase should not change projections directly
- It should change what evidence future phases are allowed to claim
- If a signal has zero historical coverage, the validation output should say so explicitly

### Promotion Gate

- After this phase, the ledger must contain clean `baseline=defaults` entries for all new experiments
- This gate is satisfied only by new post-Phase-0 runs; historical ledger rows were not regenerated.
- A future planner should be able to tell whether a result is:
  - total lift
  - marginal lift
  - partial-data evidence
  - no-data / not exercised

## Phase 1: External Fantasy Priors And Opportunity Ensemble

### Why High Priority

This is the fastest path to likely weekly QB/WR lift without first rewriting the
simulator internals.

Locally verified nflreadpy loaders:

- `load_ff_opportunity()`
- `load_ff_rankings()`

These can provide high-signal priors for:

- expected fantasy points
- opportunity quality
- consensus weekly rankings and projections

### Candidate Design

Build a new top-level config family:

- `ensemble`

Core idea:

- treat external fantasy projections/opportunity metrics as priors or features
- blend them into weekly player projections after simulation, or use them to
  bias player-level usage/value estimates upstream

### Likely v1 Inputs

- expected fantasy points
- expected opportunity share
- consensus ranking
- consensus projection level

### Likely v1 Outputs

- blended weekly fantasy-point projection
- optional blended rank prior by position

### Planning Questions For The Future Session

- blend at the final projection layer or inside player-model construction?
- use one ensemble weight globally or position-specific weights?
- keep the ensemble as a pure post-sim rank/projection layer first, then move upstream later?

### Promotion Gate

- clear weekly QB and/or WR improvement against `baseline=defaults`
- no material regression in season MAE or season rank ordering

## Phase 2: Same-Season Role And Availability Engine

### Why High Priority

A major weekly miss source is not "talent" but role drift:

- injuries
- starter changes
- snap spikes
- route spikes
- target spikes
- team changes in who is actually playing

Locally available or verified inputs:

- weekly player stats
- weekly rosters
- snap counts
- depth charts
- `nflreadpy.load_injuries()`

### Candidate Config Families

- `role_trend`
- `availability`

### Core Responsibilities

- detect rising/falling role before the season totals fully catch up
- adjust weekly opportunity priors for players returning from injury
- reduce stale carry/target assumptions for players losing role
- improve same-week starter selection and availability assumptions

### Suggested v1 Scope

Focus on QB/WR first:

- QB starter certainty
- WR route/target trend acceleration
- WR injury return ramp
- WR depth-chart promotion / demotion

Then extend to:

- RB committee drift
- TE route participation drift

### Planning Notes

- This should remain separate from the existing `usage` block
- It is broader than snap-share blending and should not be forced into `usage.*`
- A future planning session should decide whether adjustments are:
  - roster-share mutations
  - final-week projection overlays
  - or a hybrid

## Phase 3: Historical Market Intelligence

### Why High Priority

The current props engine is structurally useful, but the historical data
coverage is not there for the main backtest seasons.

Observed locally:

- props parquet exists for 2025 only
- no props parquet for 2022-2024

### Candidate Config Family

- `market_history`

### Core Work

- backfill 2023-2024 historical props and line snapshots
- extend current props work from a single-point prior into a richer market signal

### Candidate Features

- closing line
- opening line
- open-to-close movement
- book dispersion / disagreement
- anytime-TD implied probability
- alternate-line shape if available
- team total and spread interaction with player markets

### Planning Questions For The Future Session

- whether the historical source should be The Odds API, another provider, or an internal stored feed
- whether line movement is modeled as:
  - a direct player prior
  - a confidence multiplier
  - or a disagreement/noise filter

### Promotion Gate

- must first prove historical data coverage for the backtest seasons
- then must beat the current stack on marginal weekly validation

## Phase 4: Tracking And Charting Expansion

### Why High Priority

The locally installed data surface is materially larger than what the project
uses today.

Verified loaders:

- `load_nextgen_stats(..., stat_type='passing')`
- `load_nextgen_stats(..., stat_type='rushing')`
- `load_ftn_charting()`
- `load_participation()`

### Candidate Config Family

- `tracking`

### Candidate Signals

- QB under-pressure vs clean-pocket splits
- QB blitz splits
- RB rushing over expected or efficiency over expected
- route participation and route share
- catchable target quality
- no-huddle pace
- RPO / play-action tendencies
- formation or personnel tendencies if available in FTN charting

### Suggested Priority Within The Phase

1. QB pressure/blitz splits
2. WR route participation and catchable-target quality
3. RB rushing efficiency-over-expected
4. team no-huddle / play-action context

### Planning Notes

- keep this separate from `usage`
- design as a tracking/charting layer with its own feature registry and coverage reporting

## Phase 5: PFF Granularity V2

### Why It Still Ranks High

PFF is already the deepest proprietary source in the stack, but the project is
using only a fraction of what has been scraped and processed locally.

Most promising underused local assets:

- `passing_detail`
- `receiving_depth`
- `rushing_direction`
- gap/zone run-blocking splits

### Candidate Uses

- QB split-dependent efficiency profiles from `passing_detail`
- WR/TE depth-role modeling from `receiving_depth`
- RB run-direction and scheme fit from `rushing_direction`
- gap vs zone line fit using `offense_run_blocking`
- richer goal-line and red-zone role priors from fantasy and depth tables

### Suggested Internal Breakdown

#### 5A. QB PFF Split Engine

- clean pocket vs pressure
- blitz vs no blitz
- short/intermediate/deep efficiency

#### 5B. WR/TE Depth Role Engine

- behind/short/medium/deep route profile
- direction and alignment role stability
- target-quality-conditioned weekly role archetypes

#### 5C. RB Scheme Fit Engine

- gap vs zone blocker environment
- run-direction tendencies
- player fit to line profile

### Planning Notes

- This phase has strong upside, but the feature design needs discipline
- Do not dump all granular columns into one monolithic "better PFF" layer
- Split by QB / WR-TE / RB sub-engines so failed ideas can be isolated cleanly

## Phase 6: Re-open Parked Levers Under The New Data Regime

### Why This Phase Exists

Some current disabled features were tested under:

- older defaults
- weaker data coverage
- weaker measurement discipline

They should be treated as parked, not dead.

### Re-test Queue

- `td_tendency`
- `i5`
- `goal_line_concentration`
- `usage.route_rate`
- `usage.ngs`
- `pff.team_context`
- coverage v2 ideas

### Rule

Do not re-open these until:

- phase 0 is complete
- and at least one richer input phase has landed

That keeps the retest from becoming a noisy rerun of earlier sweeps.

## New Config Families To Add

Future planners should use new top-level families instead of overloading
`usage`:

- `ensemble`
- `role_trend`
- `availability`
- `market_history`
- `tracking`

Reason:

- each represents a distinct data source and modeling philosophy
- each needs its own enable flag, coverage reporting, and validation lifecycle

## Suggested Execution Order

### Mandatory first

- Phase 0

### Best next parallel split after phase 0

- Phase 1 for ensemble priors
- Phase 2 for same-season role and availability

### Then

- Phase 3 if historical market data can be acquired cleanly
- Phase 4 and Phase 5 as deeper model expansion tracks

### Last

- Phase 6 retests of parked levers under the new regime

## Success Definition

The roadmap is successful if future phases produce:

- repeatable marginal lift against current defaults
- better weekly QB/WR ordering
- lower weekly MAE without masking regressions in season totals
- evaluation outputs that clearly distinguish:
  - real signal
  - no-data neutral behavior
  - and apples-to-oranges comparisons

## Immediate Next Planning Targets

If only one or two follow-up planning sessions are opened next, the best order is:

1. Phase 0: validation integrity and coverage accounting
2. Phase 1: external fantasy priors and opportunity ensemble
3. Phase 2: same-season role and availability engine

## Research Anchors

Useful external references for future planning sessions:

- [nflreadpy load functions](https://nflreadpy.nflverse.com/api/load_functions/)
- [nflreadpy data sources](https://nflreadpy.nflverse.com/)
- [The Odds API historical odds](https://the-odds-api.com/historical-odds-data/)
- [The Odds API NFL markets](https://the-odds-api.com/sports/nfl-odds.html)
- [SportsDataIO NFL workflow](https://sportsdata.io/developers/workflow-guide/nfl)
- [SportsDataIO depth charts guide](https://support.sportsdata.io/hc/en-us/articles/9916710244887-Process-Guide-Depth-Charts)
