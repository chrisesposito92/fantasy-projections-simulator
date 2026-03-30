# Roster/Team Assignment Bug Fix — Design Spec

## Problem

When projecting a current/future season (e.g., 2024), the simulator gets player team assignments from historical PBP training data (2021-2023) instead of the current-season roster. This causes:

- **Traded/signed players on wrong teams** — Joe Mixon shows as CIN instead of HOU
- **Kickers missing entirely** — not in run/pass PBP data
- **Rookies missing entirely** — no historical PBP data exists for them
- **Retired players included** — still appear from historical data

## Root Cause

`player_builder.build_player_models()` uses the same `rosters` DataFrame for both team assignment (which team is this player on?) and statistical context (what are this player's historical stats?). Since it receives training-season rosters, every player is assigned to wherever they played in 2021-2023.

## Approach: Dual-Roster Parameter

Separate team assignment from statistical profile by adding a `current_rosters` parameter. Pipeline/distributions stay unchanged. Stats come from historical PBP, team assignment comes from the target season roster.

## Design Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Backtest roster handling | Per-week roster from test season | Mid-season trades, IR moves, call-ups reflected accurately per game week |
| No-history skill players | `rookie_builder` archetypes (tier 3 / round 7 default for undrafted) | Existing infrastructure, draft-capital-based differentiation |
| No-history kickers | Dedicated `build_kicker_model()` placeholder | Kickers are name tags for attribution; actual kicking uses team-level `KickingModel` |
| Historical players not on current roster | Drop silently | No value in building models for players who won't appear in any game |
| Usage share computation | Historical team totals | Shares represent workload volume ("how much of a bellcow"), re-normalized at roster selection time via `select_rusher()`/`select_receiver()` weight division |
| Roster filtering | `status == "ACT"`, `position in ("QB", "RB", "WR", "TE", "K")` | Exclude coaches, practice squad, IR, punters, long snappers. ACT-only is the safest default — IR players shouldn't consume target/carry shares. Status filter may need tuning based on nflverse status codes (e.g., "RSN" for IR-designated-to-return) |

## Changes by File

### `player_builder.py`

**Signature change:**
```python
# Before
def build_player_models(pbp, rosters, seasons, rookie_blend_games=0)

# After
def build_player_models(pbp, current_rosters, training_seasons, rookie_blend_games=0)
```

**Internal refactor into two steps:**

1. `_aggregate_pbp_stats(pbp, training_seasons)` — Computes `receiving_stats`, `rushing_stats`, `qb_stats`, and team-level totals (pass attempts, rush attempts, red zone attempts, air yards) from PBP. This is the expensive step (iterates millions of PBP rows). Returns a stats bundle that can be cached and reused across multiple roster merges.

2. `_assemble_models(aggregated_stats, current_rosters)` — Iterates over players in `current_rosters` (filtered to active status, fantasy-relevant positions), looks up pre-computed stats by `player_id`, and builds `PlayerModel` objects. Three cases:
   - **Player found in PBP stats** — Build model with historical stats, assign team/position from current roster
   - **Skill position player (QB/RB/WR/TE) not in PBP stats** — `build_rookie_model()` with draft round defaulting to 7 (tier 3) if unknown
   - **Kicker (K) not in PBP stats** — `build_kicker_model()` placeholder

**Player metadata source change:** Lines 106-116 currently build `meta_map` from `rosters.filter(season.is_in(seasons))`. This changes to build from `current_rosters` — the latest entry per player gives current team and position.

**Team-level totals for share computation** continue to use the player's historical team from PBP `posteam`. The share represents workload volume and gets re-normalized at roster selection time.

**New function:**
```python
def build_kicker_model(player_id, name, team) -> PlayerModel
```
Returns a `PlayerModel` with `position="K"`, default `PlayerUsage()`, default `PlayerOutcomes()`, `games_played=17`. This is a name tag for scoring attribution only — kicking simulation uses team-level `KickingModel` from the pipeline.

### `game_context.py`

**`build_game` signature change:**
```python
# Before
def build_game(self, home_team, away_team, seasons=None, pbp=None, rosters=None)

# After
def build_game(self, home_team, away_team, training_seasons=None, target_season=None, week=None, pbp=None, rosters=None)
```

**`_ensure_pipeline` splits caching into two layers:**
- Pipeline output (team distributions) — cached on `training_seasons` only
- Player models — cached on `(training_seasons, target_season, week)` since different weeks produce different rosters

**Roster loading:** Loads `current_rosters = loader.load_rosters([target_season])`. If `week` is provided, filters to the latest entry per player up to that week. If not, uses the latest entry per player across the entire season.

**PBP stats caching for backtest performance:** The aggregated PBP stats (from `_aggregate_pbp_stats`) are computed once per training_seasons and cached. Per-week roster merges (via `_assemble_models`) are cheap — just dict lookups and model construction. This prevents re-parsing millions of PBP rows 18 times during a full-season backtest.

**`build_team_distributions`** — unchanged. Still uses training PBP.

**`build_team_roster`** — unchanged internally. Correct rosters now flow from correct team assignments in player models.

**Default seasons:** `target_season` defaults to `max(training_seasons) + 1`. `training_seasons` defaults to `[2022, 2023, 2024]`.

### `backtester.py`

**`Backtester.run()` change:**
```python
# Before
self.builder.build_game(home, away, seasons=self.training_seasons)

# After
self.builder.build_game(
    home, away,
    training_seasons=self.training_seasons,
    target_season=self.test_season,
    week=wk,
)
```

Each week in the backtest loop passes `week=wk`, so the builder loads the roster snapshot for that specific week. Pipeline cache is shared across all 18 weeks. PBP stats are aggregated once. Only the roster merge runs per-week.

### `cli.py`

Every real-data command threads `target_season` and `week` through to `build_game()`:

| Command | `target_season` | `week` |
|---------|-----------------|--------|
| `week` | `season` | `week_num` |
| `season` | `season_year` | `wk` (from week loop) |
| `game` | `season` | `week_num` |
| `player` | `season` | `week_num` |
| `backtest` | handled by `Backtester` internally |
| `demo` | no changes (synthetic data) |

No new CLI flags needed — `season` and `week_num` are already available in every command.

### `rookie_builder.py`

No changes to the module itself. It's already used by `blend_with_archetype()` and `build_rookie_model()`. The only change is that `build_player_models` now calls `build_rookie_model()` directly for current-roster players with no PBP history (instead of only blending existing sparse data).

For players without draft data, default to `draft_round=7` (tier 3 archetype — lowest usage expectations). This is conservative and appropriate for undrafted free agents, practice squad promotions, etc.

## What Does NOT Change

- **`models/player.py`** — `PlayerModel`, `PlayerUsage`, `PlayerOutcomes`, `TeamRoster` dataclasses unchanged
- **`engine/`** — All simulation code unchanged (play calling, resolution, selection, game flow, clock, Monte Carlo)
- **`scoring/`** — Scoring engine and projection builder unchanged
- **`output/`** — Tables and export unchanged
- **`overrides/`** — Override engine, resolver, parser unchanged
- **`data/pipeline.py`** — Pipeline builds team-level distributions from PBP, unchanged
- **`data/loader.py`** — Already supports `load_rosters([season])` for any season
- **`config/`** — Config and defaults unchanged

## Testing Strategy

- **Unit tests for `_aggregate_pbp_stats`** — Verify correct stat aggregation from PBP (existing test patterns)
- **Unit tests for `_assemble_models`** — Test all three cases: PBP player, rookie fallback, kicker fallback
- **Unit test for roster filtering** — Verify only ACT/RES status and QB/RB/WR/TE/K positions included
- **Unit test for `build_kicker_model`** — Verify placeholder model structure
- **Integration test for traded player** — Build models with player on team A in PBP, team B in current roster, verify team B assignment
- **Integration test for missing rookie** — Player on current roster with no PBP data gets archetype model
- **Integration test for retired player** — Player in PBP but not on current roster is excluded
- **Integration test for kicker** — Kicker on current roster gets placeholder model
- **Backtester test for per-week rosters** — Verify different weeks produce different roster compositions
- **Cache test** — Verify PBP stats computed once, player models rebuilt per-week change
- **Regression** — All 512 existing tests continue to pass (demo mode unaffected, real-data tests may need fixture updates for new parameters)
