# QB Designed-Run Chain Design

## Status

Design approved on 2026-04-25. This spec covers hypothesis #8 from
`docs/hypotheses-list.md`: "Build the remaining QB rushing chain for
designed-run selection and rush-gain tail behavior."

This design intentionally does not reuse the failed standalone
`qb_rushing.scramble` model. Scramble probability stays unchanged.

## Context

The current simulator separates QB scrambles from designed QB runs:

- Scrambles happen inside `_resolve_pass()` before sack, interception, and QB
  fumble checks. They roll against `passer.usage.scramble_rate` or an optional
  scramble context.
- Designed runs use the normal run path. A QB enters the designed-run rusher
  pool only when `carry_share >= MIN_QB_CARRY_SHARE`.
- `player_builder.py` already subtracts QB scramble carries from QB designed-run
  carry share when `qb_scramble` exists, and it builds scramble-yard samples from
  scramble-only rows.

The v1 learned scramble-probability slice failed smoke validation. It barely
moved QB fantasy metrics, regressed RB metrics, and did not improve QB
rushing-yards KS. The next QB rushing hypothesis should therefore model the
remaining chain: designed-run selection and QB designed-run gain tails.

## Goal

Add an off-by-default `qb_rushing.designed_runs` layer that can improve mobile-QB
fantasy projection quality by changing only two behaviors:

- the selected QB's weight inside the existing designed-run rusher pool
- the yard sample used after a QB is selected on a designed run

The layer should not change play volume, pass/run play selection, receiver
selection, RB rushing-yard sampling, or scramble probability.

## Runtime Boundary

The runtime boundary is deliberately narrow:

1. `select_play_type()` remains unchanged.
2. Pass-play scramble checks remain unchanged.
3. Designed run plays still enter `_resolve_run()`.
4. `select_rusher()` accepts an optional `QbDesignedRunContextProtocol`.
5. The context may adjust only QB candidate weights in the existing designed-run
   rusher pool.
6. If a QB is selected on a designed run, `_resolve_run()` may ask the same
   context for a QB-specific yard sample or yard factor.
7. Disabled, missing, invalid, or uncovered context falls back to current
   behavior.

This keeps attribution clean. The experiment changes who gets designed carries
among already eligible rushers and how QB designed-run yards are sampled. It does
not alter pass/run volume or scramble volume.

## Model Shape

The artifact should be temporal and target-season-specific:

```text
qb_designed_run_model_<season>.json
```

Each target-season artifact may use only seasons before the target season,
bounded by configured source-season and training-window settings. Same-season,
future-week, and same-game data must not enter runtime priors.

The artifact should contain two coupled components.

### Selector Component

The selector component should produce a bounded multiplier on the QB's existing
designed-run carry weight. It should not replace the full RB/QB rusher selector.

Suggested runtime formula:

```python
effective_qb_weight = legacy_qb_weight * qb_designed_run_factor
```

The factor should be clamped, for example to `[0.50, 2.00]`. Non-QB candidates
keep their existing weights. After the QB adjustment, all candidate weights are
renormalized by the existing selector path.

The context should not create QB designed-run eligibility. If the QB is not in
the current rusher pool, current fallback behavior remains unchanged.

### Tail Component

The tail component should apply only after a QB is selected on a designed run.
It should sample from QB designed-run yard metadata when the artifact has enough
coverage, otherwise it should fall back to the player's existing
`rushing_yards_dist` and then the current team run-yard fallback.

The tail component should use designed QB rush rows only. It must exclude
scrambles through `qb_scramble` when that field is available.

Suggested tail buckets:

- mobility tier
- red-zone flag
- short-yardage flag
- game-script bucket: trailing, neutral, leading

Each bucket needs a minimum sample threshold. Sparse buckets fall back to broader
QB-designed-run buckets before falling back to the current player distribution.
The tail path should not globally inflate yards.

## Features And Labels

Primary training source: nflverse PBP.

Selector labels should be built from designed run plays. Use roster/player
position to identify QB rushers, not pass-play fields, because designed run rows
do not reliably expose a passer:

- positive: selected rusher is a QB and the play is not a scramble
- negative: selected rusher is not the QB on a designed run
- excluded: scrambles, kneels, spikes, aborted/no-play rows, rows without a valid
  offense or rusher

Useful selector features:

- down, distance, yardline, red-zone flag, goal-to-go flag
- quarter, clock, two-minute flag
- score differential and leading/trailing flags
- home/away
- spread, total, and implied team total when available
- week bucket
- QB prior designed-run share
- team prior designed-QB-run rate
- opponent prior designed-QB-rush allowed rate
- QB mobility tier

Mobility tier should be derived from prior designed-run share and base scramble
rate using source seasons only. The exact cutoffs can be implementation details,
but the artifact must record them so validation can reproduce the tier assignment.

Tail data should use QB designed rush yards only. Tail metadata should include
sample counts and fallback lineage so validation can explain which bucket served
each runtime context.

## Implementation Shape

Extend the existing `src/fantasy_sim/data/qb_rushing/` package instead of adding
a parallel package.

Expected additions:

- `QbDesignedRunModelConfig` under `qb_rushing.designed_runs`
- `QbDesignedRunContext` in `data/qb_rushing/models.py`
- `QbDesignedRunModel` runtime loader in `data/qb_rushing/runtime.py`
- training helpers for temporal examples and tail buckets
- `scripts/fit_qb_designed_run_model.py`
- `QbDesignedRunContextProtocol` in `engine/types.py`
- optional context threading through `GameContextBuilder`, `TeamDistributions`,
  `simulate_game()`, `resolve_play()`, `_resolve_run()`, and `select_rusher()`
- validation coverage reporting for `qb_rushing.designed_runs`

Config should default off:

```yaml
qb_rushing:
  designed_runs:
    enabled: false
    artifacts_dir: null
    factor_clamp: [0.50, 2.00]
    min_examples: 500
    min_tail_samples: 20
```

Exact defaults may change during implementation if tests or fixture data show a
better narrow guardrail, but the feature must remain off by default.

## Runtime Fallbacks

The layer must fail safe:

- disabled config: current behavior
- missing artifact: current behavior
- invalid schema, model type, target season, feature list, coefficients, clamps,
  diagnostics, or tail metadata: current behavior
- unsafe source seasons: current behavior
- insufficient examples: current behavior
- non-finite selector factor or yard factor: current behavior
- no eligible QB in rusher pool: current behavior
- sparse tail bucket: broader QB tail bucket, then player `rushing_yards_dist`,
  then existing team run distribution

## Test Coverage

Tests should define the contract before validation runs:

- config parsing: default disabled, enabled override, clamp validation, minimum
  example validation
- training examples: scrambles excluded, temporal source seasons enforced, empty
  examples fail clearly
- artifact loading: missing file fallback, invalid schema fallback, unsupported
  model type fallback, unsafe source-season fallback, bad diagnostics fallback
- selector features: stable values for down, distance, yardline, clock, score,
  home/away, market fields, priors, and mobility tier
- selector behavior: QB factor changes only eligible QB weight, respects clamps,
  preserves current fallback behavior, and leaves non-QB weights otherwise intact
- run resolver behavior: QB tail path applies only to selected QB designed runs,
  never RBs and never scrambles
- game-context integration: context attaches only when enabled and a valid target
  artifact exists
- regression: disabled layer is identical to current behavior under seeded tests

## Validation Plan

Validate marginal lift against current defaults, because defaults already include
dynamic blend and residual calibration.

Fit smoke artifacts:

```bash
uv run python scripts/fit_qb_designed_run_model.py \
  --test-seasons 2022 2023 2024 \
  --min-source-season 2018 \
  --training-years 4 \
  --output-dir results/qb_rushing/designed_runs/smoke_v1
```

Run smoke validation:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 50 \
  --set qb_rushing.designed_runs.enabled=true \
  --set qb_rushing.designed_runs.artifacts_dir=results/qb_rushing/designed_runs/smoke_v1 \
  --label qb-designed-run-chain-s50
```

If smoke clears, run the decision validation:

```bash
uv run python scripts/validate.py \
  --baseline defaults \
  --sims 200 \
  --set qb_rushing.designed_runs.enabled=true \
  --set qb_rushing.designed_runs.artifacts_dir=results/qb_rushing/designed_runs/smoke_v1 \
  --label qb-designed-run-chain-s200
```

Primary promotion gate is QB-first with guardrails:

- QB weekly rank correlation improves.
- QB weekly MAE improves.
- Average rank correlation is non-worse.
- Weekly MAE is non-worse.
- RB weekly rank correlation and MAE do not materially regress.
- QB rushing-yards KS is non-worse.
- Simulated QB designed attempts and rushing yards remain plausible by mobility
  tier.

Useful diagnostics:

- QB designed attempts by player and team versus defaults
- QB rushing yards and fantasy points by mobility tier
- QB tail-bucket coverage and fallback rates
- RB designed attempts and fantasy points versus defaults
- factor distribution by game state and mobility tier
- artifact coverage by season in validation output

## Risks

- The model may predict designed QB runs better without improving fantasy
  projection metrics after post-sim calibration.
- Too-wide factors can steal realistic RB volume and fail the RB guardrail.
- Too-aggressive tail sampling can improve QB ceiling while worsening rushing-yard
  KS.
- Historical QB designed-run labels depend on `qb_scramble` quality. Bad labels
  can blur designed runs and scrambles.
- Small mobile-QB samples can overfit. Tail buckets must use explicit sample
  thresholds and conservative fallbacks.

## Non-Goals

- Do not enable or change `qb_rushing.scramble`.
- Do not replace `select_play_type()`.
- Do not replace the full rusher selector.
- Do not adjust RB yard distributions.
- Do not promote by default without a passing validation run.
