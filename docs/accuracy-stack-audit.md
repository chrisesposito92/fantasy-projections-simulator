# Accuracy Stack Audit

Research snapshot from the 2026-04-10 deep-dive session.

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
- `pff.kicker.enabled: true`
- `pff.dst_baseline.enabled: true`
- `weather.enabled: true`
- `vegas.enabled: true`
- `vegas.props.enabled: true`
- `usage.enabled: true`
- `usage.cpoe.enabled: true`
- `availability.enabled: true`
- `availability.positions: [QB, RB, WR, TE]`
- `availability.injuries.enabled: false`
- `availability.depth_charts.enabled: true`
- `availability.usage_fallback.enabled: true`
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
- `market_history.enabled: false`
- `game_script.leading_late_rb.enabled: false`
- `goal_line_concentration.enabled: false`

## Runtime Order

`GameContextBuilder` order in [`../src/fantasy_sim/data/game_context.py`](../src/fantasy_sim/data/game_context.py):

1. Base team distributions and player models from nflverse PBP + rosters
2. Vegas game environment
3. Availability engine
4. Usage engine
5. Player props
6. Matchup engine
7. Tier engine and optional team-context integration
8. Coverage engine
9. DST baseline engine
10. Kicker engine
11. TD tendency engine
12. Weather engine
13. Runtime game script overlays during simulation
14. User overrides

End-to-end projection flow after simulation:

15. Post-sim `role_trend` adjustment
16. Post-sim `market_history` adjustment
17. Post-sim `ensemble.ff_opportunity` blend

Important distinction:

- `game_script` is not baked into base roster shares
- it is resolved live from `GameState` and applied transiently during play calling
- `availability` runs before `usage`, so explicit inactive / limited decisions
  are applied before softer usage refinement touches shares
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
- PFF/weather/vegas/usage/game-script/TD-tendency layers
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

Relevant subpaths for currently enabled features:

- ff-opportunity weekly cache: `~/.fantasy-sim/cache/ff_opportunity_weekly_<season>.parquet`
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

- `market_history_weekly_2023.parquet`
- `market_history_weekly_2024.parquet`

Validation semantics from the Phase 3 v1 artifact:

- Phase 3 v1 covers `2023-2024` only
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
- participation: verified loader exists in `nflreadpy`, but this project does
  not yet wrap or cache it in `DataLoader`

That means injuries and depth charts are implemented inputs for the current
availability path, while participation is still only a verified future-phase
data surface.

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

- `market_history` is implemented in v1 as a post-sim layer
- the processed local store currently covers `2023-2024`
- `2022` is explicitly uncovered in the validation artifact
- the Phase 3 decision artifact is `phase-3-market-history-v1`
- promotion evidence scope is `covered_only`
- current default state remains `market_history.enabled: false`

Phase 3 v1 artifact:

- label: `phase-3-market-history-v1`
- baseline: `defaults`
- comparison mode: `marginal_lift`
- coverage: `market_history=partial(2023,2024)`
- covered seasons: `2023, 2024`
- uncovered seasons: `2022`
- `rank_corr delta:  -0.0003`
- `weekly_mae delta: -0.011`
- `season_mae delta: +0.036`

Interpretation:

- the covered-only deltas are too flat to justify default-on promotion
- stack-wide averages still include `2022`, but that season is no-data for
  `market_history` and cannot be treated as neutral evidence for the layer
- `2022` backfill is follow-on work, not a prerequisite for moving on to other
  phases

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
- weekly ledger history is still partly legacy
- older pre-schema ledger entries are still directional evidence, not apples-to-apples comparisons

## Remaining Evaluation Caveats

### 1. Market-history evidence is covered-only in Phase 3 v1

The current market-history implementation has processed season parquet for
`2023-2024`, while `2022` is explicitly uncovered.

Implication:

- market-specific promotion evidence must use the explicit `covered_only`
  readout
- stack-wide summaries may still show `2022`, but `2022` cannot be folded into
  market-layer averages as neutral evidence
- the current artifact does not justify changing the default state from
  `market_history.enabled: false`

### 2. Some recent comparisons are not isolated

Examples:

- `goal-line-concentration-400` differs from `game-script-trailing-control-400`
  not only by `goal_line_concentration.enabled=true`, but also by the tighter
  `game_script.leading_late_rb.rb_rank_factor_clamp`
- `baseline-new` predates later defaults that include `td_tendency` and
  `game_script`

Use these runs as directional evidence, not clean causal proof.

### 3. Weekly validation record is partially legacy

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
- `nflreadpy` already exposes the next set of promising feeds
- historical props are the clearest missing paid-data gap

### Operational rules for future planning

- separate total lift from marginal lift
- require explicit data coverage reporting by season and week
- do not call a feature neutral if it had no data during backtest
- treat parked features as "failed under previous inputs," not "permanently bad"

## Companion Document

Next planning artifact:

- [`docs/accuracy-roadmap.md`](./accuracy-roadmap.md)
