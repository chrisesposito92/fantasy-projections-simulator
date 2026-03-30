# Season Command Aggregation Fix

**Date:** 2026-03-30
**Status:** Approved

## Problem

The `season` CLI command outputs one row per player per game rather than aggregated season totals. Three additional issues:

1. No season-level aggregation — per-game projections are collected and sorted but never summed across weeks
2. No week identifier — per-week output doesn't indicate which week each row belongs to
3. Default weeks include playoffs (`game_type` values: `WC`, `DIV`, `CON`, `SB`) — should default to regular season only
4. `--output season.json` requires `--format json` even though the extension makes the intent obvious

## Design

### 1. Season Aggregation (default behavior)

After the per-game loop collects projection dicts (one per player per game), a new `_aggregate_season_projections(projs)` helper in `cli.py`:

- Groups projections by `player_id`
- Sums all numeric stat fields (`fpts`, `pass_yards`, `pass_tds`, `rush_yards`, `rush_tds`, `targets`, `receptions`, `receiving_yards`, `receiving_tds`, `interceptions`, `sacks`, `fumbles_lost`)
- Keeps metadata from first entry (`name`, `position`, `team`)
- Re-ranks by total `fpts`

For `--detail` mode in aggregated output: distribution fields (`fpts_floor`, `fpts_ceiling`, `fpts_stddev`, `*_floor`, `*_ceiling`, `*_stddev`) are dropped since summing percentiles across weeks is not statistically meaningful. Base stats and `fpts` are still summed. Users who want weekly distributions use `--by-week --detail`.

Separate `_aggregate_dst_projections(projs)` and `_aggregate_kicker_projections(projs)` helpers follow the same pattern with their respective stat fields.

### 2. `--by-week` Flag

- New `--by-week` boolean flag on the `season` command (default `False`)
- During the per-game loop, stamp each projection dict with `"week": current_week_number`
- When `--by-week` is set: skip aggregation, sort by week then fpts within week
- When `--by-week` is not set (default): run aggregation, no `week` field in final output

Table display with `--by-week`: print a week header line between groups (e.g., `"Week 1 Projections"`) rather than adding a week column to every row. CSV/JSON export includes the `week` field on every row.

### 3. Regular Season Default

- When `weeks == "all"` (default): filter schedule by `game_type == "REG"` to exclude playoffs
- When user specifies explicit weeks (`--weeks 1-18`, `--weeks 1,5,10`): use those weeks as-is, no `game_type` filter
- This dynamically adapts to season length (17 games pre-2021, 18 games 2021+) without hardcoding

Implementation: after loading schedules, apply `pl.col("game_type") == "REG"` filter before extracting unique weeks. The `parsed_weeks` path (explicit weeks) bypasses this filter.

### 4. Format Auto-Inference from `--output`

- If `--output` path ends in `.json` → infer `output_format = "json"`
- If `--output` path ends in `.csv` → infer `output_format = "csv"`
- Only infer when `--format` is not explicitly provided. Use `ctx.get_parameter_source("output_format")` to distinguish default vs. explicit — if source is `click.core.ParameterSource.DEFAULT`, infer from extension; otherwise respect the explicit value
- If `--format` is explicitly set, it takes precedence regardless of file extension

This applies to all commands that use `_display_projections()`, not just `season`.

## Files Changed

- `src/fantasy_sim/cli.py` — All four changes: aggregation helpers, `--by-week` flag, `game_type` filter, format inference
- `tests/test_cli.py` (or equivalent) — Tests for aggregation logic, by-week output, regular season filtering, format inference

## Out of Scope

- Changing `build_player_projections()` or other scoring/projections.py functions — they correctly handle per-game averaging already
- Cumulative/running totals mode
- Changes to the `week`, `game`, `player`, or `demo` commands (except format inference which benefits all commands via `_display_projections`)
