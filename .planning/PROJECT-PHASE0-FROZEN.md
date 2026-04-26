# Phase-0 Frozen Baseline Reference

**Pinned:** 2026-04-26 (Wave 0 of Phase 1 — Plan 00 Task 6)
**Defaults snapshot commit:** `9b8ab9801104221ee790a81063907dbdade3bba7` (this commit's parent — Plan 00 promotion-state commit)
**Validation command:** `validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE --baseline bare --label phase0.baseline.full`
**Ledger entries (target):** `phase0.baseline.full`, `phase0.baseline.bare`

## Why this exists

Per `01-REVIEWS.md` HIGH-4 and the revised D-32 in `01-CONTEXT.md`, Phase 1's
end-of-phase aggregate validation (Plan 11) needs a frozen reference to compare
against. This document captures that reference and the exact validation command
that produced it.

## Pin run status

> **PINNED 2026-04-26 in main repo by orchestrator.** Both `phase0.baseline.full`
> and `phase0.baseline.bare` ledger entries are present at schema v5 with
> per-position-stat `stat_mean_bias` populated. Logs at:
> - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.log`
> - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.bare.log`
>
> **Worktree mode disabled for Phase 1** (`.planning/config.json :
> workflow.use_worktrees=false`) per user decision: `results/ab_ledger.json` is
> gitignored, so worktree writes do not propagate; running sequentially in the
> main repo sidesteps both the propagation issue and Wave 3's parallel-writer
> conflict risk.

## Pin commands (executed 2026-04-26, retained for reproducibility)

```bash
# Pin 1: Phase-0 reference (Arm A = bare, Arm B = current promoted defaults)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare \
  --label "phase0.baseline.full"

# Pin 2: Self-consistency check (Arm A = bare, Arm B = bare)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --label "phase0.baseline.bare"

# Inspect both entries
uv run python scripts/validate.py --show-ledger | grep -E "phase0\.baseline\.(full|bare)"
```

## Headline metrics (from `phase0.baseline.full` Arm B, n-weighted across 2022/2023/2024)

| Metric | Value |
|--------|-------|
| QB rank_corr (PPR) | 0.9503 |
| RB rank_corr (PPR) | 0.9211 |
| WR rank_corr (PPR) | 0.9294 |
| TE rank_corr (PPR) | 0.8765 |
| Aggregate rank_corr | 0.9193 |
| Aggregate weekly_mae | 3.850 |
| Aggregate season_mae | 24.604 |
| QB pass_yards KS | 0.353 |
| WR receiving_yards KS | 0.264 |
| RB rush_yards KS | 0.254 |
| QB pass_yards mean bias (yd/g) | -28.32 (target ±5 per TGT-09; biggest gap) |
| WR receiving_yards mean bias (yd/g) | -9.10 |
| TE receiving_yards mean bias (yd/g) | -3.97 |
| RB rush_yards mean bias (yd/g) | -1.00 |

## Self-consistency check (`phase0.baseline.bare`)

`phase0.baseline.bare` ran with Arm A == Arm B (both bare engines). Expected
result: zero delta on rank_corr, MAE, KS for every position.

| Metric | Δ (Arm B − Arm A) | OK? |
|--------|-------------------|-----|
| Aggregate rank_corr | +0.0006 | ✓ (within RNG noise, sub-seed differences) |
| Aggregate weekly_mae | -0.005 | ✓ |
| Aggregate season_mae | -0.029 | ✓ |
| Aggregate ks_delta | +0.001 | ✓ |

## Plan 11 contract

The end-of-phase aggregate validation (Plan 11) MUST:

1. Run `validate.py --baseline bare --label p1.aggregate.full` AFTER all KS
   plans land and `defaults.yaml` has been updated to reflect promotions.
2. Read the Arm B metrics from BOTH `phase0.baseline.full` (this entry) AND
   `p1.aggregate.full` (the Plan 11 entry).
3. Compute Δ = `p1.aggregate.full Arm B` − `phase0.baseline.full Arm B`.
4. Evaluate Δ against the success criteria in ROADMAP.md `## Phase 1` and the
   hard floor in PROJECT.md.

## Schema dependencies

- `SeasonMetrics.stat_mean_bias` field (Cycle 3 — schema v5) is required for
  Plan 11 to evaluate Phase 1 success criterion 1 directly from ledger entries.
  Both pin entries above will be written under schema v5 because they're
  produced by the post-Plan-00 `validate.py` (which uses
  `CURRENT_LEDGER_SCHEMA_VERSION = 5`).
