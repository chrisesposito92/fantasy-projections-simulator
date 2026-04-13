# Market History Handoff

Date: 2026-04-13
Branch: `codex/phase-3-market-history`

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

Those files are **not yet wired into the simulator**.

So the next session should **not** run more A/B tests yet.

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

## What Is Left To Do

### 1. Redesign `market_history` runtime around market-native player-week signals

Current problem:

- runtime scoring and coverage still revolve around the placeholder fantasy-ish
  shape (`open_fpts`, `close_fpts`, etc.)

Target:

- use the real processed market-native parquet as the canonical source

### 2. Build The Odds API -> nflverse `player_id` crosswalk

Current problem:

- raw/player-market data identifies players by **name only**
- current PFF crosswalk is not sufficient

Likely ingredients:

- standardized player name
- team
- nflverse roster data
- ambiguity guard
- reuse ideas from:
  - [crosswalk.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/vegas/crosswalk.py)

### 3. Rework the post-sim adjuster

Current problem:

- [market_history.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/scoring/market_history.py)
  still expects the old processed abstraction

Target:

- adapt the post-sim layer to the real market-native processed schema

### 4. Only then rerun Phase 3 validation

Do **not** run new A/B tests until steps 1-3 are done.

Once the real schema and crosswalk are in:

- rebuild processed market signals
- run one single marginal validation artifact
- update docs again if the result changes

## Recommended Next Session Prompt

Use this as the kickoff prompt in the next session:

> Continue on branch `codex/phase-3-market-history`. The Odds API event inventory and close-only props backfill for `2023-2025` are complete, and `player_markets_<season>_close_core8.parquet` exists. Do not run new A/B tests yet. First redesign `market_history` around market-native player-week signals, then build the The Odds API -> nflverse player crosswalk, then rework the post-sim adjuster to use that real schema.

## Suggested First Commands For The Next Session

```bash
git switch codex/phase-3-market-history

uv run python - <<'PY'
from pathlib import Path
import polars as pl
base = Path.home()/'.fantasy-sim'/'market-history'/'processed'
for season in (2023, 2024, 2025):
    path = base / f'player_markets_{season}_close_core8.parquet'
    df = pl.read_parquet(path)
    print('season', season, 'rows', df.height, 'markets', sorted(df['market_key'].unique().to_list()))
PY
```
