---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_plan
stopped_at: Completed 02-09-PLAN.md (Phase 2 WALKED-BACK at aggregate)
last_updated: "2026-04-27T16:08:17Z"
last_activity: 2026-04-27
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 21
  completed_plans: 21
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-26)

**Core value:** Distribution shape (KS) on stat outputs that matters for season-long projections — without giving back the rank_corr / MAE wins we already shipped. Hard floor: any change must NOT regress rank_corr by >0.005 or MAE by >0.05.
**Current focus:** Phase 02 complete (WALKED-BACK at aggregate); ready to advance to Phase 03

## Current Position

Phase: 3
Plan: Not started
Status: Ready to plan
Next: Phase 03 (KS-priority retune of off-by-default PFF slices) — entry baseline = Phase-1-final-stack
Last activity: 2026-04-27

Progress: [██████████] 100% (Phase 2 complete; Phase 3 not yet started)

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02 | 9 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: N/A (no execution yet)

*Updated after each plan completion*
| Phase 01 P01 | 28.5 min | 4 tasks | 3 files |
| Phase 01 P02 | 95min | 4 tasks | 3 files |
| Phase 01 P09 | 2h 5m | 7 tasks | 13 files |
| Phase 01 P03 | 30 min | 4 tasks | 5 files |
| Phase 01 P04 | 27min | 4 tasks | 5 files |
| Phase 01 P05 | 90min | 4 tasks | 11 files |
| Phase 01 P06 | 40min | 4 tasks | 6 files |
| Phase 01 P07 | 32min | 4 tasks | 4 files |
| Phase 01 P08 | 1h 8m | 3 tasks | 2 files |
| Phase 01 P10 | 13 min | 2 tasks | 3 files |
| Phase 01 P11 | 19.4 min | 4 tasks | 5 files |
| Phase 02 P01 | 30 | 4 tasks | 6 files |
| Phase 02 P02 | 370min | 4 tasks | 10 files |
| Phase 02 P03 | 61min | 5 tasks | 13 files |
| Phase 02-structural-per-stat-calibration P04 | 90min | 3 tasks | 7 files |
| Phase 02-structural-per-stat-calibration P06 | 40m | 3 tasks | 6 files |
| Phase 02-structural-per-stat-calibration P07 | 120 | 4 tasks | 17 files |
| Phase 02-structural-per-stat-calibration P08 | 95 min | 3 tasks | 4 files |
| Phase 02-structural-per-stat-calibration P09 | ~95 min (incl. interrupted reverse-ablation; finalized inline) | 3 tasks | 7 files |

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
- [Phase ?]: [Phase 01]: Plan 01-03 KS-03: BLOCKED per D-31 hard floor — bare weekly_mae +0.164 > +0.05 limit. Same mechanism as KS-04: per-player anchor exposes bare-mode under-projection that legacy * 10.0 was masking. Flag-based rollback per D-45: phase1_ks_flags.ks03_dynamic_yard_anchor.enabled stays false in defaults.yaml; new code path stays in game_context.py but dormant. KS-15 (Plan 07) unblocked — operates on different mechanism per D-14/D-15.
- [Phase ?]: [Phase 01]: Plan 01-04 KS-05: BLOCKED per D-31 hard floor — bare weekly_mae +0.154 > +0.05 limit. CRITICAL: both A/B runs report props:none (no historical PFF props parquet for 2022/2023/2024 per forward-only PFF endpoint contract); KS-05 _apply_recv_yds path never fires in either A/B. The bare-isolation MAE failure is collateral from required vegas.enabled+props.enabled activation per D-44 bare_config_dict pattern (VEG-01 ITT pace + VEG-02 spread pass-rate), NOT from KS-05 logic. Flag-based rollback per D-45: phase1_ks_flags.ks05_props_recv_yds_fix.enabled stays false in defaults.yaml; new code path stays in props_engine.py but dormant. KS-15/KS-06/KS-07 unblocked.
- [Phase ?]: [Phase 01]: Plan 01-05 KS-06 PROMOTED under relaxed full-stack-only gate — full hard floor PASSES (Δ rank_corr +0.0008, Δ weekly_mae -0.004, Δ fpts_ks +0.000); WR/TE receiving_yards primary target non-regressive (Δ ≈ 0 across 3 seasons). Bare hard-floor failure (+0.068 weekly_mae) informational only per gate-relaxation decision. Three D-19 sub-fixes promoted: completion-only filter on team buckets (preprocessor.py), [5,18) integer fallback (play_resolver.py), MIN_PLAYER_PLAYS = 5 → 3 (player_builder.py). KS-06 is FIRST plan in Phase 1 to clear the relaxed full-stack hard floor cleanly with the new code path active. Flag default flipped to true in config/defaults.yaml. KS-07/15/29/32 unblocked.
- [Phase ?]: [Phase 01]: Plan 01-06 KS-07 PROMOTED — full hard floor PASSES (Δ rank_corr -0.0012, Δ weekly_mae +0.003, Δ fpts_ks +0.000); D-30 small-gain primary-target non-regression bar met (WR Δ ≈ 0; TE flat in 2 of 3 seasons); success criterion #3 RB rush_yards Δ ≥ 0 across all 3 seasons. KS-07 is 2nd plan in Phase 1 to clear relaxed gate cleanly with new code active. Flag default flipped to true in config/defaults.yaml. Bare regression (+0.064 weekly_mae) informational per gate-relaxation decision. KS-15/29/32 unblocked.
- [Phase ?]: KS-15 PROMOTED under relaxed gate (full hard floor passes); SHIPPED-NO-OP on QB pass_yards primary-target KS bar (Δ avg ~0). D-15 boost-zeroing implemented behaviorally; D-15b legacy non-roster paths patched per Codex MEDIUM-4
- [Phase 01]: [Phase 01]: Plan 01-08 KS-29 PROMOTED — pff.team_context.enabled=true with pass_rate_sensitivity=0.03 (best of {0.03, 0.05, 0.08} sweep); full hard floor passes (Δ rank_corr -0.0007, Δ weekly_mae -0.005); WR/TE recv_yds non-regressive primary target; bare-mode QB pass_yards regression informational per Gate Relaxation Decision; D-22 honored via existing TestApplyTeamContext::test_qb_unchanged behavior test. 2,131 tests still green. Last per-KS code/config plan in Phase 1 before Plan 10 (KS-32 measure) and Plan 11 (aggregate).
- [Phase ?]: Phase 01-10: KS-32 MEASURED-NO-CHANGE per D-24 — plays_per_team in target band and nfl_pass_attempts in band; reducing CLOCK_PASS_INCOMPLETE 5 to 3 contraindicated. p1.ks32.measure ledger #104 confirms post-Phase-1 stack matches phase0.baseline.full within noise. KS-32 satisfies REQUIREMENTS delivered definition with no source change.
- [Phase ?]: Phase 01-11: Phase 1 SHIPPED-NO-OP — aggregate p1.aggregate.full (#105) vs phase0.baseline.full (#82): hard floor PASSES (rank_corr Δ -0.0004, weekly_mae Δ +0.0142) but headline criteria 1-3 (QB pass_yards bias / KS, RB rush_yards KS) MISS. Headline finding: QB pass_yards mean bias REGRESSED -10.99 yd/g (-28.30 → -39.29; target was within ±10). KS-01 mechanism is opposite-direction so reverting it would not restore baseline. Walk-back NOT executed in Plan 11 (D-32 trigger is hard-floor regression, not headline-criteria miss). Recommended posture: fold QB pass_yards mean-bias closure into Phase 2 KS-09 (per-stat residual_calibration). Phase 2 entry baseline = ledger entry p1.aggregate.full Arm B.
- [Phase 02]: Plan 02-05 KS-10 SHIPPED — TE elite tier (>14 fpts) + per-position caps {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8} in residual_calibration; full hard floor PASSES (rank_corr +0.0001, weekly_mae -0.002); TE receptions KS -0.01 in 2024; Codex MEDIUM 7 TE|elite|market_medium n_rows=18 in 2024 artifact; TE min_bucket_rows=10 (deviation from plan's 100 — elite TEs rare ~20 rows/season); flag default flipped to enabled=true.
- [Phase 02]: Plan 02-02 KS-08 SHIPPED — simulator-weight floor=0.20 applied post-normalize in dynamic_blend._artifact_weights(); bundled weights_2023.json (7 learned + 14 fallback) and weights_2024.json (17 learned + 55 fallback) re-fit with --simulator-weight-floor 0.20; sweep {0.20, 0.30, 0.40} × {bare, full} = 6 entries + 1 promoted (#107-#113); floor=0.20 selected via D-05 (smallest passing hard floor + non-zero KS improvement); TE recv_yds -0.01 all 3 seasons; promoted A/B rank_corr -0.0004 (within 1e-3 of sweep -0.0008); 2142 tests pass.
- [Phase ?]: KS-13 SHIPPED-NO-OP: dual-gate conjunction; probe→Path B; hard floor passes but fpts KS Δ≈0 (symmetric noise does not close systematic KS gap)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none yet)* | | | |

## Session Continuity

Last session: 2026-04-27T12:43:38.758Z
Stopped at: Completed 02-07-PLAN.md (KS-13 SHIPPED-NO-OP)
Resume file: None
