# Learned Receiver Target Selection Plan

## Summary

Test a learned in-simulation receiver-selection node against `baseline=defaults`. The current selector samples from normalized roster `target_share` variants, red-zone shares, and game-script rank factors. The hypothesis should improve WR/TE/RB receiving allocation because target choice is a high-leverage per-play decision and the current rule cannot learn interactions between player role, depth chart, recent usage, routes, game state, and optional market signals.

Use a conditional softmax candidate model, not a post-sim adjuster. It should replace only the probability weights used by [player_selector.py](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/engine/player_selector.py), while leaving play calling, sacks, INTs, catch probability, yards, TD gates, scoring, dynamic blend, and residual calibration unchanged.

## Key Changes

- Add a disabled-by-default `target_selection` config with `enabled=false`, `artifacts_dir=null`, candidate positions `RB/WR/TE/FB`, probability floor, and artifact schema version. Invalid or missing artifacts always fall back to legacy receiver selection.
- Add a runtime `TargetSelectionContext` attached during [GameContextBuilder.build_game()](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/src/fantasy_sim/data/game_context.py) after all default roster adjustments are applied. It precomputes per-player static features once per game.
- Extend the pass path so `simulate_game -> resolve_play -> select_receiver` passes the target-selection context. If disabled, missing, invalid, or empty, use the existing selector exactly.
- Fit one JSON artifact per test season with a conditional multinomial logit/softmax model implemented with `numpy`/`scipy`, avoiding new ML dependencies.
- Score each candidate as `log(legacy_weight + eps) + learned_feature_delta`, then softmax over the same eligible pool legacy uses. This preserves the current selector as the anchor while letting the model learn corrections.

## Data Boundary

- Training labels: historical PBP target events where `play_type/pass_attempt` indicates a pass and `receiver_player_id` is present; exclude sacks, spikes, kneels, and no-play rows where available.
- Training window: for each test season, fit only from `target_season - training_years` through `target_season - 1`. With `--training-years 4`, 2022 can train from 2018-2021, so this model can have full 2022-2024 artifact coverage.
- Runtime inputs only: current built roster, current `GameState`, week/season, cached PBP/rosters/snap/depth/PFF files, optional market-history rows. No actuals and no current-week future data.
- Required available inputs: PBP, rosters, snap counts, depth charts, PFF receiving summary/depth, and current default roster features are locally available for the validation window. Market history is optional and currently covered for 2023-2024 only, so missing-market features must be neutral.
- Core features: legacy band weight, target-share variants, position, target rank, snap share, air-yards share, catch rate, receiving-yards mean, games played, rolling prior-week target/route/snap shares, depth-chart rank, red-zone/goal-line/third-down/trailing-late interactions, and optional market reception/receiving-yard/TD indicators.

## Validation

Smoke:

```bash
uv run python scripts/fit_target_selection.py --test-seasons 2022 2023 2024 --training-years 4 --scoring ppr --output-dir results/target_selection/smoke_v1
uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 50 --set target_selection.enabled=true --set target_selection.artifacts_dir=results/target_selection/smoke_v1 --label target-selection-s50
```

Decision:

```bash
uv run python scripts/fit_target_selection.py --test-seasons 2022 2023 2024 --training-years 4 --scoring ppr --output-dir results/target_selection/decision_v1
uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 200 --set target_selection.enabled=true --set target_selection.artifacts_dir=results/target_selection/decision_v1 --label target-selection-s200
```

Promotion gate at `sims=200`:

- all-season average rank-corr delta `>= +0.004`
- all-season weekly MAE delta `<= -0.015`
- WR weekly rank-corr delta `>= +0.006`
- WR weekly MAE non-worse by more than `+0.010`
- QB+WR combined weekly rank-corr positive and QB+WR weekly MAE non-worse
- no position regresses weekly rank-corr by more than `-0.004` or weekly MAE by more than `+0.030`
- WR receptions and receiving-yards KS must improve or regress by less than `+0.010`

Focused tests should cover config loading, artifact fallback, candidate feature construction, no-leakage week filters, deterministic selection with fixed RNG, legacy parity when disabled, and validation override wiring.

## Risks And Fallbacks

- Main risk is overfitting target allocation and hurting MAE after the promoted post-sim stack. Keep v1 coarse, global, and anchored to legacy weights.
- Rookies, trades, missing depth rows, missing market rows, or zero-feature candidates use neutral feature values and the legacy base weight.
- If all learned weights are invalid, NaN, zero, or leave fewer than two candidates, fall back to legacy selection for that play.
- If smoke improves WR rank but hurts distribution shape, do not proceed to promotion until the candidate model is clipped or simplified.
- Keep defaults unchanged until the decision run clears the gate; after promotion, bundle `decision_v1` artifacts and flip `target_selection.enabled=true`.
