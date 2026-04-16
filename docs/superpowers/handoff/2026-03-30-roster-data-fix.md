# Handover: Roster/Team Assignment Bug Fix

## The Problem

When projecting a future/current season (e.g., 2024), the simulator uses historical PBP data (2021-2023) for model fitting. But it also gets **team assignments** from that same historical data. This means:

- **Joe Mixon** shows as CIN RB (his 2021-2023 team) instead of HOU (his 2024 team)
- **Every free agent, trade, and roster move** is missed
- **Kickers** don't appear at all because they're not in run/pass PBP data
- **Rookies** who weren't in the league during training years are completely missing from rosters

## Root Cause

`player_builder.build_player_models(pbp, rosters, seasons)` gets both the player's **team** and their **stats** from the same data source (historical PBP + historical rosters). There's no separation between "who is on which team NOW" and "what are this player's historical stats."

`GameContextBuilder.build_game()` passes `training_seasons` (e.g., [2021, 2022, 2023]) to both the pipeline AND the player builder. So the roster data is from the training period, not the target season.

## The Fix (High Level)

Separate team assignment from statistical profile:

1. **Current roster** (target season, e.g., 2024): Determines which players are on which teams, their positions, and availability
2. **Historical PBP** (training seasons, e.g., 2021-2023): Provides statistical profiles (usage rates, outcome distributions)
3. **Merge**: Build statistical profiles from historical data, then assign players to their CURRENT team

This also naturally fixes:
- **Kickers**: They're in the current roster even though they're not in PBP data → get placeholder models
- **Rookies**: They're in the current roster → get archetype models from `rookie_builder`
- **Free agents/trades**: Player stats come from their historical play, but team assignment comes from current roster

## Affected Files

- `src/fantasy_sim/data/player_builder.py` — needs `current_rosters` parameter separate from PBP rosters
- `src/fantasy_sim/data/game_context.py` — needs to load target season roster AND training season PBP
- `src/fantasy_sim/data/rookie_builder.py` — should be used for current-roster players without historical PBP data
- `src/fantasy_sim/cli.py` — may need to pass target season separately

## Current Architecture (for reference)

```python
# game_context.py - current flow
def build_game(self, home_team, away_team, seasons):
    # seasons = training_seasons (e.g., [2021, 2022, 2023])
    pipeline_output = pipeline.build(pbp)  # uses training PBP
    player_models = build_player_models(pbp, rosters, seasons)  # ← BUG: rosters from training years
    home_roster = build_team_roster(home_team, player_models)
    away_roster = build_team_roster(away_team, player_models)

# player_builder.py - current flow
def build_player_models(pbp, rosters, seasons):
    # Gets player metadata (name, position, TEAM) from rosters
    # Gets stats from PBP
    # Both use the same seasons → team assignment is stale
```

## Desired Architecture

```python
# game_context.py - desired flow
def build_game(self, home_team, away_team, training_seasons, target_season):
    pipeline_output = pipeline.build(pbp)  # training PBP for distributions

    # Load CURRENT roster for team assignments
    current_rosters = loader.load_rosters([target_season])

    # Build stats from HISTORICAL PBP, assign teams from CURRENT roster
    player_models = build_player_models(
        pbp=training_pbp,
        current_rosters=current_rosters,  # ← team assignments from here
        training_seasons=training_seasons,
    )

    # Players on current roster but NOT in historical PBP → use rookie/archetype models
    # Kickers on current roster → placeholder kicker models

    home_roster = build_team_roster(home_team, player_models)
    away_roster = build_team_roster(away_team, player_models)
```

## Project Context

- 512 tests currently passing
- 39 source files, 47 test files
- Design spec: `docs/superpowers/specs/2026-03-29-fantasy-projections-simulator-design.md`
- CLI reference: `CLI-COMMANDS.md`
- CLAUDE.md has full architecture documentation

## Prompt for New Context

Use `/brainstorming` with this argument:

```
We found a critical bug in the fantasy-projections-simulator: player team assignments come from historical PBP training data instead of current-season rosters. This means traded/signed players show up on their OLD team (e.g., Joe Mixon as CIN instead of HOU in 2024), kickers are missing from most rosters (they're not in PBP data), and rookies without historical data are absent entirely.

The fix requires separating "which team is this player on" (current season roster) from "what are this player's stats" (historical PBP). See the detailed handover doc at docs/superpowers/handover/2026-03-30-roster-data-fix.md for the full problem description, root cause, affected files, and desired architecture.

This is NOT a new feature — it's a bug fix to existing architecture. The brainstorm should focus on: (1) exactly how to restructure build_player_models and GameContextBuilder, (2) how to handle players on the current roster with no historical PBP data (rookies, kickers, practice squad promotions), (3) how to handle players with historical data who retired or are no longer in the league, (4) whether the backtest command needs different handling (it's testing a historical season, so "current roster" IS the historical roster).
```
