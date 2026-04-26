# Roadmap: Fantasy Projections Simulator — Distribution Calibration

## Overview

This initiative closes the distribution-shape (KS) gap that survives our current promoted defaults — without giving back the rank_corr / MAE wins already shipped. The journey runs from confirmed code-defect cleanup, through structural per-stat calibration, into Phase 5 slice retunes, and finishes with new-signal integration that needs the rest of the stack stabilized first. Phase 1 also front-loads The Odds API alternate-line scrape so the high-volume credit tier (~4.93M of 5M credits, ~2 weeks of life) is fully spent before drop-down — the engine that consumes that data lands in Phase 4 once the rest of the calibration stack is stable.

**Hard floor for every change:** rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 (per `scripts/validate.py` A/B). KS gain *under that floor* is the ranking signal.

**Granularity:** standard (5-8 phases). 5 phases used; KS-21 split across Phase 1 (scrape, time-sensitive) and Phase 4 (engine, normal dependency order).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4, 5): Planned milestone work
- Decimal phases (e.g. 2.1): Reserved for urgent insertions if discovered

- [ ] **Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape** — Confirmed code defects + cheap calibration constants + Odds API alt-line historical scrape (data only, no engine yet)
- [ ] **Phase 2: Structural Per-Stat Calibration** — Architectural changes (per-stat residual_calibration, dynamic_blend simulator-weight floor, tier_engine reliability, share normalization, ff_opportunity width, thin-bucket shrinkage, clamping fix)
- [ ] **Phase 3: Phase 5 Slice Activation (KS-Priority Retune)** — Retune off-by-default PFF slices (rb_scheme_fit, depth_role.efficiency, qb_split, designed-run/rb_efficiency re-measurement) under KS-priority validation
- [ ] **Phase 4: New Signal Integration (Including Odds API Engine)** — Integrate `last_ten_json` empirical CDF, PFF `projections_json` cross-stat consistency, and Odds API alt-line CDF engine (consumes Phase 1 scrape)
- [ ] **Phase 5: Initiative Wrap-up & Outcome Validation** — Final aggregate A/B against 2022-2024, outcome-target verification (TGT-01..TGT-10), update PROJECT.md / AGENTS.md / `docs/`

## Phase Details

### Phase 1: Bug Fixes, Cheap Calibration & Time-Sensitive Scrape
**Goal**: Ship confirmed code-defect fixes (theme A) and cheap calibration retunes (theme E) that have isolated low-risk mechanisms; in parallel, complete The Odds API alternate-line scrape for 2022-2024 weeks 1-18 while the high-credit tier is still active so the engine consumption in Phase 4 has data to consume.
**Depends on**: Nothing (first phase)
**Requirements**: KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32

(Note: The Odds API historical scrape — KS-21's data-acquisition deliverable — runs in Phase 1 as time-sensitive infrastructure. KS-21 the *requirement* is mapped to Phase 4 because the engine integration is what closes the requirement.)

**Success Criteria** (what must be TRUE):
  1. QB pass_yards mean bias narrowed from ~−28 yd/game to within ±10 yd/game across 2022-2024 (measured by `scripts/validate.py`), driven primarily by KS-01 (RZ TD-gate fix) and KS-04 (CATCH_YARDS_BOOST retune)
  2. QB pass_yards KS dropped from ~0.36 baseline to ≤ 0.28 across 2022-2024 (intermediate target on the path to TGT-01 ≤ 0.20)
  3. RB rush_yards KS recovers from defaults' 0.26 regression back to ≤ 0.23 (matching bare baseline) — driven mainly by KS-07 RZ catch-rate retune
  4. Across all positions: rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs prior promoted defaults (hard floor; per-change gate)
  5. Odds API alternate-line markets (`player_pass_yds_alternate`, `player_reception_yds_alternate`, `player_rush_yds_alternate`, `player_pass_attempts_alternate`, `player_receptions_alternate`, `player_rush_attempts_alternate`) cached as parquet at `~/.fantasy-sim/odds/` for 2022-2024 weeks 1-18 (or up to The Odds API's historical-coverage limit) — verified by row counts logged after each season's scrape
**Plans**:

**Wave 1**
- 01 — KS-01 RZ TD-gate distribution preservation
- 09 — KS-21 alt-line scrape (parallel to KS-01; file-isolated)

**Wave 2** *(blocked on Wave 1 completion)*
- 02 — KS-04 conditional CATCH_YARDS_BOOST retune

**Wave 3** *(blocked on Wave 2 completion)*
- 03 — KS-03 matchup/coverage per-player dist-mean anchor
- 04 — KS-05 props engine magnitude bug + default constant
- 05 — KS-06 backup-receiver fallback (preprocessor + player_builder + play_resolver)
- 06 — KS-07 positional RZ catch rate modifiers

**Wave 4** *(blocked on Wave 3 completion)*
- 07 — KS-15 field-position clamping fix + CATCH_YARDS_BOOST=0

**Wave 5** *(blocked on Wave 4 completion)*
- 08 — KS-29 pff.team_context re-enable + sensitivity sweep

**Wave 6** *(blocked on Wave 5 completion)*
- 10 — KS-32 clock runoff measure-then-decide

**Wave 7** *(blocked on Wave 6 completion)*
- 11 — Phase 1 aggregate validation (p1.aggregate.full)

**Cross-cutting constraints** (appear in 2+ plans' `must_haves.truths`):
- D-25/D-26: one commit per KS-XX in dependency order; KS-01 → KS-04 → KS-15 RZ stack must ship in this order
- D-27: ledger label scheme `p1.ksXX.{bare,full}`; KS-29 sweep adds `s003/s005/s008` suffixes; KS-32 may use `p1.ks32.measure`
- D-28: validation set = all 2022-2024, 200 sims/season, PPR scoring (every per-plan A/B + aggregate)
- D-29: A/B mode per change = isolation + full-stack; agents execute `scripts/validate.py` directly per the 2026-04-26 rule reversal
- D-30/D-31: hard floor on rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 for promotion; medium-large items (KS-01/04/05/15) require KS Δ ≤ -0.01 on primary target
- D-33/D-34: TDD-first for KS-01/04/15 (RZ stack); test-after acceptable for KS-03/05/06/07/29
- D-35: existing 1,200+ test suite stays green throughout
**Cross-references to Outcome Targets**: TGT-01, TGT-02, TGT-05, TGT-06, TGT-07, TGT-09, TGT-10
**Risk notes**:
- KS-01 + KS-04 + KS-15 interact (all touch the clamping/RZ stack); per HYPOTHESES.md they must ship in dependency order: KS-01 first, then KS-04 (boost retune relative to fixed RZ), then KS-15 (clamping). KS-15 may allow `CATCH_YARDS_BOOST` to drop to 0; preserve TD-gate calibration via tests.
- KS-32 (clock runoff) might shift total plays/game; validate via `validate_passing.py` before promotion.
- Odds API historical alt-line coverage may be enterprise-only at the standard tier — if so, scope reduces to "what's available" and KS-21b in Phase 4 validates against current/upcoming weeks of 2025-2026 instead of historical 2022-2024.
- Each fix should be A/B tested in isolation (`baseline+X`) AND full-stack (`all_engines+X`) per project A/B testing approach.

### Phase 2: Structural Per-Stat Calibration
**Goal**: Address the architectural blocker that `residual_calibration` and `dynamic_blend` adjust `fpts` only, leaving stat distributions un-calibrated. Add a per-stat residual_calibration layer, raise `dynamic_blend` simulator weight off zero, raise `tier_engine` reliability cap for high-touch players, and refine the calibration knobs (per-position max_abs_adjustment, TE elite tier, ff_opportunity width, share-normalization residual, thin-bucket Bayesian shrinkage). With Phase 1 bug noise removed, structural-fix measurements are now interpretable.
**Depends on**: Phase 1 (clamping/RZ noise must be removed before structural per-stat residuals are fit)
**Requirements**: KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14
**Success Criteria** (what must be TRUE):
  1. Per-stat `residual_calibration` shipping (KS-09): `pass_yards`, `receiving_yards`, `rush_yards`, `receptions`, etc. all receive post-sim correction (not just fpts), measurable by inspecting projection rows from `scripts/validate.py` and confirming stat columns differ from raw simulator output for 2022-2024 ledger entries
  2. TE receptions KS recovers from ~0.35 to ≤ 0.27 (TGT-04 hit), driven by KS-08 simulator-weight floor + KS-09 per-stat corrections + KS-10 TE elite tier
  3. Aggregate fpts KS held ≤ 0.18 across all positions (TGT-08 hit) — KS-08 floor restores Monte Carlo variance contribution
  4. WR receptions KS reduced from ~0.28 to ≤ 0.24 (intermediate target on the path to TGT-03 ≤ 0.22)
  5. Across all positions: rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs Phase-1-promoted baseline (hard floor; per-change gate)
**Plans**: TBD
**Cross-references to Outcome Targets**: TGT-01, TGT-02, TGT-03, TGT-04, TGT-05, TGT-06, TGT-07, TGT-08, TGT-09, TGT-10
**Risk notes**:
- KS-09 is the architecturally largest change in the initiative — affects `scripts/fit_residual_calibration.py`, the calibration artifact schema, and the projection_layers ordering. Two integration paths per HYPOTHESES.md: (a) corrected stats → re-derived fpts (cleaner, riskier); (b) corrected stats + existing fpts correction (safer, two-stage). User's preference per Open Question 6 is needed; default to (b) for safer rollback.
- KS-08 simulator-weight floor (recommendation grid-search 0.20/0.30/0.40) may regress MAE because `ff_opportunity` is currently winning MAE precisely *because* it dominates. Pick the smallest floor that recovers KS while staying within MAE +0.05.
- KS-09 should ship behind a feature flag (`ensemble.residual_calibration.stat_level.enabled`) so it can be rolled back without losing fpts-level calibration if integration breaks.
- KS-12 share-normalization residual interacts with `availability` engine — coordinate so the residual doesn't double-count availability-driven share reductions.
- KS-13 ff_opportunity width depends on lo/hi quantile columns existing in raw FF Opportunity data — verify via `data/ensemble/loader.py` before implementation; if not present, KS-13 reduces to fitting our own residual variance model.

### Phase 3: Phase 5 Slice Activation (KS-Priority Retune)
**Goal**: Re-validate off-by-default PFF Phase 5 slices under KS-priority (Phase 5 was originally parked under rank_corr/MAE-priority). Now that the baseline is stable post-Phase-2, slice retunes should not be contaminated by clamping/calibration noise.
**Depends on**: Phase 2 (per-stat residual_calibration must exist so slice mutations are measured against per-stat-corrected baseline, not raw simulator)
**Requirements**: KS-02, KS-16, KS-17, KS-18
**Success Criteria** (what must be TRUE):
  1. RB rush_yards KS reduced to ≤ 0.22 (TGT-06 hit), primarily via KS-02 enabling `pff.rb_scheme_fit` (already-positive decision artifact under rank/MAE; expected positive under KS as well)
  2. WR receiving_yards KS reduced to ≤ 0.22 (intermediate target on path to TGT-02 ≤ 0.20), TE receiving_yards KS reduced to ≤ 0.27 (intermediate target on path to TGT-05 ≤ 0.25), driven by KS-16 enabling + retuning `pff.depth_role` + `pff.depth_role.efficiency`
  3. QB pass_yards mean bias narrowed to within ±5 yd/game (TGT-09 hit), driven by KS-17 retuning + re-enabling `pff.qb_split` (lower sensitivities, tighter gating per HYPOTHESES.md)
  4. KS-18 measurement complete: stat-specific KS for QB rushing_yards (designed-run on) and RB rush_yards (`tracking.rb_efficiency` on) recorded in ledger; promotion decision documented per slice
  5. Across all positions: rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs Phase-2-promoted baseline (hard floor; per-change gate)
**Plans**: TBD
**Cross-references to Outcome Targets**: TGT-01, TGT-02, TGT-03, TGT-05, TGT-06, TGT-09
**Risk notes**:
- KS-16 may need clamp widening from `[0.94, 1.06]` / `[0.92, 1.08]` to `[0.90, 1.10]` if first-pass KS doesn't move; this is a retune iteration, not a base-case assumption.
- KS-17 risks weekly_mae regression (v1 had +0.006); the retune lowers sensitivities and tightens gating which should reduce variance, but careful per-position monitoring is required.
- KS-18 designed-run smoke had `rank_corr Δ −0.0007` and TE weekly regressed `−0.0049` (essentially at hard floor); per user memory "designed-run priority parked after smoke," KS-18 is *measurement only* (no code retune) per HYPOTHESES.md scope. Decision artifact gets recorded; promotion is up to the user.
- KS-02 enabling rb_scheme_fit must NOT conflict with KS-18 `tracking.rb_efficiency` — if both promote, validate stack interaction (HYPOTHESES.md flags this as an open question).

### Phase 4: New Signal Integration (Including Odds API Engine)
**Goal**: Integrate the cached-but-unused PFF `last_ten_json` empirical CDF, integrate PFF `projections_json` for cross-stat consistency, and build the Odds API alt-line CDF engine that consumes the Phase-1 scrape. These signals layer on top of the now-stable post-Phase-3 baseline.
**Depends on**: Phase 3 (slice retunes must stabilize before new-signal integration so KS deltas attribute correctly), AND Phase 1 (Odds API scrape must be on disk for KS-21 engine to consume)
**Requirements**: KS-19, KS-20, KS-21
**Success Criteria** (what must be TRUE):
  1. PFF `last_ten_json` parsed in `props_loader.py` and consumed by a new `_apply_distribution_blend` method in `props_engine.py` (KS-19); per-player `last_ten_dist` distribution-aware blend produces smaller KS than the current mean-only blend on 2024-2025 ledger entries with `vegas.props.enabled=true`
  2. PFF `projections_json` parsed and consumed for QB cross-stat consistency (KS-20); QB pass_yards / pass_attempts / pass_completions joint distribution KS measurable via new ledger metric
  3. Odds API alt-line CDF engine wired in `PlayerPropsEngine.apply()` (KS-21); for QBs with ≥3 alt-line markets in cache, simulator's `P(pass_yds > threshold)` matches market-implied probability within ±5% absolute deviation
  4. QB pass_yards KS reduced to ≤ 0.20 (TGT-01 hit), WR receiving_yards KS reduced to ≤ 0.20 (TGT-02 hit), WR receptions KS reduced to ≤ 0.22 (TGT-03 hit) — KS-19/20/21 stack delivering final closure
  5. Across all positions: rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs Phase-3-promoted baseline (hard floor; per-change gate)
**Plans**: TBD
**Cross-references to Outcome Targets**: TGT-01, TGT-02, TGT-03, TGT-05, TGT-07, TGT-09, TGT-10
**Risk notes**:
- KS-19 has a data-coverage caveat: only 2025 props are scraped at PFF. For 2022-2024 backtest validation, KS-19 either validates against 2025 only OR depends on PFF historical backfill (open question — Phase 1 includes a 1-day probe of PFF Consumer historical access).
- KS-21 implied-probability conversion can be tricky if vig isn't handled correctly; de-vig pairs (over+under → ~1.0) before constructing the CDF.
- KS-19 + KS-21 mutate the same prop-stat distributions — order matters. Ship KS-19 first (simpler), then KS-21 layered on top so the alt-line CDF refines KS-19's empirical-mix output rather than replacing it.
- All three new-signal items interact with Phase 2's per-stat residual_calibration. KS-09 corrections may absorb some of the signal that KS-19/20/21 would otherwise add — measure KS deltas with KS-09 on AND off to ensure complementarity, not redundancy.
- Mid-season role changes (trades, IR returns) can produce bimodal `last_ten_json` samples for KS-19 — apply recency weighting and drop samples >180 days old per HYPOTHESES.md.

### Phase 5: Initiative Wrap-up & Outcome Validation
**Goal**: Run the final aggregate A/B comparing the Phase-4-promoted defaults vs the original Phase-0 baseline, verify all 10 outcome targets (TGT-01..TGT-10), update project documentation (PROJECT.md "Validated" section, AGENTS.md "Current State", `docs/`), and document any TGT that fell short (with explicit rationale per HYPOTHESES.md sanity check).
**Depends on**: Phases 1-4 (this is the consolidation pass)
**Requirements**: None (this phase has no new KS-XX requirements; it validates the work of Phases 1-4)
**Success Criteria** (what must be TRUE):
  1. Aggregate A/B run captured in ledger: Phase-4-defaults vs original-defaults baseline across 2022-2024, all PPR scoring, 200 sims/season — both per-stat KS and aggregate fpts KS recorded
  2. Outcome target audit: each of TGT-01..TGT-10 marked Hit / Partial / Missed with the underlying KS / mean-bias number from the aggregate A/B; per HYPOTHESES.md sanity check expectation is 70-100% closure (TE receptions and RB receiving_yards are the two most-uncertain targets)
  3. PROJECT.md "Validated" section updated to move successful KS-XX items from Active; "Active" reduced to remaining open items (if any); Key Decisions table updated with phase-by-phase decisions taken
  4. AGENTS.md "Current State" section updated to reflect newly-promoted defaults (KS-XX promotions, slice activations, new engines); `docs/` updated for KS-21 Odds API engine and KS-09 stat-level residual_calibration
  5. v2 backlog (REQUIREMENTS.md "v2 Requirements") preserved unchanged for the follow-up initiative; any new v2 items discovered during Phases 1-4 added with rationale
**Plans**: TBD
**Cross-references to Outcome Targets**: TGT-01..TGT-10 (all)
**Risk notes**:
- TGT-04 (TE receptions ≤ 0.27 relaxed) and TGT-07 (RB receiving_yards ≤ 0.34 relaxed) have the tightest hypothesis budgets per HYPOTHESES.md sanity check; if either falls short, document explicitly rather than over-claim.
- If the hard floor is breached at any final-aggregate cut, regress the offending change (Phase 4's last promotion is most likely culprit) — do not ship the regression to keep KS gains.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bug Fixes, Cheap Calibration & Scrape | 3/12 | In Progress|  |
| 2. Structural Per-Stat Calibration | 0/TBD | Not started | - |
| 3. Phase 5 Slice Activation (KS-Priority) | 0/TBD | Not started | - |
| 4. New Signal Integration | 0/TBD | Not started | - |
| 5. Initiative Wrap-up & Outcome Validation | 0/TBD | Not started | - |

## Coverage

**Total v1 requirements:** 23 (KS-01, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 02, 29, 32)
**Mapped to phases:** 23 ✓
**Unmapped:** 0
**Duplicates:** 0

| Phase | KS-XX Items | Count |
|-------|-------------|-------|
| Phase 1 | KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32 | 9 |
| Phase 2 | KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14 | 7 |
| Phase 3 | KS-02, KS-16, KS-17, KS-18 | 4 |
| Phase 4 | KS-19, KS-20, KS-21 | 3 |
| Phase 5 | (no new KS-XX; validates Phases 1-4) | 0 |
| **Total** | | **23** |

## Critical-Path Notes

**Time-sensitive: KS-21 scrape split**
- The Odds API tier currently has ~4.93M of 5M credits remaining (~2 weeks of life). The user explicitly directed: "do a ton of scraping for data we might be ASAP so that I can drop the subscription tier for next month."
- KS-21 is mapped to Phase 4 (engine integration is the canonical "delivered" work that closes the requirement) but the **scrape sub-deliverable** runs in Phase 1 as time-sensitive infrastructure.
- Phase 1 success criterion #5 explicitly tracks the scrape; Phase 4 KS-21 integration consumes the cached parquet without re-running the scrape.

**Dependency chain (cannot reorder)**
- Phase 1 bug fixes must precede Phase 2 structural fixes — otherwise per-stat residual_calibration bakes in remediable bug-driven biases.
- Phase 2 must precede Phase 3 — slice retunes need a stable per-stat baseline so KS deltas attribute correctly to each slice.
- Phase 3 must precede Phase 4 — new-signal integration interacts with retuned engines; doing it before retunes muddies attribution.
- Phase 1 (scrape) must precede Phase 4 (KS-21 engine) — engine has nothing to consume without scraped data.

**Hard-floor enforcement**
- Every KS-XX is a promotion-candidate change. Each goes through `scripts/validate.py` A/B in both isolation (`baseline+X`) and full-stack (`all_engines+X`) modes per project A/B-testing approach (see memory file `feedback_ab_testing_approach.md`).
- The user runs validation manually (per memory file `feedback_ab_manual.md`); agents implement and propose changes but do NOT run validation scripts.

**Highest-risk phase: Phase 2**
- KS-09 (per-stat `residual_calibration`) is the architecturally largest change in the initiative. It touches the calibration artifact schema, the post-sim projection_layers ordering, and the validation harness output. Recommend feature-flag-gated rollout so it can be rolled back without losing existing fpts-level calibration.
- KS-08 (`dynamic_blend` simulator-weight floor) and KS-09 interact — both target the same compression mechanism. Sequence KS-08 first (simpler grid-search), then KS-09 layered on top.
