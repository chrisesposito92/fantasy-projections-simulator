# Requirements: Fantasy Projections Simulator — Distribution Calibration

**Defined:** 2026-04-26
**Core Value:** Distribution shape (KS) on stat outputs for season-long projections — without giving back the rank_corr / MAE wins we already shipped. Hard floor: any change must NOT regress rank_corr by >0.005 or MAE by >0.05.

**Note on IDs:** `TGT-XX` (in `PROJECT.md`) are *outcome metrics*. `KS-XX` (here) are *hypotheses* — concrete deliverables that combine to hit those outcomes. They are different namespaces; full details for each hypothesis live in `.planning/research/HYPOTHESES.md`.

## v1 Requirements

The 23 hypotheses in scope for this initiative, grouped by theme. Each requirement is "delivered" when (a) the change is implemented + tested, (b) the A/B harness runs through `scripts/validate.py`, (c) the hard-floor check passes, and (d) the change is promoted (or rejected with documented rationale).

### A. Bugs

Confirmed code defects causing measurable bias. Bug-fix-class changes — should ship first.

- [x] **KS-01**: Fix `_tackled_short()` RZ TD-gate truncation at `src/fantasy_sim/engine/play_resolver.py:279-284, 421-424`. Replace the punitive yards-rewrite with `min(yard_line - 1, sampled_yards)`. → Impacts TGT-01, TGT-02, TGT-05, TGT-07, TGT-09, TGT-10
- [ ] **KS-03**: Fix `_apply_matchup` and `_apply_coverage` hardcoded `* 10.0` yard anchor at `src/fantasy_sim/data/game_context.py:534-544, 591`. Replace with per-player `np.mean(receiving_yards_dist)` to mirror the (correctly-implemented) weather engine. → Impacts TGT-02, TGT-05, TGT-07, TGT-10
- [ ] **KS-05**: Fix props-engine magnitude bug at `src/fantasy_sim/data/vegas/props_engine.py:248` where `_apply_recv_yds` multiplies per-catch `dist_mean` by `games_played`. Also adjust `_DEFAULT_TEAM_PASS_YDS = 230.0 → ~240.0` to match NFL average. → Impacts TGT-01, TGT-02, TGT-05, TGT-09, TGT-10
- [ ] **KS-06**: Fix backup-share fallback shrinking WR/TE receiving distributions when starter is questionable. → Impacts TGT-02, TGT-05
- [ ] **KS-15**: Fix yards-distribution clamping bug that drops upper-tail values for QB pass_yards and WR receiving_yards. → Impacts TGT-01, TGT-02, TGT-09, TGT-10

### B. Structural Fixes

Architectural changes — most leverage on stat-level KS regressions. Sequenced after bugs so measurements aren't contaminated by bug-driven noise.

- [ ] **KS-08**: Add `dynamic_blend` simulator-weight floor (recommendation: grid-search 0.20/0.30/0.40 around current near-zero values in `weights_2024.json`). Restores Monte Carlo variance contribution to the post-sim ensemble. → Impacts TGT-08, TGT-04, TGT-05
- [ ] **KS-09**: Extend `residual_calibration` to operate at the stat-column level, not just `fpts`. THE structural blocker for stat-level KS work. Files: `src/fantasy_sim/scoring/residual_calibration.py:422` (and surrounding artifact-loading code). → Impacts every TGT
- [ ] **KS-10**: Add per-position `max_abs_adjustment` clamp + a TE-specific elite-tier override that prevents `_merge_thin_tiers` from collapsing the `TE|high|*` calibration bucket. → Impacts TGT-04, TGT-05, TGT-08
- [ ] **KS-11**: Raise `tier_engine` `reliability_cap` from 0.80 to ~0.90 for high-touch players (PFF tier 1+2). Currently the cap shrinks elite-player distributions toward fat-middle pools. → Impacts TGT-02, TGT-05, TGT-06
- [ ] **KS-12**: Address share-normalization residual that re-distributes target/carry shares to sum to 1.0 weekly, removing legitimate cross-player variance. → Impacts TGT-03, TGT-04, TGT-06
- [ ] **KS-13**: Fix `ff_opportunity` prior to carry width (currently used as a point estimate by `dynamic_blend`). → Impacts TGT-04, TGT-05, TGT-08
- [ ] **KS-14**: Bayesian shrinkage tuning for thin (`MIN_BUCKET_PLAYS=10` fallback) buckets. → Impacts every yards TGT (small but additive)

### C. Phase 5 Slice Activation (KS-priority retune)

Off-by-default features that were validated under rank_corr/MAE — re-validate / retune for KS specifically.

- [ ] **KS-02**: Enable `pff.rb_scheme_fit` (already-positive decision artifact: rank_corr +0.0018, weekly_mae −0.003, season_mae −0.040; KS never measured). → Impacts TGT-06
- [ ] **KS-16**: Enable + retune `pff.depth_role` and `pff.depth_role.efficiency` for WR/TE — only WR/TE-specific layer that scales `receiving_yards_dist`. → Impacts TGT-02, TGT-03, TGT-05
- [ ] **KS-17**: Retune `pff.qb_split` (per-game receiver efficiency from QB pressure splits) for QB pass_yards mean bias. → Impacts TGT-01, TGT-09
- [ ] **KS-18**: Re-measure `qb_rushing.scramble`, QB designed-run chain, and the relevant `tracking.rb_efficiency` slices under KS-priority validation (no code changes; measurement-only). → Impacts QB rush, RB rush distributions

### D. New Signal Integration

Signals available but unused. KS-19 / KS-20 reuse already-cached PFF data; KS-21 is the time-sensitive Odds API scrape.

- [ ] **KS-19**: Parse + blend `~/.fantasy-sim/pff/props/props_*.parquet` `last_ten_json` empirical CDF into per-player distribution sampling. Cached signal — zero new scrape cost. → Impacts every prop stat
- [ ] **KS-20**: Cross-stat consistency from PFF `projections_json` (already cached) for QB pass_yards/attempts/completions/TDs. → Impacts TGT-01, TGT-02, TGT-09
- [ ] **KS-21**: Build Odds API alternate-line CDF pipeline + historical backfill (multi-line over/under markets define a CDF directly). **Time-sensitive** — front-load scrape while ~4.93M of 5M-credit tier is still active (~2 weeks). Engine consumption can land later but raw scrape must happen ASAP. → Impacts TGT-01, TGT-02, TGT-07, TGT-09, TGT-10

  **Note on phase split:** The KS-21 *requirement* is delivered when the engine integration ships in Phase 4. The *scrape* sub-deliverable runs in Phase 1 as time-sensitive infrastructure (see ROADMAP.md Phase 1 success criterion #5). The requirement remains mapped to a single phase (Phase 4) per the 100% coverage rule; Phase 1 carries the data-acquisition work.

### E. Calibration Constant Retuning

Cheap parameter changes ranked by ROI. Shipped alongside bug fixes.

- [x] **KS-04**: Retune `CATCH_YARDS_BOOST` (currently `+1` outside RZ, disabled in RZ). Likely undersized for WR; consider `+2` and/or enabling in RZ post-KS-01. → Impacts TGT-01, TGT-02, TGT-05, TGT-07, TGT-10
- [ ] **KS-07**: Retune RZ catch-rate / TD-gate constants stack. → Impacts TGT-02, TGT-05, TGT-07, TGT-10
- [ ] **KS-29**: Retune sack-rate prior. → Impacts TGT-01, TGT-09
- [ ] **KS-32**: Retune QB pass-volume prior (per-game pass attempts). → Impacts TGT-01, TGT-09

## v2 Requirements

P5 long-tail items deferred to a follow-up initiative. 10 items, mostly engineering-heavy with most-uncertain payoff. Captured for traceability; not in current roadmap.

### F. Long-tail signal integration (deferred)

- **KS-22**: Build per-zone `QbDepthEngine` from PFF `passing_detail` (5-10 days)
- **KS-23**: aDOT / time-to-throw priors
- **KS-24**: PFF `rushing_summary.breakaway_*` columns for RB tail
- **KS-25**: Per-target CB matchup from PFF `receiving_coverage.coverage_player_id`
- **KS-26**: Wind direction + gusts (Open-Meteo extra fields)
- **KS-27**: Snap-count variance signal
- **KS-28**: NGS expected-yards re-validation
- **KS-30**: Log-scale factor composition (cross-week dispersion)
- **KS-31**: Kicker / DST shrinkage retune
- **KS-33**: Sack rate + RZ TD gate validation

## Out of Scope

| Feature | Reason |
|---------|--------|
| New positions (DST/K rewrites) | Their KS values are acceptable; separate initiative if needed |
| Engine re-architecture | Play-by-play loop is solid; KS issues are calibration / signals |
| Auction values, lineup optimization, draft tooling | Projection accuracy only |
| UI / dashboard work | CLI output stays as-is |
| Replacing nflverse / PFF / Open-Meteo / Odds API as providers | Add signals from existing providers, not switch providers |
| P5 long-tail items (KS-22..KS-33) | Deferred to v2 — see above |

## Traceability

Phase mapping set by `gsd-roadmapper` during ROADMAP.md creation (2026-04-25). The Odds API alternate-line scrape — a sub-deliverable of KS-21 — runs in Phase 1 as time-sensitive infrastructure even though the KS-21 requirement is mapped to Phase 4 (engine integration is the canonical "delivered" work).

| Requirement | Phase | Status |
|-------------|-------|--------|
| KS-01 | Phase 1 | Complete |
| KS-02 | Phase 3 | Pending |
| KS-03 | Phase 1 | Pending |
| KS-04 | Phase 1 | Complete |
| KS-05 | Phase 1 | Pending |
| KS-06 | Phase 1 | Pending |
| KS-07 | Phase 1 | Pending |
| KS-08 | Phase 2 | Pending |
| KS-09 | Phase 2 | Pending |
| KS-10 | Phase 2 | Pending |
| KS-11 | Phase 2 | Pending |
| KS-12 | Phase 2 | Pending |
| KS-13 | Phase 2 | Pending |
| KS-14 | Phase 2 | Pending |
| KS-15 | Phase 1 | Pending |
| KS-16 | Phase 3 | Pending |
| KS-17 | Phase 3 | Pending |
| KS-18 | Phase 3 | Pending |
| KS-19 | Phase 4 | Pending |
| KS-20 | Phase 4 | Pending |
| KS-21 | Phase 4 (scrape sub-deliverable runs in Phase 1) | Pending |
| KS-29 | Phase 1 | Pending |
| KS-32 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

**Phase-by-phase counts:**

| Phase | KS-XX Items | Count |
|-------|-------------|-------|
| Phase 1 | KS-01, KS-03, KS-04, KS-05, KS-06, KS-07, KS-15, KS-29, KS-32 | 9 |
| Phase 2 | KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14 | 7 |
| Phase 3 | KS-02, KS-16, KS-17, KS-18 | 4 |
| Phase 4 | KS-19, KS-20, KS-21 | 3 |
| Phase 5 | (validation / wrap-up; no new KS-XX) | 0 |
| **Total** | | **23** |

## Outcome Targets (TGT-XX)

For convenience — full text in `PROJECT.md`. Each requirement above lists which TGT-XX it impacts.

| ID | Description | Current | Target |
|----|-------------|---------|--------|
| TGT-01 | QB pass_yards KS | ~0.36 | ≤ 0.20 |
| TGT-02 | WR receiving_yards KS | ~0.26 | ≤ 0.20 |
| TGT-03 | WR receptions KS | ~0.28 | ≤ 0.22 |
| TGT-04 | TE receptions KS | ~0.35 | ≤ 0.27 (relaxed) |
| TGT-05 | TE receiving_yards KS | ~0.31 | ≤ 0.25 |
| TGT-06 | RB rush_yards KS | ~0.26 | ≤ 0.22 |
| TGT-07 | RB receiving_yards KS | ~0.42 | ≤ 0.34 (relaxed) |
| TGT-08 | Aggregate fpts KS | 0.15-0.25 | ≤ 0.18 |
| TGT-09 | QB pass_yards mean bias | -28 yd/g | ±5 yd/g |
| TGT-10 | WR receiving_yards mean bias | -9 yd/g | ±2 yd/g |

---
*Requirements defined: 2026-04-26*
*Last updated: 2026-04-25 — phase mappings populated by `gsd-roadmapper`*
