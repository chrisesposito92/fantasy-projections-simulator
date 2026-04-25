# QB Scramble Model Design

## Status

Design approved on 2026-04-24. This spec covers the first slice of the
hypothesis from `docs/hypotheses-list.md`: "Build a QB rushing model for
scramble probability, designed-run selection, and rush-gain tail behavior."

This slice covers scramble probability only. It is a planning artifact and does
not change runtime behavior.

## Context

The current simulator handles QB rushing in two separate paths:

- Scrambles happen inside `_resolve_pass()` before sack, interception, and pass
  fumble checks. The selected passer rolls against `passer.usage.scramble_rate`.
- Designed QB runs use the normal run path. A QB enters the designed-run rusher
  pool only when `carry_share >= MIN_QB_CARRY_SHARE`.

`player_builder.py` already separates these paths when the nflverse
`qb_scramble` field exists. It subtracts scramble carries from QB designed-run
carry share, uses scramble-only plays to build `scramble_yards_dist`, and uses
historical scramble counts to compute `scramble_rate`.

The hypothesis list ranks QB rushing first because QB weekly rank correlation is
a key gap and mobile-QB fantasy value is high leverage. The same document
recommends splitting the work into scramble probability first, then designed
runs and gain-tail behavior. This spec follows that recommendation.

## Intended Change

Add an off-by-default learned scramble-probability layer that adjusts the
existing QB scramble check with a bounded context factor:

```python
effective_scramble_rate = base_scramble_rate * learned_context_factor
```

The model should not replace the player prior. `passer.usage.scramble_rate`
remains the base rate learned from historical player data. The new layer learns
when the current game state should increase or reduce that prior.

This first slice should not change:

- pass/run play selection
- designed QB run selection
- RB carry selection
- QB `carry_share` construction
- scramble yard sampling
- sack, interception, fumble, touchdown, safety, and clock resolution

That boundary gives the experiment a clean A/B test against current promoted
defaults.

## Runtime Boundary

The runtime node owns only the scramble probability multiplier inside pass
resolution.

Runtime behavior should be:

1. Select the passer exactly as today.
2. Read the passer's current `usage.scramble_rate` as the base rate.
3. Ask an optional `QbScrambleContext` for a finite context factor.
4. If a factor exists, multiply the base rate and clamp the effective rate.
5. Roll the existing scramble check with the effective rate.
6. Resolve scramble yards, home-field adjustment, safety, touchdown, fumble, and
   clock exactly as today.
7. If the context is disabled, missing, invalid, or returns `None`, use the
   existing base rate with no change.

The model should run only on pass plays. It should not alter `select_play_type()`
or `select_rusher()`.

## Data Inputs And Availability

Use nflverse PBP as the primary training source. The first version should train
from pass/dropback-like rows that can identify QB scrambles through
`qb_scramble`.

Likely training fields:

- `season`, `week`, `game_id`
- `posteam`, `defteam`, `home_team`, `away_team`
- `passer_player_id`, `passer_player_name`
- `qb_scramble`
- `down`, `ydstogo`, `yardline_100`
- `qtr`, `quarter_seconds_remaining`, `half_seconds_remaining`,
  `game_seconds_remaining`
- `score_differential`
- `spread_line`, `total_line`

Useful derived features:

- down and distance indicators
- red-zone and goal-to-go indicators
- yardline, quarter, clock, and two-minute indicators
- score differential and trailing/leading indicators
- home/away indicator
- week bucket
- spread, total, and implied team total when available
- QB prior scramble rate from source seasons
- team prior scramble rate and opponent prior scramble rate allowed

Artifacts must be temporal. A target-season artifact may use only seasons before
the target season, bounded by the configured source-season and training-window
settings. Same-game and future-week data must not enter runtime priors.

## Implementation Shape

Add a new package:

- `src/fantasy_sim/data/qb_rushing/config.py`
- `src/fantasy_sim/data/qb_rushing/models.py`
- `src/fantasy_sim/data/qb_rushing/training.py`
- `src/fantasy_sim/data/qb_rushing/runtime.py`
- `src/fantasy_sim/data/qb_rushing/__init__.py`

Add config under `qb_rushing.scramble:` in `config/defaults.yaml`, defaulting
off:

- `enabled: false`
- `artifacts_dir: null`
- `factor_clamp`, for example `[0.50, 1.75]`
- `probability_clamp`, for example `[0.00, 0.25]`
- `min_examples`
- schema and model metadata

Use a regularized logistic or log-rate adjustment implemented with existing
numeric dependencies. The model should be anchored to the current player prior.
The artifact should include:

- schema version
- model type
- target season
- source seasons
- feature names
- coefficients
- intercept
- factor clamp
- probability clamp
- example count, positive rate, log loss, convergence flag, and source-season
  coverage diagnostics

Add `scripts/fit_qb_scramble_model.py` to write one artifact per target season.
Initial command shape:

```bash
uv run python scripts/fit_qb_scramble_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/qb_rushing/scramble/smoke_v1
```

Runtime wiring should follow the learned play-call and target-selection pattern:

- Load `qb_scramble_model_<target_season>.json` when enabled.
- Build an optional per-team/game `QbScrambleContext` in `GameContextBuilder`.
- Store the context on the team simulation distributions or another narrow
  runtime holder passed into `_resolve_pass()`.
- Extend `_resolve_pass()` to ask for a factor before the existing scramble roll.
- Report artifact coverage in validation output so disabled, missing, partial,
  invalid, and covered states are visible.

## Test Coverage

Focused tests should define the contract before validation runs:

- config parsing: disabled default, enabled override, invalid clamps, missing
  artifact directory
- training helpers: temporal source-season selection, feature matrix shape,
  empty-example failure, deterministic small-fixture artifact
- runtime artifact loading: missing file fallback, invalid schema fallback,
  unsupported model type fallback, non-finite coefficient fallback
- feature construction: stable values for down, distance, yardline, clock, score,
  home/away, market fields, and QB prior
- factor computation: finite output, factor clamp, probability clamp, pocket-QB
  guardrails
- `play_resolver.py`: disabled context matches existing behavior, valid high
  factor increases seeded scramble frequency, invalid context falls back to base
  rate
- `GameContextBuilder`: context attaches only when enabled and a valid target
  artifact exists
- regression tests: QB `carry_share` and designed-run rusher pool stay unchanged

## Validation

Validate marginal lift against current defaults, because defaults already include
dynamic blend and residual calibration.

Smoke fit:

```bash
uv run python scripts/fit_qb_scramble_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/qb_rushing/scramble/smoke_v1
```

Smoke validation:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set qb_rushing.scramble.enabled=true \
  --set qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/smoke_v1 \
  --label qb-scramble-model-s50
```

Decision validation if smoke clears:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 200 \
  --set qb_rushing.scramble.enabled=true \
  --set qb_rushing.scramble.artifacts_dir=results/qb_rushing/scramble/smoke_v1 \
  --label qb-scramble-model-s200
```

Smoke should clear only if average rank correlation and weekly MAE are not worse
than defaults. The 200-sim decision run should require:

- Average rank-correlation delta across QB/RB/WR/TE is at least `+0.0030`.
- Weekly MAE delta is at most `-0.025`.
- QB weekly rank correlation improves.
- QB weekly MAE improves.
- RB does not materially regress, because this model should not steal designed
  carries from RBs.
- QB rushing-yards KS is not worse.
- Scramble rate and QB rushing attempts remain plausible by player archetype.
- Artifact coverage is full for promoted seasons, or the verdict is explicitly
  marked covered-only.

Useful diagnostics:

- simulated scramble attempts by QB and team versus defaults
- QB rushing attempts, rushing yards, and fantasy points by mobility tier
- effective scramble-rate distribution by game state
- model log loss versus base player prior
- pocket-QB false-positive rates

## Risks

- The model may predict football scrambles better without improving fantasy
  projection metrics after post-sim calibration.
- A factor that is too wide can inflate pocket-QB rushing and damage realism.
- The current scramble check happens before sack and interception checks, so a
  large factor can indirectly reduce sacks, pass attempts, and passing yards.
- Market and team-prior features can leak if target-season data is not bounded
  carefully.
- QB rushing is sparse, especially for pocket passers, so the model may overfit
  unless it uses strong regularization and conservative clamps.

## Fallback And Default Behavior

- `qb_rushing.scramble.enabled=false` by default.
- Missing artifacts fall back to current `scramble_rate` behavior.
- Invalid schema or unsupported model type falls back to current behavior.
- Missing required features fall back to current behavior.
- Non-finite factors or probabilities fall back to current behavior.
- If validation improves QB but hurts top-line metrics, RB opportunity, or QB
  rushing-yard distribution quality, the verdict is no promotion or a narrower
  follow-up slice, not a weakened promotion gate.

## Out Of Scope

- Learned designed-run selection for QBs.
- Changes to `MIN_QB_CARRY_SHARE`.
- New scramble-yard or rushing-yard gain-tail distributions.
- Red-zone or goal-line QB carry concentration.
- Replacing pass/run play calling.
- Replacing sack, interception, or fumble ordering.
