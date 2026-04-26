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

> **DEFERRED TO USER EXECUTION IN MAIN REPO.** This plan was executed in a
> parallel worktree (`agent-a9cef1594e25fe6b3`). The `results/ab_ledger.json`
> file is gitignored (per repo `.gitignore` line 19), so any pin runs executed
> here will not propagate to the main-repo ledger that downstream plans (01-11)
> consume. The pin runs MUST be re-executed in the main repo by the user (or a
> follow-up agent operating in the main repo) before any Phase 1 KS plan that
> depends on these labels begins execution.
>
> **Smoke verification done in worktree:** `validate.py --sims 2 --seasons 2024
> --scoring ppr --positions QB --baseline bare --arm-b-base bare --label
> phase0.smoke.bare` was executed end-to-end against the new `--arm-b-base bare`
> flag and confirmed:
> - The flag parses and routes correctly through Arm B construction.
> - `bare_config_dict()` produces a valid Arm B config that runs to completion.
> - The new `stat_mean_bias` field is populated in the persisted ledger entry.
> - All existing pipeline stages (build games, dual-arm sim, projection layers,
>   metric collection) work end-to-end with the new code paths.
>
> The smoke entry was deleted from the worktree ledger after verification.

## User action required (run in main repo, not worktree)

```bash
# Pin 1: Phase-0 reference (Arm A = bare, Arm B = current promoted defaults)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare \
  --label "phase0.baseline.full" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.full.log

# Pin 2: Self-consistency check (Arm A = bare, Arm B = bare)
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --label "phase0.baseline.bare" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/phase0.baseline.bare.log

# Inspect both entries
uv run python scripts/validate.py --show-ledger | grep -E "phase0\.baseline\.(full|bare)"
```

After the user runs these in the main repo, headline metrics from
`phase0.baseline.full` Arm B should be copied into the table below for
downstream reference.

## Headline metrics (from `phase0.baseline.full` Arm B)

(To be filled in by the user after running the pin commands in the main repo.)

| Metric | Value |
|--------|-------|
| QB rank_corr (PPR) | TBD |
| RB rank_corr (PPR) | TBD |
| WR rank_corr (PPR) | TBD |
| TE rank_corr (PPR) | TBD |
| Aggregate rank_corr | TBD |
| Aggregate weekly_mae | TBD |
| Aggregate season_mae | TBD |
| QB pass_yards KS | TBD |
| WR receiving_yards KS | TBD |
| RB rush_yards KS | TBD |
| QB pass_yards mean bias (yd/g) | TBD (read from `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]`; ledger schema v5) |

## Self-consistency check (`phase0.baseline.bare`)

`phase0.baseline.bare` ran with Arm A == Arm B (both bare engines). Expected
result: zero delta on rank_corr, MAE, KS for every position. If non-zero delta
is observed, the `--arm-b-base bare` wiring has a bug — investigate before
proceeding to Phase 1 KS work.

| Metric | Δ (Arm B - Arm A) | OK? |
|--------|-------------------|-----|
| Aggregate rank_corr | TBD | TBD |
| Aggregate weekly_mae | TBD | TBD |

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
