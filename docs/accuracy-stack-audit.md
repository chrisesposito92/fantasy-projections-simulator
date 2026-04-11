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
- `game_script.enabled: true`
- `game_script.trailing_late.enabled: true`
- `td_tendency.enabled: true`
- `td_tendency.i5_enabled: true`

Built but currently parked or disabled:

- `ensemble.enabled: false`
- `ensemble.ff_opportunity.enabled: false`
- `ensemble.ff_rankings.enabled: false`
- `pff.team_context.enabled: false`
- `pff.talent.enabled: false`
- `usage.ngs.enabled: false`
- `usage.route_rate.enabled: false`
- `game_script.leading_late_rb.enabled: false`
- `goal_line_concentration.enabled: false`

## Runtime Order

Actual order in [`src/fantasy_sim/data/game_context.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/game_context.py):

1. Base team distributions and player models from nflverse PBP + rosters
2. Vegas game environment
3. Usage engine
4. Player props
5. Matchup engine
6. Tier engine and optional team-context integration
7. Coverage engine
8. DST baseline engine
9. Kicker engine
10. TD tendency engine
11. Weather engine
12. Runtime game script overlays during simulation
13. User overrides

Important distinction:

- `game_script` is not baked into base roster shares
- it is resolved live from `GameState` and applied transiently during play calling
- `ensemble` is not part of `GameContextBuilder`; when enabled, it is applied
  post-sim in validation, `Backtester`, and the non-detail `week` / `season`
  / `game` CLI flows after projections are generated
- `player` and `--detail` CLI output currently bypass the ensemble blend

That is a useful architectural pattern for future "situation-only" levers.

## Local Data Inventory

### Repo Surface

The repo currently has:

- core simulation engine
- validation harnesses
- PFF/weather/vegas/usage/game-script/TD-tendency layers
- docs describing prior experiments and sweeps

Most relevant files for accuracy work:

- [`config/defaults.yaml`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/config/defaults.yaml)
- [`scripts/validate.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/scripts/validate.py)
- [`src/fantasy_sim/data/game_context.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/game_context.py)
- [`src/fantasy_sim/validation/ledger.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/validation/ledger.py)

### `~/.fantasy-sim`

Local store present at `/Users/chrisesposito/.fantasy-sim`:

- `cache/`
- `pff/`
- `props/`
- `weather/`

### nflverse / local cache coverage

Observed local caches:

- PBP caches for 2018-2024 combinations
- weekly rosters through 2025
- schedules through 2025
- snap counts for 2022-2024
- weekly player stats for 2022-2025
- NGS receiving caches for 2022-2024

### PFF processed data

Observed under `~/.fantasy-sim/pff/processed/`:

- 295 parquet files across NFL and NCAA
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

### Props history

Observed under `~/.fantasy-sim/pff/props/`:

- `props_2025_week01.parquet` through `props_2025_week18.parquet`

Missing for backtest seasons:

- no local props parquet files for 2022
- no local props parquet files for 2023
- no local props parquet files for 2024

This matters because defaults currently enable props, but historical backtests
for 2022-2024 are not actually using historical props inputs.

## Verified nflreadpy Surface For Future Phases

Verified locally from the installed `nflreadpy` package:

- `load_injuries`
- `load_participation`
- `load_ftn_charting`
- `load_ff_opportunity`
- `load_ff_rankings`
- `load_depth_charts`
- `load_nextgen_stats(seasons, stat_type)` with `passing`, `receiving`, or `rushing`

These loaders are real and do not need speculative wrapper design.

## Phase 1 Ensemble Implementation Notes

- `ff_opportunity` is the implemented required Phase 1 v1 source
- `total_fantasy_points_exp` is the current prior feature
- joins use nflverse `player_id`
- uncovered rows remain neutral
- runtime player-week blend coverage is not yet summarized in the coverage helper output
- `ff_rankings` remains future/optional pending historical coverage, schema, and backtest-year checks

The ensemble family is implemented in code, but the defaults remain off and no
promotion has been claimed yet.

## What The Current Ledgers Actually Tell Us

### Unified ledger

The current validation path is now wired to record new runs with:

- `baseline=defaults` marginal runs
- schema version
- comparison metadata
- coverage summaries

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
- per-run coverage reporting now covers props, PFF, weather, and usage

Still caveats:

- historical props are still missing for 2022-2024
- weekly ledger history is still partly legacy
- older pre-schema ledger entries are still directional evidence, not apples-to-apples comparisons

## Remaining Evaluation Caveats

### 1. Historical props are absent for the main backtest seasons

Defaults enable props, but props files exist only for 2025.

Implication:

- 2022-2024 validation does not actually evaluate props as a historical signal
- "props enabled" in current defaults is operationally true for forward use, but
  largely inert in historical A/B

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
