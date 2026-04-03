# PFF Talent-Tier Distribution Engine — Design Spec

## Problem

The current pipeline builds player models from PBP history, producing obviously wrong rankings because PBP volume reflects role and opportunity, not talent:

- Tony Pollard -> RB5 (volume from lack of alternatives, not talent)
- Jerry Jeudy -> WR2 (high targets from a bad QB throwing short)
- Raheem Mostert -> above Jahmyr Gibbs (one scheme-dependent season vs elite talent in timeshare)
- Rachaad White -> RB7 (volume-inflated by game script)
- Jakobi Meyers -> WR3 (target hog on a bad offense)

The talent stabilizer (Bayesian mean-nudging) can't fix this. Shifting a catch rate by +0.008 doesn't change a player's projected tier. The distributions themselves are still built from misleading PBP data.

## Solution: Talent-Tier Distribution Selection

Use PFF talent grades to SELECT which tier of distributions a player draws from, rather than just nudging means.

**Current flow (PBP-first):**
```
Player's PBP history -> personal distributions -> nudge means with PFF -> simulate
```

**New flow (PFF-informed selection):**
```
Player's PFF grades -> identify talent tier -> select tier distributions from PBP pool
                                            -> blend with personal PBP via reliability score
                                            -> simulate
```

PFF grades drive distribution SELECTION. PBP provides the distribution SHAPE for each tier.

## Architecture Decisions

### Approach: Drop-in Replacement at GameContextBuilder

The `TierEngine` replaces `TalentStabilizer` at the same integration point in `GameContextBuilder.build_game()`. Player models are still built PBP-first by `player_builder`, then the tier engine overwrites fields based on tier distributions and reliability blending.

The talent stabilizer stays in the codebase as a config-toggled alternative for A/B comparison.

**Why this approach:**
- Same integration point, same caching patterns — minimal pipeline disruption
- A/B testing is trivial: swap one config flag
- `player_builder` stays PFF-agnostic
- Rollback is instant

### Discrete Tiers, Designed for Continuous

The `select_distributions()` interface is tier-implementation-agnostic. v1 uses discrete tiers; continuous kNN is a future drop-in replacement with no caller changes.

### Scope: Talent Only

v1 is purely about talent-tier distribution selection. Team context adjustments (team pass rate, OL grade, QB quality) are deferred to v2, validated with the same A/B harness.

## Tier Structure

### 5 Tiers Per Position

Primary grade drives tier assignment. Secondary grade shifts scalars within the tier.

| Tier | Primary Grade Percentile | Label         | ~Players/tier/season |
|------|--------------------------|---------------|----------------------|
| 1    | 85th+                    | Elite         | ~15                  |
| 2    | 65th-85th                | Above Average | ~20                  |
| 3    | 40th-65th                | Average       | ~25                  |
| 4    | 20th-40th                | Below Average | ~20                  |
| 5    | Below 20th               | Replacement   | ~15                  |

~75-95 players per tier across 6 seasons (2020-2025).

### Position Grade Assignments

| Position | Primary        | Secondary        | Rationale                                          |
|----------|----------------|------------------|----------------------------------------------------|
| RB       | grades_run     | elusive_rating   | Talent + elusiveness separates bellcows from plodders |
| WR       | grades_pass_route | yprr          | Route quality + per-route production captures alpha WRs |
| TE       | grades_pass_route | recv_grade*   | Separates pass-catching TEs from blockers          |

\* `recv_grade` needs column name verification against PFF parquet schema. May be `grades_offense` or another column. Config-level fix if different.
| QB       | grades_pass    | accuracy_percent | Overall passing + accuracy captures tier well      |

The grade dict is open-ended: adding dimensions later is a config change, not a code change.

### Secondary Grade: Within-Tier Scalar Interpolation

Once a player is placed in a tier by their primary grade, the secondary grade shifts their expected scalar values within that tier's range. High secondary -> pull toward top of tier's distribution. Low secondary -> pull toward bottom.

Interpolation is piecewise linear through (p25, p50, p75) of the tier's scalar distribution. Clamped to [p25, p75] — no extrapolation.

### Yards Distributions: No Secondary Grade Effect

Within a tier, yards distributions (receiving_yards_dist, rushing_yards_dist) are shared across all players. The full pool preserves realistic shape, variance, and tails. Secondary grade does NOT affect yards distributions — it only shifts scalars.

Rationale: within a talent tier, differences between players show up in how often they touch the ball (target_share, catch_rate) and where they line up (air_yards_share), not in the shape of their yards-per-catch curve on a given play.

Note: this is about within-tier secondary grade interpolation only. The PBP reliability blending step (see below) DOES blend personal yards with tier yards via concatenation — that's a separate mechanism.

## Module Structure

### New Files

- `src/fantasy_sim/data/pff/tier_engine.py` — `TierEngine` class (main entry point)
- `scripts/validate_tier_spotcheck.py` — 10-player before/after spot-check script

### Modified Files

- `src/fantasy_sim/data/pff/models.py` — new dataclasses
- `src/fantasy_sim/data/pff/config.py` — parse tier config from YAML
- `src/fantasy_sim/data/game_context.py` — wire TierEngine at the talent stabilizer hook point
- `config/defaults.yaml` — `tier_engine:` config section

## Core Types

### TierDistributions (public — returned by select_distributions)

```python
@dataclass
class TierDistributions:
    """Interpolated distributions for a specific player from their tier."""
    target_share: float
    carry_share: float
    catch_rate: float
    air_yards_share: float
    fumble_rate: float
    scramble_rate: float
    receiving_yards_dist: np.ndarray | None
    rushing_yards_dist: np.ndarray | None
```

### TierAssignment

```python
@dataclass
class TierAssignment:
    tier: int                    # 1-5
    primary_percentile: float    # where player sits on primary grade
    secondary_percentile: float  # within-tier percentile on secondary grade
    reliability: float           # PBP weight (0.15 to 0.85)
```

### Config Types

```python
@dataclass
class PositionGradeConfig:
    primary: str       # e.g., "grades_pass_route" for WR
    secondary: str     # e.g., "yprr" for WR

@dataclass
class TierConfig:
    enabled: bool
    cutoffs: list[float]              # [0.85, 0.65, 0.40, 0.20]
    position_grades: dict[str, PositionGradeConfig]
    reliability_max_games: int        # 32
    reliability_team_change_penalty: float  # 0.5
    reliability_variance_weight: float     # 0.3
    reliability_floor: float          # 0.15
    reliability_cap: float            # 0.85
    blend_pool_size: int              # 500
```

### Internal Pool Storage

```python
@dataclass
class _TierPoolEntry:
    """Internal: stored in tier pools, not exposed to callers."""
    # Scalars: (p25, median, p75) for secondary interpolation
    target_share: tuple[float, float, float]
    carry_share: tuple[float, float, float]
    catch_rate: tuple[float, float, float]
    air_yards_share: tuple[float, float, float]
    fumble_rate: tuple[float, float, float]
    scramble_rate: tuple[float, float, float]
    # Yards: full tier pool arrays
    receiving_yards_dist: np.ndarray | None
    rushing_yards_dist: np.ndarray | None
    # Secondary grade values for percentile computation
    secondary_grades: np.ndarray
    # Metadata
    n_player_seasons: int
```

## Tier Pool Building

### Process

For each set of training seasons (cached by `tuple(training_seasons)`):

1. **Load PFF grades** — per-player, per-season average across games. Loaded from existing PFF parquet files via `PffLoader`.

2. **Aggregate PBP per-season** — separate from `player_builder._aggregate_pbp_stats()` which aggregates across seasons. The tier pool builder has its own `_aggregate_pbp_per_season()` that groups by `(player_id, season)`.

3. **Cross-reference** — PFF player_id (int) -> nflverse player_id (str) via existing crosswalk.

4. **Assign tiers** — For each position, compute primary grade percentiles across ALL player-seasons combined (not per-season). Assign each player-season to tier 1-5 based on cutoffs.

5. **Build pools** — For each (position, tier):
   - Scalars: compute (p25, median, p75) of target_share, catch_rate, etc. from PBP stats of players in this tier
   - Yards: concatenate all play-level yards from all player-seasons in the tier
   - Record secondary grade values for within-tier percentile computation

### Pool Sizes (6 NFL seasons, estimated)

| Position | Player-seasons | Per tier (~) | Yards values per tier (~) |
|----------|---------------|-------------|--------------------------|
| QB       | ~200          | ~40         | ~15,000 pass attempts    |
| RB       | ~400          | ~80         | ~12,000 carries          |
| WR       | ~600          | ~120        | ~8,000 catches           |
| TE       | ~300          | ~60         | ~4,000 catches           |

### Thin Tier Handling

If a position-tier has fewer than 20 player-seasons, merge with the adjacent tier toward the middle (Tier 1 merges with 2, Tier 5 merges with 4). Log a warning.

### No Recency Weighting

Tier pools use all seasons equally. Recency matters for a specific player's projection (handled by reliability blending), not for the tier template.

## Assignment & Selection Interface

### Public API

```python
class TierEngine:
    def __init__(self, config: TierConfig, pff_loader: PffLoader): ...

    def select_distributions(
        self,
        pff_grades: dict[str, float],
        position: str,
    ) -> tuple[TierAssignment, TierDistributions]:
        """Assign talent tier and return interpolated distributions.

        Interface is tier-implementation-agnostic. The grade dict is
        open-ended: only configured grades are read, extras ignored.
        """

    def apply_tiers(
        self,
        roster: TeamRoster,
        crosswalk: dict[int, str],
        training_seasons: list[int],
        nfl_roster: pl.DataFrame | None = None,
        target_season: int | None = None,
    ) -> None:
        """Apply tier-based adjustments to all players in a roster.
        Mutates in place. Mirrors TalentStabilizer.stabilize_roster().
        """
```

### Tier Assignment

```python
def _assign_tier(self, primary_grade: float, position: str) -> int:
    """Primary grade -> tier 1-5 via precomputed percentile boundaries."""
    # boundaries = [85th_value, 65th_value, 40th_value, 20th_value]
    for tier, boundary in enumerate(self._boundaries[position], start=1):
        if primary_grade >= boundary:
            return tier
    return 5
```

### Within-Tier Interpolation

Secondary grade percentile maps to scalar values via piecewise linear interpolation through (p25, p50, p75). Clamped to [p25, p75] — no extrapolation.

```
secondary_pct = 0.0 -> p25 (low end of tier)
secondary_pct = 0.5 -> p50 (tier median)
secondary_pct = 1.0 -> p75 (high end of tier)
```

### Missing PFF Data

Players not in the PFF crosswalk get no tier adjustment. Their PBP model is used as-is (effectively reliability = 1.0).

## PBP Reliability & Blending

### Reliability Score

Three factors determine how much to trust personal PBP data:

```python
def compute_reliability(self, games_played, changed_teams, weekly_shares) -> float:
    # Factor 1: Sample size — min(games_played / max_games, 1.0)
    # Factor 2: Team change — penalty multiplier if changed teams
    # Factor 3: Share variance — coefficient of variation of weekly shares
    #
    # raw = sample * team * (1.0 - cv * variance_weight)
    # return clamp(raw, floor=0.15, cap=0.85)
```

PBP weight is capped at 0.85 (15% tier floor). Tier weight is at least 0.15 for every player with PFF data.

### Example Reliability Scores

| Player                              | Games | Team Change | Share CV | Reliability |
|-------------------------------------|-------|-------------|----------|-------------|
| Davante Adams (3yr, stable)         | 48    | No          | 0.15     | 0.85 (cap)  |
| Tony Pollard (1yr, new team)        | 17    | Yes         | 0.20     | 0.24        |
| Jalen Hurts (2yr, stable)           | 30    | No          | 0.10     | 0.85 (cap)  |
| Rookie (0 games)                    | 0     | N/A         | N/A      | 0.15 (floor)|
| Volatile backup (4 games, wild)     | 4     | No          | 0.80     | 0.15 (floor)|

### Blending: Scalars

Weighted average using reliability.

```python
player.usage.target_share = reliability * pbp_value + tier_weight * tier_value
player.outcomes.catch_rate = reliability * pbp_value + tier_weight * tier_value
# Same for: carry_share, air_yards_share, fumble_rate, scramble_rate
```

### Blending: Yards Distributions

Concatenation with proportional resampling (same approach as existing `blend_with_archetype()` for rookies).

```python
BLEND_POOL_SIZE = 500
n_pbp = int(reliability * BLEND_POOL_SIZE)
n_tier = BLEND_POOL_SIZE - n_pbp

pbp_sample = rng.choice(personal_yards, size=n_pbp, replace=True)
tier_sample = rng.choice(tier_yards, size=n_tier, replace=True)
blended = np.concatenate([pbp_sample, tier_sample])
```

Players with no personal PBP (rookies) get 100% tier pool.

### Fields NOT Blended

These remain PBP-sourced:
- `red_zone_carry_share`, `red_zone_target_share` — tier pools lack sufficient RZ data per tier
- `red_zone_catch_rate` — same reason
- `scramble_yards_dist` — QB-specific, small samples per tier
- `pass_fumble_rate` — QB-specific
- `games_played`, `weeks_missed` — meta fields

## Pipeline Integration

### GameContextBuilder Flow

```
1. Build TeamDistributions                          <- unchanged
2. Build TeamRoster (PlayerModels from PBP)         <- unchanged
3. [PFF MATCHUP] if matchup.enabled                 <- unchanged (parked)
4. [PFF TIER ENGINE] if tier_engine.enabled:
       tier_engine.apply_tiers(roster, ...)
       _normalize_roster_shares(roster)
   [PFF TALENT] elif talent.enabled:                <- kept as fallback
       talent_stabilizer.stabilize_roster(...)
       _normalize_roster_shares(roster)
5. Return                                           <- unchanged
```

Only one of tier_engine or talent is active. If both enabled, tier engine wins.

### Configuration

```yaml
pff:
  enabled: true
  data_dir: null

  tier_engine:
    enabled: true
    cutoffs: [0.85, 0.65, 0.40, 0.20]
    position_grades:
      QB:
        primary: grades_pass
        secondary: accuracy_percent
      RB:
        primary: grades_run
        secondary: elusive_rating
      WR:
        primary: grades_pass_route
        secondary: yprr
      TE:
        primary: grades_pass_route
        secondary: recv_grade
    reliability:
      max_games: 32
      team_change_penalty: 0.5
      variance_weight: 0.3
      floor: 0.15
      cap: 0.85
    blend_pool_size: 500

  matchup:
    enabled: false
    # ... unchanged

  talent:
    enabled: false
    # ... preserved for A/B comparison
```

### CLI

No new flags. `--pff/--no-pff` controls the overall PFF layer. Tier vs talent is config-level. A/B testing via `--mode tier` on the validation script.

## Validation

### Success Criteria

| Criterion               | Metric                          | Threshold   | Gate? |
|--------------------------|---------------------------------|-------------|-------|
| Rank ordering improves   | rank_corr delta vs PFF-on       | > 0.0       | Yes   |
| Problem players fixed    | Spot-check directional accuracy | >= 8/10     | Yes   |
| No accuracy regression   | weekly_mae                      | < 6.0       | Yes   |
| No accuracy regression   | season_mae                      | < 25        | Yes   |
| Distribution calibration | boom/bust calibration           | Track only  | No    |

### 10-Player Spot-Check

Script prints before/after projections for:
- 5 volume-inflated (expected to drop): Pollard, Jeudy, White, Meyers, Mostert
- 5 talent-deflated (expected to rise): Gibbs + 4 identified from PFF-vs-PBP rank mismatches

Pass threshold: 8/10 move in the correct direction.

### A/B Harness

Extends `validate_pff_signal.py` with `--mode tier`. Same metrics, same ledger format. Results directly comparable to existing talent stabilizer runs.

## Future Path

1. **Team context layer (v2)** — Adjust tier distributions for team pass rate, OL grade, QB quality. Ship and A/B test separately.
2. **Continuous kNN (v3)** — Replace discrete tier assignment with k-nearest-neighbors in PFF grade space. `select_distributions()` interface unchanged, internal implementation swaps.
3. **Positional archetypes within tiers** — Sub-pool yards distributions by player archetype (deep vs slot vs possession WR). A form of multi-dimensional tiering.
4. **Weekly tier monitoring** — Track in-season PFF grade changes to detect mid-season role/talent shifts.

## Relationship to Existing Code

- **Replaces**: `TalentStabilizer` as the primary PFF adjustment (talent.py kept for A/B)
- **Unchanged**: `player_builder.py` (PBP model building), `game_sim.py` / `play_resolver.py` / `monte_carlo.py` (sim engine), `matchup.py` (parked, orthogonal)
- **Modified**: `game_context.py` (integration point), `models.py` / `config.py` (new types), `defaults.yaml` (new config section)
