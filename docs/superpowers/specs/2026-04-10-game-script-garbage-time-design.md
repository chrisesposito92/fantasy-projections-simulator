# Game Script / Garbage Time Design

## Problem

The simulator already uses `score_diff` inside `GameStateBucket`, so late-game run/pass selection is not fully blind to scoreboard state. The missing layer is who gets the ball and how aggressively the offense behaves once game state becomes abnormal.

Two gaps remain:

1. **Trailing-late desperation is too flat.**
   The offense can pass more often because of the existing play-call buckets, but target distribution still comes from static baseline shares. The sim does not tighten volume toward top pass catchers or speed up enough in obvious catch-up situations.

2. **Late blowout personnel drift is absent.**
   When teams are protecting large fourth-quarter leads, the sim still gives the same baseline carry tree instead of shifting some rush volume from RB1 toward secondary backs.

This likely hurts weekly fantasy accuracy most at QB and WR, where trailing-late target concentration and pace changes drive large point swings.

## Goals

- **Phase 1:** improve trailing-late desperation behavior with team-specific pass rate, pace, and target concentration overlays.
- **Phase 2:** add late-lead RB carry redistribution as a separate, independently measurable overlay.
- **Primary success target:** improve QB and WR weekly rank correlation.
- **Guardrails:** do not regress overall `rank_corr` and `weekly_mae`.
- **Constraint:** keep base roster construction neutral. Game script should be applied transiently during simulation, not baked into static roster shares.
- **Constraint:** use historical PBP only. No new external data source or dependency.

## Approach

Use a **state-driven runtime overlay** backed by **empirical state splits with Bayesian fallback**.

The system has two layers:

1. **Build-time learning**
   A new `GameScriptEngine` learns team and rank-bucket priors from historical PBP for specific late-game regimes.

2. **Runtime application**
   A lightweight `RuntimeGameScript` object is derived from live `GameState` on each play. It applies pass-rate, pace, target concentration, or RB redistribution overlays without mutating the underlying roster.

This keeps the architecture aligned with the current codebase:

- `GameContextBuilder` continues to build neutral base distributions and rosters.
- `simulate_game()` decides when abnormal game script is active.
- `play_caller` and `player_selector` apply transient weight changes for the current play only.

## Approved Scope

### Phase 1: Trailing-Late Desperation

Allowed to change:

- team pass rate
- team pace
- player target concentration

Explicitly not allowed to change:

- fourth-down decisions
- PAT / 2-point decisions
- QB scramble rate
- catch rate or yardage efficiency
- base target shares stored on the roster

### Phase 2: Late-Lead RB Redistribution

Allowed to change:

- RB carry allocation within the RB subgroup only

Explicitly not allowed to change:

- pass target tree
- QB designed-run share
- backup QB / WR / TE substitution logic

## Regime Definitions

The first version uses explicit runtime regimes rather than a fully open-ended state matrix.

### `neutral`

Default state. No overlay. Current simulation behavior.

### `trailing_late`

Active when the offense is in the fourth quarter and either of these is true:

- `score_differential <= -8`
- `clock <= 300` and `score_differential <= -4`

Interpret `score_differential` from the offense perspective via `GameState.score_differential`.

This captures both:

- clear fourth-quarter deficits
- smaller deficits inside the final five minutes

### `leading_late_rb`

Active when all of the following are true:

- `quarter == 4`
- `clock <= 600`
- `score_differential >= 14`

This keeps phase 2 narrow: only obvious late blowouts.

### Priority

Only one regime is active per play:

1. `trailing_late`
2. `leading_late_rb`
3. `neutral`

In practice the first two do not overlap because the score differential signs oppose each other. The explicit priority just keeps the runtime contract simple.

## Data Layer

### New Package

Add a small `game_script` package under `src/fantasy_sim/data/`:

- `src/fantasy_sim/data/game_script/engine.py`
- `src/fantasy_sim/data/game_script/models.py`
- `src/fantasy_sim/data/game_script/config.py`
- `src/fantasy_sim/data/game_script/__init__.py`

This is large enough to justify a package instead of a single file.

### Input Data

Use nflverse PBP only, filtered with the same no-leakage rule used elsewhere:

- training data comes from `week < target_week`
- no target-week or future-play leakage

No new scraping is required.

### Learned Outputs

For each team, learn a compact `GameScriptProfile` with:

- `trailing_late_pass_rate_factor`
- `trailing_late_pace_factor`
- `trailing_late_target_factors`
- `leading_late_rb_factors`

These are neutral-centered multipliers. `1.0` means no change.

## Empirical Learning Rules

### 1. Team Pass Rate Factor

Measure each team's pass rate in `trailing_late` plays and compare it to that team's neutral pass rate.

```
team_ratio = trailing_late_pass_rate / neutral_pass_rate
league_ratio = league_trailing_late_pass_rate / league_neutral_pass_rate

factor = bayesian_blend(
    observed=team_ratio,
    prior=league_ratio,
    n_obs=trailing_late_pass_attempts + trailing_late_rush_attempts,
    prior_strength=pass_rate_prior_strength,
)
factor = clamp(factor, pass_rate_clamp)
```

At runtime, this multiplies the base pass probability in `PlayCallingDist`.

### 2. Team Pace Factor

Measure seconds per offensive snap in `trailing_late` versus neutral offense.

Because the engine already models tempo through `pace_factor`, learn pace as a ratio of **neutral seconds per play** to **trailing-late seconds per play**:

```
team_ratio = neutral_seconds_per_play / trailing_late_seconds_per_play
league_ratio = league_neutral_seconds_per_play / league_trailing_late_seconds_per_play

factor = bayesian_blend(
    observed=team_ratio,
    prior=league_ratio,
    n_obs=trailing_late_plays,
    prior_strength=pace_prior_strength,
)
factor = clamp(factor, pace_factor_clamp)
```

`factor > 1.0` means faster tempo and therefore less clock runoff per play.

### 3. Target Concentration by Rank Bucket

Do **not** learn raw player-ID late splits. That would be too sparse and too brittle across roster churn.

Instead:

- rank eligible pass catchers on each team by **neutral base target share**
- bucket them as:
  - `rank1`
  - `rank2`
  - `rank3_plus`
- learn how those bucket shares move in `trailing_late` states

Computation:

```
team_bucket_ratio = trailing_late_bucket_share / neutral_bucket_share
league_bucket_ratio = league_trailing_late_bucket_share / league_neutral_bucket_share

bucket_factor = bayesian_blend(
    observed=team_bucket_ratio,
    prior=league_bucket_ratio,
    n_obs=trailing_late_targets,
    prior_strength=target_prior_strength,
)
bucket_factor = clamp(bucket_factor, target_rank_factor_clamp)
```

At runtime:

- determine the current team target ranking from the roster's **current base shares**
- multiply each eligible player's `target_share` by the factor for that rank bucket
- renormalize within the eligible target pool

This means user overrides and weekly roster changes naturally feed into the runtime ranking while the learned priors still come from stable historical team behavior.

### 4. RB Carry Redistribution by Rank Bucket

Phase 2 follows the same pattern but only inside the RB subgroup.

- rank current RBs by **neutral base carry share**
- bucket them as:
  - `rb1`
  - `rb2`
  - `rb3_plus`
- learn how those bucket shares move in `leading_late_rb` states

Computation:

```
team_bucket_ratio = leading_late_bucket_share / neutral_bucket_share
league_bucket_ratio = league_leading_late_bucket_share / league_neutral_bucket_share

bucket_factor = bayesian_blend(
    observed=team_bucket_ratio,
    prior=league_bucket_ratio,
    n_obs=leading_late_rb_carries,
    prior_strength=rb_carry_prior_strength,
)
bucket_factor = clamp(bucket_factor, rb_rank_factor_clamp)
```

Runtime rule:

- reweight only the RB subgroup
- preserve total RB carry mass
- leave QB / WR / FB carry shares unchanged

That keeps phase 2 faithful to the approved scope: redistribution among backs, not a full personnel model.

## Model Changes

### Data Models

Add new dataclasses in `data/game_script/models.py`:

```python
@dataclass(frozen=True)
class TargetRankFactors:
    rank1: float = 1.0
    rank2: float = 1.0
    rank3_plus: float = 1.0


@dataclass(frozen=True)
class RbRankFactors:
    rb1: float = 1.0
    rb2: float = 1.0
    rb3_plus: float = 1.0


@dataclass(frozen=True)
class GameScriptProfile:
    team: str
    trailing_late_pass_rate_factor: float = 1.0
    trailing_late_pace_factor: float = 1.0
    trailing_late_target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    leading_late_rb_factors: RbRankFactors = field(default_factory=RbRankFactors)
```

### Runtime Model

Add a runtime-only object in `engine` or `data/game_script/models.py`:

```python
@dataclass(frozen=True)
class RuntimeGameScript:
    regime: Literal["neutral", "trailing_late", "leading_late_rb"]
    pass_rate_factor: float = 1.0
    pace_factor: float = 1.0
    target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    rb_factors: RbRankFactors = field(default_factory=RbRankFactors)
```

### TeamDistributions Extension

Extend `TeamDistributions` in `engine/types.py`:

```python
game_script_profile: GameScriptProfile | None = None
```

That gives `simulate_game()` direct access to the learned profile without mutating `TeamRoster`.

## Runtime Integration

### `GameContextBuilder`

During `build_game()`, attach a `GameScriptProfile` to each team's `TeamDistributions`.

Important rule:

- the profile is learned at build time
- the overlay is applied at runtime
- the base roster remains untouched

This keeps user overrides compatible. If a user changes `target_share` or `carry_share`, the runtime ranking logic will apply the learned bucket multipliers to the overridden baseline rather than the historical baseline.

### `simulate_game()`

On every play:

1. read `GameState`
2. resolve current regime with a small helper
3. build a `RuntimeGameScript`
4. pass it into play-calling and player-selection paths

### `select_play_type()`

Add an optional `script` argument:

```python
def select_play_type(
    state: GameState,
    play_calling: PlayCallingDist,
    rng: np.random.Generator,
    script: RuntimeGameScript | None = None,
) -> str:
```

Behavior:

- start from `play_calling.get_probs(bucket)`
- if `script` is absent or neutral, keep current behavior
- otherwise multiply the pass probability by `script.pass_rate_factor`
- recompute run as `1 - pass`
- clamp and renormalize to valid probabilities

### `resolve_play()`

Add an optional `script` argument and feed it through to player selection. Also combine pace factors:

```python
effective_pace = off_dists.pace_factor * script.pace_factor
```

Neutral script keeps the existing result because `script.pace_factor == 1.0`.

### `select_receiver()`

Add optional runtime script weighting.

Behavior:

- filter to available players first using the existing `_filter_available()`
- rank eligible receivers by current base `target_share`
- if regime is `trailing_late`, apply rank bucket multipliers
- renormalize and sample

Red zone selection remains orthogonal:

- first choose baseline red-zone or non-red-zone share as today
- then apply the `trailing_late` rank multiplier
- renormalize

That preserves the existing red-zone feature while allowing late-game concentration.

### `select_rusher()`

Phase 1: unchanged.

Phase 2 behavior in `leading_late_rb`:

- split the eligible rusher pool into RBs and non-RBs
- keep non-RB weights unchanged
- reweight RBs by `rb1`, `rb2`, `rb3_plus`
- renormalize the RB subgroup back to its original total RB mass
- combine RB and non-RB weights and sample

This preserves QB designed-run share.

## Configuration

Add a new section to `config/defaults.yaml`:

```yaml
game_script:
  enabled: false
  trailing_late:
    enabled: true
    deficit_threshold: 8
    final_five_minutes: 300
    final_five_deficit_threshold: 4
    pass_rate_prior_strength: 250
    pace_prior_strength: 250
    target_prior_strength: 80
    pass_rate_clamp: [1.00, 1.35]
    pace_factor_clamp: [1.00, 1.20]
    target_rank_factor_clamp: [0.85, 1.25]
  leading_late_rb:
    enabled: false
    lead_threshold: 14
    late_minutes: 600
    rb_carry_prior_strength: 100
    rb_rank_factor_clamp: [0.80, 1.20]
```

Design intent:

- `game_script.enabled` gates the entire system
- `trailing_late.enabled` and `leading_late_rb.enabled` allow phase-by-phase A/B testing
- thresholds are explicit and sweepable

## A/B Validation

### Phase 1

```bash
uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --label "game-script-trailing"
```

### Phase 2

```bash
uv run python scripts/validate.py --sims 50 --set game_script.enabled=true --set game_script.trailing_late.enabled=true --set game_script.leading_late_rb.enabled=true --label "game-script-rb"
```

### Suggested Sweeps

```bash
uv run python scripts/validate.py --sims 50 --set game_script.trailing_late.pass_rate_prior_strength=150 --label "gs-pass-ps150"
uv run python scripts/validate.py --sims 50 --set game_script.trailing_late.target_prior_strength=50 --label "gs-target-ps50"
uv run python scripts/validate.py --sims 50 --set game_script.leading_late_rb.rb_carry_prior_strength=60 --label "gs-rb-ps60"
```

## Validation Metrics

### Primary Phase 1 Target

- QB weekly rank correlation
- WR weekly rank correlation

### Overall Guardrails

- overall `rank_corr`
- overall `weekly_mae`
- no material regression in season MAE or calibration if tracked in the harness

### Realism Checks

Add targeted validation views for:

- trailing-late pass rate delta versus actual team splits
- trailing-late pace delta versus actual team splits
- top-target concentration shift versus actual team splits
- leading-late RB1/RB2 carry split versus actual team splits

These should live beside the existing A/B harness rather than replacing it.

## Testing Strategy

- **Unit: regime resolver**  
  known `GameState` values map to `neutral`, `trailing_late`, or `leading_late_rb`

- **Unit: team factor learning**  
  pass-rate and pace ratios shrink correctly toward league priors

- **Unit: target concentration learning**  
  bucket ratios produce expected `rank1`, `rank2`, `rank3_plus` multipliers

- **Unit: RB redistribution learning**  
  bucket ratios produce expected `rb1`, `rb2`, `rb3_plus` multipliers

- **Unit: `select_play_type()` overlay**  
  pass probability moves in the correct direction and remains normalized

- **Unit: `select_receiver()` overlay**  
  `rank1` concentration increases in `trailing_late` while neutral behavior is unchanged

- **Unit: `select_rusher()` overlay**  
  `leading_late_rb` shifts carries away from RB1 while preserving total RB carry mass

- **Integration: neutral regression**  
  missing profile or neutral regime reproduces current behavior

- **Integration: no temporal leakage**  
  target week data never contributes to learned factors

- **A/B validation**  
  required before enabling defaults

## Scope Boundaries

### In Scope

- new `GameScriptEngine` and config/models
- team-specific trailing-late pass-rate factor
- team-specific trailing-late pace factor
- rank-based trailing-late target concentration
- rank-based leading-late RB carry redistribution
- runtime regime resolver
- independent toggles for phase 1 and phase 2
- tests and validation hooks

### Out of Scope

- fourth-down aggression
- PAT / 2-point logic
- catch-rate or yards-per-target adjustments
- QB scramble-rate changes
- backup QB substitution
- WR / TE blowout diffusion
- full personnel packages or snap-level substitutions
- any new external data source

## Why This Shape

Three alternatives were considered:

1. **Inline modifiers directly in the game loop**  
   Fastest to code, but it would entangle regime logic with play simulation and make tuning harder.

2. **State-driven runtime context layer**  
   Chosen approach. It keeps build-time learning separate from runtime application and matches the current engine boundaries.

3. **Fully learned state-split distributions swapped at build time**  
   More statistically pure, but much heavier and much riskier for sparsity at the player level.

The chosen design keeps the problem small enough to validate in phases while still targeting the biggest missing behavioral layer in the simulator.
