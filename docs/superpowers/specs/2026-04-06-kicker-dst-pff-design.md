# Kicker/DST from PFF Grades — Design Spec

**Date:** 2026-04-06
**Roadmap Item:** #6 — Kicker/DST from PFF Grades
**Scope:** Kicker engine (per-kicker accuracy with Bayesian shrinkage) + light DST baseline (fumble rate + defensive TD rates)

## Context

Currently kickers use a placeholder model (`build_kicker_model()`) with empty usage/outcomes — zero player-specific data. The team-level `KickingModel` stores league-average FG rates by distance bucket, so all kickers are projected identically. DST scoring comes entirely from play-by-play simulation aggregates. The matchup engine adjusts sack and INT rates per-opponent, but `fumble_rate`, `INT_RETURN_TD_RATE` (fixed 0.20), and `FUMBLE_RETURN_TD_RATE` (fixed 0.10) are untouched by any PFF layer.

PFF data for both is already scraped and available:
- `field_goal_summary` — per-kicker, per-game distance accuracy (20/30/40/50+ yards), PAT stats, kicker grades
- `defense_summary` — per-player, per-game defensive grades, counting stats (sacks, INTs, forced fumbles, fumble recoveries, defensive TDs), snap counts

## Part 1: Kicker Engine

### New File

`src/fantasy_sim/data/pff/kicker.py` — `KickerEngine` class

### Data Source

`field_goal_summary` parquet via `PffLoader.load_facet("field_goal_summary", seasons)`.

Key columns: `player_id`, `team`, `season`, `week`, `twenty_attempts/made`, `thirty_attempts/made`, `forty_attempts/made`, `fifty_attempts/made`, `pat_attempts/made`, `grades_fgep_kicker`.

### Crosswalk

Build a kicker-specific crosswalk (PFF `player_id` ↔ nflverse `player_id`) using the same two-layer pattern from `loader.py`:
- Layer 1: nflverse roster `pff_id` match
- Layer 2: exact name + team fallback
- Store both forward (PFF→nflverse) and reverse (nflverse→PFF) mappings so `compute()` can look up by nflverse ID

### Mechanism: Bayesian Shrinkage

For each kicker, aggregate attempts/makes across all loaded games by distance bucket. Apply per-bucket shrinkage:

```
blended_rate = (personal_makes + prior_strength * league_rate) / (personal_attempts + prior_strength)
```

- `personal_makes` / `personal_attempts`: kicker's total from PFF data across training seasons
- `league_rate`: league-average rate for that distance bucket (computed from all kickers in loaded data)
- `prior_strength`: configurable pseudo-attempts (default 20) — controls how quickly personal data overwhelms the prior

High-volume kickers (~30+ FGA/season) will be dominated by personal data. Low-volume kickers or kickers with few attempts at a specific distance stay near league average.

### Distance Bucket Mapping

PFF uses finer-grained buckets than the sim's `KickingModel`:

| PFF Bucket | Sim Bucket | Mapping |
|-----------|-----------|---------|
| `twenty` (20-29 yd) + `thirty` (30-39 yd) | `0_39` | Weighted average by attempts |
| `forty` (40-49 yd) | `40_49` | Direct |
| `fifty` (50+ yd) | `50_plus` | Direct |
| `pat` | `xp_rate` | Direct |

The PFF `one` bucket (1-19 yd, extremely rare) is folded into the twenty+thirty pool if any attempts exist.

### API

```python
class KickerEngine:
    def __init__(self, config: KickerConfig, training_seasons: list[int]) -> None:
        """Load field_goal_summary for all training seasons, compute league averages, build crosswalk.

        Training seasons should include the target season — kicker accuracy is stable
        across seasons, so max data produces better shrinkage. The caller passes
        all available seasons (e.g., [2022, 2023, 2024] for a 2024 projection).
        No max_week filtering needed since kicker accuracy doesn't change mid-season
        in a way that matters for projections.
        """

    def compute(self, kicker_player_id: str) -> KickingModel | None:
        """Return per-kicker KickingModel or None if insufficient data.

        Takes a nflverse player_id. Uses a reverse crosswalk (nflverse → PFF)
        built during __init__ to look up the kicker's PFF stats.
        """
```

Returns `None` when:
- Kicker not found in reverse crosswalk (no PFF data)
- Kicker has fewer than `min_attempts` total FG attempts across all loaded seasons

### Fallback

When `compute()` returns `None`, the existing team-level `KickingModel` (from PBP data) is preserved unchanged.

### Config

New section in `defaults.yaml` under `pff:`:

```yaml
kicker:
  enabled: true
  prior_strength: 20
  min_attempts: 5
```

New dataclass in `models.py`:

```python
@dataclass
class KickerConfig:
    enabled: bool = True
    prior_strength: int = 20
    min_attempts: int = 5
```

Added to `PffConfig` alongside existing engine configs.

## Part 2: DST Baseline Engine

### New File

`src/fantasy_sim/data/pff/dst_baseline.py` — `DstBaselineEngine` class

### Data Source

`defense_summary` parquet via `PffLoader.load_facet("defense_summary", seasons)`.

Key columns: `team`, `season`, `week`, `player_id`, `forced_fumbles`, `fumble_recoveries`, `fumble_recovery_touchdowns`, `interceptions`, `interception_touchdowns`, `snap_counts_defense`, `grades_run_defense`.

### What the Matchup Engine Already Covers

The matchup engine adjusts per-opponent via `MatchupContext`:
- `sack_rate_factor` — from PFF pass rush + OL grades
- `int_rate_factor` — from PFF coverage grades
- `catch_rate_factor`, `pass_yards_factor`, `rush_yards_factor` — offensive adjustments

### What the DST Baseline Adds (Non-Overlapping)

| Gap | Current State | DST Baseline Fix |
|-----|--------------|-----------------|
| Fumble rate | Not adjusted by any PFF layer | Team-aggregate forced fumble quality → `fumble_rate_factor` on opposing `TurnoverRates.fumble_rate` |
| Pick-six rate | Fixed constant `INT_RETURN_TD_RATE = 0.20` | Team-specific rate from PFF `interception_touchdowns / interceptions` with shrinkage |
| Fumble return TD rate | Fixed constant `FUMBLE_RETURN_TD_RATE = 0.10` | Team-specific rate from PFF `fumble_recovery_touchdowns / fumble_recoveries` with shrinkage |

### Mechanism

**Fumble rate factor:**
1. For each team-game, sum `forced_fumbles` and `snap_counts_defense` across all players
2. Compute team's forced fumble rate per defensive snap
3. Z-score across all teams in the rolling window
4. Convert to multiplier: `1.0 + z_score * sensitivity`
5. Clamp to configured range

**Defensive TD rates (Bayesian shrinkage, not z-score):**
Since sample sizes are tiny (2-5 pick-sixes per team per season), z-scores would be noisy. Instead, compute team-specific rates with Bayesian shrinkage toward the league constant:

```
team_int_return_td_rate = (team_int_tds + prior_strength * 0.20) / (team_ints + prior_strength)
team_fumble_return_td_rate = (team_fum_tds + prior_strength * 0.10) / (team_fum_recs + prior_strength)
```

Teams with many defensive TDs relative to opportunities will have rates above the constant; teams with few will be near the constant.

**Rolling window:** Same-season data with `week < max_week`. Early-season blend with previous season via linear ramp when team has `< min_games` games (same pattern as matchup engine).

### New Dataclasses

In `pff/models.py`:

```python
@dataclass
class DstBaselineContext:
    fumble_rate_factor: float = 1.0
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10
```

In `engine/types.py`:

```python
@dataclass
class DefensiveTdRates:
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10
```

New field on `TeamDistributions`:
```python
defensive_td_rates: DefensiveTdRates = field(default_factory=DefensiveTdRates)
```

Defaults to current constants, so all existing code works without changes unless PFF is enabled.

### API

```python
class DstBaselineEngine:
    def __init__(self, config: DstBaselineConfig, seasons: list[int]) -> None:
        """Load defense_summary, precompute league aggregates."""

    def compute(self, defense_team: str, target_season: int, max_week: int) -> DstBaselineContext:
        """Return per-team DST baseline adjustments."""
```

### Integration in game_sim.py

Replace constant references:
- `INT_RETURN_TD_RATE` → `def_dists.defensive_td_rates.int_return_td_rate`
- `FUMBLE_RETURN_TD_RATE` → `def_dists.defensive_td_rates.fumble_return_td_rate`

Where `def_dists` is the defending team's `TeamDistributions`. The module-level constants remain as default values.

### Config

```yaml
dst_baseline:
  enabled: true
  sensitivities:
    fumble_rate: 0.06
  prior_strength: 10
  min_games: 4
  clamp: [0.85, 1.15]
```

New dataclass:

```python
@dataclass
class DstBaselineConfig:
    enabled: bool = True
    sensitivities: dict[str, float] = field(default_factory=lambda: {"fumble_rate": 0.06})
    prior_strength: int = 10
    min_games: int = 4
    clamp: list[float] = field(default_factory=lambda: [0.85, 1.15])
```

## Part 3: Integration & Layer Ordering

### Layer Order in build_game()

```
1. Build base distributions + rosters (existing)
2. Matchup engine (existing) — per-opponent sack/INT/yards adjustments
3. Tier engine (existing) — player quality blending
4. Coverage engine (existing) — per-WR CB matchup adjustments
5. DST baseline engine (NEW) — fumble_rate_factor + defensive TD rates
6. Kicker engine (NEW) — replace team-level KickingModel
7. User overrides + normalize (existing, stays last)
```

Kicker and DST baseline are independent of each other. Both come after existing PFF layers and before user overrides.

### CLI

No new flags. Existing `--pff/--no-pff` controls all PFF layers. Individual engine enable/disable via `defaults.yaml`.

### A/B Harness

Extend `validate_pff_signal.py` with new modes:
- `--mode kicker` — kicker engine only
- `--mode dst_baseline` — DST baseline only
- `--mode kicker+dst_baseline` — both together
- Compose with existing: `--mode kicker+dst_baseline+tier+matchup+coverage`

The `--config-override` mechanism supports `kicker` and `dst_baseline` keys for parameter sweeps.

### PffConfig Updates

```python
@dataclass
class PffConfig:
    enabled: bool = True
    data_dir: str | None = None
    tier_engine: TierConfig = field(default_factory=TierConfig)
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    team_context: TeamContextConfig = field(default_factory=TeamContextConfig)
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
    kicker: KickerConfig = field(default_factory=KickerConfig)          # NEW
    dst_baseline: DstBaselineConfig = field(default_factory=DstBaselineConfig)  # NEW
```

## Part 4: Testing & Validation

### Unit Tests

**`tests/test_data/test_pff/test_kicker.py` (~15-20 tests):**
- Bayesian shrinkage math: high-volume kicker rate near personal, low-volume near league average
- Distance bucket mapping: PFF twenty+thirty → 0_39 weighted by attempts
- XP rate shrinkage from PAT data
- `min_attempts` threshold: below threshold returns `None`
- Crosswalk: PFF player_id maps to nflverse kicker
- Missing kicker in PFF data: returns `None`, team-level model preserved
- Zero attempts in a distance bucket: inherits league average entirely
- Integration: `build_game()` with PFF enabled produces kicker-specific KickingModel

**`tests/test_data/test_pff/test_dst_baseline.py` (~15-20 tests):**
- Fumble rate factor: elite run defense → factor > 1.0, bad defense → factor < 1.0
- Defensive TD rates: team with high pick-six count → `int_return_td_rate` > 0.20
- Bayesian shrinkage on TD rates: 1 INT / 1 pick-six doesn't produce 100% rate
- Clamp enforcement: extreme z-scores clamped to [0.85, 1.15]
- Early-season blend: < 4 games → blends with previous season
- No previous season data: falls back to neutral (1.0 factors, default TD rates)
- Integration: `build_game()` applies fumble_rate_factor to opposing TurnoverRates
- Integration: `game_sim.py` uses team-specific defensive TD rates from DefensiveTdRates

### Validation

- Run existing backtest before/after to measure impact on rank_corr, weekly_mae, season_mae
- A/B harness with `--mode kicker+dst_baseline+tier+matchup+coverage` for additive value measurement
- Kicker differentiation check: elite kicker (e.g., Tucker) should project higher FG points than replacement-level

### Success Criteria

- No regression in backtest targets (rank_corr > 0.80, weekly_mae < 6.0)
- A/B harness shows non-negative delta on rank_corr and season_mae
- Kicker projections differentiate: measurable spread between best and worst kickers
