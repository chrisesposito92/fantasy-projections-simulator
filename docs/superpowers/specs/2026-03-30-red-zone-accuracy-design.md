# Red Zone Accuracy & QB Stat Calibration

**Date**: 2026-03-30
**Status**: Approved
**Scope**: Fix 4 QB stat accuracy issues in season-long projections

## Problem Statement

Season-long projections (18 weeks, 100 sims/game) show systematic QB stat distortions:

| Stat | Observed | Expected (Real NFL) | Severity |
|------|----------|-------------------|----------|
| Passing TDs | 9 QBs above 40; Goff at 54.7 (near NFL record) | QB1 ~35-40, median starter ~22-28 | Critical |
| Passing Yards | Only 5 QBs break 3000 over 18 weeks | QB1 ~4000+, most starters >3000 | Critical |
| QB Fumbles Lost | Only 2 QBs >= 1.0 FL | Most starters ~3-6 FL | Major |
| QB Rush Yards | Allen 1056, Hurts 968 | Allen ~550, Hurts ~630 | Moderate |
| INTs | Slightly understated | — | Monitor (no active fix) |

## Root Causes

### 1. Red Zone TD Inflation (Passing TDs + Passing Yards)

`play_resolver.py:150-161` — When a pass is completed, yards are sampled from `receiver.outcomes.receiving_yards_dist`, which is built from ALL catches across ALL field positions. The TD check is deterministic: `yard_line - yards <= 0` triggers a TD.

Near the goal line, this is wildly unrealistic. At the opponent's 5-yard line, ~60-70% of a receiver's historical catches exceed 5 yards, making nearly every red zone completion a TD. In real NFL, TD rates per completion drop sharply with distance:

| Yardline | Real Pass TD/Completion | Real Run TD/Attempt |
|----------|------------------------|---------------------|
| 1-3      | 0.914                  | 0.462               |
| 4-5      | 0.819                  | 0.263               |
| 6-10     | 0.556                  | 0.141               |
| 11-15    | 0.286                  | 0.047               |
| 16-20    | 0.151                  | 0.031               |

The inflation is worst at 11-20 yards where the sim over-produces TDs by 2-4x. The knock-on effect on passing yards: inflated TDs → constant field position resets → fewer sustained drives → less yardage accumulated per game.

Additionally, real NFL red zone completion rate is 0.516 vs 0.607 overall (0.85x ratio). The sim uses overall catch rate everywhere.

### 2. Scramble Rate Includes Designed Runs (QB Rush Yards)

`player_builder.py:348-352` — `scramble_rate` is computed as `qb_rush / (qb_pass + qb_rush)`, which lumps designed QB runs with actual scrambles. The `qb_scramble` column in nflverse PBP data distinguishes them. Impact:

| QB | Current Rate (all rushes) | Correct Rate (scrambles only) | Inflation |
|----|--------------------------|------------------------------|-----------|
| J. Allen | 0.171 | 0.077 | 2.2x |
| L. Jackson | 0.213 | 0.089 | 2.4x |
| J. Hurts | 0.246 | 0.089 | 2.8x |
| J. Fields | 0.246 | 0.096 | 2.6x |
| C. Williams | 0.105 | 0.073 | 1.4x |
| P. Mahomes | 0.070 | 0.065 | 1.1x |

Mobile QBs are inflated 2-3x. Pocket passers are barely affected.

### 3. No QB Non-Sack Fumble Path (QB Fumbles)

QB fumbles only trigger on sacks (`sack_fumble_rate` ~10% of sacks) and scrambles (`fumble_rate`). There is no fumble path for normal pass dropbacks — botched snaps, strip attempts while throwing, etc.

Real NFL 2024 data: 63 fumbles on 18,614 non-sack pass plays = 0.0034 per play.

## Design

### Approach: Data-First Hybrid (C+)

Maximize data-driven decisions. Use per-player data where sample sizes support it. Fall back to calibrated aggregate rates (from real 2024 NFL data) where per-player samples are too sparse. Only the TD probability gate uses aggregate constants, because per-player red zone TD rates are too noisy to be meaningful.

### Change 1: Scramble Rate Fix

**Files**: `data/player_builder.py`

In `_aggregate_pbp_stats()`:
- Use the `qb_scramble` column from PBP data to separate scrambles from designed runs
- Track `scramble_count` per QB: rows where `play_type == 'run'` AND `qb_scramble == 1` AND rusher matches passer
- Track `scramble_yards`: yards list from scramble plays only (for `scramble_yards_dist`)
- Designed runs (`qb_scramble != 1`) are excluded from both scramble_rate and scramble_yards_dist

In `_assemble_models()`:
- `scramble_rate = scramble_count / (qb_pass_attempts + scramble_count)`
- `scramble_yards_dist` built from scramble-only plays (not designed runs)
- Minimum sample for scramble_yards_dist remains `MIN_PLAYER_PLAYS = 5`

**Fallback**: If `qb_scramble` column is not present in the PBP data (older datasets), fall back to existing behavior (all QB rushes).

### Change 2: Red Zone Catch Rate

**Files**: `data/player_builder.py`, `models/player.py`, `engine/play_resolver.py`

New field on `PlayerOutcomes`:
```python
red_zone_catch_rate: float = 0.0
```

In `_aggregate_pbp_stats()`:
- Track `rz_catches` per receiver: `complete_pass == 1` where `yardline_100 <= 20`
- Already tracks `rz_targets`

In `_assemble_models()`:
- If `rz_targets >= 10` (MIN_BUCKET_PLAYS threshold): `red_zone_catch_rate = rz_catches / rz_targets`
- If below threshold: `red_zone_catch_rate = catch_rate * 0.85` (league-average fallback, derived from 2024 data: 0.516 / 0.607 = 0.850)

In `_resolve_pass()`:
- When `state.yard_line <= 20`: use `receiver.outcomes.red_zone_catch_rate` for the completion check
- Fallback: if `red_zone_catch_rate == 0.0`, use `catch_rate * 0.85`

### Change 3: Red Zone TD Probability Gate

**Files**: `engine/play_resolver.py`

New module-level constants — gate probabilities representing "given a catch/run with enough yards to score, probability it actually is a TD." Calibrated so that the combined effect of catch rate modifier + TD gate produces rates matching real 2024 NFL data.

```python
# Probability a would-be passing TD actually scores, by yardline bucket
PASS_TD_GATE = {
    (1, 3): 0.90,
    (4, 5): 0.90,
    (6, 10): 0.80,
    (11, 15): 0.50,
    (16, 20): 0.30,
}

# Probability a would-be rushing TD actually scores, by yardline bucket
RUN_TD_GATE = {
    (1, 3): 0.65,
    (4, 5): 0.55,
    (6, 10): 0.40,
    (11, 15): 0.25,
    (16, 20): 0.15,
}
```

New function `_red_zone_td_gate(yard_line: int, play_type: str, rng) -> bool`:
- Look up gate probability from the appropriate table
- Return `rng.random() < gate_probability`
- Outside the red zone (yard_line > 20): return `True` (existing behavior)

In `_resolve_pass()` (player-aware path):
```
if is_complete and state.yard_line <= 20 and (state.yard_line - yards) <= 0:
    if _red_zone_td_gate(state.yard_line, "pass", rng):
        yards = _clamp_yards(state.yard_line, yards)
        is_td = True
    else:
        # Tackled short of goal line
        yards = max(1, state.yard_line - rng.integers(1, max(2, state.yard_line // 3)))
        is_td = False
else:
    is_td = is_complete and (state.yard_line - yards) <= 0
```

Same pattern in `_resolve_run()` using `RUN_TD_GATE`.

When the gate fails: receiver/rusher is tackled short. Shortfall is randomized with a cap of roughly one-third of the starting yard line (e.g., from the 15, they typically end up around the 11-14). This creates realistic goal-to-go situations that may convert on subsequent plays or end in FG attempts.

### Change 4: QB Non-Sack Fumble Check

**Files**: `data/player_builder.py`, `models/player.py`, `engine/play_resolver.py`

New field on `PlayerOutcomes`:
```python
pass_fumble_rate: float = 0.0
```

In `_aggregate_pbp_stats()`:
- Track per-QB: count of `fumble_lost == 1` on pass plays where `sack != 1`
- Track per-QB: total non-sack pass plays

In `_assemble_models()`:
- `pass_fumble_rate = non_sack_fumbles / non_sack_pass_plays` per QB
- If fewer than 100 pass plays: use league average `0.0034`

In `_resolve_pass()` — the fumble check goes BEFORE the completion check, in the existing sequence:
```
1. Scramble check (existing)
2. Sack check (existing)
3. INT check (existing)
4. QB strip/botched snap fumble check (NEW)
5. Completion/incompletion (existing)
```

If the QB fumble fires, the play returns immediately as a fumble with 0 yards (ball never left QB's hand). A pass attempt is still recorded (same as sacks — a pass play was called but disrupted). The fumble must be attributed to the QB in `_update_player_stats` — currently only receiver and rusher fumbles are tracked at the player level, so a new branch is needed: `if result.is_fumble and not result.is_sack and not result.is_complete: qb.fumbles_lost += 1`.

### Change 5: Red Zone Yards Blending

**Files**: `engine/play_resolver.py`

When inside the red zone (`yard_line <= 20`), on non-TD completions:
- `player_yards`: sampled from `receiver.outcomes.receiving_yards_dist` (existing)
- `team_yards`: already sampled from `play_outcomes.sample_yards("pass", bucket, rng)` (line 144, already field-position-aware via GameStateBucket)
- Blended: `yards = min(player_yards, max(team_yards, 1))`

The `min()` ensures the player can't exceed what the team-level distribution suggests for that field position. Player quality is preserved on short catches. Long-tail outliers from the global distribution get capped to realistic red zone yardage (~5-8 yards from team-level data).

Same logic for runs in `_resolve_run()`: blend `rusher_yards` with `team_yards` on non-TD red zone runs.

### Change 6: Rookie/Archetype Defaults

**Files**: `data/rookie_builder.py`

Add reasonable defaults for new fields in positional archetypes:
- `red_zone_catch_rate`: `catch_rate * 0.85` for each archetype tier
- `pass_fumble_rate`: `0.0034` (league average) for QB archetypes

### What's NOT Changing

- Run game mechanics outside the red zone
- Receiver/RB selection logic
- Play calling distributions
- Clock management
- Penalty system
- Scoring engine
- INT rates (wait and see after other fixes)
- Legacy path (no roster) behavior

## Testing Strategy

**Unit tests** for each new function:
- `_red_zone_td_gate()` probability behavior
- Scramble rate computation with `qb_scramble` column
- Red zone catch rate computation and fallback
- QB pass fumble rate computation and fallback
- Red zone yards blending logic

**Integration test**: Run a short sim (50-100 sims) and verify:
- Pass TD rates per red zone completion approximate real NFL rates
- Scramble rates for known QBs are in the correct range
- QB fumble counts are non-trivial
- Red zone yards per catch are lower than overall yards per catch

**Regression**: All existing tests pass. No behavioral change outside the red zone (except scramble rate fix, which is global).

## Calibration Data Source

All constants derived from 2024 NFL PBP data via nflverse/nflreadpy:
- 20,006 pass plays, 2,815 red zone pass plays
- 18,614 non-sack pass plays, 63 non-sack fumbles
- Red zone completion rate: 0.516 (overall: 0.607, ratio: 0.850)
- Red zone Y/C: 6.8 (overall: 11.0, ratio: 0.620)
- Per-yardline-bucket TD rates from 1,452 red zone completions and 2,712 red zone runs
