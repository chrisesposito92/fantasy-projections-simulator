# Goal-Line Concentration Design

## Problem

The simulator currently learns one receiving red-zone share and one rushing red-zone share per player:

- `red_zone_target_share` for targets inside the 20
- `red_zone_carry_share` for carries inside the 20

That single split is too coarse for goal-line work. A player can have ordinary red-zone volume from the 6-20 yard band but still dominate touches at the 1-5 yard line, or the reverse. The current model loses that distinction because [`player_builder.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/player_builder.py) collapses both bands into one share and [`player_selector.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/engine/player_selector.py) uses that same share everywhere inside the 20.

This shows up most clearly in goal-line rushing, but the same structural issue exists for goal-line receiving. The next accuracy lever is to split red-zone opportunity concentration into two buckets:

- outer red zone: `yardline_100` 6-20
- goal line: `yardline_100` 1-5

## Approach

Add a new config-gated feature, `goal_line_concentration`, that learns separate 6-20 and 1-5 opportunity shares for both targets and carries. The feature is internal-only in this phase. It does not add new override fields, new CLI flags, or new end-user controls.

When enabled, runtime player selection should choose weights by field position:

- `yard_line <= 5`: use goal-line shares
- `6 <= yard_line <= 20`: use outer-red-zone shares
- otherwise: use the existing base shares

The feature changes only opportunity allocation. It does not modify:

- play-call selection
- TD gate probabilities
- inside-5 TD factors
- matchup, weather, props, or game-script layers

This keeps the feature isolated to one question: whether explicit goal-line concentration improves accuracy.

## Architecture

The implementation stays inside the existing usage pipeline rather than adding a separate runtime context object.

### PlayerUsage additions

Add four internal fields to `PlayerUsage` in [`models/player.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/models/player.py):

- `outer_rz_target_share: float = 0.0`
- `goal_line_target_share: float = 0.0`
- `outer_rz_carry_share: float = 0.0`
- `goal_line_carry_share: float = 0.0`

These are internal model fields, not override-facing API.

### Data layer

Extend `_aggregate_pbp_stats()` in [`player_builder.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/player_builder.py) to collect per-player and per-team opportunity counts in two bands.

Receiving counts:

- `outer_rz_targets`
- `goal_line_targets`

Rushing counts:

- `outer_rz_carries`
- `goal_line_carries`

Matching team totals:

- `team_outer_rz_pass_attempts`
- `team_goal_line_pass_attempts`
- `team_outer_rz_rush_attempts`
- `team_goal_line_rush_attempts`

Band definitions are explicit and non-overlapping:

- goal line: `yardline_100 <= 5`
- outer red zone: `6 <= yardline_100 <= 20`

### Model assembly

Extend `_assemble_models()` to compute the four new internal usage shares from the corresponding per-player counts and team totals. This follows the existing share-building pattern:

- player count divided by matching historical team total
- current roster assignment preserved
- no new external data sources

### Runtime selection

Update [`select_receiver()`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/engine/player_selector.py) and `select_rusher()` in the same file so the selected weight source depends on both yard line and config:

- feature off: current behavior
- feature on and `yard_line <= 5`: prefer `goal_line_*_share`
- feature on and `6 <= yard_line <= 20`: prefer `outer_rz_*_share`
- outside red zone: current base share behavior

The selection code remains the only runtime consumer of the new sub-shares.

## Data Flow

1. Historical PBP is aggregated into per-player and per-team counts for 6-20 and 1-5.
2. Model assembly converts those counts into internal usage shares.
3. Team-roster construction normalizes the new share fields across the current roster.
4. Runtime selector chooses the correct share family for the current yard-line band.
5. If the chosen share family is unavailable, runtime falls back to the existing red-zone share, then base share.

No new engine is introduced. The feature rides the same historical-data-to-roster-to-selector path that the simulator already uses for base and red-zone shares.

## Fallback And Error Handling

This phase should rely on explicit fallbacks, not Bayesian priors.

### No priors in phase one

The first experiment should answer whether the split itself adds signal. Adding priors or shrinkage immediately would make it harder to interpret A/B results and would introduce another tuning dimension before the simpler structural question is answered.

### Runtime fallback order

Receiving:

1. band-specific share (`goal_line_target_share` or `outer_rz_target_share`)
2. `red_zone_target_share`
3. `target_share`

Rushing:

1. band-specific share (`goal_line_carry_share` or `outer_rz_carry_share`)
2. `red_zone_carry_share`
3. `carry_share`

### Zero-mass behavior

If the relevant band has no usable share mass on the current roster, the selector must fall back instead of producing a zero-weight pool or inventing pseudo-mass.

This is the safety contract:

- missing player history is allowed
- missing team-band history is allowed
- empty current-roster mass is allowed
- all of those cases degrade to existing behavior rather than raising or changing semantics

If `goal_line_concentration.enabled` is `false`, behavior must be identical to today.

## Normalization

[`build_team_roster()`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/player_builder.py) currently normalizes:

- `carry_share`
- `red_zone_carry_share`
- `target_share`
- `red_zone_target_share`

The new feature requires equivalent normalization passes for:

- `outer_rz_carry_share`
- `goal_line_carry_share`
- `outer_rz_target_share`
- `goal_line_target_share`

Normalization rules stay the same:

- normalize only among eligible current-roster players with positive mass
- preserve relative proportions
- skip normalization when the total is zero

This keeps selector weights interpretable and prevents stale historical teammates from leaking probability mass out of the current roster.

## Configuration

Add a new top-level section to [`config/defaults.yaml`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/config/defaults.yaml):

```yaml
goal_line_concentration:
  enabled: false
```

Phase one intentionally has a single switch. No sensitivity values, clamps, or priors are needed until the base split proves useful.

The feature should be activated through the existing validation override path:

```bash
uv run python scripts/validate.py --sims 50 --set goal_line_concentration.enabled=true --label "goal-line-concentration"
```

If that first run is promising, follow-up confirmation should use higher-sim runs before changing defaults.

## Testing Strategy

### Data extraction and assembly

Add tests in [`tests/test_data/test_player_builder.py`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/tests/test_data/test_player_builder.py) to verify:

- `yardline_100 <= 5` counts feed goal-line buckets
- `6 <= yardline_100 <= 20` counts feed outer-red-zone buckets
- shares are computed from the matching team totals
- band-specific share fields normalize to `1.0` when current-roster mass exists
- zero-mass cases preserve fallback viability

### Runtime selector behavior

Add deterministic selector tests under [`tests/test_engine`](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/tests/test_engine) for:

- feature enabled + `yard_line <= 5` uses goal-line shares
- feature enabled + `6 <= yard_line <= 20` uses outer-red-zone shares
- feature disabled uses existing red-zone shares
- missing sub-share mass falls back to existing red-zone shares
- missing red-zone share still falls back to base share

### Regression safety

Existing red-zone share tests should continue to pass unchanged when the feature is off. Override tests should remain unchanged because this phase does not expose any new override fields.

## Validation Plan

Run the feature in isolation first:

```bash
uv run python scripts/validate.py --sims 50 --set goal_line_concentration.enabled=true --label "goal-line-concentration"
```

If the signal is positive, confirm with longer runs such as:

```bash
uv run python scripts/validate.py --sims 200 --set goal_line_concentration.enabled=true --label "goal-line-concentration-200"
uv run python scripts/validate.py --sims 400 --set goal_line_concentration.enabled=true --label "goal-line-concentration-400"
```

Success should be judged primarily by whether the feature improves weekly accuracy metrics for TD-sensitive positions, especially RB and high-leverage receivers, without creating a meaningful regression in overall top-line validation.

If the result is neutral or noisy, keep the feature off and stop there. This phase is an experiment, not a default-on commitment.

## Scope Boundaries

### In scope

- split red-zone opportunity shares into 6-20 and 1-5 bands
- support both receiving and rushing concentration
- keep the feature behind a single config flag
- keep the new sub-shares internal-only
- update normalization and selector logic to use the new bands
- add unit and regression tests

### Out of scope

- new override fields for band-specific shares
- Bayesian priors or shrinkage for the new bands
- changes to play-call probabilities
- changes to TD gate probabilities
- changes to the existing inside-5 TD tendency feature
- new external data sources or scraping
- any user-facing CLI surface beyond existing `--set` overrides
