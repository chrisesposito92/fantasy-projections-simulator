---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 1 replan complete (incorporates Codex 01-REVIEWS.md HIGH-1..HIGH-4 + MEDIUMs)
last_updated: "2026-04-26T07:00:00.000Z"
last_activity: 2026-04-26 -- Phase 1 replan complete (12 plans incl. new Plan 00)
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 12
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-26)

**Core value:** Distribution shape (KS) on stat outputs that matters for season-long projections — without giving back the rank_corr / MAE wins we already shipped. Hard floor: any change must NOT regress rank_corr by >0.005 or MAE by >0.05.
**Current focus:** Phase 1 — Bug Fixes, Cheap Calibration & Time-Sensitive Scrape (REPLANNED 2026-04-26)

## Current Position

Phase: 1 of 5 (Bug Fixes, Cheap Calibration & Time-Sensitive Scrape)
Plan: 0 of 12 in current phase (Plan 00 = Wave 0 prerequisite per replan)
Status: Ready to execute (post-replan)
Last activity: 2026-04-26 -- Phase 1 replan complete; addresses Codex 01-REVIEWS.md HIGH-1..4 + MEDIUM-1..4 + LOW-2/3

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: N/A (no execution yet)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Initiative scope: KS as priority metric; hard floor of -0.005 rank_corr / -0.05 MAE for any KS-targeting change
- Phase structure: 5 phases, derived from synthesizer's 4-phase suggestion + a Phase 5 wrap-up
- KS-21 split: scrape (Phase 1, time-sensitive) vs engine integration (Phase 4, dependency-ordered) — required by 2-week Odds API tier window
- TE receptions / RB receiving_yards targets relaxed (TGT-04 ≤ 0.27, TGT-07 ≤ 0.34) per sanity check on hypothesis budget
- v1 = P1-P4 (23 hypotheses); P5 long-tail items (KS-22, KS-23, KS-24, KS-25, KS-26, KS-27, KS-28, KS-30, KS-31, KS-33) deferred to follow-up initiative
- **Replan 2026-04-26 (D-36..D-43):** Phase 1 replanned to address Codex `01-REVIEWS.md`. Key changes:
  - **D-36/D-37/D-38 (HIGH-1..3):** New Plan 00 (Wave 0) implements `--arm-b-base bare` flag on `validate.py` for true isolation A/B + pins `phase0.baseline.full` ledger entry. All per-KS plans use `--baseline bare --arm-b-base bare` for the bare ledger entry.
  - **HIGH-2:** Plan 09 split into raw fetch + parquet build steps (`fetch_market_history_props.py` + `build_market_history_player_markets.py`); acceptance gates on both.
  - **HIGH-3:** Plan 09 snapshot labels renamed `open_*` → `prior_*` to honestly describe API semantics.
  - **HIGH-4:** Plan 11 now uses `--baseline bare --label p1.aggregate.full` (no `--set`) and computes Phase-1-vs-Phase-0 delta from ledger entries.
  - **D-39 (MEDIUM-1):** KS-03 hypothesis widened to cover `_apply_matchup` rushing branch (per D-16b).
  - **D-40 (MEDIUM-2):** Per-KS commit cadence revised to "promotion-state commit per plan" with standardized message format.
  - **D-41 (MEDIUM-3):** Plan 04 test path corrected to `tests/test_data/test_vegas/`; Plan 05 API ref corrected to `Preprocessor().compute_play_outcomes()`.
  - **D-42 (MEDIUM-4):** Plan 07 widened to patch the legacy non-roster paths in `_resolve_pass`/`_resolve_run` (per D-15b).
  - **D-43 (LOW polish):** Plan 08 preflight uses existing `tests/test_data/test_pff/test_tier_engine.py:848` behavior test instead of ad-hoc grep; phase logs directory created in Wave 0.
  - Plan count: 11 → 12 (added Plan 00).

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none yet)* | | | |

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 1 context gathered
Resume file: --resume-file
