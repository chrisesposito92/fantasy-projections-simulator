# Market History Handoff

Date: 2026-04-13
Branch: `codex/phase-3-market-history`

## Status Note

This handoff is now historical.

The Phase 3 runtime redesign, The Odds API to nflverse crosswalk, post-sim
adjuster rewrite, and validation reruns are complete on this branch. The
canonical current state lives in:

- [accuracy-roadmap.md](./accuracy-roadmap.md)
- [accuracy-stack-audit.md](./accuracy-stack-audit.md)
 

## Current State

The branch now has three distinct layers of work:

1. **Phase 3 plumbing**
   - `market_history` config family
   - post-sim `market_history` layer
   - validation/backtest/non-detail CLI wiring
   - coverage-aware reporting and ledger metadata
   - roadmap/audit updates

2. **The Odds API acquisition**
   - full NFL regular-season event inventory for `2023-2025`
   - full **close-only** player-props backfill for `2023-2025`

3. **Market-native processed signals**
   - processed player-week market signal parquet built from cached raw props

## Important Reality Check

The **old Phase 3 runtime path is still built around the earlier placeholder
abstraction** (`open_fpts`, `close_fpts`, `books`, `line_stddev`,
`anytime_td_prob`).

The **new real data path** is the market-native processed parquet:

- `player_markets_2023_close_core8.parquet`
- `player_markets_2024_close_core8.parquet`
- `player_markets_2025_close_core8.parquet`

Those files are now wired into the simulator and validation path.

Promoted validation artifacts:

- `phase-3-market-history-v2-real-schema`
- `phase-3-market-history-v2-real-schema-qb-wr`
- `phase-3-market-history-v2-total-lift`

## Completed Data Pulls

### Event inventory

Cached under:

- `~/.fantasy-sim/market-history/raw/events/`

Processed inventories:

- `~/.fantasy-sim/market-history/processed/events_inventory_2023.parquet`
- `~/.fantasy-sim/market-history/processed/events_inventory_2024.parquet`
- `~/.fantasy-sim/market-history/processed/events_inventory_2025.parquet`

Coverage:

- `2023`: `272` events
- `2024`: `272` events
- `2025`: `272` events

### Player props

Cached under:

- `~/.fantasy-sim/market-history/raw/props/<season>/close_core8/<event_id>.json`

Coverage:

- `2023`: `272` events
- `2024`: `272` events
- `2025`: `272` events

This is a **complete close-only regular-season archive** for the selected
market set.

## Current Market Set

The full backfill was run with `close_core8`, using:

- `player_pass_attempts`
- `player_pass_yds`
- `player_pass_tds`
- `player_rush_attempts`
- `player_rush_yds`
- `player_receptions`
- `player_reception_yds`
- `player_anytime_td`

`player_rush_tds` was intentionally dropped.

## Processed Market-Native Output

Built with:

```bash
uv run python scripts/build_market_history_player_markets.py \
  --season 2023 2024 2025 \
  --snapshot-label close_core8
```

Output files:

- `~/.fantasy-sim/market-history/processed/player_markets_2023_close_core8.parquet`
- `~/.fantasy-sim/market-history/processed/player_markets_2024_close_core8.parquet`
- `~/.fantasy-sim/market-history/processed/player_markets_2025_close_core8.parquet`

Current row counts:

- `2023`: `26063`
- `2024`: `21595`
- `2025`: `20581`

Schema is **long-form and market-native**, centered on fields like:

- `market_key`
- `player_name`
- `player_name_normalized`
- `line`
- `line_stddev`
- `over_price`
- `under_price`
- `yes_price`
- `implied_prob`
- `bookmaker_count`

The processing code lives in:

- [player_markets.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/market_history/player_markets.py)
- [build_market_history_player_markets.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/scripts/build_market_history_player_markets.py)

## Scripts Added

### Event inventory

- [fetch_market_history_events.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/scripts/fetch_market_history_events.py)

Examples:

```bash
uv run python scripts/fetch_market_history_events.py --season 2023 2024 2025
uv run python scripts/fetch_market_history_events.py --season 2023 2024 2025 --rebuild-only
```

### Props backfill

- [fetch_market_history_props.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/scripts/fetch_market_history_props.py)

Examples:

```bash
uv run python scripts/fetch_market_history_props.py \
  --season 2023 2024 2025 \
  --snapshot-label close_core8
```

### Player-market processing

- [build_market_history_player_markets.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/scripts/build_market_history_player_markets.py)

Examples:

```bash
uv run python scripts/build_market_history_player_markets.py \
  --season 2023 2024 2025 \
  --snapshot-label close_core8
```

## Auth

The Odds API key is read from:

- `~/.fantasy-sim/market-history/.env`

Expected variable:

```bash
THE_ODDS_API_KEY=...
```

Legacy fallback:

```bash
THE_ODDS_API=...
```

## Documentation Updated

The standalone script usage is documented in:

- [CLI-COMMANDS.md](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/docs/CLI-COMMANDS.md)

## Recommendation On Open vs Close

Right now we only pulled **close** snapshots (`close_core8`).

Recommendation:

- **Do not pull open yet**
- close-only is sufficient for:
  - schema work
  - crosswalk work
  - first integration pass

Open snapshots are only worth adding later if movement becomes important after
the real market-native integration is working.

## Completed From This Handoff

- `market_history` runtime redesigned around market-native player-week signals
- The Odds API to nflverse `player_id` crosswalk implemented
- post-sim adjuster reworked to use the real `player_markets_*_close_core8`
  schema
- validation coverage switched to the new processed files and crosswalk inputs
- Phase 3 rerun with fresh A/B artifacts and promoted to default-on

## Remaining Follow-On Work

- `2022` market-history backfill, if a credible source can be acquired
- optional expansion beyond the promoted `close_core8` market set
- open-snapshot experimentation only if the promoted close-only path stops
  improving results
