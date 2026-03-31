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

## Resolution Order

When multiple config sources are used, they merge in this order (later overrides earlier):

1. `config/defaults.yaml` — Base scoring rules and simulation settings
2. `config/season.yaml` — Auto-loaded if present (team/player overrides)
3. `--config PATH` — Explicit override config file
4. `--scoring-config PATH` — Custom scoring rules
5. `--override "X.Y=Z"` — CLI flags (highest priority)
