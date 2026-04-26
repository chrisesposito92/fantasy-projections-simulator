# Fantasy Projections Simulator — Distribution Calibration

## What This Is

NFL fantasy football play-by-play simulator that produces Monte Carlo projections for QB / RB / WR / TE / DST / K. Mature codebase with 1,200+ tests, an 8-engine PFF intelligence layer, Vegas (ITT pace, spread pass-rate, props), weather, and a post-sim ensemble (`role_trend → dynamic_blend → residual_calibration`). Built for and used by Chris (the user) to drive his fantasy decisions.

This `PROJECT.md` formalizes the **next initiative**: closing the distribution-shape gap that survives our promoted defaults despite strong rank/mean accuracy.

## Core Value

**Distribution shape (KS) on stat outputs that matters for season-long projections — without giving back the rank_corr / MAE wins we already shipped.**

If a single change improves KS by N points but regresses rank_corr by >0.005 or MAE by >0.05, it does not ship. KS gain *under that floor* is the ranking signal.

## Requirements

### Validated

<!-- Inferred from existing code via .planning/codebase/ map; locked. -->

- ✓ **Play-by-play simulation engine** with empirical distributions, GameStateBucket lookups, RZ TD gates, scramble/sack/INT/fumble resolution — `src/engine/`
- ✓ **Monte Carlo runner** producing per-player stat distributions across N sims — `src/engine/runner.py`
- ✓ **PFF intelligence layer** (TierEngine, MatchupEngine, TeamContextEngine, RbSchemeFitEngine*, QbSplitEngine*, CoverageEngine, KickerEngine, DstBaselineEngine) — `src/data/pff/` (* = off-by-default)
- ✓ **Vegas engine** (ITT pace VEG-01, spread pass-rate VEG-02, player props VEG-03) — `src/data/vegas/`
- ✓ **Weather engine** (wind/temp/precipitation, Open-Meteo) — `src/data/weather/`
- ✓ **Post-sim ensemble** (`role_trend → dynamic_blend → residual_calibration`) producing fpts adjustments only — `src/scoring/projection.py`, `src/scoring/calibration/`
- ✓ **A/B validation harness** with persistent ledger, KS distribution diagnostics, hold-out backtesting — `src/validation/`, `scripts/validate.py`
- ✓ **Strong rank_corr and MAE accuracy** at promoted defaults across 2022-2024 (avg rank_corr delta +0.205, weekly_mae delta -1.47, season_mae delta -20.0)

### Active

<!-- Outcome targets (TGT-XX) for this initiative. The 25 in-scope hypotheses live in REQUIREMENTS.md (KS-01..KS-21, KS-29, KS-32, traced back to HYPOTHESES.md). -->

- [ ] **TGT-01**: QB `pass_yards` KS reduced from ~0.36 to ≤ 0.20 across 2022-2024
- [ ] **TGT-02**: WR `receiving_yards` KS reduced from ~0.26 to ≤ 0.20 across 2022-2024
- [ ] **TGT-03**: WR `receptions` KS reduced from ~0.28 to ≤ 0.22
- [ ] **TGT-04**: TE `receptions` KS reduced from ~0.35 to ≤ 0.27 (largest defaults-vs-bare regression; target relaxed from ≤0.25 after sanity-check flagged budget as tightest)
- [ ] **TGT-05**: TE `receiving_yards` KS reduced from ~0.31 to ≤ 0.25
- [ ] **TGT-06**: RB `rush_yards` KS reduced from ~0.26 to ≤ 0.22 (defaults currently regresses vs bare)
- [ ] **TGT-07**: RB `receiving_yards` KS reduced from ~0.42 to ≤ 0.34 (target relaxed from ≤0.30 after sanity-check flagged largest gap with least-direct levers)
- [ ] **TGT-08**: Aggregate `fpts` KS held ≤ 0.18 across all positions (currently 0.15-0.25)
- [ ] **TGT-09**: QB pass_yards mean bias closed from -28 yd/game to within ±5 yd/game
- [ ] **TGT-10**: WR receiving_yards mean bias closed from -9 yd/game to within ±2 yd/game

(Outcome targets — TGT-04 and TGT-07 relaxed after sanity-check; others held. The hypothesis backlog `.planning/research/HYPOTHESES.md` shows plausible 70-100% closure across these targets through P1-P4. **Hypothesis IDs (KS-XX) and outcome target IDs (TGT-XX) are different namespaces — don't conflate.**)

### Out of Scope

- **Adding new positions** (DST and Kicker stay as-is) — KS for those is a separate initiative
- **Re-architecting the engine** (play-by-play loop is solid) — KS issues are calibration / signal coverage, not engine bugs
- **Auction values, lineup optimization, draft tooling** — projection accuracy only
- **UI / dashboard work** — CLI output stays as-is
- **Replacing nflverse / PFF / Open-Meteo / The Odds API as data providers** — gaps will be closed by adding signals from existing providers, not switching providers
- **P5 long-tail signal integration** (KS-22..KS-33 in HYPOTHESES.md) — deferred to a follow-up initiative. Includes the per-zone QB depth engine (KS-22, 5-10 days), aDOT/time-to-throw priors (KS-23), per-target CB matchup (KS-25), and other engineering-heavy items. v1 scope is P1-P4 (25 hypotheses).

## Context

**Backtest evidence motivating this work** (PPR, 200 sims/season, defaults vs bare baseline):

| Stat | 2022 KS | 2023 KS | 2024 KS | Mean bias (proj − actual) |
|------|---------|---------|---------|---------------------------|
| QB pass_yards | 0.34 | 0.37 | 0.35 | -25 to -31 yd/game |
| WR receiving_yards | 0.25 | 0.26 | 0.28 | -9 to -10 yd/game |
| WR receptions | 0.26 | 0.26 | 0.31 | -0.4 to -0.5 |
| TE receptions | 0.38 | 0.32 | 0.34 | -0.1 to -0.3 |
| TE receiving_yards | 0.32 | 0.30 | 0.32 | -3 to -4 yd/game |
| RB rush_yards | 0.29 | 0.23 | 0.25 | within ±2 yd/game |
| RB receiving_yards | 0.44 | 0.39 | 0.43 | -0.4 to -1.6 yd/game |
| fpts | 0.25 | 0.23 | 0.15 | (varies) |

**Pattern:** KS is bad two ways — (1) **mean bias** (stats systematically projected low; QB pass_yards & WR receiving_yards worst) and (2) **distribution-shape regression where defaults make KS worse than bare** (TE receptions/yards 0.20→0.32, RB rush_yards 0.22→0.29, WR receptions 0.21→0.31). Ensemble is winning on rank/MAE but compressing or shifting variance at the stat level.

**Confirmed root causes** (from deep-dive research, full backlog in `.planning/research/HYPOTHESES.md`):
- **Bug**: `_tackled_short()` in `play_resolver.py` overwrites clamped yards with strictly shorter values when RZ TD-gate fails — accounts for ~10-15 yd/game on QB pass_yards alone (KS-01).
- **Bug**: `_apply_recv_yds` at `props_engine.py:248` multiplies per-catch dist_mean by games_played — magnitude bug shifting WR/TE/RB receiving_yards distributions DOWN (KS-05).
- **Bug**: `_apply_matchup` and `_apply_coverage` use a hardcoded 10-yd anchor instead of `np.mean(receiving_yards_dist)`, narrowing the dynamic range of receiver-yards adjustments (KS-03).
- **Structural**: `residual_calibration` and `dynamic_blend` adjust **fpts only** — stat-level distributions never get post-sim correction (KS-09). This is THE architectural blocker for stat-level KS work.
- **Structural**: `dynamic_blend` zeroes simulator weight in `weights_2024.json` (sim ≤ 0.05 for nearly every TE/WR/RB bucket), replacing fpts with the point-estimate `ff_opportunity` prior — biggest fpts compressor (KS-08).
- **Structural**: `tier_engine._merge_thin_tiers` collapses 5 TE tiers into 1-2 fat-middle pools, so the `TE|high|*` correction bucket is *empty* in calibration_2024.json (root of the TE 0.20→0.32 regression).
- **Off-by-default slices**: All 7 are dormant (not broken). `rb_scheme_fit` already shows positive rank_corr/MAE deltas in its decision artifact but was never KS-measured (KS-02). `depth_role.efficiency` is the only WR/TE-specific layer that scales `receiving_yards_dist` (KS-16).
- **Time-sensitive signal**: The Odds API has alternate-line markets that define a CDF directly — currently we only consume mean lines (KS-21).

**Recently completed work informing this initiative:**
- QB designed-run chain (just merged) — separates designed runs from scrambles; may be a piece of the QB rush distribution puzzle
- Phase 1 / 2 / 6 promoted: ff_opportunity ensemble, availability, market_history close_core8
- Phase 3 executing: PFF Phase 3 signals (snap blend +0.147 rank_corr was best; CPOE marginal; NGS/route_rate kept off)

**Time-sensitive data acquisition window:**
- The Odds API tier currently active is generous (5M credits, ~66k used; ~4.93M remaining; ~2 weeks left at this tier). KS-19, KS-20, KS-21 (alternate-line markets + props historical backfill) all require Odds API scraping. Phase ordering must front-load Odds API data collection while the high tier is active — once dropped to a lower tier next month, historical backfill would be cost-prohibitive.

## Constraints

- **Hard floor on existing wins**: No change ships if it regresses rank_corr by >0.005 or MAE by >0.05 (per A/B harness over 2022-2024)
- **Tech stack** locked: Python 3.12+, polars (NOT pandas), numpy, uv, pytest. No new ML frameworks or DSL changes — additive layers/engines only
- **Test discipline**: 1,200+ test suite must stay green; new features need tests (TDD preferred)
- **Validation discipline**: Every promotion change goes through `scripts/validate.py` A/B with persistent ledger; both isolation (`baseline+X`) and full-stack (`all_engines+X`) modes
- **Data sources**: nflverse + PFF (premium subscription, locally scraped) + The Odds API + Open-Meteo. Open to adding free data; new paid sources need explicit justification
- **Manual A/B execution**: User runs A/B validation scripts; agents propose and implement changes but do not run validation runs
- **PFF blending discipline**: PFF layers must NOT blend `carry_share`, `scramble_rate`, or yards for QBs (calibration foot-gun from prior work)
- **GSD workflow enforcement**: All edits go through GSD commands (`/gsd-quick`, `/gsd-debug`, `/gsd-execute-phase`)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Treat KS as the priority metric for this initiative | Rank/MAE wins are large but season-long stat distributions are visibly off, hurting confidence | — Pending |
| Hard floor of -0.005 rank_corr / -0.05 MAE for any KS-targeting change | Don't trade a real, shipped capability for a still-hypothetical KS win | — Pending |
| All four positions in scope (QB, RB, WR, TE) | TE has the largest defaults-vs-bare regression; ignoring it leaves the ensemble distorting variance for that position | — Pending |
| Discarded prior 1,500-line KS roadmap (commit 103b711) | Was outdated; ground research in current code state and current backtest, not a frozen plan | — Pending |
| Brownfield mapping refreshed before scoping | All 7 docs in `.planning/codebase/` regenerated 2026-04-26 to anchor research | ✓ Good |
| v1 scope = P1-P4 (25 hypotheses); P5 deferred | P5 long-tail items are mostly 5-10 day engineering with most-uncertain payoff. Cleaner v1 boundary; P5 items become follow-up initiative if results warrant | — Pending |
| TE receptions and RB receiving_yards targets relaxed | Sanity check flagged both as borderline against the structural-fix budget. Avoids initiative being declared partial-fail on these two single metrics | — Pending |
| Front-load Odds API scraping while high tier is active | 5M-credit budget expires in ~2 weeks; historical backfill would be cost-prohibitive on a lower tier. Affects phase ordering — data acquisition for KS-19/KS-20/KS-21 happens earliest practical opportunity | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-26 after initialization*
