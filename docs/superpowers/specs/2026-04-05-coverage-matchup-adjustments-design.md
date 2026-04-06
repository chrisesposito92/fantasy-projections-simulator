# Coverage Matchup Adjustments Design

**Date:** 2026-04-05
**Status:** Approved
**Roadmap item:** #5 — Coverage Matchup Adjustments
**Baseline:** RB tertiary (#37) default, 978 tests, tier + NCAA rookie + matchup + archetypes active

## Summary

Per-WR coverage matchup adjustments using PFF's `defense_coverage_matchup` facet. Maps each offensive WR to the opposing CB by alignment, then adjusts catch_rate and yards_per_reception based on that CB's rolling performance profile. Outcome-based stats (catch rate allowed, YPR allowed) serve as the primary signal, with PFF coverage grades as a stabilizer for low-sample CBs.

This is a player-level overlay on top of the existing team-level matchup engine. Team-level says "this defense is generally tough on receivers"; coverage says "specifically, your WR1 faces an elite CB while your WR3 faces a weak one."

**Expected impact:** LOW for season-level backtest (matchup effects average out over 17 games), HIGH for weekly projection accuracy. Validated via WR-specific weekly metrics rather than the standard season-level A/B harness.

## Scope

- **Adjustments:** catch_rate + yards_per_reception only. No target_share (coordinators still target their WR1 against tough coverage — volume is scheme-driven, efficiency is matchup-driven).
- **Positions:** WR only. TEs excluded for v1 (noisier LB/S coverage mapping, TEs already got biggest tier engine lift).
- **Mapping:** Alignment-based (WR position -> CB position). Shadow detection is a v2 enhancement.

## Architecture

### New File

`src/fantasy_sim/data/pff/coverage.py` — `CoverageEngine` class, peer to `MatchupEngine` and `TierEngine`.

### Data Flow

```
defense_coverage_matchup parquet
        |
        v
+---------------------+
|  CoverageEngine     |
|                     |
|  1. Load facet data |
|  2. Build CB profiles (rolling window)
|  3. Map WR alignment -> CB alignment
|  4. Compute z-scores (outcome + grade)
|  5. Return per-WR modifiers
+---------+-----------+
          | dict[player_id, CoverageModifiers]
          v
+---------------------+
|  GameContextBuilder |
|  build_game()       |
|                     |
|  ... team matchup   |
|  ... tier engine    |
|  ... normalize      |
|  > apply_coverage() | <-- NEW (last PFF step)
|  ... return         |
+---------------------+
```

### Call Signature

```python
class CoverageEngine:
    def __init__(self, loader: PffLoader, config: CoverageConfig) -> None: ...

    def compute(
        self,
        defense_team: str,
        offense_roster: TeamRoster,
        target_season: int | None = None,
        max_week: int | None = None,
    ) -> dict[str, CoverageModifiers]:
        """Return per-WR modifiers for one offense vs one defense."""
```

Takes `offense_roster` (not just team name) because we need to know which WRs are on the roster and determine their alignments.

Returns dict keyed by `player_id` with `CoverageModifiers(catch_rate_modifier, ypr_modifier)` centered on 1.0.

## Data Model

### New Dataclasses (in `models.py`)

```python
@dataclass
class CoverageModifiers:
    """Per-WR modifiers from coverage matchup analysis."""
    catch_rate_modifier: float = 1.0
    ypr_modifier: float = 1.0

@dataclass
class CoverageConfig:
    """Configuration for the coverage matchup engine."""
    enabled: bool = True
    catch_rate_sensitivity: float = 0.04
    ypr_sensitivity: float = 0.04
    min_coverage_targets: int = 20
    min_z_score_targets: int = 10
    min_z_score_population: int = 8
    factor_clamp: tuple[float, float] = (0.95, 1.05)
    min_games: int = 4
```

### PffConfig Extension

```python
@dataclass
class PffConfig:
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = ...
    talent: TalentConfig = ...
    tier_engine: TierConfig = ...
    team_context: TeamContextConfig = ...
    coverage: CoverageConfig = ...  # NEW
```

## CB Profile Building

### Identifying Starting CBs

The matchup rows only carry the offensive receiver's `team`/`franchise_id`, not the defender's. To identify which team a CB plays for: in a given `game_id`, matchup rows where the receiver belongs to team A mean the `coverage_player_id` belongs to team A's opponent. So to find CBs for a given defense:

1. Find all `game_id`s where the defensive team's opponent has offensive receiver rows
2. The `coverage_player_id` values in those matchup rows are the defensive team's players

Filter to:
- `coverage_player_id IS NOT NULL` (matchup rows, not offensive aggregates)
- Games where the receiver's team is the opponent of the target defense (inferred via `game_id`)
- Defender `pff_position` in (LCB, RCB, SCB) — other positions (FS, SS, LBs) ignored for v1
- Rolling window: same season, `week < max_week`

Group by `(coverage_player_id, pff_position)`. The CB with the most targets at each of the three alignment slots (LCB, RCB, SCB) is the presumed starter.

### Aggregating Stats

For each starter CB, aggregate all their matchup rows in the rolling window:

- **catch_rate_allowed** = `sum(receptions) / sum(targets)`
- **ypr_allowed** = `sum(yards) / sum(receptions)`
- **coverage_grade** = target-weighted mean of `grades_coverage_defense`, falling back to `grades_overall` when the coverage-specific grade is null
- **total_targets** = `sum(targets)` (used for reliability ramp)

### Early-Season Blend

When a CB has played fewer than `min_games` games in the current season, blend with their previous-season profile using a linear ramp:

```
blend_weight = games_played / min_games
current_season_profile * blend_weight + prev_season_profile * (1 - blend_weight)
```

Same pattern as the team-level `MatchupEngine`.

A CB new to their team (free agent / trade) uses only current-team data — no blending with previous-team stats.

## Alignment Mapping

### WR Alignment Determination

Each WR's primary alignment comes from their matchup data in the same rolling window (same season, `week < max_week`) — which `pff_position` they appear in most often (plurality of targets). The `defense_coverage_matchup` facet records the offensive player's `pff_position` per row (LWR, RWR, SLWR, SRWR).

Fallback for WRs with no matchup data (rookies, etc.): assign by target_share rank — WR1/WR2 -> outside (WR1->RCB, WR2->LCB), WR3+ -> SCB.

### Alignment -> CB Mapping

| WR Alignment | Opposing CB |
|---|---|
| RWR (right WR) | LCB (left CB) |
| LWR (left WR) | RCB (right CB) |
| SLWR or SRWR (slot) | SCB (slot CB) |

Standard NFL convention: outside WRs face the CB on the opposite side.

### Multi-Alignment WRs

For v1, use the primary alignment (plurality of targets). A v2 enhancement could weight across alignments proportionally.

## Factor Computation

### Step 1: Z-Score Computation

For each metric (catch_rate_allowed, ypr_allowed, coverage_grade), compute z-scores across ALL CBs league-wide at the same alignment. Population: all CBs at that alignment with >= `min_z_score_targets` (10) in the rolling window.

- `catch_rate_z = (cb.catch_rate_allowed - mean_at_alignment) / std_at_alignment`
- `ypr_z = (cb.ypr_allowed - mean_at_alignment) / std_at_alignment`
- `grade_z = -(cb.coverage_grade - mean_at_alignment) / std_at_alignment` (inverted: higher grade = tougher CB = negative WR adjustment)

### Step 2: Reliability Ramp (Outcome-Grade Blend)

```
reliability = min(cb.total_targets / min_coverage_targets, 1.0)
blended_catch_z = reliability * catch_rate_z + (1 - reliability) * grade_z
blended_ypr_z = reliability * ypr_z + (1 - reliability) * grade_z
```

At 20+ targets: outcomes fully dominate. At 0 targets: grade is the entire signal. At 10 targets: 50/50.

### Step 3: Convert to Modifiers

```
catch_rate_modifier = clamp(1.0 + blended_catch_z * catch_rate_sensitivity, *factor_clamp)
ypr_modifier = clamp(1.0 + blended_ypr_z * ypr_sensitivity, *factor_clamp)
```

Starting sensitivities (0.04) are deliberately conservative — lower than team-level matchup sensitivities (0.06-0.075). Coverage signal is more granular but noisier.

### Step 4: Application

In `GameContextBuilder._apply_coverage()`:

```python
for player in roster.players:
    if player.position != "WR":
        continue
    mods = coverage_modifiers.get(player.player_id)
    if mods is None:
        continue
    if mods.catch_rate_modifier != 1.0:
        player.outcomes.catch_rate = clamp(
            player.outcomes.catch_rate * mods.catch_rate_modifier, 0.0, 1.0
        )
        player.outcomes.red_zone_catch_rate = clamp(
            player.outcomes.red_zone_catch_rate * mods.catch_rate_modifier, 0.0, 1.0
        )
    if mods.ypr_modifier != 1.0:
        shift = (mods.ypr_modifier - 1.0) * 10.0
        player.outcomes.receiving_yards_dist += shift
```

Mirrors the pattern in `_apply_matchup()` — multiplicative for catch_rate, additive shift for yards.

## Pipeline Ordering

In `build_game()`:

1. Build team distributions + rosters
2. **Team-level matchup** — all receivers get same catch_rate_factor (team defense quality)
3. **Tier engine** + team context — player quality calibration via PFF grade tiers
4. **Share normalization** — carry/target shares sum to 1.0
5. **Coverage matchup** — individual WRs get personalized modifiers based on their CB **(NEW)**
6. Return

Coverage is the last PFF layer. It's the most game-specific, most granular adjustment. Placed after tier blending so it doesn't get overwritten. Since it only touches catch_rate and YPR (not shares), it doesn't affect normalization.

## Configuration (defaults.yaml)

```yaml
pff:
  coverage:
    enabled: true
    catch_rate_sensitivity: 0.04
    ypr_sensitivity: 0.04
    min_coverage_targets: 20
    min_z_score_targets: 10
    min_z_score_population: 8
    factor_clamp: [0.95, 1.05]
    min_games: 4
```

### Tuning Knobs

| Knob | What it controls | Sweep range |
|---|---|---|
| `catch_rate_sensitivity` | How much CB z-score moves WR catch rate | 0.02-0.08 |
| `ypr_sensitivity` | How much CB z-score moves WR yards/reception | 0.02-0.08 |
| `min_coverage_targets` | Targets needed before outcomes fully dominate grade | 10-40 |
| `factor_clamp` | Max +/-% adjustment per WR | [0.93,1.07] to [0.97,1.03] |
| `min_games` | Games before current-season only (early-season blend) | 3-6 |
| `min_z_score_targets` | Min targets for CB to be in z-score population | 5-15 |
| `min_z_score_population` | Min CBs at alignment for valid z-scores | 5-10 |

### A/B Harness Integration

`--config-override '{"coverage": {"catch_rate_sensitivity": 0.06}}'` — same pattern as existing PFF configs.

New `--mode` options: `coverage+tier`, `coverage+tier+matchup`.

## Validation Strategy

### Primary Metrics (new, WR-specific weekly)

1. **WR-only weekly rank_corr** — Spearman correlation of projected vs actual WR fantasy points, per-week then averaged. Headline metric for this feature.

2. **WR weekly MAE by matchup difficulty** — Split WR-weeks into terciles by modifier magnitude (easy/neutral/tough). Compare MAE across buckets. Engine works if MAE improves for easy and tough matchups vs neutral.

3. **Directional accuracy** — For each WR-week where modifier deviates from 1.0, check if actual outcome moved in predicted direction. Target: >55% (above coin flip).

### Regression Checks (existing)

4. **Standard A/B harness** — Full rank_corr, weekly MAE, season MAE, calibration. Guardrail: coverage must not hurt overall accuracy. Expect flat results.

5. **Per-position A/B breakdown** — Verify WR rank_corr doesn't degrade.

### Implementation

WR-specific metrics added to `validate_pff_signal.py` as `--wr-coverage-detail` flag. Supplements (doesn't replace) standard metrics.

### Sweep Strategy

Baseline: `--mode tier+matchup` (current default). Test: `--mode coverage+tier+matchup`.

Sweep order: sensitivities first (0.02, 0.04, 0.06, 0.08), then clamp range, then min_coverage_targets.

## Edge Cases

| Scenario | Handling |
|---|---|
| No CB data at an alignment | Neutral modifier (1.0). No adjustment > bad guess. |
| Backup CB mid-season | Rolling window handles naturally. Below `min_coverage_targets`, grade stabilizer carries more weight. |
| WR with no alignment data | Fallback: WR1/WR2 -> outside, WR3+ -> slot (by target_share rank). |
| CB traded mid-season | Filter matchup rows by `franchise_id` matching current defensive team. |
| Early season (weeks 1-3) | Linear ramp blends current + previous season CB profiles. |
| Small z-score population | If < `min_z_score_population` (8) CBs at alignment, return neutral modifiers. |
| Bye weeks | `max_week` filter means no new data added. Existing profile unchanged. |
| Coverage engine disabled | `enabled: false` -> `build_game()` skips `_apply_coverage()`. |
| PFF data not available | `load_facet()` returns empty DataFrame -> empty dict -> no modifiers. Graceful no-op. |
| CB new to team (free agent) | Only current-team data used. No blending with previous-team stats. |

## Future Enhancements (v2)

- **Shadow detection:** Track when a specific CB follows a WR regardless of alignment. Requires pattern detection from historical data.
- **TE coverage:** Extend to TE vs LB/S matchups. Noisier mapping, lower marginal value over tier engine.
- **Target_share suppression:** If directional accuracy shows extreme shadow matchups DO suppress targets (WR1 drawing 2 targets instead of 8), add as a v2 signal.
- **Multi-alignment weighting:** For WRs who split time between slot and outside, weight modifiers proportionally by alignment frequency.
- **Snap-count weighting:** Weight CB profiles by snaps played per game rather than targets, if snap data becomes available.
