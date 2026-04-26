# Phase 1 Logs Directory

Per Plan 00 D-43, this directory holds logs from validate.py runs executed
during Phase 1 plans (00-11).

## Phase-0 baseline pin logs

`phase0.baseline.full.log` and `phase0.baseline.bare.log` are produced by Plan
00 Task 6 when the user runs the pin commands (see `PROJECT-PHASE0-FROZEN.md`).

The pin commands MUST be run in the main repo (not a worktree), because the
`results/ab_ledger.json` file is gitignored and worktree ledger writes do not
propagate to the main-repo ledger that downstream plans (01-11) consume.

## Smoke verification (Plan 00 worktree)

`phase0.baseline.full.partial.log` (22 lines) captures the harness start of a
killed 200-sim run that was used to verify the new `--arm-b-base` flag and
`bare_config_dict()` helper end-to-end. It was killed before the simulation
phase completed so the worktree could return promptly to the orchestrator.
The reproduced output up through "workers     : 4 per season" and the parallel
season build progress confirms:
- The `--arm-b-base` flag parses correctly.
- The new `bare_config_dict()` helper produces a valid Arm B config.
- Coverage summary computes correctly (note: PFF coverage shows full(2022,2023,2024)
  for the Arm B = defaults case, and all sub-engines disabled in the bare base
  case during the smoke).
- `validate.py` reaches the parallel-season build phase without errors.

## Per-KS plan logs

Plans 01-08 and 10 will write `p1.ksXX.bare.log` and `p1.ksXX.full.log` for
each KS A/B run; Plan 09 will write KS-21 scrape progress logs; Plan 11 will
write `p1.aggregate.full.log` for the end-of-phase aggregate validation.

All logs are intended to be committed alongside the per-plan SUMMARY for audit
trail purposes.
