# Learned Play-Call Model Design

## Status

Design approved on 2026-04-24. This spec covers the hypothesis from
`docs/hypotheses-list.md`: "Replace empirical pass/run choice with a learned
play-call model."

This is a planning artifact only. It does not change runtime behavior.

## Context

The current simulator chooses pass or run with `PlayCallingDist`, which is built
by `Preprocessor.compute_play_calling()` from historical team and
`GameStateBucket` pass/run rates. At runtime, `engine.play_caller.select_play_type()`
looks up the bucket probability and samples pass or run. If a bucket has too few
plays, it falls back to the team's historical default pass/run split.

The current default stack also modifies the play-call environment:

- Vegas ITT still changes pace.
- Vegas spread currently adjusts only `PlayCallingDist.default`.
- Game script currently applies a late-trailing pass-rate multiplier at play
  selection time.
- Dynamic blend and residual calibration run after simulation and are already
  enabled by default.

The validation ledger shows that broad heuristic layers are often near the noise
floor, while promoted gains have come from role/market/post-sim priors. Learned
in-sim nodes remain plausible, but the parked receiver target-selection result
shows that each learned node needs a clean boundary, strict fallback behavior,
and promotion evidence against current defaults.

## Intended Change

Add an off-by-default learned play-call node that predicts `P(pass)` directly
for the current offensive team and game state. When enabled and covered by a
valid artifact, this node replaces the empirical pass/run lookup for that play.
It should improve backtest numbers by learning interactions that the current
bucketed historical rates cannot represent well:

- down and distance
- yardline and red-zone state
- quarter and clock
- score differential
- team and opponent tendencies
- home/away context
- spread, total, and implied team total
- recent team-level play-calling context

The learned model should own pass/run probability when active. To avoid
double-counting, it should consume market and late-game context directly and skip
only the current pass-rate modifiers from Vegas spread and game script. It should
keep Vegas pace, game-script pace, game-script target/RB effects, and all
downstream play resolution behavior.

## Runtime Boundary

The model predicts only the binary play type at the current `select_play_type()`
boundary:

- output: pass probability, then sampled `pass` or `run`
- no ownership of fourth-down punt/field-goal/go-for-it decisions
- no ownership of target selection
- no ownership of rusher selection
- no ownership of scramble, sack, interception, fumble, yards, TD, or clock
  resolution

Runtime behavior should be:

1. Resolve fourth-down decisions exactly as today.
2. Resolve the runtime game-script profile exactly as today.
3. Call `select_play_type()` with the current `GameState`, empirical
   `PlayCallingDist`, optional game-script object, and optional learned
   play-call context.
4. If the learned context is enabled and returns a valid finite probability,
   clamp it to the configured probability range and sample pass/run from it.
5. Otherwise fall back to the current empirical `PlayCallingDist` path.
6. Pass the selected play type into existing play resolution unchanged.

When the learned node is active for a team/game, the current Vegas spread
pass-rate adjustment and game-script pass-rate multiplier should not be applied
to play-call probability. Vegas volume/pace remains active.

## Data Inputs And Availability

Use nflverse PBP as the primary training source. The current local cache has the
required fields for a first version:

- `season`, `week`, `game_id`
- `posteam`, `defteam`, `home_team`, `away_team`
- `play_type`
- `down`, `ydstogo`, `yardline_100`
- `qtr`, `quarter_seconds_remaining`, `half_seconds_remaining`,
  `game_seconds_remaining`
- `score_differential`, `posteam_score`, `defteam_score`
- `spread_line`, `total_line`
- `roof`, `surface`, `goal_to_go`

Training examples should include only rows with `play_type in {"pass", "run"}`
and a valid offensive team. The existing 2022-2024 PBP cache has about 106,000
pass/run plays and full spread/total coverage. Older cached PBP exists back to
2018, so `--min-source-season 2018` is viable for fitting target-season
artifacts.

Artifacts must be temporal:

- `play_call_model_2022.json` uses seasons before 2022, bounded by
  `--min-source-season`.
- `play_call_model_2023.json` uses seasons before 2023.
- `play_call_model_2024.json` uses seasons before 2024.

Any target-season team priors must be prior-season or prior-week only. The first
version should prefer prior-season team features to keep the implementation
simple and avoid same-season leakage.

## Implementation Shape

Add a new package:

- `src/fantasy_sim/data/play_call_model/config.py`
- `src/fantasy_sim/data/play_call_model/models.py`
- `src/fantasy_sim/data/play_call_model/training.py`
- `src/fantasy_sim/data/play_call_model/runtime.py`
- `src/fantasy_sim/data/play_call_model/__init__.py`

Add config under `play_call_model:` in `config/defaults.yaml`, defaulting off:

- `enabled: false`
- `artifacts_dir: null`
- `probability_clamp`, for example `[0.05, 0.95]`
- `fallback: empirical`
- schema/model metadata

Use a regularized logistic model implemented with existing `numpy` and `scipy`.
Avoid adding a new ML dependency for v1. The artifact should include:

- schema version
- model type
- target season
- source seasons
- feature names
- coefficients
- intercept
- probability clamp
- diagnostics such as example count, pass rate, log loss, convergence, and
  source-season coverage

Add `scripts/fit_play_call_model.py` to write one artifact per target season.
The initial command shape should be:

```bash
uv run python scripts/fit_play_call_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/play_call_model/smoke_v1
```

Runtime wiring should follow the existing target-selection pattern:

- Add a `PlayCallModelConfig` loader to validation config and CLI config paths.
- Add a runtime `PlayCallModel` that loads
  `play_call_model_<target_season>.json`.
- Build a per-team/game `PlayCallContext` in `GameContextBuilder`.
- Add `play_call_context` to `TeamDistributions`.
- Extend `select_play_type()` to prefer `play_call_context.pass_probability()`
  when valid.
- Extend coverage reporting so the validation header and ledger can distinguish
  covered, partial, missing, and disabled artifact states.

## Test Coverage

Focused tests should cover the contract before broad validation runs:

- config parsing: disabled default, enabled override, invalid clamp, invalid
  fallback value
- training helpers: feature matrix shape, temporal source-season selection,
  empty-example failure, deterministic fit output on a small fixture
- artifact runtime: missing artifact fallback, invalid schema fallback,
  coefficient parsing, probability clamp, non-finite probability fallback
- `select_play_type()`: learned context wins when valid, empirical fallback wins
  when context returns `None`, game-script pass-rate multiplier is skipped only
  for the learned path
- `GameContextBuilder`: attaches a play-call context only when config is enabled,
  target season is present, and the artifact is loadable
- validation coverage: `play_call_model` reports disabled, full, partial, and
  missing states from artifact files

## Validation

Validate marginal lift against current defaults, because defaults already include
the promoted post-sim stack.

Smoke run:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set play_call_model.enabled=true \
  --set play_call_model.artifacts_dir=results/play_call_model/smoke_v1 \
  --label play-call-model-s50
```

Decision run if smoke clears:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 200 \
  --set play_call_model.enabled=true \
  --set play_call_model.artifacts_dir=results/play_call_model/smoke_v1 \
  --label play-call-model-s200
```

Primary promotion gate:

- Average rank-correlation delta across QB/RB/WR/TE is at least `+0.0030`.
- Weekly MAE delta is at most `-0.025`.
- QB and WR do not regress on both weekly rank correlation and weekly MAE.
- Stat KS does not show obvious distribution damage for WR receiving yards, QB
  passing yards, RB rushing yards, or TE receiving yards.
- Simulated pass rate, rush rate, total plays, and position opportunity splits
  remain within sane NFL-like ranges and do not drift sharply versus defaults.
- Artifact coverage is full for the promoted seasons, or promotion scope is
  explicitly marked covered-only.

Useful additional diagnostics:

- model log loss versus empirical team default and empirical bucket baseline
- average predicted pass rate by down, quarter, score bucket, and team
- simulated play volume versus defaults
- pass attempts, rush attempts, targets, carries, and fantasy points by position

## Risks

- The model may improve football play-call prediction while failing to improve
  fantasy projection metrics after dynamic blend and residual calibration.
- Small pass-rate bias can propagate into QB attempts, RB carry volume, receiver
  opportunity, and stat KS damage.
- Team categorical features can overfit, especially with only a few seasons of
  data.
- Market fields and game-script state overlap with existing runtime modifiers,
  so the active learned path must avoid double-counting pass-rate adjustments.
- Same-game leakage is the main data risk; target-season labels must never be
  used for target-season artifacts.
- Late-game behavior must remain plausible because play calling strongly affects
  comeback scripts, target distribution, and pace.

## Fallback And Default Behavior

- `play_call_model.enabled=false` by default.
- Missing artifact falls back to empirical play calling.
- Invalid schema falls back to empirical play calling.
- Missing required features fall back to empirical play calling.
- Non-finite or out-of-range probabilities fall back to empirical play calling.
- If smoke improves rank correlation but damages opportunity sanity or stat KS,
  the verdict is no promotion or a bounded rescue phase, not a weakened gate.

## Out Of Scope

- Replacing target selection.
- Replacing ball-carrier selection.
- Replacing scramble/sack/interception logic.
- Replacing passing yards, catch probability, YAC, or TD models.
- Changing dynamic blend or residual calibration.
- Adding a new external ML dependency.
