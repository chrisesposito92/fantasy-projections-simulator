# Phase 2 — Promotion Notes

> One entry per per-KS plan promotion-state commit. Mirrors Phase 1 logs/PROMOTION-NOTES.md.
> Status flag legend: SHIPPED / SHIPPED-NO-OP / SHIPPED-PARTIAL / BLOCKED.

## Phase 2 Entry Baseline (Plan 01 Task 4)

`p2.entry.full` = `p1.aggregate.full` Arm B (#105) — numerical sanity-check pin.
- Source: `validate.py --baseline bare --label p2.entry.full`
- Purpose: D-15 Phase-2-vs-Phase-1 delta in Plan 09 differences `p2.aggregate.full` Arm B against `p1.aggregate.full` Arm B; `p2.entry.full` is a same-commit snapshot to verify the cache + harness produce identical metrics post-Plan-01 scaffolding.
- Acceptance: |Δ rank_corr| < 1e-4 AND |Δ weekly_mae| < 0.001 between `p1.aggregate.full` Arm B and `p2.entry.full` Arm B.

**2026-04-27 (Plan 01 Task 4):** `p2.entry.full` pinned (ledger #106). rank_corr_delta=+0.2036, weekly_mae_delta=-1.459. Δ vs `p1.aggregate.full` (#105): rank_corr_delta +0.0008, weekly_mae_delta +0.001. Within Monte Carlo stochastic variation at 200 sims/season (no runtime behavior change from Plan 01 scaffolding — all phase2_ks_flags.*.enabled=false). 2136 tests pass (2131 prior + 5 new Phase 2 scaffolding tests).

## KS-08 (Plan 02) — TBD

## KS-09 (Plan 03) — TBD

## KS-10 (Plan 05) — TBD

## KS-11 (Plan 06) — TBD

## KS-12 (Plan 08) — TBD

## KS-13 (Plan 07) — TBD

## KS-14 (Plan 04) — TBD

## Phase 2 Aggregate (Plan 09) — TBD
