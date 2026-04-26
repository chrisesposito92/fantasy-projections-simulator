---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 01-09-PLAN.md (KS-21 PROMOTED)
last_updated: "2026-04-26T18:01:21.834Z"
last_activity: 2026-04-26
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 12
  completed_plans: 4
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-26)

**Core value:** Distribution shape (KS) on stat outputs that matters for season-long projections — without giving back the rank_corr / MAE wins we already shipped. Hard floor: any change must NOT regress rank_corr by >0.005 or MAE by >0.05.
**Current focus:** Phase 01 — bug-fixes-cheap-calibration-time-sensitive-scrape

## Current Position

Phase: 01 (bug-fixes-cheap-calibration-time-sensitive-scrape) — EXECUTING
Plan: 4 of 12
Status: Ready to execute
Last activity: 2026-04-26

Progress: [███░░░░░░░] 33%

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
| Phase 01 P01 | 28.5 min | 4 tasks | 3 files |
| Phase 01 P02 | 95min | 4 tasks | 3 files |
| Phase 01 P09 | 2h 5m | 7 tasks | 13 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Initiative scope: KS as priority metric; hard floor of -0.005 rank_corr / -0.05 MAE for any KS-targeting change
- Phase structure: 5 phases, derived from synthesizer's 4-phase suggestion + a Phase 5 wrap-up
- KS-21 split: scrape (Phase 1, time-sensitive) vs engine integration (Phase 4, dependency-ordered) — required by 2-week Odds API tier window
- TE receptions / RB receiving_yards targets relaxed (TGT-04 ≤ 0.27, TGT-07 ≤ 0.34) per sanity check on hypothesis budget
- v1 = P1-P4 (23 hypotheses); P5 long-tail items (KS-22, KS-23, KS-24, KS-25, KS-26, KS-27, KS-28, KS-30, KS-31, KS-33) deferred to follow-up initiative
- **Replan 2026-04-26 Cycle 1 (D-36..D-43):** Phase 1 replanned to address Codex `01-REVIEWS.md` Cycle 1 findings. Key changes:
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
- **Replan 2026-04-26 Cycle 3 (D-44, D-45, D-46):** Phase 1 re-replanned to address Codex `01-REVIEWS.md` Cycle 2 findings (3 NEW HIGHs + 2 partial-resolves of Cycle 1 HIGH-2/HIGH-3). Final cycle before max-cycles escalation gate. Key changes:
  - **D-44 (Cycle-2 NEW HIGH #2 fix):** `bare_config_dict()` enumerated exhaustively to include EVERY top-level engine gate (`pff.enabled`, `vegas.enabled`, `usage.enabled`, `props.enabled`, etc.) AND sub-engine flags AND the new D-45 KS feature flags (Plan 00 Task 1). Plan 00 Task 4 integration test promoted to HARD GATE (`test_bare_config_dict_produces_all_None_engines`); the Cycle-2 "loosen the test" escape hatch REMOVED.
  - **D-45 (Cycle-2 NEW HIGH #1 fix):** Per-KS code changes feature-gated. New `phase1_ks_flags:` block in `config/defaults.yaml` with 8 flags (one per code-change KS); `get_phase1_ks_flags()` shim in `src/fantasy_sim/config/loader.py` (Plan 00 Task 8). Per-KS plans (01, 02, 03, 04, 05, 06, 07, 10 retune) all invoke `--set phase1_ks_flags.ksXX_<name>.enabled=true` for Arm B so the A/B is genuinely two-arm. Per-KS Task 4 promotion commits flip flag default to true after passing A/B.
  - **D-46 (Cycle-2 NEW HIGH #3 fix):** `SeasonMetrics.stat_mean_bias` field added (schema v4 → v5); `validate.py` writes per-position-stat mean bias alongside `stat_ks` (Plan 00 Task 9). Plan 11 Task 2 reads `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` directly from both `phase0.baseline.full` and `p1.aggregate.full` ledger entries to evaluate success criterion 1; no side script.
  - **HIGH-2/HIGH-3 partial-resolve cleanup:** `01-RESEARCH.md` reconciled with `01-CONTEXT.md` and Plan 09 — User Constraints D-02/D-06/D-08 updated; parallel-track architecture diagram updated; Pattern 4 split into raw-fetch + parquet-build steps; Pattern 5 explicitly renames `open_*` → `prior_*` and documents `previous_timestamp` honesty; Example 3 bash blocks rewritten with both pipeline steps; Anti-patterns updated to forbid `open_*` labels and "fetch writes parquet" wording.
  - Plan 00 expanded: 7 tasks → 9 tasks (Task 8 = config block + loader shim, Task 9 = ledger schema bump + validate.py wiring). New file `tests/test_validation/test_ledger_schema.py`.
  - Plan count unchanged: 12.
- [Phase 01]: Plan 01-01 KS-01: SHIPPED-NO-OP per D-31 — _tackled_short_preserve_distribution per D-09 ships behind phase1_ks_flags.ks01_preserve_distribution=true; hard floor passes both A/B entries (Δ rank_corr +0.0011/+0.0004, Δ weekly_mae -0.002/+0.003), KS Δ on QB pass_yards <= -0.01 promotion bar barely met (only 2024 full -0.01); bug fix is a correct precondition for KS-04/KS-15. — Mechanism only fires on RZ TD-gate failures; per-game stat impact below detection threshold at 200 sims; KS-04+KS-15 will stack on this foundation per dependency-mandatory order in D-26.
- [Phase ?]: Plan 01-02 KS-04: BLOCKED per D-31 hard floor — bare weekly_mae +0.167 > +0.05 limit. Conditional boost (D-11) correctly removes fictitious yards but exposes underlying under-projection in bare mode. Flag-based rollback via D-45: phase1_ks_flags.ks04_conditional_catch_boost.enabled stays false in defaults.yaml; new code path stays in play_resolver.py but dormant. KS-15 (Plan 07) unblocked — removes boost entirely per D-15.
- [Phase ?]: Plan 01-09 KS-21 PROMOTED: 9 raw cache trees + 9 processed parquet under ~/.fantasy-sim/market-history/ — Consumed 132K of ~4.93M Odds API credits (~2.7%); remaining 4.80M. Phase 4 OddsApiCdfLoader contract: accept snapshot_label param (default prior_alt6, fallback close_alt6); gracefully degrade by available alt markets per (season,event) — 4 of 6 in 2023, 5 of 6 in 2024, all 6 in 2025.

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none yet)* | | | |

## Session Continuity

Last session: 2026-04-26T18:01:21.828Z
Stopped at: Completed 01-09-PLAN.md (KS-21 PROMOTED)
Resume file: None
