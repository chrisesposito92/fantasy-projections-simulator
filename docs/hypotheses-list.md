# Simulator Accuracy Hypothesis List

## State Readout

The stable simulator is already strong versus bare, but recent marginal levers are mostly at the noise floor. The clear wins have come from external priors and role/market signals: `ff_opportunity`, availability without injuries, `market_history`, dynamic source blending, and residual calibration. The flat or parked areas are mostly heuristic micro-layers or narrowly scoped in-simulation replacements: tracking slices, PFF depth/efficiency, QB split, RB scheme-fit, NGS, route-rate, team context, goal-line concentration, the first learned receiver target-selection node, and the first learned play-call node.

The main conclusion: stop trying broad "turn on another adjustment layer" experiments. The lightweight post-sim calibration stack has now been promoted. Replacing high-leverage simulation decision nodes is still plausible, but the learned target-selection and learned play-call results show that these replacements need better labels/features or a larger structural change than a shallow standalone probability replacement.

## Validated Results

### Dynamic Blend Weights

Status: **PROMOTED**. The dynamic blender learned coarse convex weights for simulator, `ff_opportunity`, and `market_history` by position, week bucket, source mask, and market-confidence bucket. It runs after simulation and suppresses the fixed `market_history -> ff_opportunity` post-sim layers when enabled, avoiding double blending.

Validation used `baseline=defaults` with artifacts from `results/dynamic_blend/decision_s200`; the promoted artifacts are bundled under `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200`. `props=none`; the market input was the existing `market_history` close-core8 prior. Season 2022 had no learned artifact because the fit used `--min-source-season 2022`, so it correctly ran as fallback-only and is not counted as learned-market evidence.

| Run | Sims | Ledger | Scope | Rank Corr Delta | Weekly MAE Delta | Season MAE Delta | Verdict |
|---|---:|---:|---|---:|---:|---:|---|
| `dynamic-blend-s50` | 50 | #72 | all seasons 2022-2024 | +0.0055 | -0.233 | -2.349 | smoke pass |
| `dynamic-blend-s50` | 50 | #72 | covered seasons 2023-2024 | +0.0091 | -0.344 | -3.503 | smoke pass |
| `dynamic-blend-s200` | 200 | #73 | all seasons 2022-2024 | +0.0062 | -0.221 | -2.393 | gate pass |
| `dynamic-blend-s200` | 200 | #73 | covered seasons 2023-2024 | +0.0088 | -0.328 | -3.559 | gate pass |
| `dynamic-blend-s200-postfix` | 200 | #74 | all seasons 2022-2024 | +0.0069 | -0.226 | -2.505 | gate pass |
| `dynamic-blend-s200-postfix` | 200 | #74 | covered seasons 2023-2024 | +0.0099 | -0.338 | -3.765 | gate pass |

Post-review decision-run weekly position deltas were all positive on rank correlation and non-worse on weekly MAE: QB `+0.0102` / `-0.097`, RB `+0.0378` / `-0.406`, WR `+0.0213` / `-0.225`, TE `+0.0065` / `-0.095`. This clears the promotion gate: covered-season average rank-correlation lift is above `+0.0050`, covered weekly MAE improves by more than `-0.025`, QB+WR improve on both priority metrics, and no position regresses.

### Residual Calibration

Status: **PROMOTED**. Residual calibration is a post-sim additive correction layer that runs after the promoted projection stack. It learns small bucketed fantasy-point residual corrections by `position + usage_tier + projection_source_confidence`, then applies them to final non-detail player projection rows without altering stat columns.

Validation used `baseline=defaults` with artifacts from `results/residual_calibration/decision_s200`; the promoted artifacts are bundled under `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200`. Season 2022 has no learned artifact because the fit uses only source seasons before the test season, so it correctly runs as zero-fallback and is not counted as artifact-covered evidence.

| Run | Sims | Ledger | Scope | Rank Corr Delta | Weekly MAE Delta | Season MAE Delta | Verdict |
|---|---:|---:|---|---:|---:|---:|---|
| `residual-calibration-s50` | 50 | #75 | all seasons 2022-2024 | +0.0023 | -0.037 | -1.312 | smoke pass |
| `residual-calibration-s50` | 50 | #75 | covered seasons 2023-2024 | +0.0021 | -0.060 | -1.917 | smoke pass |
| `residual-calibration-s200` | 200 | #76 | all seasons 2022-2024 | +0.0020 | -0.043 | -1.384 | promoted |
| `residual-calibration-s200` | 200 | #76 | covered seasons 2023-2024 | +0.0027 | -0.068 | -2.066 | promoted |

Decision-run weekly position deltas were: QB `+0.0030` / `-0.019`, RB `+0.0017` / `-0.042`, WR `+0.0035` / `-0.050`, TE `-0.0043` / `-0.027`. The TE weekly-rank guardrail was borderline by `0.0003`, but the run improved covered-season MAE materially, improved covered average rank correlation, improved QB+WR rank correlation, and was accepted for promotion. The layer is now enabled by default with bundled artifacts for 2023-2024 and zero fallback for missing/invalid artifacts.

### Learned Receiver Target Selection

Status: **NO_PROMOTION**. This experiment replaced only the receiver-selection weights inside the pass-play resolver with a learned conditional softmax candidate model. The model kept the legacy selector as the anchor by scoring each eligible candidate as `log(legacy_weight + eps) + learned_feature_delta`, then sampling from the learned softmax over the same RB/WR/TE/FB candidate pool. Defaults remained unchanged, and the runtime fallback stayed legacy selection when artifacts or candidate probabilities were unavailable.

The implementation fit one artifact per test season under `results/target_selection/`. The first smoke artifacts in `smoke_v1` wrote successfully, but 2023 and 2024 hit the optimizer cap at 200 iterations. A refit with `--max-iter 500` under `smoke_v1_iter500` converged all three artifacts, so 1000 iterations were unnecessary: 2022 converged at 213 iterations on 52,878 examples, 2023 at 236 iterations on 70,255 examples, and 2024 at 241 iterations on 70,858 examples.

| Run | Sims | Ledger | Artifact Dir | Rank Corr Delta | Weekly MAE Delta | Season MAE Delta | FPTS KS Delta | Verdict |
|---|---:|---:|---|---:|---:|---:|---:|---|
| `target-selection-s50-capped` | 50 | #79 | `results/target_selection/smoke_v1` | +0.0010 | -0.005 | -0.058 | -0.001 | noisy smoke only; capped optimizer |
| `target-selection-s50-iter500` | 50 | #80 | `results/target_selection/smoke_v1_iter500` | -0.0013 | +0.000 | +0.048 | +0.001 | no promotion |

The converged run failed the smoke bar before a 200-sim decision run. Weekly position deltas were mixed: QB `+0.0024` rank corr but `+0.003` MAE, RB `-0.0034` / `+0.030`, WR `-0.0028` / `-0.002`, and TE `+0.0029` / `-0.027`. The model did not improve the intended WR rank signal, and the RB/overall rank regression was enough to stop the path.

Likely reasons it did not work:

- The model mostly learned a shallow correction to already-normalized `target_share`, so there may not have been enough independent signal left after the current usage, game-script, dynamic-blend, and residual-calibration layers.
- Training labels were raw historical targets, but runtime targets are only one step in a longer chain that also includes play calling, sacks/scrambles, catch rate, yards, TD gates, and post-sim calibration. A better target allocator can still be neutralized or inverted by downstream fantasy-point aggregation.
- The v1 feature set emphasized static roster/player features available at game build time. It did not fully model route participation, personnel packages, defensive coverage, QB read tendencies, or same-week role shocks, which are the exact interactions that make target distribution hard.
- The legacy anchor protected fallback behavior, but it also limited upside: the learned model could tilt candidate probabilities, not discover a materially different passing structure or correct under-projected receiving volume.
- Full 2022-2024 artifact coverage required source-season context construction with bounded historical lookback. That worked after clamping context seasons to 2018+, but early source seasons still had thinner feature history than later validation seasons.

The takeaway is not "learned in-sim nodes are bad"; it is that receiver selection was too narrow as a standalone v1. A future receiver/WR model should probably be coupled to passing-chain decomposition or route/air-yards/catch-probability modeling instead of only replacing the final target draw.

### Learned Play-Call Model

Status: **NO_PROMOTION**. This experiment replaced the empirical pass/run lookup at the `select_play_type()` boundary with an off-by-default temporal logistic model that predicts `P(pass)` from down, distance, yardline, quarter, clock, score, home/away, spread, total, implied team total, week, and prior team pass tendencies. When enabled and covered by a valid artifact, the learned node owns pass/run probability and skips the current Vegas spread pass-rate and game-script pass-rate modifiers for that team only. Vegas pace and all downstream target, rusher, scramble, sack, turnover, yards, TD, dynamic-blend, and residual-calibration behavior remain unchanged.

Artifacts were fitted under `results/play_call_model/smoke_v1` with prior-season labels only (`--min-source-season 2018`, `--training-years 4`). All three artifacts converged: 2022 used 136,259 examples with pass rate `0.591`, 2023 used 138,407 examples with pass rate `0.586`, and 2024 used 140,484 examples with pass rate `0.583`. Runtime and coverage validation reject missing, invalid, non-temporal, non-finite, or schema-incompatible artifacts and fall back to empirical play calling.

| Run | Sims | Artifact Dir | Rank Corr Delta | Weekly MAE Delta | Season MAE Delta | FPTS KS Delta | Verdict |
|---|---:|---|---:|---:|---:|---:|---|
| `play-call-model-s50` | 50 | `results/play_call_model/smoke_v1` | +0.0029 | -0.023 | +0.055 | n/a | borderline smoke; QB pass-yards KS concern |
| `play-call-model-s200` | 200 | `results/play_call_model/smoke_v1` | +0.0026 | -0.018 | -0.006 | -0.004 | no promotion |

The decision run missed the promotion gate: average rank-correlation lift was below `+0.0030`, weekly MAE improvement was short of `-0.025`, RB regressed, and QB passing-yards KS worsened in every tested season. Weekly position deltas were QB `+0.0084` / `-0.173`, RB `-0.0083` / `+0.087`, WR `+0.0091` / `-0.031`, and TE `+0.0111` / `-0.053`. QB pass-yards KS moved by roughly `+0.011`, `+0.018`, and `+0.019` for 2022, 2023, and 2024.

Likely reasons it did not work:

- The model improved QB, WR, and TE weekly ranking enough to show signal, but it shifted broad pass/run volume in a way that hurt RB opportunity and QB passing-yards distributions.
- The training objective predicted historical pass/run labels, not the fantasy metric after sacks, scrambles, targets, yards, TD gates, dynamic blend, and residual calibration.
- The feature set captured game state and market context but not personnel, formation, QB designed-run tendency, offensive coordinator style, or same-week role shocks.
- Replacing pass/run without also decomposing the passing chain left downstream pass-yards and receiving-yard models to absorb volume changes they were not calibrated for.

The path should stay parked as a standalone pass/run replacement. Revisit only if coupled to a richer passing-chain, QB-rushing, or play-volume calibration model.

### QB Scramble Model

Status: **NO_PROMOTION** for the v1 scramble-probability slice. The model is implemented off by default and loads temporal artifacts from `qb_rushing.scramble.artifacts_dir`. Missing, invalid, or incompatible artifacts fall back to the base QB `scramble_rate`.

Smoke artifacts were fitted under `results/qb_rushing/scramble/smoke_v1` with prior-season labels only (`--min-source-season 2018`, `--training-years 4`). All three artifacts converged: 2022 used 84,256 examples with scramble rate `0.044293581466008355`, 2023 used 84,979 examples with scramble rate `0.0456701067322515`, and 2024 used 86,088 examples with scramble rate `0.048380726698262246`.

#### No Promotion

| Run | Sims | Artifact Dir | Rank Corr Delta | Weekly MAE Delta | Season MAE Delta | FPTS KS Delta | Verdict |
|---|---:|---|---:|---:|---:|---:|---|
| `qb-scramble-model-s50` | 50 | `results/qb_rushing/scramble/smoke_v1` | -0.0009 | -0.005 | -0.067 | -0.001 | stopped before 200-sim decision run |

The 50-sim run covered `qb_rushing.scramble=full(2022,2023,2024)` but failed the smoke gate because average rank-correlation delta was negative. Weekly QB metrics improved slightly (`rank_corr +0.0037`, weekly MAE `-0.002`), but RB weekly MAE regressed by `+0.005`, RB weekly rank correlation moved `-0.0004`, and QB rushing-yards KS worsened in 2022 (`+0.02`), 2023 (`+0.01`), and 2024 (`+0.00`). Defaults remain unchanged.

## Hypotheses

| # | Status | Hypothesis | Why It Has Sound Logic |
|---:|---|---|---|
| 1 | Done | **Learn dynamic blend weights for simulator vs `ff_opportunity` vs `market_history` by position/week/source coverage.** | **Promoted.** Post-review `rank_corr +0.0069`, weekly MAE `-0.226` overall; covered-season readout `rank_corr +0.0099`, weekly MAE `-0.338`. |
| 2 | Done | **Add residual calibration by position, usage tier, and projection source confidence.** | **Promoted.** Decision run `rank_corr +0.0020`, weekly MAE `-0.043` overall; covered-season readout `rank_corr +0.0027`, weekly MAE `-0.068`. |
| 3 | Open | **Backfill and expand historical market/props coverage, especially missing 2022 and richer prop markets.** | Market history is one of the few promoted marginal wins, but validation is covered-only and props coverage is absent historically. More complete market data should improve QB/WR role, TD, and volume estimates. |
| 4 | No Promotion | **Replace empirical pass/run choice with a learned play-call model.** | **Parked after v1.** Decision run improved QB/WR/TE but missed the overall gate: rank corr `+0.0026`, weekly MAE `-0.018`, RB regressed, and QB pass-yards KS worsened in all seasons. Revisit only as part of a richer passing-chain or volume-calibration model. |
| 5 | No Promotion | **Replace receiver selection with a learned target-share/candidate model.** | **Parked after v1.** Converged smoke artifacts regressed average rank corr `-0.0013` with neutral weekly MAE, and WR weekly rank corr moved `-0.0028`. Revisit only as part of a richer passing-chain or route/air-yards model. |
| 6 | Open | **Split passing yards into learned air-yards, catch probability, and YAC nodes.** | Current completed-pass yards use a player receiving-yards distribution plus a fixed boost. Decomposing the pass chain should better capture QB/receiver/defense context and improve both QB and WR rankings. |
| 7 | Open | **Build a QB rushing model for scramble probability, designed-run selection, and rush-gain tail behavior.** | QB weekly rank correlation remains a key gap, and current scramble logic is a global QB rate checked before sack/INT. Mobile QB fantasy value is high-leverage and context-dependent. |
| 8 | Open | **Build a learned RB/ball-carrier selection model for designed runs.** | RB usage is sensitive to injuries, depth chart shifts, game script, and committees. Current carry selection uses historical carry shares normalized onto current rosters, which can lag role changes. |
| 9 | Open | **Replace fixed red-zone TD gates with a learned TD conversion model.** | TDs dominate fantasy error. Current gates are static tables plus player TD tendency factors; prior goal-line concentration hurt rank ordering, which suggests the concept matters but the heuristic is too blunt. |
| 10 | Open | **Rework injury/availability as a hard-actives plus role-impact model, not a broad injury-status toggle.** | Availability without injuries won; injuries are still off. A stricter model using confirmed inactives/IR plus teammate role redistribution could capture real weekly role shocks without noisy questionable-status penalties. |

## Prioritization

Recommended scoring scale:

- **Expected lift:** 5 = likely material marginal lift; 1 = likely noise-floor lift.
- **Implementation cost:** 5 = cheapest; 1 = largest build.
- **Data availability:** 5 = current local data is enough; 1 = missing/paid/manual data dependency.
- **Validation clarity:** 5 = clean `baseline=defaults` A/B with low attribution ambiguity; 1 = hard to isolate.

| Priority | Status | Hypothesis | Expected Lift | Cost | Data | Validation Clarity | Score | Recommended Use |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | Open | **Build a QB rushing model** | 4 | 2 | 4 | 4 | 14 | Good QB-specific upside and a clean pain point, but do not repeat standalone scramble-probability v1. Continue only with designed-run selection, rush-gain tails, or a coupled QB-rushing chain. |
| 2 | Open | **Split passing yards into air yards, catch probability, and YAC** | 5 | 1 | 4 | 3 | 13 | Very high QB/WR upside. More promising than target selection alone because it models the pass-chain pieces that turn target allocation into fantasy points. |
| 3 | Open | **Build learned ball-carrier selection for designed runs** | 3 | 2 | 4 | 4 | 13 | Useful RB role-drift work and a clean selector boundary, but likely lower top-line lift than QB rushing or passing-chain decomposition. |
| 4 | Open | **Replace fixed red-zone TD gates** | 4 | 2 | 4 | 3 | 13 | TDs are high leverage, but prior goal-line concentration hurt rank ordering, so this needs a narrow learned conversion design. |
| 5 | Open | **Backfill and expand market/props coverage** | 5 | 2 | 2 | 3 | 12 | High upside, but data acquisition and historical coverage are the blocker. Best run as a data-readiness phase before modeling. |
| 6 | Open | **Rework injury/availability role impact** | 4 | 2 | 3 | 3 | 12 | Valuable if hard inactive/depth evidence is reliable, but avoid reviving noisy questionable-status logic. |
| - | No Promotion | **Replace empirical pass/run choice with a learned play-call model** | 4 | 3 | 4 | 4 | 15 | Parked after decision run missed: rank corr `+0.0026`, weekly MAE `-0.018`, RB regression, and persistent QB pass-yards KS damage. Revisit only with richer passing-chain or volume calibration. |
| - | No Promotion | **Replace receiver selection with a learned target model** | 5 | 2 | 4 | 4 | 15 | Parked after converged smoke run missed: average rank corr `-0.0013`, weekly MAE flat, WR rank corr `-0.0028`. Revisit only with richer pass-chain features/objective. |
| - | Done | **Learn dynamic blend weights** | 5 | 4 | 4 | 5 | 18 | Promoted; keep as part of defaults and use as the source stack for future residual/model tests. |
| - | Done | **Add residual calibration** | 4 | 4 | 5 | 5 | 18 | Promoted; monitor TE rank-corr sensitivity in future decision runs. |

Recommended execution order:

1. **QB rushing model**: clean QB-specific pain point; skip standalone scramble-probability v1 and continue with designed runs, gain tails, or a coupled QB-rushing chain.
2. **Passing-chain decomposition**: high-upside QB/WR work that can revisit receiver allocation through air yards, catch probability, and YAC rather than target draw alone.
3. **Learned ball-carrier selection**: useful RB role-drift work with a localized selector boundary.
4. **Market/props backfill**: run once the exact missing data and historical coverage path is defined.

Planning recommendation:

- Use one dedicated planning session per top-five hypothesis before implementation.
- Keep each plan decision-complete: data inputs, runtime interface, feature boundaries, validation command, and promotion gate.
- Do not bundle hypotheses in one validation run. Every implementation should earn promotion against `baseline=defaults` on its own.
- Use lighter spike-style planning only for dynamic blend weights and residual calibration; use full design planning for learned in-sim nodes.

## Validation Defaults

Use `baseline=defaults` for every hypothesis unless testing total lift. Primary acceptance should be marginal `rank_corr` and `weekly_mae`, with QB/WR as tie-breakers. Treat market-history results as covered-only until 2022 is backfilled. Keep parked heuristic layers off unless a redesigned version beats defaults in isolation.
