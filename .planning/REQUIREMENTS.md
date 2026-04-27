# Requirements: Fantasy Projections Simulator — Distribution Calibration

**Defined:** 2026-04-26
**Core Value:** Distribution shape (KS) on stat outputs for season-long projections — without giving back the rank_corr / MAE wins we already shipped. Hard floor: any change must NOT regress rank_corr by >0.005 or MAE by >0.05.

**Note on IDs:** `TGT-XX` (in `PROJECT.md`) are *outcome metrics*. `KS-XX` (here) are *hypotheses* — concrete deliverables that combine to hit those outcomes. They are different namespaces; full details for each hypothesis live in `.planning/research/HYPOTHESES.md`.

## v1 Requirements

The 23 hypotheses in scope for this initiative, grouped by theme. Each requirement is "delivered" when (a) the change is implemented + tested, (b) the A/B harness runs through `scripts/validate.py`, (c) the hard-floor check passes, and (d) the change is promoted (or rejected with documented rationale).

### A. Bugs

Confirmed code defects causing measurable bias. Bug-fix-class changes — should ship first.

- [x] **KS-01**: Fix `_tackled_short()` RZ TD-gate truncation at `src/fantasy_sim/engine/play_resolver.py:279-284, 421-424`. Replace the punitive yards-rewrite with `min(yard_line - 1, sampled_yards)`. → Impacts TGT-01, TGT-02, TGT-05, TGT-07, TGT-09, TGT-10
- [x] **KS-03**: Fix `_apply_matchup` and `_apply_coverage` hardcoded `* 10.0` yard anchor at `src/fantasy_sim/data/game_context.py:534-544, 591`. Replace with per-player `np.mean(receiving_yards_dist)` to mirror the (correctly-implemented) weather engine. → Impacts TGT-02, TGT-05, TGT-07, TGT-10
- [x] **KS-05**: Fix props-engine magnitude bug at `src/fantasy_sim/data/vegas/props_engine.py:248` where `_apply_recv_yds` multiplies per-catch `dist_mean` by `games_played`. Also adjust `_DEFAULT_TEAM_PASS_YDS = 230.0 → ~240.0` to match NFL average. → Impacts TGT-01, TGT-02, TGT-05, TGT-09, TGT-10
- [x] **KS-06**: Fix backup-share fallback shrinking WR/TE receiving distributions when starter is questionable. → Impacts TGT-02, TGT-05
- [x] **KS-15**: Fix yards-distribution clamping bug that drops upper-tail values for QB pass_yards and WR receiving_yards. → Impacts TGT-01, TGT-02, TGT-09, TGT-10

### B. Structural Fixes

Architectural changes — most leverage on stat-level KS regressions. Sequenced after bugs so measurements aren't contaminated by bug-driven noise.

- [x] **KS-08** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Add `dynamic_blend` simulator-weight floor (grid-searched 0.20/0.30/0.40; selected 0.20). Restores Monte Carlo variance contribution to the post-sim ensemble. SHIPPED in isolation, reverted at full-stack aggregate (iter-1 marginal_delta_rank_corr = -0.000187 — net positive contributor but couldn't carry the stack). Architecture preserved: `apply_simulator_weight_floor()` + CLI flag in `fit_dynamic_blend_weights.py`. → Impacts TGT-08, TGT-04, TGT-05
- [x] **KS-09** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Extend `residual_calibration` to operate at the stat-column level via `corrected_<stat>` columns + ±2σ clamp + schema_v2 artifacts. SHIPPED-PARTIAL in isolation, reverted at aggregate (highest harm_score in iter-1 reverse-ablation: +0.00716; per-stat bias delta too small at 200 sims to outweigh stack regression). **Architecture preserved as a Phase 3+ lever:** corrected_<stat> infrastructure + schema_v2 loader + validate.py routing remain in tree — Phase 3 can re-fit with different methods (more sims, stratified sampling, alt clamp, hierarchical priors). The headline mean-bias miss (TGT-09 QB pass_yards) is now Phase 3+'s top priority. → Impacts every TGT
- [x] **KS-10** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Add per-position `max_abs_adjustment` clamp (D-07 values: QB 2.5 / RB 2.0 / WR 1.5 / TE 0.8) + TE-specific elite-tier override (≥14 fpts threshold, 4-tier classification). SHIPPED in isolation, reverted at aggregate. Architecture preserved: `USAGE_TIER_THRESHOLDS_4`, per-position cap config, TE elite tier in `usage_tier()`. → Impacts TGT-04, TGT-05, TGT-08
- [x] **KS-11** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Raise `tier_engine` reliability cap via per-position config (WR/TE 0.30/0.95, RB 0.25/0.92; QB stays at global 0.20/0.80 per QB-untouched invariant). SHIPPED in isolation, reverted at aggregate (essentially neutral in iter-1 ablation). Architecture preserved: `pff.tier_engine.position_reliability` config block + flag-gated loader. → Impacts TGT-02, TGT-05, TGT-06
- [x] **KS-12** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Share-normalization residual via `clip(active/typical, 0.5, 1.0)` factor + 0.05 backup TE/WR threshold. SHIPPED in isolation, reverted at aggregate (net positive contributor in iter-1 ablation but couldn't carry the stack). Architecture preserved: `_expected_active_share_factor()` + `_scale_shares_with_factor()` + `MIN_BACKUP_RECEIVING_SHARE` constant. → Impacts TGT-03, TGT-04, TGT-06
- [x] **KS-13** (NO-OP — Phase 2 walked back 2026-04-27): `ff_opportunity` prior width via Path B Gaussian (Path A unavailable: nflverse FF Opportunity has no quantile columns). SHIPPED-NO-OP — sampling adds symmetric noise around prior_fpts but distribution gap is from systematic bias, not insufficient prior width. Architecture preserved: probe + fitter + lazy artifact loader + dual-gate (master flag + sub-flag conjunction). → Impacts TGT-04, TGT-05, TGT-08
- [x] **KS-14** (INVALIDATED-AT-AGGREGATE — Phase 2 walked back 2026-04-27): Effective `MIN_BUCKET_PLAYS` 10→5 via flag-gated helper + Bayesian shrinkage at strength `5 * len(team_default)` for buckets with 5-9 plays. SHIPPED in isolation, reverted at aggregate. Architecture preserved: `_effective_min_bucket_plays()` + `_apply_bayesian_shrinkage()` + audit metric. → Impacts every yards TGT (small but additive)

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
- [x] **KS-21**: Build Odds API alternate-line CDF pipeline + historical backfill (multi-line over/under markets define a CDF directly). **Time-sensitive** — front-load scrape while ~4.93M of 5M-credit tier is still active (~2 weeks). Engine consumption can land later but raw scrape must happen ASAP. → Impacts TGT-01, TGT-02, TGT-07, TGT-09, TGT-10

  **Note on phase split:** The KS-21 *requirement* is delivered when the engine integration ships in Phase 4. The *scrape* sub-deliverable runs in Phase 1 as time-sensitive infrastructure (see ROADMAP.md Phase 1 success criterion #5). The requirement remains mapped to a single phase (Phase 4) per the 100% coverage rule; Phase 1 carries the data-acquisition work.

### E. Calibration Constant Retuning

Cheap parameter changes ranked by ROI. Shipped alongside bug fixes.

- [x] **KS-04**: Retune `CATCH_YARDS_BOOST` (currently `+1` outside RZ, disabled in RZ). Likely undersized for WR; consider `+2` and/or enabling in RZ post-KS-01. → Impacts TGT-01, TGT-02, TGT-05, TGT-07, TGT-10
- [x] **KS-07**: Retune RZ catch-rate / TD-gate constants stack. → Impacts TGT-02, TGT-05, TGT-07, TGT-10
- [x] **KS-29**: Retune sack-rate prior. → Impacts TGT-01, TGT-09
- [x] **KS-32**: Retune QB pass-volume prior (per-game pass attempts). → Impacts TGT-01, TGT-09

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
| KS-03 | Phase 1 | Complete |
| KS-04 | Phase 1 | Complete |
| KS-05 | Phase 1 | Complete |
| KS-06 | Phase 1 | Complete |
| KS-07 | Phase 1 | Complete |
| KS-08 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved) |
| KS-09 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved as Phase 3+ lever) |
| KS-10 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved) |
| KS-11 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved) |
| KS-12 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved) |
| KS-13 | Phase 2 | Tested — NO-OP (architecture preserved) |
| KS-14 | Phase 2 | Tested — INVALIDATED at aggregate (architecture preserved) |
| KS-15 | Phase 1 | Complete |
| KS-16 | Phase 3 | Pending |
| KS-17 | Phase 3 | Pending |
| KS-18 | Phase 3 | Pending |
| KS-19 | Phase 4 | Pending |
| KS-20 | Phase 4 | Pending |
| KS-21 | Phase 4 (scrape sub-deliverable runs in Phase 1) | Complete |
| KS-29 | Phase 1 | Complete |
| KS-32 | Phase 1 | Complete |

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
*Last updated: 2026-04-27 — Phase 2 closure: KS-08 through KS-14 marked INVALIDATED-AT-AGGREGATE / NO-OP (architecture preserved in tree as Phase 3+ levers). See `.planning/phases/02-structural-per-stat-calibration/09-phase2-aggregate-validation-SUMMARY.md`.*
