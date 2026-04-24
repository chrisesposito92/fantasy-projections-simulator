# Simulator Accuracy Hypothesis List

## State Readout

The stable simulator is already strong versus bare, but recent marginal levers are mostly at the noise floor. The clear wins have come from external priors and role/market signals: `ff_opportunity`, availability without injuries, `market_history`, dynamic source blending, and residual calibration. The flat or parked areas are mostly heuristic micro-layers: tracking slices, PFF depth/efficiency, QB split, RB scheme-fit, NGS, route-rate, team context, and goal-line concentration.

The main conclusion: stop trying broad "turn on another adjustment layer" experiments. The lightweight post-sim calibration stack has now been promoted; the next shots should either improve trusted external priors or replace high-leverage simulation decision nodes.

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

## Hypotheses

| # | Hypothesis | Why It Has Sound Logic |
|---:|---|---|
| 1 | **Learn dynamic blend weights for simulator vs `ff_opportunity` vs `market_history` by position/week/source coverage.** | **Promoted.** Post-review `rank_corr +0.0069`, weekly MAE `-0.226` overall; covered-season readout `rank_corr +0.0099`, weekly MAE `-0.338`. |
| 2 | **Add residual calibration by position, usage tier, and projection source confidence.** | **Promoted.** Decision run `rank_corr +0.0020`, weekly MAE `-0.043` overall; covered-season readout `rank_corr +0.0027`, weekly MAE `-0.068`. |
| 3 | **Backfill and expand historical market/props coverage, especially missing 2022 and richer prop markets.** | Market history is one of the few promoted marginal wins, but validation is covered-only and props coverage is absent historically. More complete market data should improve QB/WR role, TD, and volume estimates. |
| 4 | **Replace empirical pass/run choice with a learned play-call model.** | Current play calling is bucketed historical rate plus Vegas default adjustment. A model can learn score, time, down, distance, team, opponent, spread, total, and QB context interactions directly. |
| 5 | **Replace receiver selection with a learned target-share/candidate model.** | WR accuracy is a priority, and current receiver choice is mostly normalized historical target share plus red-zone/game-script tweaks. A candidate model can combine depth chart, recent usage, routes, market, defense, and game state. |
| 6 | **Split passing yards into learned air-yards, catch probability, and YAC nodes.** | Current completed-pass yards use a player receiving-yards distribution plus a fixed boost. Decomposing the pass chain should better capture QB/receiver/defense context and improve both QB and WR rankings. |
| 7 | **Build a QB rushing model for scramble probability, designed-run selection, and rush-gain tail behavior.** | QB weekly rank correlation remains a key gap, and current scramble logic is a global QB rate checked before sack/INT. Mobile QB fantasy value is high-leverage and context-dependent. |
| 8 | **Build a learned RB/ball-carrier selection model for designed runs.** | RB usage is sensitive to injuries, depth chart shifts, game script, and committees. Current carry selection uses historical carry shares normalized onto current rosters, which can lag role changes. |
| 9 | **Replace fixed red-zone TD gates with a learned TD conversion model.** | TDs dominate fantasy error. Current gates are static tables plus player TD tendency factors; prior goal-line concentration hurt rank ordering, which suggests the concept matters but the heuristic is too blunt. |
| 10 | **Rework injury/availability as a hard-actives plus role-impact model, not a broad injury-status toggle.** | Availability without injuries won; injuries are still off. A stricter model using confirmed inactives/IR plus teammate role redistribution could capture real weekly role shocks without noisy questionable-status penalties. |

## Prioritization

Recommended scoring scale:

- **Expected lift:** 5 = likely material marginal lift; 1 = likely noise-floor lift.
- **Implementation cost:** 5 = cheapest; 1 = largest build.
- **Data availability:** 5 = current local data is enough; 1 = missing/paid/manual data dependency.
- **Validation clarity:** 5 = clean `baseline=defaults` A/B with low attribution ambiguity; 1 = hard to isolate.

| Priority | Hypothesis | Expected Lift | Cost | Data | Validation Clarity | Score | Recommended Use |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | **Replace receiver selection with a learned target model** | 5 | 2 | 4 | 4 | 15 | First major in-sim learned node. High WR upside, clean runtime boundary, and strong tie to the biggest accuracy priority. |
| 2 | **Replace empirical pass/run choice with a learned play-call model** | 4 | 3 | 4 | 4 | 15 | Strong simulator-wide leverage with a clean decision point, but effects will be broader and need careful sanity checks on team play volume. |
| 3 | **Backfill and expand market/props coverage** | 5 | 2 | 2 | 3 | 12 | High upside, but data acquisition and historical coverage are the blocker. Best run as a data-readiness phase before modeling. |
| 4 | **Split passing yards into air yards, catch probability, and YAC** | 5 | 1 | 4 | 3 | 13 | Very high QB/WR upside, but this is a larger multi-node pass-chain project. Do after target/play-call boundaries are established. |
| 5 | **Build a QB rushing model** | 4 | 2 | 4 | 4 | 14 | Good QB-specific upside and a clean pain point, but scope should be split into scramble probability first, then designed runs/gain tails. |
| 6 | **Build learned ball-carrier selection for designed runs** | 3 | 2 | 4 | 4 | 13 | Useful RB role-drift work, but likely lower top-line lift than target selection or QB rushing. |
| 7 | **Rework injury/availability role impact** | 4 | 2 | 3 | 3 | 12 | Valuable if hard inactive/depth evidence is reliable, but avoid reviving noisy questionable-status logic. |
| 8 | **Replace fixed red-zone TD gates** | 4 | 2 | 4 | 3 | 13 | TDs are high leverage, but prior goal-line concentration hurt rank ordering, so this needs a narrow learned conversion design. |
| done | **Learn dynamic blend weights** | 5 | 4 | 4 | 5 | 18 | Promoted; keep as part of defaults and use as the source stack for future residual/model tests. |
| done | **Add residual calibration** | 4 | 4 | 5 | 5 | 18 | Promoted; monitor TE rank-corr sensitivity in future decision runs. |

Recommended execution order:

1. **Learned target selection**: first major learned in-simulation node because WR accuracy is a priority and the hook is localized.
2. **Learned play-call model**: broad engine leverage after target selection proves the learned-node workflow.
3. **Market/props backfill**: run once the exact missing data and historical coverage path is defined.
4. **Passing-chain decomposition**: high-upside QB/WR work after target/play-call boundaries are established.
5. **QB rushing model**: clean QB-specific pain point; split scramble probability from designed-run and gain-tail work.

Planning recommendation:

- Use one dedicated planning session per top-five hypothesis before implementation.
- Keep each plan decision-complete: data inputs, runtime interface, feature boundaries, validation command, and promotion gate.
- Do not bundle hypotheses in one validation run. Every implementation should earn promotion against `baseline=defaults` on its own.
- Use lighter spike-style planning only for dynamic blend weights and residual calibration; use full design planning for learned in-sim nodes.

## Validation Defaults

Use `baseline=defaults` for every hypothesis unless testing total lift. Primary acceptance should be marginal `rank_corr` and `weekly_mae`, with QB/WR as tie-breakers. Treat market-history results as covered-only until 2022 is backfilled. Keep parked heuristic layers off unless a redesigned version beats defaults in isolation.
