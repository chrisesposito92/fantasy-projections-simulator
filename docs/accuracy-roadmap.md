# Accuracy Roadmap

Roadmap built from the 2026-04-10 audit and research session.

Companion audit:

- [`docs/accuracy-stack-audit.md`](./accuracy-stack-audit.md)

## Goal

Improve:

- `rank_corr`
- weekly MAE
- season MAE

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

This is now implemented in v1 form and remains the fastest candidate for weekly
QB/WR lift without rewriting the simulator internals, while still covering the
four core fantasy positions by default.

Locally verified `nflreadpy` loaders:

- `load_ff_opportunity()`

These can provide high-signal priors for:

- expected fantasy points
- opportunity quality
- consensus weekly rankings and projections

Future-capable availability also exists for:

- `load_ff_rankings()`

### Status

Implemented and promoted for the broadened QB/RB/WR/TE scope.

The promotion artifact for Phase 1 is:

- `phase-1-ff-opportunity-v1-broadened`

The earlier QB/WR-only run was still useful as a narrow pilot, but the
broadened run is the decision artifact for Phase 1.

### Phase 1 v1 Scope

- `ff_opportunity` only
- default position scope is QB/RB/WR/TE
- post-sim weekly projection blend only
- no upstream usage/share mutation
- `ff_rankings` deferred from the first promotion decision

Current behavior:

- blend external fantasy opportunity priors into weekly QB/RB/WR/TE player projections
- keep uncovered rows neutral rather than forcing a synthetic adjustment
- keep weekly QB/WR accuracy as the primary success metric and tie-breaker
- preserve the existing post-sim promotion gate for marginal validation

### Implemented Behavior

- `ff_opportunity` provides the required Phase 1 v1 source across QB/RB/WR/TE
- `total_fantasy_points_exp` is the current prior feature
- default weights are QB `0.35`, WR `0.25`, RB `0.15`, and TE `0.15`
- joins use nflverse `player_id`
- the blend is applied after simulation, not during game context construction
- `ff_rankings` remains optional future work until historical coverage, schema, and backtest-year checks justify it

### Promotion Gate

- clear weekly QB and/or WR improvement against `baseline=defaults`
- no material regression in season MAE or season rank ordering across the rest of the position groups

This gate is satisfied by the broadened marginal validation run:

- label: `phase-1-ff-opportunity-v1-broadened`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `ensemble.ff_opportunity=full(2022,2023,2024)`
- averages:
  - `rank_corr delta: +0.0271`
  - `weekly_mae delta: -0.548`
  - `season_mae delta: -3.737`

Primary tie-breaker positions also improved strongly in weekly validation:

- QB weekly rank corr `+0.2448`, weekly MAE `-0.919`
- WR weekly rank corr `+0.1658`, weekly MAE `-0.648`

RB and TE also improved in the broadened run, but QB/WR remain the primary
success metrics and tie-breaker.

### Next Priority

Phase 2 is now implemented and promoted in v1.

`ff_rankings` is still available as future ensemble work, but it is not needed
to justify the promoted Phase 1 defaults.

The next implementation priority after Phase 2 is now Phase 3, with tracking
and participation expansion still intentionally deferred to the later tracking
phase instead of being folded into the Phase 2 v1 scope.

## Phase 2: Same-Season Role And Availability Engine

### Status

Implemented and promoted in v1. Manual A/B validation was user-owned and the
promotion decision is now based on the confirmed marginal validation artifact.

This phase now ships as a hybrid design:

- `availability` is a pre-usage roster mutation layer in `GameContextBuilder`
- `role_trend` is a post-sim weekly projection adjustment layer
- `role_trend` runs before the post-sim `ensemble` blend
- both config families gate activation by explicit `positions` lists

This keeps explicit starter / inactive decisions separate from softer
same-season trend nudges.

### Promoted Phase 2 Defaults

The promoted v1 default shape is:

- `availability.enabled: true`
- `availability.injuries.enabled: false`
- `availability.depth_charts.enabled: true`
- `availability.usage_fallback.enabled: true`
- `availability.positions: [QB, RB, WR, TE]`
- `role_trend.enabled: false`

Promotion artifact:

- label: `phase-2-availability-no-injuries-confirm`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `availability=full(2022,2023,2024)`
  - `availability.injuries=disabled`
  - `availability.depth_charts=full(2022,2023,2024)`
  - `availability.usage_fallback=full(2022,2023,2024)`
- averages:
  - `rank_corr delta: +0.0032`
  - `weekly_mae delta: -0.016`
  - `season_mae delta: -0.269`

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

These are now implemented as distinct top-level families rather than being
folded into `usage.*`.

### Core Responsibilities

- detect rising/falling role before the season totals fully catch up
- adjust weekly opportunity priors for players returning from injury
- reduce stale carry/target assumptions for players losing role
- improve same-week starter selection and availability assumptions

### Implemented v1 Scope

- role-trend adjustments for QB/RB/WR/TE
- conservative availability decisions for QB/RB/WR/TE
- per-position enablement via `availability.positions` and `role_trend.positions`
- explicit-signal-first availability:
  - injuries can create hard inactive or limited decisions
  - QB depth charts can create starter / non-starter decisions
  - usage fallback is soft-only
- post-sim `role_trend` adjustment before `ensemble.ff_opportunity`

### Implemented Design

- `availability` handles same-week player availability before downstream usage
  refinement, then re-normalizes roster shares
- `role_trend` adjusts weekly projections after simulation and before ensemble
- the split is intentional: availability owns inactive / limited / starter
  logic, while role trend owns directional projection drift

### Deferred From Phase 2 v1

- participation/tracking-driven hard decisions
- non-QB hard starter / promotion logic from depth charts alone
- broader route-participation and charting features that belong in Phase 4
- any attempt to let usage-only evidence create inactive or starter-out calls

### Manual Validation Handoff

The user owned the Phase 2 A/B runs and produced the promotion artifact above.
Future planners should treat that artifact as the Phase 2 decision record.

## Phase 3: Historical Market Intelligence

### Status

Implemented in v2 and promoted to the default stack.

The earlier `phase-3-market-history-v1` artifact is now superseded by the
market-native The Odds API integration. After rewiring `market_history` around
`player_markets_<season>_<snapshot_label>.parquet`, building the The Odds API
to nflverse crosswalk, and rerunning covered-season validation, the Phase 3
evidence is positive enough to turn `market_history` on by default.

### Phase 3 v1 Scope

- `market_history` implemented as a post-sim layer
- processed market-native cache built for 2023 and 2024 validation seasons,
  with 2025 local data also present
- promotion evidence evaluated with explicit covered-season reporting
- 2022 treated as no-data / uncovered rather than neutral evidence

### Promotion Artifact

Phase 3 promotion artifact:

- label: `phase-3-market-history-v2-real-schema`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- validation coverage: `market_history=partial(2023,2024)`
- covered seasons: `2023, 2024`
- uncovered seasons: `2022`
- promotion evidence scope: `covered_only`

```text
rank_corr delta:  +0.0075
weekly_mae delta: -0.065
season_mae delta: -1.288
```

Artifact interpretation:

- the stack-wide average summary still includes 2022, but that season remains
  no-data for `market_history`
- market-specific promotion evidence therefore continues to use the explicit
  `covered_only` readout instead of folding 2022 into the averages as neutral
  evidence
- the covered-only marginal result is positive on all three top-line metrics,
  so Phase 3 is promoted despite the missing 2022 backfill

Secondary confirmation artifact:

- label: `phase-3-market-history-v2-real-schema-qb-wr`
- covered-only deltas:
  - `rank_corr delta:  +0.0080`
  - `weekly_mae delta: -0.071`
  - `season_mae delta: -1.301`

Primary tie-breaker positions also improved in weekly validation:

- QB weekly rank corr `+0.0086`, weekly MAE `-0.049`
- WR weekly rank corr `+0.0144`, weekly MAE `-0.045`

Promoted Phase 3 defaults:

- `market_history.enabled: true`
- `market_history.snapshot_label: close_core8`
- keep `market_history` between `role_trend` and `ensemble.ff_opportunity`
- keep `role_trend.enabled: false` until a later phase revalidates it

### Follow-On Work

- backfill `2022` market-history data so promotion evidence can cover all three
  backtest seasons with the same market-native path
- consider open-snapshot or wider market-set expansion only after the promoted
  close-only path has been in use long enough to judge its real value
- keep both as follow-on work, not blockers for moving on to Phase 4

## Phase 4: Tracking And Charting Expansion

### Status

Implemented in code, backfilled for `2022-2024`, and validated slice-by-slice.
Not promoted.

Required Phase 4 tracking inputs were backfilled with:

- `participation_2022.parquet`, `participation_2023.parquet`, `participation_2024.parquet`
- `ftn_charting_2022.parquet`, `ftn_charting_2023.parquet`, `ftn_charting_2024.parquet`
- `ngs_passing_2022.parquet`, `ngs_passing_2023.parquet`, `ngs_passing_2024.parquet`
- `ngs_rushing_2022.parquet`, `ngs_rushing_2023.parquet`, `ngs_rushing_2024.parquet`

Phase 4 promotion rule:

- promote only if at least one of QB/RB/WR/TE improves materially
- require the other core positions to hold without material regression
- do not promote on flat "everything merely held" evidence

### Artifacts Run

`phase-4-receiver-participation-v1`

- `rank_corr delta:  -0.0006`
- `weekly_mae delta: +0.007`
- `season_mae delta: +0.072`
- Did not clear the promotion rule. WR weekly rank corr moved slightly positive, but the average readout regressed and QB/RB/TE did not hold cleanly enough to justify promotion.

`phase-4-rb-efficiency-v1`

- `rank_corr delta:  -0.0003`
- `weekly_mae delta: +0.000`
- `season_mae delta: -0.063`
- Did not clear the promotion rule. The season MAE average improved slightly, but the overall readout was effectively flat to negative and did not produce a material core-position win.

`phase-4-qb-context-v1`

- `rank_corr delta:  +0.0002`
- `weekly_mae delta: +0.007`
- `season_mae delta: +0.047`
- Did not clear the promotion rule. The average rank-correlation move was nominal while both MAE averages regressed.

### Bundle Decision

The combined Phase 4 bundle was not run.

Reason:

- none of the isolated slices produced materially positive evidence
- two slices regressed on average
- the remaining slice was effectively flat and still regressed at least one core metric
- that is not strong enough to justify taking interaction risk on the combined bundle

### Verification

Verification command run after the doc updates:

```bash
uv run pytest tests/test_data/test_tracking tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py -v
```

Result:

- `161 passed`

### Current Phase 4 Readout

- `tracking` remains a valid family in code, but it should stay default-off on current evidence
- the new backfill means data coverage is no longer the blocker for this phase
- the next useful Phase 4 work is not "run the bundle"; it is a narrower redesign or retune of individual tracking slices
- the receiver-participation and QB-context runs both logged the same small snap crosswalk gap: `WillRo08` unmatched at `0.2%`

### Next Priority

Phase 4 is no longer the next default-on candidate.

What follows from the current artifact set:

- keep `tracking.enabled: false`
- do not run the combined bundle from this slice set
- move the main planning priority to Phase 5, or come back to Phase 4 only with a narrower hypothesis for one slice at a time

## Phase 5: PFF Granularity V2

### Status

- Phase 5A `WR/TE Depth-Role V1`: implemented, validated, not promoted
- Phase 5B `WR/TE efficiency v2`: implemented, validated, not promoted
- Phase 5C `QB split engine`: implemented, validated, not promoted
- Phase 5D `RB scheme-fit engine`: implemented, validated, not promoted

### Phase 5A Scope

- `receiving_depth` only
- `WR` and `TE` only
- pre-sim role/volume only
- `target_share` and `air_yards_share` only
- no catch-rate or receiving-efficiency mutation

### Validation Artifact

- label: `phase-5-depth-role-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.depth_role=full(2022,2023,2024)`
  - `pff.depth_role.wr=full(2022,2023,2024)`
  - `pff.depth_role.te=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  -0.0005`
  - `weekly_mae delta: +0.002`
  - `season_mae delta: +0.013`

### Phase 5B Scope

- `receiving_depth` only
- `WR` and `TE` only
- pre-sim efficiency only
- `catch_rate`
- proportional `red_zone_catch_rate`
- base `receiving_yards_dist`
- no volume changes

### Phase 5B Validation Artifact

- decision artifact label: `phase-5-depth-role-efficiency-v2-activated`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.depth_role=full(2022,2023,2024)`
  - `pff.depth_role.wr=full(2022,2023,2024)`
  - `pff.depth_role.te=full(2022,2023,2024)`
  - `pff.depth_role.efficiency=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  +0.0000`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: +0.030`

Superseded setup artifact:

- `phase-5-depth-role-efficiency-v2`
- top-line deltas:
  - `rank_corr delta:  +0.0002`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: -0.017`
- this earlier row is useful as a setup/debug artifact, but it is not the
  Phase 5B decision record because the coverage header left the depth-role
  family disabled

### Phase 5C Scope

- `passing_detail` only
- QB-specific pass-catcher efficiency splits
- pre-sim efficiency only
- implemented through `pff.qb_split`
- no promotion from the first marginal validation artifact

### Phase 5C Validation Artifact

- decision artifact label: `phase-5-qb-split-v1-postfix`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.qb_split=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  +0.0000`
  - `weekly_mae delta: +0.006`
  - `season_mae delta: +0.020`

Superseded pre-fix artifact:

- `phase-5-qb-split-v1`
- top-line deltas:
  - `rank_corr delta:  +0.0005`
  - `weekly_mae delta: -0.000`
  - `season_mae delta: -0.028`
- this earlier row is useful as pre-fix evidence, but it is not the current
  Phase 5C decision record for the branch after the qb-split follow-up fixes
- verdict:
  - implemented and validated
  - not promoted
  - keep `pff.qb_split.enabled: false`

### Phase 5D Scope

- `rushing_direction`
- `offense_run_blocking`
- RB-specific rushing-efficiency only
- pre-sim `rushing_yards_dist` only
- implemented through `pff.rb_scheme_fit`
- no promotion from the first marginal validation artifact

### Phase 5D Validation Artifact

- decision artifact label: `phase-5-rb-scheme-fit-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage:
  - `pff.rb_scheme_fit=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  +0.0018`
  - `weekly_mae delta: -0.003`
  - `season_mae delta: -0.040`
- verdict:
  - implemented and validated
  - not promoted
  - keep `pff.rb_scheme_fit.enabled: false`
  - inferred from the run: the top-line lift is too small to justify promotion and weekly QB/WR both regressed

## Phase 6: Re-open Parked Levers Under The New Data Regime

### Status

In progress.

Slice A measurement cleanup is complete. The next work is isolated marginal
retests of the still-parked default-off levers.

### Phase 6 Queue

- `pff.team_context`
- `usage.ngs`
- `goal_line_concentration`
- `usage.route_rate`

### Not Part Of The Phase 6 Queue

- `td_tendency`
- `td_tendency.i5_enabled`

Reason:

- `td_tendency.enabled: true`
- `td_tendency.i5_enabled: true`

### Execution Rule

- Slice A measurement cleanup is complete
- the repo is ready for isolated retests against `baseline=defaults`
- then retest one parked lever at a time against `baseline=defaults`
- do not bundle Phase 6 levers before an isolated retest wins

### `pff.team_context` Retest Artifact

- label: `phase-6-pff-team-context-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `pff.team_context=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  -0.0000`
  - `weekly_mae delta: -0.001`
  - `season_mae delta: -0.082`
- verdict:
  - keep `pff.team_context.enabled: false` because the isolated retest did not show clear weekly QB/WR improvement or meaningful top-line lift

### `usage.ngs` Retest Artifact

- label: `phase-6-usage-ngs-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `usage.ngs=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  -0.0001`
  - `weekly_mae delta: -0.006`
  - `season_mae delta: -0.037`
- verdict:
  - keep `usage.ngs.enabled: false` because the isolated retest did not produce meaningful promotable top-line lift

### `goal_line_concentration` Retest Artifact

- label: `phase-6-goal-line-concentration-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `goal_line_concentration=full(2022,2023,2024)`
- result:
  - `rank_corr delta:  -0.0019`
  - `weekly_mae delta: -0.015`
  - `season_mae delta: -0.041`
- verdict:
  - keep `goal_line_concentration.enabled: false` because the isolated retest did not clearly improve weekly QB/WR ordering enough to justify promotion

## Accuracy Config Families

Accuracy work is now split across explicit top-level families instead of
overloading `usage`:

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

- Phase 6 retests of parked levers under the new regime
- Phase 3 if historical market data can be acquired cleanly
- Phase 5 as the deeper PFF granularity track
- Phase 4 follow-on only if a narrower tracking slice is redesigned and re-validated cleanly

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

1. Phase 6 Slice B4: `usage.route_rate` marginal retest
2. No additional parked-lever retests remain in the current Phase 6 queue after B4

## Research Anchors

Useful external references for future planning sessions:

- [nflreadpy load functions](https://nflreadpy.nflverse.com/api/load_functions/)
- [nflreadpy data sources](https://nflreadpy.nflverse.com/)
- [The Odds API historical odds](https://the-odds-api.com/historical-odds-data/)
- [The Odds API NFL markets](https://the-odds-api.com/sports/nfl-odds.html)
- [SportsDataIO NFL workflow](https://sportsdata.io/developers/workflow-guide/nfl)
- [SportsDataIO depth charts guide](https://support.sportsdata.io/hc/en-us/articles/9916710244887-Process-Guide-Depth-Charts)
