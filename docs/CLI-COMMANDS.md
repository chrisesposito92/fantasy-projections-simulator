# CLI Command Reference

Complete reference for `fantasy-sim` commands. All commands use `uv run fantasy-sim <command>`.

---

## `demo`

Run a simulation with synthetic (built-in) team data. No network or nflverse data required.

```bash
fantasy-sim demo [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--sims N` | 100 | Number of simulations per game |
| `--scoring FORMAT` | ppr | Scoring format: `ppr`, `half_ppr`, `standard` |
| `--format FORMAT` | table | Output format: `table`, `csv`, `json` |
| `--output PATH` | — | File path for csv/json export |
| `--detail` | off | Show floor/ceiling/stddev for all stats |
| `--override "X.Y=Z"` | — | Player/team override (repeatable) |
| `--config PATH` | — | Path to season.yaml with overrides |
| `--scoring-config PATH` | — | Path to custom scoring YAML |

**Examples:**
```bash
# Basic demo
fantasy-sim demo --sims 100

# Half-PPR with detailed distributions
fantasy-sim demo --sims 200 --scoring half_ppr --detail

# Export to JSON
fantasy-sim demo --sims 100 --format json --output projections.json

# Override a player's target share
fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.35"

# Multiple overrides
fantasy-sim demo --sims 100 \
  --override "HOME_WR1.target_share=0.35" \
  --override "HOME_RB1.carry_share=0.70"
```

---

## `week`

Simulate all games in a real NFL week using nflverse data. Downloads data on first run (~500MB).

```bash
fantasy-sim week WEEK_NUM [OPTIONS]
```

| Argument/Flag | Default | Description |
|------|---------|-------------|
| `WEEK_NUM` | *(required)* | Week number (1-18) |
| `--season YEAR` | 2024 | NFL season year |
| `--sims N` | from config | Number of simulations per game |
| `--scoring FORMAT` | ppr | Scoring format: `ppr`, `half_ppr`, `standard` |
| `--format FORMAT` | table | Output format: `table`, `csv`, `json` |
| `--output PATH` | — | File path for csv/json export |
| `--detail` | off | Show floor/ceiling/stddev for all stats |
| `--override "X.Y=Z"` | — | Player/team override (repeatable) |
| `--config PATH` | — | Path to season.yaml with overrides |
| `--scoring-config PATH` | — | Path to custom scoring YAML |
| `--pff/--no-pff` | from config | Enable/disable PFF adjustments |
| `--training-years N` | from config | Number of historical seasons for training data |

**Examples:**
```bash
# Simulate 2024 Week 1
fantasy-sim week 1 --season 2024 --sims 100

# Week 5 with standard scoring, export to CSV
fantasy-sim week 5 --season 2024 --scoring standard --format csv --output week5.csv

# What if Mahomes misses Week 3?
fantasy-sim week 3 --season 2024 --override "patrick_mahomes.games_played=0"

# Use a season config file
fantasy-sim week 1 --season 2024 --config config/season.example.yaml
```

---

## `season`

Simulate a full NFL season (all weeks) using real nflverse data.

```bash
fantasy-sim season [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--season YEAR` | 2024 | NFL season year |
| `--weeks RANGE` | all | Weeks to simulate: `all`, `1-5`, `1,3,5,7` |
| `--sims N` | from config | Sims per game (use lower values for full season: 20-50) |
| `--scoring FORMAT` | ppr | Scoring format: `ppr`, `half_ppr`, `standard` |
| `--format FORMAT` | table | Output format: `table`, `csv`, `json` |
| `--output PATH` | — | File path for csv/json export |
| `--detail` | off | Show floor/ceiling/stddev for all stats |
| `--override "X.Y=Z"` | — | Player/team override (repeatable) |
| `--config PATH` | — | Path to season.yaml with overrides |
| `--scoring-config PATH` | — | Path to custom scoring YAML |
| `--pff/--no-pff` | from config | Enable/disable PFF adjustments |
| `--training-years N` | from config | Number of historical seasons for training data |

**Examples:**
```bash
# Full 2024 season (use fewer sims for speed)
fantasy-sim season --season 2024 --sims 20

# Just weeks 1-5
fantasy-sim season --season 2024 --weeks 1-5 --sims 50

# Specific weeks only
fantasy-sim season --season 2024 --weeks 1,3,5,7,9 --sims 50

# Export full season rankings
fantasy-sim season --season 2024 --sims 30 --format json --output season_rankings.json
```

---

## `game`

Simulate a single game with per-team deep-dive projections. Shows both teams' player breakdowns, game score distribution, and win probabilities.

```bash
fantasy-sim game HOME_TEAM AWAY_TEAM [OPTIONS]
```

| Argument/Flag | Default | Description |
|------|---------|-------------|
| `HOME_TEAM` | *(required)* | Home team abbreviation (e.g., KC, BUF, SF) |
| `AWAY_TEAM` | *(required)* | Away team abbreviation |
| `--week N` | 1 | Week number for schedule context |
| `--season YEAR` | 2024 | NFL season year |
| `--sims N` | from config | Number of simulations |
| `--scoring FORMAT` | ppr | Scoring format |
| `--scoring-config PATH` | — | Path to custom scoring YAML |
| `--demo` | off | Use synthetic data instead of nflverse |
| `--detail` | off | Show floor/ceiling/stddev |
| `--override "X.Y=Z"` | — | Player/team override (repeatable) |
| `--config PATH` | — | Path to season.yaml with overrides |
| `--pff/--no-pff` | from config | Enable/disable PFF adjustments |
| `--training-years N` | from config | Number of historical seasons for training data |

**Examples:**
```bash
# KC vs BUF deep dive
fantasy-sim game KC BUF --week 1 --season 2024 --sims 200

# With detailed distributions
fantasy-sim game SF DAL --week 5 --season 2024 --detail

# Demo mode (no data needed)
fantasy-sim game HOME AWAY --demo --sims 100

# What if KC's pass rate increases?
fantasy-sim game KC BUF --week 1 --override "KC.pass_rate=0.65"
```

**Output includes:**
- Average score + win percentages
- HOME team projections (QB, RB, WR, TE tables)
- AWAY team projections (QB, RB, WR, TE tables)

---

## `player`

Show a single player's projection with detailed stat distributions. Uses fuzzy name matching — you can type partial or informal names.

```bash
fantasy-sim player PLAYER_QUERY [OPTIONS]
```

| Argument/Flag | Default | Description |
|------|---------|-------------|
| `PLAYER_QUERY` | *(required)* | Player name (fuzzy matched) or nflverse player_id |
| `--week N` | 1 | Week number |
| `--season YEAR` | 2024 | NFL season year |
| `--sims N` | from config | Number of simulations |
| `--scoring FORMAT` | ppr | Scoring format |
| `--scoring-config PATH` | — | Path to custom scoring YAML |
| `--demo` | off | Use synthetic data |
| `--override "X.Y=Z"` | — | Player/team override (repeatable) |
| `--config PATH` | — | Path to season.yaml with overrides |
| `--pff/--no-pff` | from config | Enable/disable PFF adjustments |
| `--training-years N` | from config | Number of historical seasons for training data |

**Examples:**
```bash
# Fuzzy name matching works
fantasy-sim player "mahomes" --week 1 --season 2024 --sims 200
fantasy-sim player "travis kelce" --week 1 --season 2024
fantasy-sim player "cmac" --week 3 --season 2024

# What if a player's target share changes?
fantasy-sim player "nico collins" --week 5 --override "nico_collins.target_share=0.30"

# Demo mode
fantasy-sim player "WR1" --demo --sims 100
```

**Output:** A stat card showing Avg, Floor (10th pct), Ceiling (90th pct), and StdDev for every stat: FPts, Rush Yds, Rush TD, Targets, Rec, Rec Yds, Rec TD, Fum Lost.

---

## `backtest`

Run historical validation against a past season. Builds models using only prior-season data (no leakage), projects every week, and compares to actual results.

```bash
fantasy-sim backtest [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--season YEAR` | 2024 | Season to backtest against |
| `--sims N` | 100 | Sims per game (lower = faster, 50-100 recommended) |
| `--scoring FORMAT` | ppr | Scoring format |
| `--training-years N` | 3 | Number of prior seasons for model fitting |

**Examples:**
```bash
# Backtest 2024 season
fantasy-sim backtest --season 2024 --sims 50

# Backtest 2023 with standard scoring
fantasy-sim backtest --season 2023 --scoring standard --sims 100

# Use more training data
fantasy-sim backtest --season 2024 --training-years 5
```

**Output:** Validation report with pass/fail for each accuracy metric:
- Weekly MAE (target: < 6.0)
- Season Total MAE (target: < 25.0)
- Rank Correlation per position (target: > 0.80)
- Boom/Bust Calibration (target: < 0.10)

---

## Standalone Validation Scripts

These are standalone Python scripts (not `fantasy-sim` subcommands). They require network access and PFF data.

### Season-Level A/B Validation

Compares PFF-on vs PFF-off projections at season-level granularity. See `scripts/validate_pff_signal.py`.

```bash
# Run A/B test for all PFF layers
uv run python scripts/validate_pff_signal.py --mode all --sims 50

# Test specific layer combination
uv run python scripts/validate_pff_signal.py --mode coverage+tier --sims 50

# Record result in the ledger
uv run python scripts/validate_pff_signal.py --mode all --sims 50 --label "baseline-v1"

# View progression across runs
uv run python scripts/validate_pff_signal.py --show-ledger

# Override PFF config for sweep testing
uv run python scripts/validate_pff_signal.py --mode tier --config-override '{"tier_engine": {"reliability_floor": 0.30}}'
```

### Weekly A/B Validation

Per-week, per-player PFF signal evaluation. Retains weekly granularity instead of aggregating to season-level. Measures per-position rank correlation, MAE, MAE by matchup difficulty, and WR directional accuracy. See `scripts/validate_weekly_signal.py`.

```bash
# Run weekly validation for all positions
uv run python scripts/validate_weekly_signal.py --mode all --sims 50

# Test specific PFF layers on WR only
uv run python scripts/validate_weekly_signal.py --mode coverage+tier --positions WR --sims 50

# Record result in the weekly ledger
uv run python scripts/validate_weekly_signal.py --mode all --sims 50 --label "weekly-baseline"

# View weekly ledger progression
uv run python scripts/validate_weekly_signal.py --show-ledger
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode MODE` | all | PFF layer(s) to enable: `matchup`, `tier`, `matchup+tier`, `coverage+tier`, `coverage+tier+matchup`, `team_context+tier`, `team_context+tier+matchup`, `ncaa_rookie+tier`, `ncaa_rookie+tier+matchup`, `talent`, `all` |
| `--sims N` | 50 | Simulations per game |
| `--seasons YEAR [YEAR...]` | 2023 2024 | Test seasons to backtest |
| `--training-years N` | 2 | Number of prior seasons for model fitting |
| `--scoring FORMAT` | ppr | Scoring format |
| `--positions POS [POS...]` | QB RB WR TE | Positions to evaluate |
| `--label TEXT` | — | Label for ledger entry (required for recording) |
| `--show-ledger` | — | Print ledger progression table and exit |
| `--config-override JSON` | — | PFF config overrides as JSON |

---

## Common Options

These options appear on most commands:

### `--scoring FORMAT`

Fantasy scoring format. Built-in options:

| Format | Reception Points | Description |
|--------|-----------------|-------------|
| `ppr` | 1.0 per reception | Point Per Reception (most common) |
| `half_ppr` | 0.5 per reception | Half PPR |
| `standard` | 0 per reception | No reception bonus |

All formats share: 0.04/pass yard, 4/pass TD, -2/INT, 0.1/rush yard, 6/rush TD, 0.1/rec yard, 6/rec TD, -2/fumble lost.

### `--scoring-config PATH`

Load a custom scoring YAML file that inherits from a preset and overrides specific values:

```yaml
# config/custom_scoring.yaml
inherit: ppr
overrides:
  passing_td: 6           # 6-point passing TDs
  reception_wr: 1.5       # WR premium
  reception_te: 1.5       # TE premium
  rushing_bonus_100: 3    # 3 bonus pts for 100+ rush yards
  receiving_bonus_100: 3  # 3 bonus pts for 100+ rec yards
  passing_bonus_300: 3    # 3 bonus pts for 300+ pass yards
```

### `--override "name.field=value"`

Apply a runtime override. Repeatable (use multiple `--override` flags).

**Player overrides:**
```bash
--override "mahomes.target_share=0.30"
--override "kelce.games_played=14"
--override "bijan_robinson.carry_share=0.75"
--override "nico_collins.red_zone_target_share=0.25"
```

Supported player fields: `target_share`, `carry_share`, `red_zone_target_share`, `red_zone_carry_share`, `snap_share`, `scramble_rate`, `catch_rate`, `fumble_rate`, `games_played`, `games_missed`.

**Team overrides:**
```bash
--override "KC.pass_rate=0.65"
--override "BUF.sack_rate=0.08"
--override "SF.int_rate=0.03"
```

Supported team fields: `pass_rate`, `int_rate`, `fumble_rate`, `sack_rate`, `sack_fumble_rate`, `pace_plays_per_game`.

**Redistribution:** When a player's target or carry share is overridden, the delta is automatically redistributed proportionally to eligible teammates.

### `--config PATH`

Load overrides from a YAML file (e.g., `config/season.yaml`):

```yaml
season: 2025
scoring_format: ppr

teams:
  KC:
    pass_rate: 0.62
  BUF:
    pass_rate: 0.58

players:
  patrick_mahomes:
    games_missed: [4, 5, 6]
  nico_collins:
    target_share: 0.28
  bijan_robinson:
    carry_share: 0.72
    red_zone_carry_share: 0.80
```

### `--detail`

Show floor (10th percentile), ceiling (90th percentile), and standard deviation for all stats — not just mean projections. Available on `demo`, `week`, `season`, and `game` commands.

### `--format FORMAT`

Output format: `table` (terminal, default), `csv`, or `json`. Use with `--output PATH` to write to file.

---

## Standalone Market-History Scripts

These are standalone scripts used to build the local historical market archive
under `~/.fantasy-sim/market-history/`. They are not `fantasy-sim`
subcommands.

### `fetch_market_history_events.py`

Fetches and caches The Odds API historical NFL **event ids** by gameday, then
builds season inventory parquet files. This is the first acquisition step and
should be run before pulling player props.

```bash
uv run python scripts/fetch_market_history_events.py --season YEAR [YEAR ...] [OPTIONS]
```

**Auth:** Reads `THE_ODDS_API_KEY` (or legacy `THE_ODDS_API`) from
`~/.fantasy-sim/market-history/.env` or the shell environment.

| Flag | Default | Description |
|------|---------|-------------|
| `--season YEAR [YEAR ...]` | *(required)* | Seasons to fetch, e.g. `2023 2024 2025` |
| `--delay SECONDS` | `0.5` | Sleep between requests |
| `--force` | off | Re-fetch raw JSON even if the cache file already exists |
| `--rebuild-only` | off | Skip network calls and rebuild inventory parquet from cached raw JSON |

**Raw cache layout:**
- `~/.fantasy-sim/market-history/raw/events/<season>/<gameday>.json`

**Processed output:**
- `~/.fantasy-sim/market-history/processed/events_inventory_<season>.parquet`

**Examples:**
```bash
# Fetch regular-season event inventory for 2023-2025
uv run python scripts/fetch_market_history_events.py --season 2023 2024 2025

# Rebuild inventories from raw cached JSON only
uv run python scripts/fetch_market_history_events.py --season 2023 2024 2025 --rebuild-only

# Re-fetch 2025 event snapshots from the API
uv run python scripts/fetch_market_history_events.py --season 2025 --force
```

### `fetch_market_history_props.py`

Fetches and caches The Odds API historical **player props** for cached event
inventory rows. This is the second acquisition step and runs against the
season inventories produced by `fetch_market_history_events.py`.

```bash
uv run python scripts/fetch_market_history_props.py --season YEAR [YEAR ...] [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--season YEAR [YEAR ...]` | *(required)* | Seasons to fetch |
| `--week N [N ...]` | all | Restrict to specific weeks |
| `--markets KEY [KEY ...]` | core 8 markets | Markets to request from The Odds API |
| `--regions REGION` | `us` | Region(s) to request; NFL use should generally stay `us` |
| `--snapshot-label LABEL` | `close_core8` | Cache label for this snapshot set |
| `--date-source FIELD` | `commence_time` | Inventory field used to build the historical snapshot date |
| `--offset-minutes N` | `0` | Offset added to the selected `date-source` |
| `--delay SECONDS` | `0.5` | Sleep between requests |
| `--limit N` | — | Limit the number of events fetched; useful for probing |
| `--force` | off | Re-fetch even if the raw props snapshot already exists |

**Supported `--date-source` values:**
- `commence_time`
- `snapshot_date`
- `previous_snapshot_timestamp`
- `next_snapshot_timestamp`

**Default core markets:**
- `player_pass_attempts`
- `player_pass_yds`
- `player_pass_tds`
- `player_rush_attempts`
- `player_rush_yds`
- `player_receptions`
- `player_reception_yds`
- `player_anytime_td`

**Raw cache layout:**
- `~/.fantasy-sim/market-history/raw/props/<season>/<snapshot-label>/<event_id>.json`

**Examples:**
```bash
# One-event probe for 2024 Week 1 close snapshots
uv run python scripts/fetch_market_history_props.py \
  --season 2024 \
  --week 1 \
  --markets player_pass_yds \
  --snapshot-label close_core8 \
  --limit 1

# Close snapshots for all core markets in 2023-2025
uv run python scripts/fetch_market_history_props.py \
  --season 2023 2024 2025 \
  --snapshot-label close_core8

# Pull a pre-kick snapshot 30 minutes before kickoff
uv run python scripts/fetch_market_history_props.py \
  --season 2025 \
  --snapshot-label close_minus_30 \
  --date-source commence_time \
  --offset-minutes -30
```

### `build_market_history_player_markets.py`

Builds processed **market-native player-week signals** from cached raw props
JSON. This is the current processed layer for The Odds API player props.

```bash
uv run python scripts/build_market_history_player_markets.py --season YEAR [YEAR ...] [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--season YEAR [YEAR ...]` | *(required)* | Seasons to build |
| `--snapshot-label LABEL` | `close_core8` | Raw props snapshot label to aggregate |

**Processed output:**
- `~/.fantasy-sim/market-history/processed/player_markets_<season>_<snapshot-label>.parquet`

**Examples:**
```bash
# Build processed player-week market signals from the close-core8 archive
uv run python scripts/build_market_history_player_markets.py \
  --season 2023 2024 2025 \
  --snapshot-label close_core8
```

### `import_market_history.py`

Legacy importer for the older placeholder `market_history_weekly_<season>.parquet`
cache. The current Phase 3 runtime uses
`build_market_history_player_markets.py` and
`player_markets_<season>_<snapshot-label>.parquet` instead.

```bash
uv run python scripts/import_market_history.py --season YEAR [YEAR ...]
```

**Examples:**
```bash
uv run python scripts/import_market_history.py --season 2023 2024 2025
```

---

## Resolution Order

When multiple config sources are used, they merge in this order (later overrides earlier):

1. `config/defaults.yaml` — Base scoring rules and simulation settings
2. `config/season.yaml` — Auto-loaded if present (team/player overrides)
3. `--config PATH` — Explicit override config file
4. `--scoring-config PATH` — Custom scoring rules
5. `--override "X.Y=Z"` — CLI flags (highest priority)
