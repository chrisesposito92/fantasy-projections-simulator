# Matchup Engine — Same-Season Rolling Window

**Date:** 2026-04-03
**Status:** Approved
**Branch:** separate from main (new feature branch)

## Problem

The matchup engine was disabled because cross-season defensive data (2022-2023 predicting 2024) didn't correlate — defensive quality shifts too much year-to-year. Same-season data (weeks 1-7 predicting week 8) is much more predictive. The tier engine answers "who is this player?" but the matchup engine answers "who are they playing this week?" — these are additive signals.

## Data Strategy

`MatchupEngine.compute()` receives `target_season: int` and `max_week: int` instead of `training_seasons`. For a week 8 game, PFF defensive/OL data is loaded from the current season filtered to `week < max_week` (weeks 1-7).

### Early-Season Blend

When a team has fewer than `min_games` (4) same-season games:

- **Blend weight** = `same_season_games / min_games` (linear ramp)
- Previous-season data (`target_season - 1`, full season) fills the gap with weight `1 - blend_weight`
- Factors are computed independently from each dataset, then weighted-averaged
- Once `min_games` reached: same-season only, no blending

| Team games in window | Same-season weight | Prev-season weight |
|---------------------|-------------------|-------------------|
| 0 (week 1)          | 0%                | 100%              |
| 1                   | 25%               | 75%               |
| 2                   | 50%               | 50%               |
| 3                   | 75%               | 25%               |
| 4+                  | 100%              | 0%                |

If previous season data is also missing, factors return neutral (1.0).

## Cache Strategy

Full season data is cached at the loader level with key `"{facet}_{season}"` — one entry per season, reused across weeks. Week filtering (`week < max_week`) is applied in-memory after retrieval via a cheap polars filter, not cached. This means:

- Same-season data: cached as `"{facet}_{target_season}"`, filtered each call (trivial cost)
- Previous-season data: cached as `"{facet}_{prev_season}"`, no filtering needed (full season)

Within a single week simulation, all games reuse the same cached season loads. Across weeks (season command), the same cached full-season data is reused — only the filter changes.

Week filtering happens inside `MatchupEngine` after loading via `PffLoader.load_facet()`, not in the loader itself. This keeps the loader generic and avoids breaking tier engine / talent stabilizer which load full seasons.

## Integration — GameContextBuilder

`build_game()` passes `target_season` and `week` through to `compute()`:

```python
home_ctx = self._matchup_engine.compute(
    defense_team=away_team,
    offense_team=home_team,
    target_season=target_season,
    max_week=week,
)
```

The `training_seasons` and `season_weights` params are removed from `compute()` — no longer needed. The engine derives previous season as `target_season - 1`.

If `target_season` or `max_week` is None (demo mode), `compute()` returns neutral `MatchupContext()`.

Pipeline ordering preserved: base model -> matchup -> tier -> normalize -> user overrides -> normalize.

## MatchupEngine.compute() Internal Flow

1. **Guard**: if not enabled, or `target_season`/`max_week` is None -> return neutral `MatchupContext()`.

2. **Load data per factor spec**:
   - Load `target_season` full data via `_load_cached(facet, [target_season])`
   - Filter to `week < max_week` in-memory (polars filter)
   - Count team's games in filtered set

3. **Decide blend**:
   - `team_game_count >= min_games` -> same-season data only
   - `team_game_count < min_games` -> also load `target_season - 1`, compute factor from each dataset independently, weighted-average with `blend_weight = team_game_count / min_games`

4. **Compute factor**: reuse existing `_compute_single_factor()` unchanged. Called once per dataset (same-season, prev-season), then blended.

5. **League stats basis**: computed from ALL teams in the filtered dataset, not just the two playing. Keeps z-scores meaningful.

New helper: `_compute_blended_factor(facet, team, spec, target_season, max_week)` encapsulates load -> filter -> blend logic.

## Sensitivity Defaults

Ship with current conservative values from `defaults.yaml` — no changes:

```yaml
matchup:
  pass_defense_sensitivity: 0.04
  pass_rush_sensitivity: 0.05
  run_defense_sensitivity: 0.04
  int_rate_sensitivity: 0.03
  ol_pass_sensitivity: 0.04
  ol_run_sensitivity: 0.03
  factor_clamp: [0.90, 1.10]
  min_games: 4
```

Sensitivity sweep is a follow-up after A/B validation confirms the engine adds signal.

## A/B Testing

Two new modes in `validate_pff_signal.py`:

- `--mode matchup` — matchup engine only (tier disabled). Isolates matchup contribution vs baseline.
- `--mode matchup+tier` — both enabled. Tests whether they're additive.
- Existing `--mode tier` unchanged.

Config override support: `--config-override '{"matchup": {"pass_defense_sensitivity": 0.06}}'` for future sweeps.

Expected runs:
```bash
# Matchup-only vs baseline
uv run python scripts/validate_pff_signal.py --mode matchup --sims 50 --label "matchup-v1"

# Combo vs tier-only
uv run python scripts/validate_pff_signal.py --mode matchup+tier --sims 50 --label "matchup+tier-v1"
```

**Success criteria**: matchup-only should improve weekly MAE (its target metric). matchup+tier should be at least as good as tier-only — if worse, the engines interfere and need investigation.

## Test Plan

### Unit tests (`tests/test_data/test_pff/test_matchup.py`)

1. Rolling window filtering — `compute()` with `target_season=2024, max_week=8` only uses weeks 1-7
2. Early-season blending — linear ramp: 1 game = 25%, 2 = 50%, 3 = 75%, 4+ = 100%
3. Week 1 fallback — 0 same-season games = 100% previous season
4. No data at all — neither season has data = neutral factors (1.0)
5. Cache key correctness — same facet+season+week hits cache, different week misses
6. Guard clauses — `target_season=None` or `max_week=None` = neutral context
7. Blended factor math — weighted average of two independently-computed factors

### Integration tests (`tests/test_data/test_game_context.py`)

8. `build_game()` passes `target_season` and `max_week` to matchup engine
9. Matchup + tier ordering — both produce non-neutral results when enabled together

No new statistical tests — the A/B harness covers validation.

## Files Modified

| File | Change |
|------|--------|
| `src/fantasy_sim/data/pff/matchup.py` | New `compute()` signature, `_compute_blended_factor()`, week filtering, cache key update |
| `src/fantasy_sim/data/game_context.py` | Pass `target_season`/`week` to matchup engine |
| `scripts/validate_pff_signal.py` | Add `--mode matchup` and `--mode matchup+tier` |
| `tests/test_data/test_pff/test_matchup.py` | 7 new unit tests |
| `tests/test_data/test_game_context.py` | 2 new integration tests |
| `config/defaults.yaml` | No changes (keep current conservative values) |
