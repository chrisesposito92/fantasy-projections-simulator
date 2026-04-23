# Simulator Accuracy Hypothesis List

## State Readout

The stable simulator is already strong versus bare, but recent marginal levers are mostly at the noise floor. The clear wins have come from external priors and role/market signals: `ff_opportunity`, availability without injuries, and `market_history`. The flat or parked areas are mostly heuristic micro-layers: tracking slices, PFF depth/efficiency, QB split, RB scheme-fit, NGS, route-rate, team context, and goal-line concentration.

The main conclusion: stop trying broad “turn on another adjustment layer” experiments. The next 7-10 shots should either improve trusted external priors or replace high-leverage simulation decision nodes.

## Hypotheses

| # | Hypothesis | Why It Has Sound Logic |
|---:|---|---|
| 1 | **Learn dynamic blend weights for simulator vs `ff_opportunity` vs `market_history` by position/week/source coverage.** | Fixed blend weights already produced the biggest modern lift, so learned or backtested weights should be a high-probability incremental win without changing football logic. |
| 2 | **Backfill and expand historical market/props coverage, especially missing 2022 and richer prop markets.** | Market history is one of the few promoted marginal wins, but validation is covered-only and props coverage is absent historically. More complete market data should improve QB/WR role, TD, and volume estimates. |
| 3 | **Replace empirical pass/run choice with a learned play-call model.** | Current play calling is bucketed historical rate plus Vegas default adjustment. A model can learn score, time, down, distance, team, opponent, spread, total, and QB context interactions directly. |
| 4 | **Replace receiver selection with a learned target-share/candidate model.** | WR accuracy is a priority, and current receiver choice is mostly normalized historical target share plus red-zone/game-script tweaks. A candidate model can combine depth chart, recent usage, routes, market, defense, and game state. |
| 5 | **Split passing yards into learned air-yards, catch probability, and YAC nodes.** | Current completed-pass yards use a player receiving-yards distribution plus a fixed boost. Decomposing the pass chain should better capture QB/receiver/defense context and improve both QB and WR rankings. |
| 6 | **Build a QB rushing model for scramble probability, designed-run selection, and rush-gain tail behavior.** | QB weekly rank correlation remains a key gap, and current scramble logic is a global QB rate checked before sack/INT. Mobile QB fantasy value is high-leverage and context-dependent. |
| 7 | **Build a learned RB/ball-carrier selection model for designed runs.** | RB usage is sensitive to injuries, depth chart shifts, game script, and committees. Current carry selection uses historical carry shares normalized onto current rosters, which can lag role changes. |
| 8 | **Replace fixed red-zone TD gates with a learned TD conversion model.** | TDs dominate fantasy error. Current gates are static tables plus player TD tendency factors; prior goal-line concentration hurt rank ordering, which suggests the concept matters but the heuristic is too blunt. |
| 9 | **Rework injury/availability as a hard-actives plus role-impact model, not a broad injury-status toggle.** | Availability without injuries won; injuries are still off. A stricter model using confirmed inactives/IR plus teammate role redistribution could capture real weekly role shocks without noisy questionable-status penalties. |
| 10 | **Add residual calibration by position, usage tier, and projection source confidence.** | The current stack blends several strong priors but likely has systematic over/under-shoots by position and player tier. A lightweight calibration layer can improve MAE while leaving simulation mechanics intact. |

## Prioritization

Recommended scoring scale:

- **Expected lift:** 5 = likely material marginal lift; 1 = likely noise-floor lift.
- **Implementation cost:** 5 = cheapest; 1 = largest build.
- **Data availability:** 5 = current local data is enough; 1 = missing/paid/manual data dependency.
- **Validation clarity:** 5 = clean `baseline=defaults` A/B with low attribution ambiguity; 1 = hard to isolate.

| Priority | Hypothesis | Expected Lift | Cost | Data | Validation Clarity | Score | Recommended Use |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | **Learn dynamic blend weights** | 5 | 4 | 4 | 5 | 18 | Start here. It builds on the two strongest proven layers, `ff_opportunity` and `market_history`, without changing simulation mechanics. |
| 2 | **Add residual calibration** | 4 | 4 | 5 | 5 | 18 | Pair closely after dynamic blends. This is low-risk MAE work that can expose systematic bias by position and usage tier. |
| 3 | **Replace receiver selection with a learned target model** | 5 | 2 | 4 | 4 | 15 | First major in-sim learned node. High WR upside, clean runtime boundary, and strong tie to the biggest accuracy priority. |
| 4 | **Replace empirical pass/run choice with a learned play-call model** | 4 | 3 | 4 | 4 | 15 | Strong simulator-wide leverage with a clean decision point, but effects will be broader and need careful sanity checks on team play volume. |
| 5 | **Backfill and expand market/props coverage** | 5 | 2 | 2 | 3 | 12 | High upside, but data acquisition and historical coverage are the blocker. Best run as a data-readiness phase before modeling. |
| 6 | **Split passing yards into air yards, catch probability, and YAC** | 5 | 1 | 4 | 3 | 13 | Very high QB/WR upside, but this is a larger multi-node pass-chain project. Do after target/play-call boundaries are established. |
| 7 | **Build a QB rushing model** | 4 | 2 | 4 | 4 | 14 | Good QB-specific upside and a clean pain point, but scope should be split into scramble probability first, then designed runs/gain tails. |
| 8 | **Build learned ball-carrier selection for designed runs** | 3 | 2 | 4 | 4 | 13 | Useful RB role-drift work, but likely lower top-line lift than target selection or QB rushing. |
| 9 | **Rework injury/availability role impact** | 4 | 2 | 3 | 3 | 12 | Valuable if hard inactive/depth evidence is reliable, but avoid reviving noisy questionable-status logic. |
| 10 | **Replace fixed red-zone TD gates** | 4 | 2 | 4 | 3 | 13 | TDs are high leverage, but prior goal-line concentration hurt rank ordering, so this needs a narrow learned conversion design. |

Recommended execution order:

1. **Dynamic blend weights**: highest signal-to-risk ratio; should produce a fast decision-grade readout.
2. **Residual calibration**: low-risk follow-on that can improve weekly MAE and reveal systematic bias.
3. **Learned target selection**: first major learned in-simulation node because WR accuracy is a priority and the hook is localized.
4. **Learned play-call model**: broad engine leverage after target selection proves the learned-node workflow.
5. **Market/props backfill**: run once the exact missing data and historical coverage path are defined.

Planning recommendation:

- Use one dedicated planning session per top-five hypothesis before implementation.
- Keep each plan decision-complete: data inputs, runtime interface, feature boundaries, validation command, and promotion gate.
- Do not bundle hypotheses in one validation run. Every implementation should earn promotion against `baseline=defaults` on its own.
- Use lighter spike-style planning only for dynamic blend weights and residual calibration; use full design planning for learned in-sim nodes.

## Validation Defaults

Use `baseline=defaults` for every hypothesis unless testing total lift. Primary acceptance should be marginal `rank_corr` and `weekly_mae`, with QB/WR as tie-breakers. Treat market-history results as covered-only until 2022 is backfilled. Keep parked heuristic layers off unless a redesigned version beats defaults in isolation.
