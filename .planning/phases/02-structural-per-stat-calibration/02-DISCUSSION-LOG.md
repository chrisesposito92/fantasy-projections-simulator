# Phase 2: Structural Per-Stat Calibration — Discussion Log

**Discussion held:** 2026-04-26
**Mode:** default (no flags)
**Audience:** human reference (audits, retrospectives). NOT consumed by downstream agents.

## Context Loaded

- `.planning/PROJECT.md` — initiative scope, hard floor, Phase 1 closure note
- `.planning/REQUIREMENTS.md` — 23 KS-XX hypotheses; Phase 2 owns KS-08, 09, 10, 11, 12, 13, 14
- `.planning/ROADMAP.md` §"Phase 2" — goal, dependencies, success criteria, risk notes
- `.planning/STATE.md` — Phase 1 closed; Phase-2 entry baseline = `p1.aggregate.full` (#105) Arm B
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md` — Phase 1 D-44/D-45/D-46 patterns inherited
- `.planning/research/HYPOTHESES.md` §KS-08..KS-14 + Open Questions §658-680
- `.planning/codebase/*.md` — refreshed brownfield map (7 docs)
- Code surfaces probed: `residual_calibration.py`, `dynamic_blend.py`, `ensemble.py`, `weights_2024.json` artifact

## Areas Selected for Discussion

User selected ALL FOUR proposed gray-area clusters:
1. KS-09 architecture
2. KS-08 sim-weight floor
3. Calibration knobs (KS-10/11/12/13/14)
4. Phase 2 logistics

## Discussion by Area

### Area 1 — KS-09 Architecture

**Q1: After per-stat residual_calibration writes corrected stat columns, how should fpts be derived?**

Options presented:
- Two-stage layered (Recommended) — per-stat correction first, then existing fpts correction on raw_sim_fpts (independent)
- Re-derive from corrected stats — recompute fpts via scoring config; existing fpts correction drops or is re-fit
- Hybrid: stage A fpts as backstop — recompute then apply shrunk fpts correction on top

**User selected:** Two-stage layered.
**Captured as:** D-01.
**Notes:** Resolves HYPOTHESES Open Q 6 in favor of (b). Cost (corrected stats vs corrected fpts can diverge slightly) accepted; not chased in v1.

---

**Q2: How should KS-09's per-stat residual_calibration ship?**

Options presented:
- Feature-flag gated (Recommended) — `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled`, continues Phase 1 D-45 pattern
- Hard structural change — no flag, git revert as rollback
- Flag + dedicated artifact opt-in — two-flag scheme with artifact `stat_corrections` key as second gate

**User selected:** Feature-flag gated.
**Captured as:** D-02.
**Notes:** Resolves Open Q 5. Plan 01 must enumerate the 7 new flags in `bare_config_dict()` per Phase 1 D-44 (Codex Cycle-2 fix).

---

**Q3: Which stat columns should the per-stat residual_calibration cover in v1?**

Options presented:
- All scoring-impacting stats (Recommended) — ~14 columns: yards/TDs/receptions/fumbles per position
- Headline KS targets only — ~7 columns matching PROJECT.md context table
- Yards-only first, expand later — pass_yards / receiving_yards / rush_yards only

**User selected:** All scoring-impacting stats.
**Captured as:** D-03.
**Notes:** Aligns with `feedback_quality_over_simplicity.md`. If artifact-fitting shows certain columns (e.g., `interceptions`) lack sufficient bucket data, planner may scope-reduce in-plan.

---

**Q4: How should per-row stat corrections be bounded to prevent runaway adjustments?**

Options presented:
- Stat std-scaled clamp (Recommended) — `±2 * sqrt(actual_var)` per `(position, usage_tier, stat)` bucket
- Per-stat fixed caps — hard-coded numbers per stat in defaults.yaml
- Position+tier per-stat caps — KS-10 mirror; ~150 caps to tune
- Two-tier: std primary, hard secondary — std-scaled + secondary safety rail

**User selected:** Stat std-scaled clamp.
**Captured as:** D-04.
**Notes:** Per HYPOTHESES KS-09 verbatim. `clamp_std` lives in artifact, not config.

### Area 2 — KS-08 Sim-Weight Floor

**Q5: How should the simulator-weight floor be selected?**

Options presented:
- Three-point sweep, smallest-passing (Recommended) — `{0.20, 0.30, 0.40}`, smallest floor passing hard floor + non-zero KS Δ
- Three-point sweep, largest-improving — same set, prioritize KS over MAE preservation
- Five-point sweep, U-shape select — `{0.10, 0.20, 0.30, 0.40, 0.50}`, elbow detection

**User selected:** Three-point smallest-passing.
**Captured as:** D-05.
**Notes:** Matches ROADMAP risk note "pick the smallest floor that recovers KS while staying within MAE +0.05".

---

**Q6: How should the simulator-weight floor be implemented in dynamic_blend?**

Options presented:
- Option A: floor + renormalize (Recommended) — `_artifact_weights()` clamp + renormalize, re-fit `fit_dynamic_blend_weights.py` with floor constraint
- Option B: shrinkage center — `proj_fpts = sim + alpha*(ff_opp - sim) + epsilon*randn()`, larger architectural change
- Option A first, Option B if A insufficient — staged with Plan 02 + optional Plan 02b

**User selected:** Option A.
**Captured as:** D-06.
**Notes:** Surgical change. Option B deferred — KS-13 (ff_opp prior width) covers similar mechanism with simpler architecture.

### Area 3 — Calibration Knobs

**Q7: KS-10 (per-position max_abs_adjustment + TE elite tier) — which numbers ship?**

Options presented:
- HYPOTHESES values (Recommended) — QB 2.5 / RB 2.0 / WR 1.5 / TE 0.8 + TE elite tier > 14.0 + min_bucket_rows 100
- Sweep TE-only first — keep others at 1.5, sweep TE cap
- Sweep all four positions — ~12 A/B runs

**User selected:** HYPOTHESES values verbatim.
**Captured as:** D-07.

---

**Q8: KS-11 (tier_engine reliability cap retune) — what scope ships?**

Options presented:
- Position-specific cap raise (Recommended) — config block, no code restructure
- Mixture-of-CDFs at tails only — band-targeted blending
- Position cap + mixture combo — both

**User selected:** Position-specific cap raise (config-only).
**Captured as:** D-08.
**Notes:** Mixture-of-CDFs deferred. QB stays at floor 0.20 / cap 0.80 per `feedback_qb_calibration.md`.

---

**Q9: KS-12 (share-normalization residual) — what's the right scope for Phase 2?**

Options presented:
- Compose with availability (Recommended) — `expected_active_shares` formula, coordinates with availability engine
- Relax sum-to-1.0 only — simpler, no availability coupling
- Defer to Phase 4 / future initiative — skip in Phase 2

**User selected:** Compose with availability.
**Captured as:** D-09.
**Notes:** ROADMAP risk note flags availability double-count as planner's primary integration concern; plan 08 must document integration test cases.

---

**Q10: KS-13 (ff_opportunity prior width) — how to handle the lo/hi quantile question?**

Options presented:
- Probe first, then decide (Recommended) — single plan, two execution paths
- Fit our own residual std up front — skip probe
- Defer KS-13 if KS-08 hits — wait until KS-08 lands

**User selected:** Probe first, then decide.
**Captured as:** D-10.
**Notes:** Both Path A (lo/hi found) and Path B (fitted residual std) pre-coded so the plan doesn't stall on probe outcome.

---

**Q11: KS-14 (thin-bucket Bayesian shrinkage) — what shape ships?**

Options presented:
- MIN_BUCKET_PLAYS 10→5 + Bayesian shrinkage (Recommended) — full HYPOTHESES KS-14 spec
- Lower threshold only, no shrinkage — simplest cut
- Defer KS-14 to Phase 5 wrap-up — skip in Phase 2

**User selected:** Full spec (10→5 + shrinkage).
**Captured as:** D-11.

### Area 4 — Phase 2 Logistics

**Q12: After KS-08 → KS-09 (locked by ROADMAP critical path), what's the order for KS-10/11/12/13/14?**

Options presented:
- Risk-graded: 14, 10, 11, 13, 12 (Recommended) — ascending hard-floor risk
- Gain-graded: 11, 10, 13, 14, 12 — descending KS gain
- Dependency-graded: 13, 11, 10, 14, 12 — KS-13 first (composes with KS-08)

**User selected:** Risk-graded.
**Captured as:** D-12.
**Notes:** KS-12 last because `_normalize_roster_shares` fires 9+ times per game build (biggest blast radius).

---

**Q13: How should plans be split across the 7 KS items?**

Options presented:
- One plan per KS (Recommended) — Phase 1 cadence; 9 plans total (Plan 01 baseline + 7 KS + Plan 09 aggregate)
- Bundle small items (KS-10/13/14 in one plan) — 7 plans
- Two-plan KS-09 split — 10 plans, KS-09 schema-bump separate from runtime gating

**User selected:** One plan per KS.
**Captured as:** D-13.
**Notes:** Each KS gets isolated A/B + promotion commit. Mirrors Phase 1.

---

**Q14: What's the promotion bar for KS-09 specifically?**

Options presented:
- Hard floor + KS Δ ≤ -0.03 on QB pass_yards (Recommended) — plus mean bias |Δ| ≤ 5 yd/g
- Hard floor + multi-stat KS bar — at least 3 of 7 headline stats Δ ≤ -0.02
- Hard floor + composite bar — average KS Δ across 7 stats ≤ -0.025

**User selected:** Hard floor + KS Δ ≤ -0.03 on QB pass_yards + bias |Δ| ≤ 5 yd/g.
**Captured as:** D-14.
**Notes:** Phase 1 D-31 was -0.01; KS-09 rated "very large" so bar tightens. PROJECT.md flags QB pass_yards bias (-39.29 yd/g) as the architectural lever.

---

**Q15: How should the end-of-phase aggregate validation work?**

Options presented:
- Mirror Phase 1 Plan 11 pattern (Recommended) — single `p2.aggregate.full` vs `p1.aggregate.full`
- Two-pivot aggregate — both vs Phase 1 and vs Phase 0
- Per-KS-cumulative + final aggregate — running stack ledger entries

**User selected:** Mirror Phase 1 Plan 11.
**Captured as:** D-15.
**Notes:** Walk-back trigger = hard-floor regression on the Phase-2-vs-Phase-1 delta only. Two-pivot deferred to Phase 5 wrap-up.

## Summary

- **15 questions asked** across 4 areas; all answered with the recommended option.
- **15 decisions captured** (D-01 through D-15) plus 10 carry-forward items (C-01 through C-10).
- **Open Questions resolved from HYPOTHESES.md:** Q2 (KS-08 floor — D-05/D-06), Q5 (KS-09 rollout — D-02), Q6 (KS-09 fpts integration — D-01).
- **No scope creep** — discussion stayed within KS-08..KS-14 boundary; all out-of-phase items flagged in `<deferred>`.
- **No conflicts** with carry-forward decisions or memory rules.

## Deferred Ideas Captured

See `02-CONTEXT.md` `<deferred>` section. Highlights:
- KS-09 path (a) re-derive fpts — future consolidation plan
- KS-08 Option B shrinkage center — Phase 2 follow-up if Option A underdelivers
- KS-11 mixture-of-CDFs — v2 backlog if cap raise underdelivers
- KS-12 simpler relax-sum-to-1.0 — fallback within Plan 08 if availability composition proves brittle
- Per-KS cumulative ledger entries — Phase 5 wrap-up
- Phase-2-vs-Phase-0 two-pivot aggregate — Phase 5 wrap-up

---

*Discussion gathered: 2026-04-26*
