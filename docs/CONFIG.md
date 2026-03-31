# Configuration Reference

Complete reference for every configuration option in the fantasy projections simulator.

## Quick Start

```bash
# 1. Copy the example season config
cp config/season.example.yaml config/season.yaml

# 2. Edit it with your overrides
#    (see sections below for every available field)

# 3. Run — auto-detected from config/season.yaml
uv run fantasy-sim week 1 --season 2024 --sims 100

# Or pass explicitly (required for non-standard filenames)
uv run fantasy-sim week 1 --season 2024 --config config/season.2025.yaml
```

Minimal working `season.yaml`:

```yaml
players:
  tyreek_hill:
    target_share: 0.27
```

---

## Config File Types

The simulator uses three config files, each serving a different purpose:

| File | Purpose | How to Use |
|------|---------|-----------|
| `config/defaults.yaml` | Base scoring presets, simulation settings, position thresholds | Rarely edited. Changed by modifying the file directly. |
| `config/season.yaml` | Per-season player and team overrides | Created per season. Auto-detected or passed via `--config`. |
| `config/custom_scoring.yaml` | League-specific scoring rules | Created per league. Passed via `--scoring-config`. |

---

## Config Resolution Chain

Configuration merges through 5 layers. Higher layers override lower:

```
6. CLI --override "name.field=value"       (highest — always wins)
5. season.yaml  players: / teams:
4. --scoring-config  custom_scoring.yaml
3. season.yaml  scoring_format:            (overrides CLI --scoring)
2. season.yaml  season: / weeks:           (used when CLI flag not explicitly set)
1. config/defaults.yaml                    (lowest priority)
```

**Important:** `scoring_format` in season.yaml **always overrides** the CLI `--scoring` flag. The `season` and `weeks` keys are different — they only apply when the CLI flag is not explicitly passed (they act as defaults, not overrides).

---

## Season Config (`season.yaml`)

### Parsed Keys

All of these keys are read by the simulator:

| Key | Type | Description |
|-----|------|-------------|
| `season` | int | NFL season year. Used as default when `--season` is not explicitly passed on the CLI. |
| `weeks` | string | Weeks to simulate (`'all'`, `'1-5'`, or `'1,3,5'`). Used as default when `--weeks` is not explicitly passed (season command only). |
| `scoring_format` | string | `ppr`, `half_ppr`, or `standard`. Overrides CLI `--scoring`. |
| `players` | mapping | Player overrides keyed by name or nflverse player_id. |
| `teams` | mapping | Team overrides keyed by team code (e.g., `KC`, `BUF`). |

### Precedence

`season` and `weeks` from the config file act as **defaults** — they are used only when the corresponding CLI flag is not explicitly passed. An explicit `--season 2024` on the CLI always wins over `season: 2025` in the config file.

`scoring_format` works differently — it **always overrides** the CLI `--scoring` flag when present.

### Auto-Detection

The simulator checks for `config/season.yaml` (exact filename). Files with other names like `config/season.2025.yaml` are **not** auto-detected. Pass them explicitly:

```bash
uv run fantasy-sim week 1 --season 2025 --config config/season.2025.yaml
```

### Silent Skip Behavior

- If a player name in the `players:` section can't be resolved (typo, not on the active roster), it is **silently skipped**. No error is raised.
- Team overrides for teams not in the current matchup are **silently ignored**.

### Full Example

```yaml
# config/season.2025.yaml
season: 2025              # Documentation only (not parsed)
weeks: all                # Documentation only (not parsed)
scoring_format: half_ppr  # Parsed — overrides CLI --scoring

teams:
  KC:
    pass_rate: 0.62
    pace_plays_per_game: 68
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

---

## Player Override Fields

### Usage Fields

Control how often a player is involved in plays.

| Field | Type | Range | Positions | Notes |
|-------|------|-------|-----------|-------|
| `target_share` | float | 0.0 - 1.0 | WR, TE, RB | Fraction of team targets. **Triggers redistribution.** |
| `carry_share` | float | 0.0 - 1.0 | RB, QB | Fraction of team carries. **Triggers redistribution.** QBs need >= 0.10 to be in the designed-run pool. |
| `red_zone_target_share` | float | 0.0 - 1.0 | WR, TE, RB | Target share inside the 20. Does not trigger redistribution. |
| `red_zone_carry_share` | float | 0.0 - 1.0 | RB | Carry share inside the 20. Does not trigger redistribution. |
| `snap_share` | float | 0.0 - 1.0 | All | Determines starter (QB with highest snap_share starts). Does not trigger redistribution. |
| `scramble_rate` | float | 0.0 - 1.0 | QB | Rate at which the QB scrambles instead of passing. |

### Outcome Fields

Control what happens when a player is involved in a play.

| Field | Type | Range | Notes |
|-------|------|-------|-------|
| `catch_rate` | float | 0.0 - 1.0 | Catch success rate when targeted. |
| `fumble_rate` | float | 0.0 - 1.0 | Fumble rate per rush or reception. |

### Meta Fields

Control game availability.

| Field | Type | Notes |
|-------|------|-------|
| `games_played` | int | 1-17. Total games the player appears in. |
| `games_missed` | list of ints | Specific week numbers missed, e.g., `[4, 5, 6]`. **Must be a list** (not a single number). Automatically sets `games_played = 17 - len(list)`. |

### Not Overridable

These fields exist on the player model but are **computed-only** from play-by-play data. They cannot be set via overrides:

| Field | Model | Description |
|-------|-------|-------------|
| `air_yards_share` | PlayerUsage | Fraction of team air yards. |
| `red_zone_catch_rate` | PlayerOutcomes | RZ catch rate (from PBP or `catch_rate * 0.92` fallback). |
| `pass_fumble_rate` | PlayerOutcomes | Per-QB non-sack fumble rate. |
| `receiving_yards_dist` | PlayerOutcomes | Historical yards-per-catch distribution (numpy array). |
| `rz_receiving_yards_dist` | PlayerOutcomes | Red zone yards-per-catch distribution. |
| `rushing_yards_dist` | PlayerOutcomes | Historical yards-per-carry distribution. |
| `scramble_yards_dist` | PlayerOutcomes | Historical yards-per-scramble distribution. |

---

## Team Override Fields

| Field | Type | Range | Notes |
|-------|------|-------|-------|
| `pass_rate` | float | 0.0 - 1.0 | Fraction of plays that are passes. Run rate automatically becomes `1.0 - pass_rate`. |
| `int_rate` | float | 0.0 - 1.0 | Interception rate per pass play. |
| `fumble_rate` | float | 0.0 - 1.0 | Fumble rate per play. |
| `sack_rate` | float | 0.0 - 1.0 | Sack rate per pass play. |
| `sack_fumble_rate` | float | 0.0 - 1.0 | Fraction of sacks that result in fumbles. |
| `pace_plays_per_game` | float | > 0 | Total plays per game. Baseline is 65. Higher values = faster-paced offense, more total plays. Converted internally to a pace factor (`value / 65`). |

---

## What You Can't Override

| Category | Why Not | Workaround |
|----------|---------|------------|
| **Kickers** | Kicking is modeled at team level (`KickingModel`: FG make rate, XP rate). No per-kicker override fields exist. | Indirectly affected by `pace_plays_per_game` (more drives = more FG opportunities). |
| **DST scoring directly** | Defensive stats emerge from the opponent's offensive simulation. | Override the opponent's `int_rate`, `fumble_rate`, `sack_rate` to affect DST output. |
| **Yards distributions** | Stored as numpy arrays from historical PBP. Not expressible as simple config values. | No workaround. These are derived from multi-season PBP data. |
| **Computed rates** | `red_zone_catch_rate`, `pass_fumble_rate`, `air_yards_share` are derived from PBP. | Override the overridable counterpart where available (e.g., `catch_rate` affects overall catch rate). |
| **Schedule / matchups** | The simulator uses nflverse schedule data. | Use `--demo` mode for arbitrary matchups (`fantasy-sim game HOME AWAY --demo`). |

---

## Player Name Resolution

When you specify a player name in `season.yaml` or via `--override`, the simulator resolves it through four steps (in order):

| Step | Method | Example |
|------|--------|---------|
| 1 | Exact player_id match | `00-0036355` (nflverse ID) |
| 2 | Exact name match (case-insensitive) | `Patrick Mahomes` |
| 3 | Underscore-to-space conversion | `patrick_mahomes` -> "patrick mahomes" |
| 4 | Fuzzy match (thefuzz library) | `mahomes` -> "Patrick Mahomes" (score 90) |

Fuzzy match parameters:
- Minimum score to accept: **70/100**
- Ambiguity threshold: **5 points** (if 2+ players score within 5 of the best, raises `AmbiguousMatchError` listing all options)

### Demo Mode Player IDs

In demo mode, players use synthetic IDs. Use these for demo overrides:

| Home Team | Away Team |
|-----------|-----------|
| `HOME_QB` | `AWAY_QB` |
| `HOME_WR1` | `AWAY_WR1` |
| `HOME_WR2` | `AWAY_WR2` |
| `HOME_TE` | `AWAY_TE` |
| `HOME_RB1` | `AWAY_RB1` |
| `HOME_RB2` | `AWAY_RB2` |

```bash
uv run fantasy-sim demo --sims 100 --override "HOME_WR1.target_share=0.30"
```

---

## Share Redistribution

When you change `target_share` or `carry_share`, the delta is automatically redistributed to eligible teammates to keep shares balanced.

### How It Works

1. The delta (new value - old value) is calculated
2. Eligible teammates are those with share > 0 for that field
3. The delta is subtracted proportionally from teammates based on their current share
4. No teammate's share goes below 0.0

### Example

WR1 has `target_share: 0.24`. You override to `0.30` (+0.06 delta).

Before:
```
WR1: 0.24, WR2: 0.18, TE: 0.16, RB1: 0.10, RB2: 0.05
```

After (0.06 subtracted proportionally from WR2, TE, RB1, RB2):
```
WR1: 0.30, WR2: 0.158, TE: 0.140, RB1: 0.088, RB2: 0.044
```

### Which Fields Trigger Redistribution

| Field | Redistributes? |
|-------|---------------|
| `target_share` | Yes |
| `carry_share` | Yes |
| `red_zone_target_share` | No |
| `red_zone_carry_share` | No |
| `snap_share` | No |
| `scramble_rate` | No |

---

## Scoring Configuration

### Built-in Presets

All values shown. `half_ppr` and `standard` inherit from `ppr` and only override `reception`.

#### Offensive Scoring

| Key | PPR | Half PPR | Standard | Description |
|-----|-----|----------|----------|-------------|
| `passing_yard` | 0.04 | 0.04 | 0.04 | Points per passing yard |
| `passing_td` | 4 | 4 | 4 | Points per passing TD |
| `interception` | -2 | -2 | -2 | Points per interception thrown |
| `rushing_yard` | 0.1 | 0.1 | 0.1 | Points per rushing yard |
| `rushing_td` | 6 | 6 | 6 | Points per rushing TD |
| `reception` | 1 | 0.5 | 0 | Points per reception (base) |
| `receiving_yard` | 0.1 | 0.1 | 0.1 | Points per receiving yard |
| `receiving_td` | 6 | 6 | 6 | Points per receiving TD |
| `fumble_lost` | -2 | -2 | -2 | Points per fumble lost |
| `two_point` | 2 | 2 | 2 | Points per 2-point conversion |

#### Kicker Scoring

| Key | Default | Description |
|-----|---------|-------------|
| `fg_0_39` | 3 | Points per FG made, 0-39 yards |
| `fg_40_49` | 4 | Points per FG made, 40-49 yards |
| `fg_50_plus` | 5 | Points per FG made, 50+ yards |
| `xp_made` | 1 | Points per extra point made |
| `fg_miss` | -1 | Points per missed field goal |

#### DST Scoring

| Key | Default | Description |
|-----|---------|-------------|
| `dst_sack` | 1 | Points per sack |
| `dst_interception` | 2 | Points per interception |
| `dst_fumble_recovery` | 2 | Points per fumble recovery |
| `dst_td` | 6 | Points per defensive/ST touchdown |
| `dst_safety` | 2 | Points per safety |

#### DST Points-Allowed Brackets

Exactly one bracket applies per game based on the opponent's final score:

| Key | Score Range | Default Points |
|-----|------------|----------------|
| `dst_points_allowed_0` | 0 (shutout) | 10 |
| `dst_points_allowed_1_6` | 1-6 | 7 |
| `dst_points_allowed_7_13` | 7-13 | 4 |
| `dst_points_allowed_14_20` | 14-20 | 1 |
| `dst_points_allowed_21_27` | 21-27 | 0 |
| `dst_points_allowed_28_34` | 28-34 | -1 |
| `dst_points_allowed_35_plus` | 35+ | -4 |

### Custom Scoring Config

Create a YAML file that inherits from a preset and overrides specific values:

```yaml
# config/custom_scoring.yaml
inherit: ppr       # Required: base preset (ppr, half_ppr, or standard)

overrides:         # Optional: scoring keys to override or add
  passing_td: 6
  reception_te: 1.5
  rushing_bonus_100: 3
  receiving_bonus_100: 3
  passing_bonus_300: 3
```

Usage:
```bash
uv run fantasy-sim week 1 --scoring-config config/custom_scoring.yaml
```

### Position-Specific Reception Keys

Override the base `reception` value for specific positions:

| Key | Overrides `reception` for | Example Use Case |
|-----|--------------------------|-----------------|
| `reception_qb` | QBs | Rare, but available |
| `reception_rb` | Running backs | Devalue RB receptions |
| `reception_wr` | Wide receivers | |
| `reception_te` | Tight ends | TE premium leagues |

If a position-specific key is not set, the generic `reception` value is used.

```yaml
# TE premium: TEs get 1.5 per catch, everyone else gets 1.0
inherit: ppr
overrides:
  reception_te: 1.5
```

### Yardage Bonuses

Yardage bonuses are **stackable**: a player with 210 rush yards triggers both the 100-yard and 200-yard bonuses.

| Key | Threshold | Example |
|-----|-----------|---------|
| `rushing_bonus_100` | >= 100 rush yards | 3 points |
| `rushing_bonus_200` | >= 200 rush yards | 3 points (stacks with 100) |
| `receiving_bonus_100` | >= 100 receiving yards | 3 points |
| `receiving_bonus_200` | >= 200 receiving yards | 3 points |
| `passing_bonus_300` | >= 300 passing yards | 3 points |
| `passing_bonus_400` | >= 400 passing yards | 3 points |
| `passing_bonus_500` | >= 500 passing yards | 3 points |

These are **not set by default** in any preset. Add them via `--scoring-config`:

```yaml
inherit: ppr
overrides:
  rushing_bonus_100: 3
  rushing_bonus_200: 3
  receiving_bonus_100: 3
  passing_bonus_300: 3
  passing_bonus_400: 5
```

### Preset Inheritance (`_inherit`)

Scoring presets in `defaults.yaml` support inheritance via the `_inherit` key:

```yaml
scoring:
  ppr:
    passing_yard: 0.04
    reception: 1
    # ... all fields defined

  half_ppr:
    _inherit: ppr          # Gets all PPR values
    reception: 0.5         # Overrides just this one

  standard:
    _inherit: ppr
    reception: 0
```

You can add custom presets to `defaults.yaml` using the same pattern:

```yaml
scoring:
  superflex:
    _inherit: ppr
    passing_td: 6

  te_premium:
    _inherit: half_ppr
    reception_te: 1.5
```

Circular inheritance (A inherits B, B inherits A) raises a `ConfigError`.

---

## Simulation Settings

These live in `config/defaults.yaml` and control the simulation engine:

```yaml
simulation:
  num_sims: 1000                         # Default sims per game (overridden by CLI --sims)
  historical_seasons: [2022, 2023, 2024] # Training data seasons
  recency_weights: [0.2, 0.3, 0.5]      # Weight per season (most recent = highest)
  rookie_blend_games: 4                  # Games before switching from archetype to personal data
```

### Position Minimum Thresholds

Players below these thresholds are excluded from model building:

```yaml
positions:
  qb:
    min_snaps: 200
  rb:
    min_carries: 30
    min_targets: 10
  wr:
    min_targets: 30
  te:
    min_targets: 20
  k: {}         # No threshold
  dst: {}       # No threshold
```

---

## CLI Override Syntax

Override individual fields from the command line without a config file:

```bash
uv run fantasy-sim week 1 --override "mahomes.target_share=0.30"
```

### Format

```
--override "entity.field=value"
```

- **entity**: Player name/ID or team code
- **field**: Any valid override field name
- **value**: Automatically parsed as int, float, list, or string

### Value Parsing

| Input | Parsed As | Example |
|-------|-----------|---------|
| No decimal | int | `games_played=15` -> `15` |
| Has decimal | float | `target_share=0.28` -> `0.28` |
| Brackets | list of ints | `games_missed=[4,5,6]` -> `[4, 5, 6]` |
| Other | string | `some_field=custom` -> `"custom"` |

### Team vs. Player Detection

The entity is treated as a **team** if it is 2-3 uppercase characters. Everything else is a **player**.

| Entity | Detected As | Example |
|--------|-------------|---------|
| `KC` | Team | `--override "KC.pass_rate=0.62"` |
| `BUF` | Team | `--override "BUF.pace_plays_per_game=70"` |
| `mahomes` | Player | `--override "mahomes.games_played=14"` |
| `patrick_mahomes` | Player | `--override "patrick_mahomes.target_share=0.30"` |

### Multiple Overrides

Repeat the `--override` flag:

```bash
uv run fantasy-sim week 1 --season 2024 \
  --override "mahomes.games_missed=[4,5,6]" \
  --override "kelce.target_share=0.22" \
  --override "KC.pass_rate=0.62"
```

### Precedence

CLI `--override` flags always take precedence over `--config` file values. If both set the same field, the CLI wins.

---

## Practical Recipes

### Model an Injury (ACL Tear Weeks 8-17)

```yaml
players:
  nick_chubb:
    games_missed: [8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
```

### Model a Suspension (4 Games)

```yaml
players:
  deshaun_watson:
    games_missed: [1, 2, 3, 4]
```

### Model a Mid-Season Trade

Increase the traded player's target share on the new team. The simulator resolves players by their current roster, so just override the share:

```yaml
players:
  amari_cooper:
    target_share: 0.22
```

### Bellcow RB Workload

```yaml
players:
  derrick_henry:
    carry_share: 0.78
    red_zone_carry_share: 0.85
```

### Dual-Threat QB Increase

```yaml
players:
  jalen_hurts:
    scramble_rate: 0.12
    carry_share: 0.18
```

### Reduce a Boom-or-Bust Receiver's Catch Rate

```yaml
players:
  dk_metcalf:
    catch_rate: 0.58
```

### Pass-Heavy Offense With High Pace

```yaml
teams:
  MIA:
    pass_rate: 0.65
    pace_plays_per_game: 70
```

### Leaky Defense (More Turnovers)

To boost a DST's production, increase the turnover rates of the **opposing** offense:

```yaml
teams:
  NYJ:                    # The opposing team
    int_rate: 0.035
    fumble_rate: 0.018
```

### TE Premium League

```yaml
# config/te_premium.yaml
inherit: ppr
overrides:
  reception_te: 1.5
```

```bash
uv run fantasy-sim week 1 --scoring-config config/te_premium.yaml
```

### Superflex / 6-Point Passing TD League

```yaml
# config/superflex.yaml
inherit: ppr
overrides:
  passing_td: 6
```

### Full Yardage Bonus League

```yaml
# config/bonuses.yaml
inherit: half_ppr
overrides:
  rushing_bonus_100: 3
  rushing_bonus_200: 5
  receiving_bonus_100: 3
  receiving_bonus_200: 5
  passing_bonus_300: 3
  passing_bonus_400: 5
  passing_bonus_500: 7
```

### Combine Config File + CLI Override

Load a season config but override one player from the CLI:

```bash
uv run fantasy-sim week 1 --season 2024 \
  --config config/season.2025.yaml \
  --override "travis_kelce.target_share=0.18"
```

The CLI override for Kelce takes precedence over any value in the config file.

---

## Validation Rules and Common Errors

### Errors That Raise Exceptions

| Error | Cause | Fix |
|-------|-------|-----|
| `ValueError: games_missed must be a list` | `games_missed: 4` (single number) | Use `games_missed: [4]` |
| `ValueError: pass_rate must be between 0.0 and 1.0` | `pass_rate: 1.5` | Use a value between 0.0 and 1.0 |
| `ValueError: pace_plays_per_game must be positive` | `pace_plays_per_game: 0` or negative | Use a positive number (baseline: 65) |
| `ValueError: Unknown override field 'xyz'` | Typo or non-existent field | Check field name against tables above |
| `AmbiguousMatchError` | 2+ players match with similar fuzzy scores | Use a more specific name or the nflverse player_id |
| `KeyError: No player found matching 'xyz'` | Fuzzy match score too low (< 70/100) | Check spelling. Error message shows best score achieved. |
| `ConfigError: Circular _inherit detected` | Preset A inherits B, B inherits A | Fix the inheritance chain in defaults.yaml |
| `ConfigError: Unknown scoring format 'xyz'` | Invalid `scoring_format` or `--scoring` value | Use `ppr`, `half_ppr`, or `standard` |

### Silent Behaviors (No Error Raised)

| Behavior | When It Happens | How to Catch It |
|----------|-----------------|-----------------|
| Player override silently skipped | Player name can't be resolved (typo, not on roster) | Check output — missing player means override didn't apply |
| Team override silently ignored | Team code doesn't match any team in the current matchup | Verify team code matches nflverse abbreviation (e.g., `KC` not `KCC`) |
| `scoring_format` silently overrides CLI `--scoring` | season.yaml has `scoring_format: standard` but you passed `--scoring ppr` | Remove `scoring_format` from season.yaml or don't use `--scoring` |
| `season`/`weeks` only apply when CLI flag not set | You passed `--season 2024` explicitly, so `season: 2025` in config is ignored | Omit `--season` from CLI to use the config file value |
| Config file not auto-detected | File is not named exactly `config/season.yaml` | Use `--config path/to/your/file.yaml` explicitly |
