# Dynamic Blend Weights Plan

## Status

**Promoted.** The post-review decision run `dynamic-blend-s200-postfix` cleared the promotion gate and dynamic blend is now enabled by default. Bundled artifacts live under `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200`; `weights_dir: null` uses those artifacts at runtime. The accepted decision readout was all-season `rank_corr +0.0069`, weekly MAE `-0.226`, season MAE `-2.505`; covered-season readout was `rank_corr +0.0099`, weekly MAE `-0.338`, season MAE `-3.765`.

## Summary

Implement a post-simulation dynamic blender that replaces the fixed sequential `market_history -> ensemble.ff_opportunity` weights when enabled. It learns convex weights for `simulator`, `ff_opportunity`, and `market_history` by position, week bucket, and source coverage/confidence, then tests the learned blender against `baseline=defaults`.

Why this should help: the promoted priors are the strongest recent signals: `ff_opportunity` is full-covered for 2022-2024 and had the largest marginal lift, while `market_history` is positive on covered seasons 2023-2024. Fixed weights apply the same trust level to every player-week; learned weights should reduce overuse in weak/noisy cases and increase prior weight where history says it helps.

## Runtime And Data Boundary

- Runtime boundary: only non-detail post-sim projection rows, after simulation and after `role_trend` if it is ever enabled. Do not touch `GameContextBuilder`, play resolution, player model building, PFF engines, weather, Vegas, or market ingestion.
- When `ensemble.dynamic_blend.enabled=true`, `apply_projection_layers` should skip the fixed `MarketHistoryProjectionAdjuster` and fixed `FfOpportunityProjectionEnsembler`, then run one dynamic blender over the raw post-sim projection row.
- Data sources:
  - simulator source: current projection row `fpts` before fixed post-sim market/FF blending
  - FF source: normalized `ff_opportunity.total_fantasy_points_exp`, keyed by `player_id`; local cache exists for 2022-2024
  - market source: `market_history` close-core8 player-market prior computed from existing market-history logic; local processed data exists for 2023-2025, with 2022 missing
  - training target: historical actual fantasy points from nflverse player stats; never used at runtime
- Leakage rule: fitted weights for a test season may only use source seasons `< test_season`. For 2022, no learned artifact is expected and runtime falls back to current fixed-equivalent behavior.

## Implementation Changes

- Add config under [config/defaults.yaml](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/config/defaults.yaml): `ensemble.dynamic_blend.enabled=true`, `weights_dir=null`, `week_buckets=[1-4,5-12,13-18]`, `min_bucket_rows=200`, `min_bucket_weeks=6`, `grid_step=0.05`, and `fallback=fixed_defaults`.
- Add typed config/models beside the existing ensemble config. Public behavior: `load_ensemble_config()` returns `dynamic_blend` config, and CLI `--set ensemble.dynamic_blend.*=...` works through existing override parsing.
- Add a dynamic blender in scoring that:
  - builds available sources per player-week
  - maps to bucket: `position + week_bucket + source_mask + market_confidence_bucket`
  - loads the season-specific artifact from `weights_dir`
  - applies learned convex weights to final `fpts`, recomputes `rank`, and stamps metadata such as source mask, bucket, weights, and fallback reason
  - applies existing market-supported stat-column blending with the learned market component weight when market is present; FF remains fantasy-point-only
- Add a fitting script: `scripts/fit_dynamic_blend_weights.py`.
  - It generates row-level source tables by running the default simulator with fixed post-sim market/FF layers suppressed.
  - It joins actuals, FF priors, and market priors.
  - It fits small grid-searched convex weights per bucket, shrinking/falling back to current fixed-equivalent weights when bucket data is sparse or fails to beat the fixed baseline on training MAE.
  - It writes one artifact per test season under `results/dynamic_blend/<run>/weights_<season>.json`, with schema version, source seasons, sims, scoring, bucket rows, learned weights, and training deltas.
- After promotion, keep `ensemble.dynamic_blend.enabled=true` and `weights_dir=null` so runtime uses the bundled decision artifacts; leave existing `market_history` and `ff_opportunity` configs available as fallback inputs.

## Validation And Gate

Smoke run:

```bash
uv run python scripts/fit_dynamic_blend_weights.py --test-seasons 2022 2023 2024 --min-source-season 2022 --sims 50 --training-years 4 --scoring ppr --output-dir results/dynamic_blend/smoke_s50

uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 50 --set ensemble.dynamic_blend.enabled=true --set ensemble.dynamic_blend.weights_dir=results/dynamic_blend/smoke_s50 --label dynamic-blend-s50
```

Decision run:

```bash
uv run python scripts/fit_dynamic_blend_weights.py --test-seasons 2022 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir results/dynamic_blend/decision_s200

uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 200 --set ensemble.dynamic_blend.enabled=true --set ensemble.dynamic_blend.weights_dir=results/dynamic_blend/decision_s200 --label dynamic-blend-s200
```

Promotion gate at `sims=200`:

- artifact-covered seasons 2023-2024 average `rank_corr_delta >= +0.0050`
- artifact-covered seasons 2023-2024 average `weekly_mae_delta <= -0.025`
- QB+WR combined rank-corr delta is positive and QB+WR weekly MAE is non-worse
- no position has aggregate `rank_corr_delta < -0.003` or weekly MAE regression `> +0.030`
- 2022 must be reported as fallback/no-learned-artifact, not counted as learned-market evidence

Required tests:

- config loading and CLI override propagation
- source-row construction with missing FF, missing market, low confidence, and 2022 market absence
- weight fitting on small synthetic data where the known best source wins
- fallback to fixed-equivalent weights on sparse buckets and missing artifact
- validation path proves dynamic mode suppresses fixed market/FF layers and avoids double blending
- focused regression suite: `uv run pytest tests/test_data/test_ensemble/test_config.py tests/test_scoring/test_dynamic_blend.py tests/test_scoring/test_market_history.py tests/test_validation/test_config.py tests/test_validation/test_validate_script.py -v`

## Risks And Defaults

- Overfitting is the main risk. Do not learn per-player, per-team, or per-opponent weights in v1; use only coarse buckets and fixed-default fallback.
- Market history is partial. 2022 stays fallback-only; market-weight learning is mainly judged on 2024 because 2023 has only 2022 as prior training and 2022 has no market data.
- Missing or invalid artifacts must not fail normal projections. Runtime should fall back to the current fixed-equivalent blend for the available source set, then to simulator-only if no source exists.
- If validation improves MAE but hurts rank ordering, do not promote. The project priority is still rank correlation with QB/WR as tie-breakers.
