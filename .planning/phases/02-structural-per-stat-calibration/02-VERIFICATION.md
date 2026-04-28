---
phase: 02-structural-per-stat-calibration
verified: 2026-04-27T18:00:00Z
status: passed
score: 8/8 acceptance checks verified
overrides_applied: 0
terminal_state: WALKED-BACK
---

# Phase 2: Structural Per-Stat Calibration — Verification Report

**Phase Goal:** Address the architectural blocker that `residual_calibration` and `dynamic_blend` adjust `fpts` only, leaving stat distributions un-calibrated. Add a per-stat residual_calibration layer, raise `dynamic_blend` simulator weight off zero, raise `tier_engine` reliability cap for high-touch players, and refine the calibration knobs (per-position max_abs_adjustment, TE elite tier, ff_opportunity width, share-normalization residual, thin-bucket Bayesian shrinkage). With Phase 1 bug noise removed, structural-fix measurements are now interpretable.

**Verified:** 2026-04-27T18:00:00Z
**Status:** passed
**Terminal State:** WALKED-BACK (intentional, documented)
**Re-verification:** No — initial verification

---

## Verification Context: Two Valid Framings

This phase has a non-standard terminal state. The verification question splits cleanly into two framings:

1. **Did Phase 2 ship the architectural changes its goal called for?** YES — all 7 KS items were implemented, tested, A/B-validated, code is in tree.
2. **Did Phase 2 produce a net-positive change to the runtime baseline?** NO — the full-stack composition failed the Phase-2-vs-Phase-1 hard floor (Δ rank_corr = −0.00512, limit −0.005), with 6 of 8 priority stats regressing on KS. All 7 `phase2_ks_flags` reverted to `enabled: false`.

The walk-back is documented and intentional. The ROADMAP success criteria (SC-2, SC-3, SC-4) were not achieved in the runtime baseline; SC-1, SC-5 were achieved (architecture exists, hard floor passes post-walkback). This VERIFICATION.md reports the honest outcome of both framings.

---

## Acceptance Checks

### 1. Nine SUMMARY.md files exist (one per plan)

| Plan | File | Status |
|------|------|--------|
| 01 | `01-phase2-scaffolding-and-entry-baseline-SUMMARY.md` | VERIFIED |
| 02 | `02-ks08-dynamic-blend-simulator-floor-SUMMARY.md` | VERIFIED |
| 03 | `03-ks09-per-stat-residual-calibration-SUMMARY.md` | VERIFIED |
| 04 | `04-ks14-thin-bucket-shrinkage-SUMMARY.md` | VERIFIED |
| 05 | `05-ks10-per-position-caps-te-elite-tier-SUMMARY.md` | VERIFIED |
| 06 | `06-ks11-tier-engine-position-reliability-SUMMARY.md` | VERIFIED |
| 07 | `07-ks13-ff-opportunity-prior-width-SUMMARY.md` | VERIFIED |
| 08 | `08-ks12-share-normalization-residual-SUMMARY.md` | VERIFIED |
| 09 | `09-phase2-aggregate-validation-SUMMARY.md` | VERIFIED |

All 9 plans executed. Evidence: 9 SUMMARY.md files present on disk.

### 2. config/defaults.yaml has all 7 phase2_ks_flags.*.enabled = false

All 7 flags confirmed `enabled: false` post-walkback:

| Flag | Value | Walk-back comment |
|------|-------|-------------------|
| `ks08_dynamic_blend_simulator_floor.enabled` | `false` | "WALKED-BACK 2026-04-27 (was SHIPPED in isolation; reverted at aggregate)" |
| `ks09_per_stat_residual_calibration.enabled` | `false` | "WALKED-BACK 2026-04-27 (highest harm_score +0.0072 in iter-1 ablation)" |
| `ks10_per_position_caps.enabled` | `false` | "WALKED-BACK 2026-04-27 (was SHIPPED in isolation; reverted at aggregate)" |
| `ks11_position_reliability.enabled` | `false` | "WALKED-BACK 2026-04-27 (was SHIPPED in isolation; reverted at aggregate)" |
| `ks12_share_normalization_residual.enabled` | `false` | "WALKED-BACK 2026-04-27 (was SHIPPED in isolation; reverted at aggregate)" |
| `ks13_ff_opportunity_prior_width.enabled` | `false` | "NO-OP 2026-04-27 (Path B; never moved fpts KS; consistent with walk-back)" |
| `ks14_thin_bucket_shrinkage.enabled` | `false` | "WALKED-BACK 2026-04-27 (was SHIPPED in isolation; reverted at aggregate)" |

Status: VERIFIED

### 3. Walk-back marker file exists

`logs/p2_walkback_complete.marker` confirmed present with full content:
- `walkback_status: WALKED-BACK`
- `finalized: 2026-04-27`
- `final_promoted_set: []`
- `reverted_flags: [ks08, ks09, ks10, ks11, ks12, ks13, ks14]`
- `post_walkback_verification` block confirming byte-equivalence to Phase-1-final-stack

Status: VERIFIED

### 4. test_aggregate.py hard-floor assertion passes

`tests/test_validation/test_aggregate.py` — 4 tests, all PASSED:
- `test_phase2_vs_phase1_delta_within_hard_floor_post_walkback` — PASSED (Δ rank_corr = −0.00079, well within −0.005 limit)
- `test_phase2_qb_pass_yards_bias_d14_evaluation` — PASSED
- `test_reverse_ablation_marginal_delta_computation` — PASSED
- `test_reverse_ablation_coupled_cluster_pair_revert` — PASSED

Note: The walkback marker note states the iter-1 partial-revert entry (KS-09 off, others on) was expected to fail by 0.000147. The final re-pinned `p2.aggregate.full` entry (all flags off, byte-equivalent to Phase-1-final-stack) passes the hard floor with Δ rank_corr = −0.00079. The assertion fires against the final re-pinned entry, which passes correctly.

Status: VERIFIED

### 5. REQUIREMENTS.md marks all 7 KS-XX as INVALIDATED-AT-AGGREGATE / NO-OP

| Requirement | Status in REQUIREMENTS.md |
|-------------|--------------------------|
| KS-08 | "Tested — INVALIDATED at aggregate (architecture preserved)" |
| KS-09 | "Tested — INVALIDATED at aggregate (architecture preserved as Phase 3+ lever)" |
| KS-10 | "Tested — INVALIDATED at aggregate (architecture preserved)" |
| KS-11 | "Tested — INVALIDATED at aggregate (architecture preserved)" |
| KS-12 | "Tested — INVALIDATED at aggregate (architecture preserved)" |
| KS-13 | "Tested — NO-OP (architecture preserved)" |
| KS-14 | "Tested — INVALIDATED at aggregate (architecture preserved)" |

Footer: "Last updated: 2026-04-27 — Phase 2 closure: KS-08 through KS-14 marked INVALIDATED-AT-AGGREGATE / NO-OP (architecture preserved in tree as Phase 3+ levers)."

Status: VERIFIED

### 6. PROJECT.md Failed Hypotheses section populated and discoverable

`PROJECT.md` line 57 section `### Failed Hypotheses (do not retry as-is)` contains a full table with one row per hypothesis (KS-08 through KS-14), documenting:
- What was tried
- Status (INVALIDATED at aggregate / NO-OP)
- Phase (02 for all)
- Why it failed
- What architecture is preserved

Key Decisions table also includes: "Phase 2 walked back at aggregate (2026-04-27)" with full rationale.

Status: VERIFIED

### 7. pytest is green — 2,195 tests

```
2195 passed, 51 warnings in 38.25s
```

Run confirmed: `uv run pytest tests/ -x -q --tb=no` — all 2,195 tests pass. No failures or errors.

Status: VERIFIED

### 8. KS-09 corrected_<stat> infrastructure preserved in tree

Verified in production source (`src/fantasy_sim/scoring/residual_calibration.py`):
- `ARTIFACT_SCHEMA_VERSION = 2` (v1 = fpts-only; v2 = fpts + per-stat stat_corrections)
- `stat_corrections` block read and written in artifact fit/load paths
- `corrected_<stat>` columns written at lines 612 and 623 in `adjust_week()`
- `_KS12_SHARE_NORM_RESIDUAL` flag-gate pattern confirmed in `src/fantasy_sim/data/player_builder.py`
- `_expected_active_share_factor()` function at line 794 of `player_builder.py`
- `MIN_BACKUP_RECEIVING_SHARE = 0.05` constant at line 48
- KS-11 `position_reliability` config block confirmed in `src/fantasy_sim/data/pff/tier_engine.py` (lines 957, 963)
- KS-10 `USAGE_TIER_THRESHOLDS_4` with elite tier at 14.0 fpts confirmed in `residual_calibration.py`
- KS-08 `--simulator-weight-floor` CLI flag confirmed in `scripts/fit_dynamic_blend_weights.py` (line 266)
- KS-13 fitter/probe pipeline confirmed in Plan 07 SUMMARY (artifacts in tree, flags off)
- KS-14 `_effective_min_bucket_plays()` + `_apply_bayesian_shrinkage()` confirmed in SUMMARY; flag-gated

All 7 KS architectures are in tree with flags off — the code exists but is not active at runtime.

Status: VERIFIED

---

## Observable Truths (ROADMAP Success Criteria Assessment)

The ROADMAP defines 5 success criteria for Phase 2. Given the WALKED-BACK terminal state, they are assessed against both framings.

| SC | Truth | Architecture Exists | Runtime Achieved | Notes |
|----|-------|--------------------|--------------------|-------|
| SC-1 | Per-stat residual_calibration ships: stat columns receive post-sim correction (not just fpts) | VERIFIED | GATED (flag off) | `corrected_<stat>` infrastructure exists; not active at runtime until flag flipped |
| SC-2 | TE receptions KS recovers from ~0.35 to ≤ 0.27 | VERIFIED (mechanism exists) | NOT ACHIEVED | Full-stack aggregate regressed TE receptions KS +0.0195 |
| SC-3 | Aggregate fpts KS held ≤ 0.18 across all positions | VERIFIED (mechanism exists) | NOT ACHIEVED | Full-stack: fpts_ks went 0.20963 → 0.21992 (+0.0103) |
| SC-4 | WR receptions KS reduced from ~0.28 to ≤ 0.24 | VERIFIED (mechanism exists) | NOT ACHIEVED | Full-stack WR receptions KS: ~unchanged (−0.0005, within noise) |
| SC-5 | rank_corr regression ≤ 0.005 AND MAE regression ≤ 0.05 vs Phase-1-promoted baseline | VERIFIED | VERIFIED (post-walkback) | Post-walkback: Δ rank_corr = −0.00079, Δ MAE = +0.00018 — both well within limits |

**Assessment:** SC-1 (architecture) and SC-5 (hard floor post-walkback) achieved. SC-2, SC-3, SC-4 (runtime KS targets) not achieved because the full-stack composition required reverting all flags. This is the documented and expected outcome of a WALKED-BACK phase.

---

## Artifacts in Tree

| Artifact | Description | Status |
|----------|-------------|--------|
| `src/fantasy_sim/scoring/residual_calibration.py` | KS-09 corrected_<stat> infrastructure + KS-10 per-position caps + TE elite tier | VERIFIED (substantive, flag-gated) |
| `src/fantasy_sim/data/player_builder.py` | KS-12 `_expected_active_share_factor()` + `MIN_BACKUP_RECEIVING_SHARE` | VERIFIED (substantive, flag-gated) |
| `src/fantasy_sim/data/pff/tier_engine.py` | KS-11 `position_reliability` config block | VERIFIED (substantive, flag-gated) |
| `scripts/fit_dynamic_blend_weights.py` | KS-08 `--simulator-weight-floor` CLI flag | VERIFIED |
| `scripts/fit_residual_calibration.py` | KS-09 per-stat artifact fitter | VERIFIED (referenced in SUMMARY) |
| `tests/test_validation/test_aggregate.py` | Phase-2-vs-Phase-1 delta computation + hard-floor assertion | VERIFIED (4/4 pass) |
| `tests/test_validation/test_config.py` | `test_phase2_ks_flags_present_and_default_false` — promoted set empty | VERIFIED (passes) |
| `tests/test_scoring/test_residual_calibration.py` | KS-09 corrected_<stat> column tests (8+ tests) | VERIFIED (in full passing suite) |
| `tests/test_validation/test_validate_corrected_stat_routing.py` | KS-09 corrected_<stat> validate.py routing tests | VERIFIED (in full passing suite) |
| `config/defaults.yaml` | All 7 `phase2_ks_flags.*.enabled = false` | VERIFIED |
| `logs/p2_walkback_complete.marker` | Walk-back finalization marker | VERIFIED |
| `logs/PROMOTION-NOTES.md` | Per-KS promotion decisions + aggregate walk-back record | VERIFIED |
| `logs/p2_phase2_vs_phase1_delta.json` | Iter-1 aggregate delta artifact | VERIFIED (file present) |
| `logs/p2_reverse_ablation.json` | Iter-1 marginal deltas per KS | VERIFIED (file present) |
| `logs/p2_aggregate_full.log` | Initial p2.aggregate.full ledger entry (#129) | VERIFIED |
| `logs/p2_aggregate_full_walkback.log` | Post-iter-1 KS-09-off entry (#136) | VERIFIED |
| `.planning/REQUIREMENTS.md` | All 7 KS marked INVALIDATED-AT-AGGREGATE / NO-OP | VERIFIED |
| `.planning/PROJECT.md` | `### Failed Hypotheses` table populated with KS-08..KS-14 | VERIFIED |

---

## Anti-Patterns Scan

Scanned key Phase 2 modified files for placeholder/stub patterns.

All flag-gated `return early` paths in production code are intentional guard clauses (e.g., `if not ks09_enabled: return row unchanged`), not stub placeholders. No unimplemented TODOs found in the critical paths. The `enabled: false` defaults are the walk-back mechanism, not missing implementation.

No blockers found. No warnings flagged.

---

## Behavioral Spot-Checks

Step 7b: Performed against `test_aggregate.py` (the primary runnable artifact for this phase).

| Behavior | Result | Status |
|----------|--------|--------|
| Hard-floor assertion fires and passes | 4/4 tests pass in 0.48s | PASS |
| Full pytest suite green at 2,195 | `2195 passed, 51 warnings in 38.25s` | PASS |
| `phase2_ks_flags` all false in live config | Confirmed via `grep` against `config/defaults.yaml` | PASS |
| Walk-back marker file exists | Confirmed present at `logs/p2_walkback_complete.marker` | PASS |

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| KS-08 | dynamic_blend simulator-weight floor | INVALIDATED at aggregate (architecture preserved) | PROMOTION-NOTES.md + PROJECT.md Failed Hypotheses |
| KS-09 | per-stat residual_calibration | INVALIDATED at aggregate (architecture preserved as Phase 3+ lever) | corrected_<stat> in residual_calibration.py |
| KS-10 | per-position caps + TE elite tier | INVALIDATED at aggregate (architecture preserved) | USAGE_TIER_THRESHOLDS_4 in residual_calibration.py |
| KS-11 | tier_engine position_reliability | INVALIDATED at aggregate (architecture preserved) | position_reliability config block in tier_engine.py |
| KS-12 | share-normalization residual | INVALIDATED at aggregate (architecture preserved) | _expected_active_share_factor() in player_builder.py |
| KS-13 | ff_opportunity prior width | NO-OP (Path B; never moved fpts KS) | SUMMARY Plan 07: SHIPPED-NO-OP per D-30 |
| KS-14 | thin-bucket Bayesian shrinkage | INVALIDATED at aggregate (architecture preserved) | _effective_min_bucket_plays() + _apply_bayesian_shrinkage() |

All 7 requirements for this phase are closed in REQUIREMENTS.md with the correct INVALIDATED-AT-AGGREGATE / NO-OP status. No orphaned requirements.

---

## Summary

Phase 2 is correctly finalized in its WALKED-BACK terminal state. All 8 acceptance checks pass:

1. All 9 SUMMARY.md files exist — every plan was executed
2. All 7 `phase2_ks_flags` are `enabled: false` in `config/defaults.yaml`
3. Walk-back marker file is present and fully populated
4. `test_aggregate.py` hard-floor assertion passes (4/4 tests green)
5. REQUIREMENTS.md marks all 7 KS-XX as INVALIDATED-AT-AGGREGATE / NO-OP
6. PROJECT.md `### Failed Hypotheses` section is populated and discoverable
7. pytest green at 2,195 tests
8. KS-09 corrected_<stat> infrastructure (most valuable Phase 3+ lever) is preserved in tree

The walk-back is an honest, empirically grounded outcome: each per-KS A/B passed the hard floor in isolation, but the full-stack composition produced a "death by a thousand cuts" regression (Δ rank_corr = −0.00512, 6 of 8 priority stats KS-regressed, QB pass_yards mean bias worsened). Reverse-ablation iter-1 marginals were all within MC noise (|Δ| < 0.001 per item), confirming no single KS was responsible — the protocol-determined end-state was full revert.

The ROADMAP Success Criteria were partially achieved: SC-1 (architecture) and SC-5 (hard floor post-walkback) are satisfied; SC-2/SC-3/SC-4 (runtime KS targets) were not achieved at the aggregate level. This is the expected and documented outcome of a WALKED-BACK phase — the architecture exists for Phase 3+ to build on without re-implementing.

**Phase 3 inherits a clean entry baseline equal to the Phase-1-final-stack (all Phase 2 flags off = byte-equivalent to Phase 2 entry = Phase 1 final state).**

---

_Verified: 2026-04-27T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
