# Phase 1 — Promotion Notes

This file tracks per-KS promotion decisions across Phase 1. Each `## KS-XX`
section records the A/B ledger entries, the hard-floor + promotion-bar
evaluation, and the resulting decision (PROMOTED / SHIPPED-NO-OP / BLOCKED).

Hard floor (D-31): Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05 for BOTH the
`p1.ksXX.bare` and `p1.ksXX.full` ledger entries. Promotion bar for medium-large
items (D-31): KS Δ on the primary target ≤ -0.01.

---

## KS-01

**Decision: SHIPPED-NO-OP**

**Date:** 2026-04-26
**Plan:** 01-01
**Code change:** `_tackled_short_preserve_distribution` per D-09; gated behind
`phase1_ks_flags.ks01_preserve_distribution.enabled` (Cycle 3 D-45). Both
`_resolve_pass` and `_resolve_run` RZ TD-gate failure branches use the new
helper when the flag is on; legacy `_tackled_short` preserved as the
else-branch.

### Ledger results

| Entry | Δ rank_corr | Δ weekly_mae | Δ season_mae | Δ fpts_ks | Hard floor (D-31)? |
|-------|-------------|--------------|--------------|-----------|--------------------|
| p1.ks01.bare | +0.0011 | -0.002 | -0.063 | +0.000 | PASS |
| p1.ks01.full | +0.0004 | +0.003 | +0.046 | +0.000 | PASS |

### QB pass_yards primary-target detail

Phase-0 reference (`phase0.baseline.full` Arm B): KS = 0.353, mean bias = -28.32 yd/g.

| Season | bare A | bare B | bare ΔKS | full A | full B | full ΔKS | full B mean (yd/g) |
|--------|--------|--------|----------|--------|--------|----------|---------------------|
| 2022 | 0.34 | 0.35 | +0.00 | 0.34 | 0.34 | -0.00 | 189.7 (-28.0) |
| 2023 | 0.35 | 0.35 | -0.00 | 0.37 | 0.37 | +0.00 | 192.0 (-25.0) |
| 2024 | 0.38 | 0.38 | +0.00 | 0.36 | 0.35 | -0.01 | 196.0 (-22.5) |

QB pass_yards mean bias (Arm B) is essentially unchanged from Phase-0:
~-28.5 / -16.0 / -27.0 in bare; ~-28.0 / -25.0 / -22.5 in full. The mechanism
fires only on RZ TD-gate failures, so per-game stat impact at 200 sims is
below detection threshold.

### Promotion-bar evaluation (D-31, medium-large)

QB pass_yards KS Δ on the `p1.ks01.full` entry is ~-0.00 averaged across
seasons (best season -0.01 in 2024, no movement in 2022/2023). The promotion
bar of "≤ -0.01" is not cleanly met. Per D-31 "If hard floor passes but KS
doesn't move, mark as 'shipped no-op' and continue — the bug fix is correct
even if KS doesn't budge."

### Decision rationale

- Hard floor passes on BOTH ledger entries (no rank_corr / MAE regression).
- The bug fix is correct (preserves the sampled distribution per D-09).
- KS movement is below detection threshold; KS-04 / KS-15 will stack on top.
- D-26 mandates KS-01 → KS-04 → KS-15 dependency order; KS-01 must ship first.

**Action:** flip `phase1_ks_flags.ks01_preserve_distribution.enabled` from
`false` to `true` in `config/defaults.yaml` (per D-45). Plan 02 (KS-04) and
Plan 07 (KS-15) build on this foundation.

### Logs

- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks01.bare.log`
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks01.full.log`

### Commits

- Task 1 (RED): `80d8d11` — `test(01-01): add failing tests for KS-01 RZ TD-gate distribution preservation`
- Task 2 (GREEN): `9f7b588` — `feat(01-01): implement KS-01 _tackled_short_preserve_distribution per D-09`
