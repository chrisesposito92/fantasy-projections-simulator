# Accuracy Stack Audit

Research snapshot updated through the Phase 6 measurement-cleanup pass.

This document is meant to be the durable "current state" companion to
[`docs/accuracy-roadmap.md`](./accuracy-roadmap.md). It captures what is
actually active in code, what has been built but parked, what data is present
locally, and which evaluation caveats should be fixed before trusting new A/B
results.

## Primary Goal

Improve:

- `rank_corr`
- weekly MAE
- season MAE

Tie-breaker preference for future work:

- weekly QB/WR accuracy first
- then preserve or improve season totals and the rest of the position groups

## Current Defaults

Active in `config/defaults.yaml` as of this audit:

- `ensemble.enabled: true`
- `ensemble.ff_opportunity.enabled: true`
- `ensemble.ff_rankings.enabled: false`
- `pff.enabled: true`
- `pff.tier_engine.enabled: true`
- `pff.matchup.enabled: true`
- `pff.coverage.enabled: true`
- `pff.qb_split.enabled: false`
- `pff.depth_role.enabled: false`
- `pff.depth_role.efficiency.enabled: false`
- `pff.rb_scheme_fit.enabled: false`
- `pff.kicker.enabled: true`
- `pff.dst_baseline.enabled: true`
- `weather.enabled: true`
- `vegas.enabled: true`
- `vegas.props.enabled: true`
- `usage.enabled: true`
- `usage.cpoe.enabled: true`
- `tracking.enabled: false`
- `tracking.window_weeks: 4`
- `tracking.receiver_participation.enabled: true`
- `tracking.receiver_participation.positions: [WR, TE]`
- `tracking.rb_efficiency.enabled: true`
- `tracking.qb_context.enabled: true`
- `availability.enabled: true`
- `availability.positions: [QB, RB, WR, TE]`
- `availability.injuries.enabled: false`
- `availability.depth_charts.enabled: true`
- `availability.usage_fallback.enabled: true`
- `market_history.enabled: true`
- `market_history.snapshot_label: close_core8`
- `role_trend.enabled: false`
- `role_trend.positions: [QB, RB, WR, TE]`
- `game_script.enabled: true`
- `game_script.trailing_late.enabled: true`
- `td_tendency.enabled: true`
- `td_tendency.i5_enabled: true`

Built but currently parked or disabled:

- `pff.team_context.enabled: false`
- `pff.talent.enabled: false`
- `usage.ngs.enabled: false`
- `usage.route_rate.enabled: false`
- `game_script.leading_late_rb.enabled: false`
- `goal_line_concentration.enabled: false`

## Runtime Order

`GameContextBuilder` order in [`../src/fantasy_sim/data/game_context.py`](../src/fantasy_sim/data/game_context.py):

1. Base team distributions and player models from nflverse PBP + rosters
2. Vegas game environment
3. Availability engine
4. Usage engine
5. Tracking engine
6. Player props
7. Matchup engine
8. Tier engine and optional team-context integration
9. RB scheme-fit engine
10. QB split engine
11. Depth-role engine
12. Coverage engine
13. DST baseline engine
14. Kicker engine
15. TD tendency engine
16. Weather engine
17. Runtime game script overlays during simulation
18. User overrides

End-to-end projection flow after simulation:

19. Post-sim `role_trend` adjustment
20. Post-sim `market_history` adjustment
21. Post-sim `ensemble.ff_opportunity` blend

Important distinction:

- `game_script` is not baked into base roster shares
- it is resolved live from `GameState` and applied transiently during play calling
- `availability` runs before `usage`, so explicit inactive / limited decisions
  are applied before softer usage refinement touches shares
- `tracking` now runs after `usage` and before props, with roster shares re-normalized after tracking mutations
- `pff.rb_scheme_fit` now runs after the tier/team-context step and before
  `pff.qb_split`
- `pff.qb_split` now runs after `pff.rb_scheme_fit` and before `pff.depth_role`
- `pff.depth_role` now runs after the tier/team-context step, re-normalizes
  roster shares, and stays after `pff.qb_split` but before per-WR coverage
  matchup adjustments
- PFF `rushing_direction` is now consumed by runtime through
  `pff.rb_scheme_fit`, but the feature remains parked behind its own disabled
  flag
- PFF `passing_detail` is now consumed by runtime through `pff.qb_split`, but
  that feature also remains parked behind its own disabled flag
- `ensemble` is not part of `GameContextBuilder`; when enabled, it is applied
  post-sim in validation, `Backtester`, and the non-detail `week` / `season`
  / `game` CLI flows after projections are generated
- `role_trend` is also post-sim and runs before `market_history`
- `market_history` is post-sim and runs before `ensemble.ff_opportunity`
- `player` and `--detail` CLI output currently bypass all three post-sim layers
  (`role_trend`, `market_history`, and `ensemble`)
- the `player` command always uses detailed projections rather than the
  aggregated non-detail projection flow

That is a useful architectural pattern for future "situation-only" levers.

## Local Data Inventory

### Repo Surface

The repo currently has:

- core simulation engine
- validation harnesses
- PFF/weather/vegas/usage/tracking/game-script/TD-tendency layers
- docs describing prior experiments and sweeps

Most relevant files for accuracy work:

- [`../config/defaults.yaml`](../config/defaults.yaml)
- [`../scripts/validate.py`](../scripts/validate.py)
- [`../src/fantasy_sim/data/game_context.py`](../src/fantasy_sim/data/game_context.py)
- [`../src/fantasy_sim/validation/ledger.py`](../src/fantasy_sim/validation/ledger.py)

### Relevant Local Stores

Relevant local stores under `~/.fantasy-sim`:

- `cache/`
- `market-history/`
- `pff/`
- `weather/`

Relevant subpaths for enabled features and evaluated/backfilled feature families:

- ff-opportunity weekly cache: `~/.fantasy-sim/cache/ff_opportunity_weekly_<season>.parquet`
- tracking caches: `~/.fantasy-sim/cache/participation_<season>.parquet`, `~/.fantasy-sim/cache/ftn_charting_<season>.parquet`, `~/.fantasy-sim/cache/ngs_passing_<season>.parquet`, and `~/.fantasy-sim/cache/ngs_rushing_<season>.parquet`
- market-history processed cache: `~/.fantasy-sim/market-history/processed/`
- player props cache: `~/.fantasy-sim/pff/props/`

### nflverse / local cache coverage

Observed local caches:

- PBP caches for 2018-2024 combinations
- weekly rosters through 2025
- schedules through 2025
- snap counts for 2022-2024
- weekly player stats for 2022-2025
- NGS receiving caches for 2022-2024
- participation caches for 2022-2024
- FTN charting caches for 2022-2024
- NGS passing caches for 2022-2024
- NGS rushing caches for 2022-2024
- `ff_opportunity_weekly_2022.parquet`
- `ff_opportunity_weekly_2023.parquet`
- `ff_opportunity_weekly_2024.parquet`

### PFF processed data

Observed under `~/.fantasy-sim/pff/processed/`:

- 190 NFL parquet files
- 105 NCAA parquet files
- one stray `.DS_Store`
- NFL coverage from 2018-2025
- NFL fantasy receiving/passing red-zone data from 2015-2025
- NCAA facets from 2021-2025

Useful currently-used PFF tables:

- `receiving_summary`
- `rushing_summary`
- `passing_summary`
- `defense_coverage`
- `defense_coverage_matchup`
- `defense_pass_rush`
- `defense_run`
- `field_goal_summary`
- `defense_summary`
- `fantasy_receiving`
- `fantasy_passing`

High-granularity PFF tables present locally but largely underused today:

- `passing_detail`
- `receiving_depth`
- `rushing_direction`
- `offense_run_blocking` gap vs zone columns
- `offense_pass_blocking`
- richer weekly defensive and receiving matchup detail

Examples of useful columns verified locally:

- `passing_detail`: pressure, blitz, no-pressure, screen, play-action, depth, field-side, sack, turnover-worthy, and completion split columns
- `receiving_depth`: route participation and output split by behind/short/medium/deep and left/center/right
- `offense_run_blocking`: `gap_grades_run_block`, `zone_grades_run_block`, and corresponding snap counts

### Market history

Observed under `~/.fantasy-sim/market-history/processed/`:

- `events_inventory_2023.parquet`
- `events_inventory_2024.parquet`
- `events_inventory_2025.parquet`
- `player_markets_2023_close_core8.parquet`
- `player_markets_2024_close_core8.parquet`
- `player_markets_2025_close_core8.parquet`

Validation semantics from the promoted Phase 3 v2 artifacts:

- Phase 3 promotion evidence still covers `2023-2024` only
- `2022` is explicitly uncovered for `market_history`
- market-specific promotion evidence uses `covered_only`
- stack-wide summaries may still show `2022`, but it must not be folded into
  market-layer averages as neutral evidence

### Props history

Observed under `~/.fantasy-sim/pff/props/`:

- `props_2025_week01.parquet` through `props_2025_week18.parquet`

Missing for backtest seasons:

- no local props parquet files for 2022
- no local props parquet files for 2023
- no local props parquet files for 2024

This matters because defaults currently enable props, but historical backtests
for 2022-2024 are not actually using historical props inputs.

## Verified Loaders Vs Local Cache State

Verified locally from the installed `nflreadpy` package:

- `load_injuries`
- `load_participation`
- `load_ftn_charting`
- `load_ff_opportunity`
- `load_ff_rankings`
- `load_depth_charts`
- `load_nextgen_stats(seasons, stat_type)` with `passing`, `receiving`, or `rushing`

These loaders are real and do not need speculative wrapper design.

Important distinction for planning and validation:

- injuries: verified loader exists and local parquet cache is created on demand by
  `DataLoader.load_injuries()`
- depth charts: verified loader exists and local parquet cache is created on
  demand by `DataLoader.load_depth_charts()`
- participation: wrapped by `DataLoader.load_participation()` and cached under
  `~/.fantasy-sim/cache/participation_<season>.parquet`
- FTN charting: wrapped by `DataLoader.load_ftn_charting()` and cached under
  `~/.fantasy-sim/cache/ftn_charting_<season>.parquet`
- NGS passing/rushing: wrapped by `DataLoader.load_nextgen_stats()` and cached
  under `~/.fantasy-sim/cache/ngs_passing_<season>.parquet` and
  `~/.fantasy-sim/cache/ngs_rushing_<season>.parquet`

That means the core Phase 4 tracking inputs are no longer future-only data
surfaces; they are implemented loader paths with local backfilled cache state
for `2022-2024`.

## Phase 1 Ensemble Implementation Notes

- `ff_opportunity` is the implemented required Phase 1 v1 source across QB/RB/WR/TE
- `total_fantasy_points_exp` is the current prior feature
- default weights are QB `0.35`, WR `0.25`, RB `0.15`, and TE `0.15`
- joins use nflverse `player_id`
- uncovered rows remain neutral
- local cache correction: ff-opportunity weekly parquet is present for 2022-2024
  under `~/.fantasy-sim/cache/`, and validation coverage treats the historical
  loader as available for those seasons
- runtime player-week blend coverage is not yet summarized in the coverage helper output
- weekly QB/WR accuracy remains the primary success metric and tie-breaker
- `ff_rankings` remains future/optional pending historical coverage, schema, and backtest-year checks; it is still deferred from the first promotion decision

Phase 1 is promoted on the broadened marginal validation artifact:

- label: `phase-1-ff-opportunity-v1-broadened`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `ensemble.ff_opportunity=full(2022,2023,2024)`
- averages:
  - `rank_corr delta: +0.0271`
  - `weekly_mae delta: -0.548`
  - `season_mae delta: -3.737`

The earlier QB/WR-only A/B remains informative as a narrow pilot, but it is not
the Phase 1 promotion artifact.

## Phase 2 Implementation Notes

- `availability` is implemented and promoted for v1
- `role_trend` is implemented but default-off
- both families gate by `positions` lists, with QB/RB/WR/TE as the default set
- `availability` runs before `usage` in `GameContextBuilder`
- `role_trend` runs post-sim before `ensemble.ff_opportunity`
- the v1 availability rule is explicit-signal-first:
  - injuries are implemented but currently default-off after marginal validation
  - QB depth charts can create hard starter / non-starter decisions
  - usage fallback is soft-only

Promoted v1 default shape:

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
- averages:
  - `rank_corr delta: +0.0032`
  - `weekly_mae delta: -0.016`
  - `season_mae delta: -0.269`

v1 rule for evidence interpretation:

- usage-only evidence is soft-only and cannot create inactive decisions
- usage-only evidence cannot create starter-out decisions
- broader participation / tracking evidence remains deferred to the tracking phase

## Phase 3 Market History Notes

- `market_history` is implemented in v2 as a post-sim layer
- the processed local store currently includes `2023-2025`
- `2022` is explicitly uncovered in the validation artifact
- the promoted Phase 3 artifact is `phase-3-market-history-v2-real-schema`
- promotion evidence scope is `covered_only`
- current default state is `market_history.enabled: true`
- current promoted snapshot source is `snapshot_label: close_core8`

Phase 3 v2 artifact:

- label: `phase-3-market-history-v2-real-schema`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `market_history=partial(2023,2024)`
- covered seasons: `2023, 2024`
- uncovered seasons: `2022`
- `rank_corr delta:  +0.0075`
- `weekly_mae delta: -0.065`
- `season_mae delta: -1.288`

QB/WR tie-breaker confirmation:

- label: `phase-3-market-history-v2-real-schema-qb-wr`
- QB weekly rank corr `+0.0086`, weekly MAE `-0.049`
- WR weekly rank corr `+0.0144`, weekly MAE `-0.045`

Interpretation:

- the covered-only deltas are strong enough to justify default-on promotion
- stack-wide averages still include `2022`, but that season is no-data for
  `market_history` and cannot be treated as neutral evidence for the layer
- `2022` backfill is follow-on work, not a prerequisite for moving on to other
  phases

## Phase 4 Tracking Notes

- `tracking` is implemented as a pre-sim layer after `usage` and before props
- current default state is `tracking.enabled: false`
- the family ships three slice toggles:
  - `tracking.receiver_participation.enabled: true`
  - `tracking.rb_efficiency.enabled: true`
  - `tracking.qb_context.enabled: true`
- required local tracking cache files are now present for `2022-2024`

Phase 4 isolated artifacts run on this branch:

- `phase-4-receiver-participation-v1`
  - `rank_corr delta:  -0.0006`
  - `weekly_mae delta: +0.007`
  - `season_mae delta: +0.072`
- `phase-4-rb-efficiency-v1`
  - `rank_corr delta:  -0.0003`
  - `weekly_mae delta: +0.000`
  - `season_mae delta: -0.063`
- `phase-4-qb-context-v1`
  - `rank_corr delta:  +0.0002`
  - `weekly_mae delta: +0.007`
  - `season_mae delta: +0.047`

Interpretation:

- none of the three isolated slices produced a material core-position win
- two slices regressed on average
- the remaining slice was effectively flat overall
- the combined bundle was therefore not run

Phase 4 verification command run after the doc updates:

```bash
uv run pytest tests/test_data/test_tracking tests/test_validation/test_config.py tests/test_validation/test_coverage.py tests/test_validation/test_parallel.py tests/test_validation/test_backtester.py tests/test_validation/test_validate_script.py tests/test_validation/test_market_history_pipeline.py tests/test_validation/test_role_trend_pipeline.py -v
```

Verification result:

- `161 passed`

Observed run caveat from the receiver/QB slices:

- `Snap crosswalk: 1/634 skill players unmatched (0.2%). Unmatched: ['WillRo08']`
- `Snap crosswalk: 1/632 skill players unmatched (0.2%). Unmatched: ['WillRo08']`

## Phase 5 Efficiency Notes

- `pff.depth_role` is now implemented in code
- `pff.depth_role.efficiency` is now implemented in code
- `pff.rb_scheme_fit` is now implemented in code
- `pff.qb_split` is now implemented in code
- `pff.depth_role.efficiency` remains nested under the existing
  `pff.depth_role` family
- current local `receiving_depth` NFL coverage is `2018-2025`
- `pff.depth_role` uses `receiving_depth` plus `rosters_weekly` crosswalk inputs
- `pff.depth_role.efficiency` uses `receiving_depth`, the PFF summary trio,
  and `rosters_weekly` crosswalk inputs
- `pff.rb_scheme_fit` uses `rushing_direction`, `offense_run_blocking`,
  `rushing_summary`, and `rosters_weekly` crosswalk inputs
- `pff.qb_split` uses `passing_detail` plus the PFF/NFLverse QB crosswalk path
- `rushing_direction` is now consumed by runtime through `pff.rb_scheme_fit`
- `passing_detail` is now used by the runtime through `pff.qb_split`
- it currently adjusts:
  - `catch_rate`
  - proportional `red_zone_catch_rate`
  - base `receiving_yards_dist`
- it does not adjust:
  - `target_share`
  - `air_yards_share`
  - `rz_receiving_yards_dist`
- local `injuries_2022-2024.parquet` exists
- legacy `market_history_weekly_2023.parquet` and `market_history_weekly_2024.parquet` exist locally
- the focused Phase 5A marginal validation artifact completed cleanly as `phase-5-depth-role-v1`
- the focused Phase 5B decision artifact ran as
  `phase-5-depth-role-efficiency-v2-activated`
- the focused Phase 5C decision artifact ran as
  `phase-5-qb-split-v1-postfix`
- the focused Phase 5D decision artifact ran as
  `phase-5-rb-scheme-fit-v1`
- Phase 5C coverage in the run header was `pff.qb_split=full(2022,2023,2024)`
- Phase 5D coverage in the run header was
  `pff.rb_scheme_fit=full(2022,2023,2024)`
- the Phase 5C run stayed effectively flat and is not promotable:
  - `rank_corr delta:  +0.0000`
  - `weekly_mae delta: +0.006`
  - `season_mae delta: +0.020`
- the Phase 5D run showed only small top-line lift and is not promotable:
  - `rank_corr delta:  +0.0018`
  - `weekly_mae delta: -0.003`
  - `season_mae delta: -0.040`
- superseded pre-fix artifact:
  - `phase-5-qb-split-v1`
  - `rank_corr delta:  +0.0005`
  - `weekly_mae delta: -0.000`
  - `season_mae delta: -0.028`
- the Phase 5B run stayed effectively flat and is not promotable:
  - `rank_corr delta:  +0.0000`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: +0.030`
- current default state remains `pff.depth_role.enabled: false`
- current default state remains `pff.depth_role.efficiency.enabled: false`
- current default state remains `pff.rb_scheme_fit.enabled: false`
- current default state remains `pff.qb_split.enabled: false`
- current Phase 5A evidence is not promotable:
  - `rank_corr delta:  -0.0005`
  - `weekly_mae delta: +0.002`
  - `season_mae delta: +0.013`

### Phase 5 Decision Record

Historical note: this decision block is preserved for context, but Phase 6 is
now the active priority.

- decide whether to retune `WR/TE efficiency v2`
- or retune `RB scheme-fit engine`
- or retune `QB split engine`
- or move on beyond Phase 5 without promoting any of the current parked PFF slices
- do not auto-promote or auto-bundle Phase 5A and Phase 5B from the current
  evidence

### Superseded Setup Artifact

- `phase-5-depth-role-efficiency-v2`
- top-line deltas:
  - `rank_corr delta:  +0.0002`
  - `weekly_mae delta: -0.002`
  - `season_mae delta: -0.017`
- this earlier row is preserved as a setup/debug artifact, but it is not the
  Phase 5B decision record because the coverage header left the depth-role
  family disabled

### Deferred Phase 5 Follow-Ons

- none currently recorded; `RB scheme-fit engine` is now implemented,
  validated, and parked

## Phase 6 Current Priority

Phase 6 now targets only the still-parked default-off levers:

- `pff.team_context`
- `usage.ngs`
- `goal_line_concentration`
- `usage.route_rate`

Not part of the parked queue anymore:

- `td_tendency`
- `td_tendency.i5_enabled`

Slice A is now the current baseline:

- explicit coverage signals now exist for `pff.team_context`
- explicit coverage signals now exist for `goal_line_concentration`
- explicit coverage signals now exist for `td_tendency` and nested `td_tendency.i5`
- `usage.route_rate` now points at the NFL processed PFF root used by runtime

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

## What The Current Ledgers Actually Tell Us

### Unified ledger

The current validation path is now wired to record new runs with:

- `baseline=defaults` marginal runs
- schema version
- comparison metadata
- coverage summaries

Phase 2 manual validation status:

- the user owned and completed the Phase 2 manual A/B validation pass
- the current promotion record is `phase-2-availability-no-injuries-confirm`

This branch did not regenerate or backfill the historical ledger files, so the
older rows remain historical evidence rather than newly produced outputs.

That means new rows can now distinguish:

- total lift versus the stripped baseline
- marginal lift versus the current default stack
- schema-era evidence versus legacy snapshots

This is a meaningful improvement for "should ship by default" decisions, but
older rows still need caveat-aware interpretation.

### Legacy ledgers still matter

Earlier local artifacts from prior runs include:

- `results/pff_ab_ledger.json`
- `results/pff_ab_ledger_pre-2022-2024.json`
- `results/weekly_ab_ledger_pre-2022-2024.json`

These are preserved historical references, not files populated by this branch
checkout. They still contain useful evidence for:

- coverage tuning
- blend-pool tuning
- tertiary RB grade lift
- weather weekly behavior
- earlier usage sweeps

### Schema drift in snapshots

`config_snapshot` records in `results/ab_ledger.json` span multiple config eras.

Examples:

- `baseline-new` snapshot predates `game_script`, `goal_line_concentration`, and `td_tendency`
- later runs include those keys

Implication:

- ledger comparisons across dates are not always apples-to-apples
- future evaluation should record a config-schema version

## Phase 0 Resolution Notes

Resolved in the new validation path:

- `td_tendency_config` is now threaded through bare dual-arm validation
- `baseline=defaults` is now a first-class marginal validation path
- validation rows now carry config-schema version and comparison metadata
- per-run coverage reporting now covers props, market history, PFF, weather,
  and usage

Still caveats:

- Phase 3 market-history promotion evidence is currently `covered_only`
- `2022` remains explicitly uncovered for `market_history`
- Phase 4 tracking evidence is currently isolated-slice evidence only; no bundle readout exists because the slices were not strong enough to justify it
- weekly ledger history is still partly legacy
- older pre-schema ledger entries are still directional evidence, not apples-to-apples comparisons

## Remaining Evaluation Caveats

### 1. Market-history evidence is still covered-only in Phase 3 v2

The current market-history implementation has processed season parquet for
`2023-2025`, while `2022` is explicitly uncovered in historical validation.

Implication:

- market-specific promotion evidence must use the explicit `covered_only`
  readout
- stack-wide summaries may still show `2022`, but `2022` cannot be folded into
  market-layer averages as neutral evidence
- the promoted Phase 3 v2 artifact justifies `market_history.enabled: true`,
  but only because the positive readout came from the covered seasons alone

### 2. Phase 4 tracking decisions must stay slice-by-slice

The current Phase 4 evidence is three isolated marginal runs, not a bundle run.

Implication:

- the current readout supports keeping `tracking.enabled: false`
- no "maybe the bundle interaction helps" inference should be made from these
  slice results
- a future Phase 4 retry should change one slice or one parameter family at a
  time, then re-run isolated validation before any combined bundle

### 3. Tracking crosswalk coverage is very close to full, but not perfect

The receiver-participation and QB-context artifacts both logged the same small
snap crosswalk gap:

- `Snap crosswalk: 1/634 skill players unmatched (0.2%). Unmatched: ['WillRo08']`
- `Snap crosswalk: 1/632 skill players unmatched (0.2%). Unmatched: ['WillRo08']`

Implication:

- this is small enough that it did not block Phase 4 evaluation
- it should still be treated as a real data-quality caveat for participation-based slices

### 4. Some recent comparisons are not isolated

Examples:

- `goal-line-concentration-400` differs from `game-script-trailing-control-400`
  not only by `goal_line_concentration.enabled=true`, but also by the tighter
  `game_script.leading_late_rb.rb_rank_factor_clamp`
- `baseline-new` predates later defaults that include `td_tendency`,
  nested `td_tendency.i5`, and `game_script`

Use these runs as directional evidence, not clean causal proof.

### 5. Weekly validation record is partially legacy

`results/weekly_ab_ledger.json` is effectively empty, while the useful weekly
evidence still lives in `results/weekly_ab_ledger_pre-2022-2024.json`.

That makes weekly signal review possible, but less discoverable than it should be.

## Current Lift Snapshot

Useful reference points from the preserved local unified ledger snapshot:

| Label | avg rank_corr delta | avg weekly MAE delta | avg season MAE delta |
|---|---:|---:|---:|
| `baseline-new` | `+0.1502` | `-0.606` | `-10.525` |
| `td-tendency-final` | `+0.1519` | `-0.588` | `-10.862` |
| `route-rate` | `+0.1519` | `-0.607` | `-10.691` |
| `i5-subfactor` | `+0.1520` | `-0.606` | `-10.655` |
| `game-script-off` | `+0.1532` | `-0.617` | `-11.120` |
| `game-script-trailing-control-400` | `+0.1534` | `-0.591` | `-10.997` |
| `goal-line-concentration-400` | `+0.1512` | `-0.598` | `-11.416` |
| `phase-4-receiver-participation-v1` | `-0.0006` | `+0.007` | `+0.072` |
| `phase-4-qb-context-v1` | `+0.0002` | `+0.007` | `+0.047` |
| `phase-4-rb-efficiency-v1` | `-0.0003` | `+0.000` | `-0.063` |
| `phase-5-depth-role-v1` | `-0.0005` | `+0.002` | `+0.013` |
| `phase-5-depth-role-efficiency-v2` | `+0.0002` | `-0.002` | `-0.017` |
| `phase-5-depth-role-efficiency-v2-activated` | `+0.0000` | `-0.002` | `+0.030` |
| `phase-5-qb-split-v1-postfix` | `+0.0000` | `+0.006` | `+0.020` |

Interpretation:

- the broad post-phase-3 stack is clearly much better than the bare baseline
- recent single-feature conclusions need marginal validation before being
  treated as default-on wins

## What To Carry Forward Into Future Planning

### Strong evidence

- the stack has meaningfully improved over the bare simulator
- usage + CPOE, PFF tiers/matchups, weather, and broad contextual layering are real contributors
- weekly QB/WR accuracy is still the right tie-breaker

### Strong local opportunities

- high-resolution PFF slices already exist locally
- `nflreadpy` tracking feeds are now backfilled locally for `2022-2024`
- historical props are the clearest missing paid-data gap

### Operational rules for future planning

- separate total lift from marginal lift
- require explicit data coverage reporting by season and week
- do not call a feature neutral if it had no data during backtest
- treat parked features as "failed under previous inputs," not "permanently bad"

## Companion Document

Next planning artifact:

- [`docs/accuracy-roadmap.md`](./accuracy-roadmap.md)
