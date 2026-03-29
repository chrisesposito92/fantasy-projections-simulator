# Fantasy Projections Simulator — Design Spec

## Overview

A Python CLI tool that simulates NFL games play-by-play using a state machine driven by historical nflverse data. Produces fantasy point projections for all offensive skill positions (QB, RB, WR, TE), kickers, and team DST. Fully configurable scoring, player/team overrides, and multiple output formats.

The simulator runs Monte Carlo simulations (N games per matchup) to produce not just point estimates but full statistical distributions — floor, ceiling, median, standard deviation — for every stat and every player.

## Goals

- Produce accurate fantasy point projections competitive with public consensus (FantasyPros, ESPN)
- Enable "what if" analysis via player and team overrides
- Support any fantasy scoring format via config-driven scoring
- Generate full stat lines, not just fantasy points
- Validate accuracy via backtesting against historical seasons

## Language & Interface

- **Language:** Python
- **Interface:** CLI (web dashboard planned for future)
- **Data source:** nflverse via nflreadpy

## Architecture

```
+---------------+    +----------------+    +-------------------+
|  Data Layer   |--->| Player/Team    |--->|   Simulation      |
|  (nflverse)   |    |   Models       |    |    Engine          |
+---------------+    +----------------+    +---------+---------+
                                                     |
+---------------+    +----------------+              |
|   Config      |--->|   Scoring      |<-------------+
|   System      |    |   Engine       |
+---------------+    +--------+-------+
                              |
                     +--------v-------+
                     |   Output /     |
                     |   Reports      |
                     +----------------+
```

1. **Data Layer** — Fetches and caches historical PBP, player stats, rosters, schedules from nflverse. Preprocesses into probability distributions the sim engine needs.
2. **Player/Team Models** — Per-team and per-player statistical profiles: play-calling tendencies, usage rates, outcome distributions. Built from historical data, overridable via config.
3. **Simulation Engine** — The state-machine core. Takes two team models, simulates a game play-by-play, outputs a complete box score.
4. **Config System** — YAML files for scoring rules, player/team overrides, simulation parameters.
5. **Scoring Engine** — Takes raw simulated stats and applies fantasy scoring rules to produce fantasy points.
6. **Output/Reports** — Rankings, distributions, full stat lines, CSV/JSON export, terminal tables.

---

## Data Layer

### Data Sources (nflreadpy)

| Function | Data | Use |
|----------|------|-----|
| `load_pbp()` | Play-by-play, 372+ columns (2000-present) | Primary source for fitting all probability distributions |
| `load_player_stats()` | Weekly player stats (114 columns) | Building player usage profiles (target share, carry share, snap share) |
| `load_rosters_weekly()` | Weekly rosters with positions, status | Knowing the active player pool each week |
| `load_schedules()` | Game matchups, home/away, spreads, over/unders | Setting up simulation matchups |
| `load_snap_counts()` | Per-game snap counts (2012+) | Modeling player involvement levels |
| `load_depth_charts()` | Starter/backup designations | Informing default usage distributions |
| `load_draft_picks()` | Historical draft data | Building rookie archetype profiles |

### Caching Strategy

- First run downloads and caches raw data locally as parquet files in `~/.fantasy-sim/cache/`
- Preprocessed distributions cached separately so the sim engine doesn't re-derive them every run
- Cache invalidation based on nflverse release dates (they update weekly during the season)

### Preprocessing Outputs

These are the derived artifacts that feed the simulation engine:

- **Play-calling distributions** per team: P(run|state), P(pass|state), P(play-action|state), conditioned on game state buckets (down, distance, score differential, quarter)
- **Play outcome distributions**: Yards gained distributions by play type, conditioned on game state
- **Player usage models**: Per-player probability of being the ball carrier/target given a play type and game state
- **Turnover/penalty rates**: Per-team rates for INTs, fumbles, penalties by type
- **Kicking models**: FG make probability by distance, XP rate
- **Drive start models**: Kickoff return distributions, touchback rates

### Historical Depth

Default: last 3 seasons of PBP data for distribution fitting, recency-weighted (e.g., 2022: 0.2, 2023: 0.3, 2024: 0.5). Configurable via settings.

---

## Simulation Engine

### Game State

```
{
  quarter: 1-5,            // 5 = overtime
  clock: int,              // seconds remaining in quarter
  possession: home | away,
  down: 1-4,
  distance: int,           // yards to first down
  yard_line: 1-99,         // own 1 to opponent 1
  home_score: int,
  away_score: int
}
```

### Simulation Loop (One Game)

1. **Coin toss** — Determine who receives first (random, or configurable)
2. **Kickoff** — Sample return distance or touchback from distributions
3. **Play Selection** — Given current state, the possessing team's model picks a play type:
   - Run vs. pass (conditioned on down, distance, score diff, quarter, clock)
   - On 4th down: punt, FG attempt, or go-for-it (based on yard line + team aggression profile)
4. **Player Selection** — Given play type + game state, select the involved player(s):
   - Pass play: select passer (QB), target receiver (weighted by target share in this game state), potential rusher on scramble
   - Run play: select ball carrier (weighted by carry share)
5. **Play Outcome** — Sample from the outcome distribution for this play type + state:
   - Yards gained (can be negative)
   - Completion/incompletion (for passes)
   - Touchdown check (if yards gained crosses goal line)
   - Turnover check (INT rate for passes, fumble rate for any play)
   - Penalty check (false start, holding, PI — affects down/distance/yards)
   - Sack check (for pass plays — affects yards + fumble probability)
   - Safety check (if sack or penalty results in ball behind own goal line)
6. **State Transition** — Update down, distance, yard line, clock, score:
   - First down if distance covered
   - Score change if TD/FG/safety
   - Possession change on turnover, punt, score, downs
   - Clock runoff (sampled based on play type — runs eat more clock)
7. **Special Events:**
   - Two-minute warning clock stop
   - PAT/2-point conversion after TDs (team-specific tendency)
   - Safety results in 2 points to defense + free kick
   - End of quarter/half handling
   - Overtime rules (current NFL OT format)
8. **Repeat** until game clock expires

### Stat Accumulation

Every play writes to a running box score — passing yards, rushing yards, receptions, targets, etc., attributed to the specific players involved. At game end, a complete stat line exists for every player who participated.

### Monte Carlo Layer

Run the simulation loop N times per game (configurable, default 1,000). Each sim produces different outcomes due to random sampling. The collection of N stat lines per player gives the full distribution (mean, median, floor, ceiling, standard deviation).

### Key Modeling Nuances

- **Game script awareness**: Score differential naturally shifts play-calling (teams behind pass more, teams ahead run more) because play selection distributions are conditioned on score diff
- **Garbage time**: Emerges naturally — teams down big in Q4 spike pass rate, completion rates shift
- **Teammate correlation**: Built in by design — if WR1 gets a target on a play, WR2 doesn't. Targets are zero-sum within a play
- **Clock management**: Late-game scenarios modeled via clock runoff distributions conditioned on game state

---

## Player & Team Models

### Team Model (one per team per season)

| Attribute | Description | Source |
|-----------|-------------|--------|
| Play-calling tendencies | Run/pass ratio by game state bucket | 3yr PBP, recency-weighted |
| Pace | Plays per game, seconds per play | PBP |
| Aggressiveness | 4th-down go-for-it rates, 2PT conversion tendency | PBP |
| O-line quality | Sack rate allowed, rush yards before contact | PBP |
| Penalty rates | Per-play penalty probability by type | PBP |
| Turnover tendency | Team-level INT rate, fumble rate baseline | PBP |

### Player Model (one per player)

**Usage Profile** (share of team's plays this player is involved in, bucketed by game state):

| Position | Key Usage Metrics |
|----------|-------------------|
| QB | Snap share, scramble rate, sack rate |
| RB | Carry share, target share, routes run per snap, red zone carry share |
| WR/TE | Target share, air yards share, red zone target share, slot vs. outside rate |
| K | Inherited from team's FG attempt rate + distance distribution |

**Outcome Distributions** (given this player is targeted/carries the ball, what happens):

| Position | Key Outcome Metrics |
|----------|---------------------|
| QB | Completion rate, air yards distribution, INT rate, sack-fumble rate, rushing yards per scramble |
| RB | Yards per carry distribution, fumble rate, receiving yards per target |
| WR/TE | Catch rate, yards-after-catch distribution, contested catch rate, TD rate in red zone |

**Injury/Availability:** Games projected to play (default 17, overridable).

### Rookie Handling

Rookies have zero NFL data, handled in tiers:

1. **Draft capital + positional archetypes** — Build archetype profiles from historical rookies at the same position and draft range (e.g., "1st round WR, picks 1-15, last 10 years"). nflverse `load_draft_picks()` provides the data.
2. **Depth chart signals** — `load_depth_charts()` reveals if a rookie is slotted as starter vs. backup. Starter inherits higher usage baseline.
3. **Rapid convergence** — After 1-2 NFL games, blend in actual data. Blend weight shifts from archetype-heavy to data-heavy as games accumulate. Configurable blend threshold (default: 4 games before data fully overtakes archetype).

### Override Integration

Overrides replace model-derived values at this layer. When `"nico_collins.target_share": 0.28` is set in config, it directly replaces the model's derived target share before simulation runs. The sim engine never knows the difference.

**Player identification:** Players in config files are referenced by nflverse `player_id` (e.g., `00-0039337` for Nico Collins). The CLI also accepts player names via `--override "nico_collins.target_share=0.30"` which fuzzy-matches against the roster to resolve to the correct `player_id`. Ambiguous matches (e.g., multiple players named "Smith") prompt the user to disambiguate.

**Redistribution logic:** When an override increases a player's usage share (e.g., target share), the excess is subtracted proportionally from all other eligible players at the same position group on the same team. For example, if WR1's target share is overridden from 0.24 to 0.28 (+0.04), that 0.04 is subtracted from the team's other pass catchers (WRs + TEs + RBs who catch passes) in proportion to their existing shares. If an override *decreases* a share, the freed share is distributed proportionally the same way.

---

## Configuration System

Three tiers of YAML config that layer on top of each other:

### 1. `config/defaults.yaml` — Ships with the tool

```yaml
simulation:
  num_sims: 1000
  historical_seasons: [2022, 2023, 2024]
  recency_weights: [0.2, 0.3, 0.5]
  rookie_blend_games: 4

scoring:
  ppr:
    passing_yard: 0.04
    passing_td: 4
    interception: -2
    rushing_yard: 0.1
    rushing_td: 6
    reception: 1
    receiving_yard: 0.1
    receiving_td: 6
    fumble_lost: -2
    two_point: 2
    fg_0_39: 3
    fg_40_49: 4
    fg_50_plus: 5
    xp: 1
    fg_miss: -1
    dst_sack: 1
    dst_interception: 2
    dst_fumble_recovery: 2
    dst_td: 6
    dst_safety: 2
    dst_points_allowed_0: 10
    dst_points_allowed_1_6: 7
    dst_points_allowed_7_13: 4
    dst_points_allowed_14_20: 1
    dst_points_allowed_21_27: 0
    dst_points_allowed_28_34: -1
    dst_points_allowed_35_plus: -4
    # Note: "points allowed" = total points scored by the opponent (offensive + defensive/ST TDs).
    # This matches standard fantasy platform behavior (ESPN, Yahoo, Sleeper).
  half_ppr:
    _inherit: ppr
    reception: 0.5
  standard:
    _inherit: ppr
    reception: 0

positions:
  qb: { min_snaps: 200 }
  rb: { min_carries: 30, min_targets: 10 }
  wr: { min_targets: 30 }
  te: { min_targets: 20 }
  k: {}
  dst: {}
```

### 2. `config/season.yaml` — Per-season setup

```yaml
season: 2025
weeks: [1, 2, 3, 4, 5]  # or "all"
scoring_format: ppr

teams:
  KC:
    pace_plays_per_game: 66
    pass_rate: 0.62
  BUF:
    pass_rate: 0.58

players:
  nico_collins:
    target_share: 0.28
  patrick_mahomes:
    games_missed: [4, 5, 6]
  bijan_robinson:
    carry_share: 0.72
    red_zone_carry_share: 0.80
```

### 3. `config/custom_scoring.yaml` — Optional league-specific rules

```yaml
inherit: ppr
overrides:
  passing_td: 6
  reception_wr: 1.5
  reception_te: 1.5
  rushing_bonus_100: 3
```

### Resolution Order

`defaults.yaml` -> `season.yaml` -> `custom_scoring.yaml` -> CLI flags

Later values override earlier ones. CLI example:
```bash
python simulate.py week 5 --override "nico_collins.target_share=0.30"
```

---

## Output System

### CLI Commands

```bash
# Simulate a specific week
python simulate.py week 5

# Simulate full season
python simulate.py season

# Single game deep dive
python simulate.py game KC BUF --week 5

# Single player analysis
python simulate.py player "nico_collins" --week 5

# What-if scenario
python simulate.py week 5 --override "nico_collins.target_share=0.30"
```

### Output Format — Full Stat Lines

All relevant stats are returned alongside fantasy points.

**QB:**
```
Rank  Player           FPts   PaYd   PaTD  INT  RuYd  RuTD  Sck  FL   2PT
1     Patrick Mahomes  22.4   274    2.1   0.7  18.3  0.2   2.1  0.3  0.1
```

**RB:**
```
Rank  Player           FPts   RuYd   RuTD  Tgt  Rec   ReYd  ReTD  FL   2PT
1     Bijan Robinson   18.7   82.3   0.7   4.2  3.1   24.8  0.2   0.2  0.1
```

**WR/TE:**
```
Rank  Player           FPts   Tgt   Rec   ReYd   ReTD  RuYd  RuTD  FL   2PT
1     Nico Collins     17.2   8.4   5.8   78.2   0.6   2.1   0.0   0.1  0.0
```

**K:**
```
Rank  Player           FPts   FGA   FGM   FG50+  XPA   XPM
1     Harrison Butker  8.9    2.1   1.8   0.4    3.2   3.1
```

**DST:**
```
Rank  Team    FPts   Sck   INT   FR   DTD  Saf  PtsAllow
1     BAL     8.2    2.8   0.9   0.7  0.2  0.1  18.4
```

### Detail Mode

`--detail` flag shows floor/ceiling/stddev for every stat, not just fantasy points.

### Game Deep Dive

```
KC vs BUF — Week 5 (1000 sims)
Avg Score: KC 24.3 - BUF 22.8
KC Win%: 54.2%   BUF Win%: 45.8%

KC Key Players:          Avg    Floor  Ceil
  Mahomes (pass yds)     274    182    391
  Mahomes (pass TD)      2.1    0      4
  ...
```

### Export Formats

- `--format csv` — Full results to CSV
- `--format json` — Structured JSON
- Default: terminal table

Floor = 10th percentile, Ceiling = 90th percentile across simulations.

---

## Validation Framework

### Phase 1: Sanity Checks (realistic football)

Run the sim on historical seasons and verify:

- Average total points per game: 45-48
- Pass/rush yard totals per team in normal NFL ranges (passing ~220-250, rushing ~100-120)
- Target shares per team sum to ~100% of team pass targets
- Carry shares sum similarly for rushes
- Overtime rate ~5%
- Safeties are rare but occur
- No player produces absurd stat lines

### Phase 2: Accuracy Benchmarks

Backtest against 2023 and 2024 seasons:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Spearman rank correlation | > 0.80 per position | Projected season rankings vs actual, per position |
| Weekly MAE (top 24) | < 6.0 fantasy pts | Mean absolute error per player per week for starters |
| Season total MAE (top 24) | < 25 pts per position | Full-season projected total vs actual |
| Boom/bust calibration | Within 10% | If sim says 20% chance of 25+ pts, should happen 18-22% historically |
| vs. Consensus | Competitive | MAE within 15% of FantasyPros consensus accuracy |

### Backtesting Methodology

1. Feed the simulator only data available before the test season (e.g., to test 2024, use only 2022-2023 for model fitting)
2. Run projections for each week
3. Compare projected stats and fantasy points against actual results
4. Calculate all metrics
5. Output a validation report

---

## Testing Strategy

Tests are woven into every phase. Each phase isn't done until its tests pass.

### Phase 1 — Data Pipeline Tests

- Data loading returns expected schemas (correct columns, types, no unexpected nulls)
- Cache hit/miss works correctly (second load is faster, identical results)
- Distribution preprocessing produces valid probability distributions (sum to 1.0, no negatives)
- Edge cases: player with 1 game of data, team relocations

### Phase 2 — State Machine Tests

**Unit tests per game mechanic:**
- First down resets distance to 10
- Touchdown triggers PAT/2PT and kickoff
- 4th down with no conversion flips possession
- Safety awards 2 points and free kick to defense
- Overtime ends correctly per current NFL rules
- Two-minute warning stops clock
- Game ends when Q4 clock hits 0 (no OT needed)
- Penalties correctly adjust down/distance/yard line (including offsetting, declined)

**Statistical tests on bulk simulations (10,000+ games):**
- Average points per game: 44-50
- Home team win rate: 52-57%
- Overtime rate: 4-7%
- Average plays per game: 120-140
- Combined turnovers per game: ~3-4
- Safety rate: ~1 per 50 games

### Phase 3 — Player Model Tests

**Unit tests:**
- Target shares for a team's receivers sum to ~1.0
- Carry shares for a team's RBs sum to ~1.0
- Rookie archetype returns plausible profile for known draft positions
- Player with 0 games missed plays all 17 weeks
- Player with games_missed override sits those weeks

**Statistical tests on bulk simulations:**
- Top QB passing yards per game: 240-290 average
- Lead RBs: 55-90 rush yards per game average
- WR1s: 5-9 targets per game average
- No player averages negative yards at any stat
- TE target shares lower than WR target shares on same team
- Kicker FG attempts per game: 1.5-2.5 average
- DST sacks per game: 2-3 average

### Phase 4 — Scoring + Config Tests

**Unit tests:**
- PPR: 5 receptions + 100 receiving yards + 1 TD = 21 points
- Standard: same stat line = 16 points
- Custom scoring with bonuses applies correctly
- Config inheritance works (custom overrides base, CLI overrides config)
- Invalid config raises helpful errors

**Integration tests:**
- End-to-end: simulate a week, verify every player's fantasy points = sum of stats x scoring weights
- CSV and JSON exports contain all expected columns and valid data
- All CLI flags work (`--week`, `--format`, `--override`, `--scoring`)

### Phase 5 — Validation Tests

- Backtest harness excludes future data (no leakage)
- Rank correlation calculation verified against known inputs
- MAE calculation verified
- Boom/bust calibration buckets computed correctly
- Validation report outputs all required metrics

### Phase 6 — Override Tests

- Player target share override redistributes remaining share to teammates
- Games missed override produces zero stats for those weeks
- Team pace override changes plays per game
- Team pass rate override shifts run/pass balance
- Stacking overrides (player + team on same team) doesn't conflict
- Override via CLI flag matches override via config file

### Testing Tools

- `pytest` as the framework
- `pytest-xdist` for parallel execution (statistical tests can be slow)
- `hypothesis` for property-based testing (e.g., "for any valid scoring config, fantasy points are never NaN")
- Tests in `tests/` directory mirroring `src/` structure

---

## Phased Build Plan

### Phase 1: Data Pipeline
Fetch and cache PBP, player stats, rosters, schedules, snap counts, depth charts via nflreadpy. Preprocess into play-calling distributions, play outcome distributions, team/player profiles.

**Done when:** Data loads reliably, distributions are computed and cached, basic statistical summaries match known NFL averages (league-average pass rate ~58%, avg yards per play ~5.5). All Phase 1 tests pass.

### Phase 2: Game State Machine
Implement the core sim loop: kickoff, plays, scoring, possession changes, game end. No individual players yet — team-level distributions only. Handle all special cases: 4th down decisions, FG attempts, punts, turnovers, safeties, penalties, two-minute warning, OT.

**Done when:** Simulated games produce realistic team-level stats (avg total points 45-48, pass/rush yard totals in normal ranges, overtime rate ~5%, reasonable score distributions). All Phase 2 tests pass.

### Phase 3: Player Models
Build per-player usage and outcome models from historical data. Implement rookie archetype system. Integrate player selection into the state machine so plays attribute to specific players.

**Done when:** Individual player stat distributions are plausible. Top QBs average 250+ pass yards, lead RBs average 60-80 rush yards, target shares sum correctly per team. All Phase 3 tests pass.

### Phase 4: Scoring + Config + CLI
Config system (defaults.yaml, season.yaml, custom_scoring.yaml). Scoring engine (raw stats to fantasy points). CLI interface with all commands. Output formatting (terminal tables, full stat lines, CSV, JSON).

**Done when:** Full end-to-end pipeline runs — `python simulate.py week 5` produces complete projections with all stats and fantasy points for every relevant player. All Phase 4 tests pass.

### Phase 5: Validation + Tuning
Backtest framework against 2023 and 2024 actuals. Implement all accuracy metrics. Iterative tuning of distributions and model parameters.

**Done when:**
- Rank correlation > 0.80 per position (season level)
- Weekly MAE < 6.0 for top-24 per position
- Boom/bust calibration within 10%
- Competitive with FantasyPros consensus (within 15% on MAE)
- All Phase 5 tests pass

### Phase 6: Overrides + Polish
Player-level and team-level override system in config and CLI flags. Error handling, progress bars, helpful error messages. Documentation.

**Done when:** Override scenarios produce sensible adjusted projections. Games-missed zeroes those weeks. Target share changes redistribute to teammates. README covers all usage. All Phase 6 tests pass.

---

## Future Enhancements (Out of Scope)

- Web dashboard UI (planned, separate project)
- Situational overrides (weather, game script conditional rules)
- IDP (individual defensive player) scoring
- College stats integration for rookie modeling
- PFF data integration (user has subscription, data extraction TBD)
- DFS lineup optimization
- Trade value analysis
- Draft ranking generator
