# Residual Calibration Plan

## Summary

Add a disabled-by-default post-simulation residual calibration layer that runs after the current promoted projection stack, including dynamic blend. It learns small additive fantasy-point corrections from historical residuals grouped by `position + usage_tier + projection_source_confidence`.

Why it should help: [results/ab_ledger.json](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/results/ab_ledger.json) shows dynamic blend improved the stack materially, but it can still leave systematic over/under-shoots by position and player tier. A bucketed median residual correction directly targets weekly MAE while leaving simulation mechanics, priors, market ingestion, and source blending unchanged.

## Runtime And Data Boundary

- Runtime boundary: final non-detail player projection rows only, after `role_trend`, `dynamic_blend` or fixed `market_history -> ff_opportunity`, and before final sorting/ranking.
- Do not touch `GameContextBuilder`, play calling, play resolution, roster/player model building, PFF/weather/Vegas engines, market-history ingestion, or actual-stat scoring.
- Runtime inputs: projection row `fpts`, `position`, existing post-sim source metadata, and a season-specific artifact JSON. Actuals are fitter-only and never available at runtime.
- Current data is sufficient: nflverse weekly actuals exist for 2022-2024, FF Opportunity cache exists for 2022-2024, promoted dynamic-blend artifacts exist for 2023-2024, and market-history `close_core8` exists for 2023-2024 only. 2022 must run as no-artifact fallback.

## Implementation Changes

- Add `ensemble.residual_calibration` config in [config/defaults.yaml](/Users/chrisesposito/Documents/github/fantasy-projections-simulator/config/defaults.yaml), default `enabled=false`, with `artifacts_dir=null`, positions `QB/RB/WR/TE`, `min_bucket_rows=200`, `min_bucket_weeks=6`, `shrinkage_prior_rows=200`, `max_abs_adjustment=1.5`, `min_training_mae_delta=-0.01`, and `fallback=zero`.
- Usage tiers are fixed from pre-calibration projected `fpts`: QB high `>=18`, mid `>=12`; RB high `>=14`, mid `>=7`; WR high `>=12`, mid `>=6`; TE high `>=9`, mid `>=4`; otherwise low.
- Source-confidence buckets: `market_high`, `market_medium`, `market_low` from market confidence thresholds `>=0.85`, `>=0.50`, `<0.50`; `external_no_market` when FF Opportunity is present without market; `simulator_only` otherwise.
- Add a scoring adjuster, likely `src/fantasy_sim/scoring/residual_calibration.py`, that loads `calibration_<season>.json`, applies the bucket correction to `fpts`, clamps final `fpts >= 0.0`, stamps metadata, and re-ranks. It does not alter stat columns.
- Update `apply_projection_layers()` so residual calibration runs after dynamic blend instead of returning immediately after dynamic blend. Wire the adjuster through CLI, `scripts/validate.py`, and `Backtester` the same way dynamic blend is wired.
- Add `scripts/fit_residual_calibration.py`. It runs the current defaults stack with residual calibration suppressed, collects final pre-calibration player-week projections, joins actual weekly fantasy points, computes residual `actual_fpts - projected_fpts`, and writes one artifact per test season using only source seasons `< test_season`.
- Fitting rule: for each bucket, use shrunken median residual: `correction = clamp(median_residual * n/(n + shrinkage_prior_rows), +/-max_abs_adjustment)`. Store bucket only when row/week minimums pass and corrected training MAE beats uncorrected MAE by at least `0.01`.

## Validation Plan

Smoke:

```bash
uv run python scripts/fit_residual_calibration.py --test-seasons 2022 2023 2024 --min-source-season 2022 --sims 50 --training-years 4 --scoring ppr --output-dir results/residual_calibration/smoke_s50
uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 50 --set ensemble.residual_calibration.enabled=true --set ensemble.residual_calibration.artifacts_dir=results/residual_calibration/smoke_s50 --label residual-calibration-s50
```

Decision:

```bash
uv run python scripts/fit_residual_calibration.py --test-seasons 2022 2023 2024 --min-source-season 2022 --sims 200 --training-years 4 --scoring ppr --output-dir results/residual_calibration/decision_s200
uv run python scripts/validate.py --baseline defaults --seasons 2022 2023 2024 --sims 200 --set ensemble.residual_calibration.enabled=true --set ensemble.residual_calibration.artifacts_dir=results/residual_calibration/decision_s200 --label residual-calibration-s200
```

Promotion gate at `sims=200`: artifact-covered seasons 2023-2024 must average `weekly_mae_delta <= -0.025`; all-season weekly MAE must improve; covered average rank-corr delta must be no worse than `-0.0015`; QB+WR combined rank-corr delta must be no worse than `-0.001`; no position may regress weekly MAE by more than `+0.030` or rank corr by more than `-0.004`.

## Tests And Risks

- Required tests: config loading/override propagation, tier and source-confidence classification, artifact schema/scoring mismatch fallback, sparse/no-lift bucket fallback, shrunken median correction/clamping, projection-layer ordering after dynamic blend, validation/CLI wiring.
- Focused regression command: `uv run pytest tests/test_data/test_ensemble/test_config.py tests/test_scoring/test_dynamic_blend.py tests/test_scoring/test_market_history.py tests/test_validation/test_config.py tests/test_validation/test_validate_script.py -v`, plus new residual-calibration tests.
- Main risks: overfitting small buckets, improving MAE while harming rank ordering, and fpts/stat inconsistency. The coarse buckets, zero fallback, correction clamp, and rank-corr gate are the guardrails.
- Promotion default: keep disabled until the decision run passes. If promoted, bundle `decision_s200` artifacts under the package artifact tree and enable the config by default.
