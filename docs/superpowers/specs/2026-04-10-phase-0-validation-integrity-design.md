# Phase 0 Validation Integrity Design

## Problem

The current validation path does not reliably distinguish:

- total lift versus the stripped baseline
- marginal lift versus the current default stack
- real evaluated signal impact versus "feature enabled but historically unexercised"
- old ledger entries from newer, more comparable runs

The verified gaps are concrete:

- bare dual-arm validation does not thread `td_tendency_config`, so Arm B is not a faithful "defaults plus overrides" comparison in that path
- the unified ledger currently has no `baseline=defaults` entries, so marginal validation is not a first-class workflow
- validation output does not report whether enabled external signals had historical coverage for the tested seasons
- ledger entries do not record schema version or enough run metadata to compare old and new runs cleanly

Phase 0 should fix those evaluation-path issues without changing projection behavior.

## Goals

- make `--baseline defaults` a first-class marginal validation path
- make bare dual-arm validation faithfully include `td_tendency_config`
- add explicit per-run data coverage reporting for enabled external signals
- version the ledger schema so older and newer runs are clearly distinguishable
- record comparison metadata needed to judge whether two runs are comparable
- update the roadmap and audit docs as part of the phase, not as follow-up cleanup

## Non-Goals

- no projection or modeling changes
- no new simulation features
- no historical props backfill
- no repeated-seed or confidence-interval execution in this phase
- no broader reporting UI beyond terminal output and ledger entries

The only allowed simulator-facing change is threading `td_tendency_config` into the bare dual-arm validation path, because that fixes evaluation correctness rather than model behavior.

## Approach

Use a **minimal validation spine**:

1. keep [`scripts/validate.py`](../../../scripts/validate.py) as the orchestrator
2. add one small validation-only helper for coverage accounting
3. extend ledger entries with explicit schema and comparability metadata
4. keep all changes isolated to validation, metadata, and documentation

This is the smallest approach that fully fixes the verified trust and comparability gaps.

## Scope Boundary

### In scope

- validation entrypoint changes in [`scripts/validate.py`](../../../scripts/validate.py)
- validation metadata and ledger changes in [`src/fantasy_sim/validation`](../../../src/fantasy_sim/validation)
- a small helper for external-signal coverage accounting
- terminal reporting improvements for comparability and coverage
- updates to:
  - [`docs/archive/accuracy-roadmap.md`](../../../docs/archive/accuracy-roadmap.md)
  - [`docs/archive/accuracy-stack-audit.md`](../../../docs/archive/accuracy-stack-audit.md)

### Out of scope

- any adjustment to projection math or feature weights
- any change to PFF, weather, vegas, usage, game-script, or TD-tendency behavior outside validation plumbing
- any new feature default flips
- any new forecasting or ranking layer

## Architecture

### `validate.py` remains the entrypoint

[`scripts/validate.py`](../../../scripts/validate.py) should continue to:

- resolve defaults and overrides
- build Arm A and Arm B engine configs
- run season validation
- print terminal summaries
- append labeled runs to the unified ledger

Phase 0 adds three responsibilities before ledger write:

- determine comparison metadata
- compute coverage summary for enabled external signals
- attach schema-tagged run metadata to the ledger entry

### Add one coverage helper

Add one small helper module under [`src/fantasy_sim/validation`](../../../src/fantasy_sim/validation) with a narrow responsibility:

- inspect enabled configs plus local cached data availability
- summarize whether each relevant signal was fully covered, partially covered, absent, or disabled for the selected test seasons

It should not:

- build game contexts
- mutate configs
- influence simulation outputs
- estimate signal value

It is a reporting component only.

### Ledger evolution stays backward-compatible

Extend [`LedgerEntry`](../../../src/fantasy_sim/validation/ledger.py) so new entries carry explicit schema and comparability metadata while older entries still load without migration.

Old entries should remain readable by defaulting missing fields to `None`, empty collections, or backward-compatible values.

## Execution Flow

The Phase 0 validation flow should be:

1. Load defaults and scoring config.
2. Resolve Arm A and Arm B engine configs.
3. Derive comparison metadata:
   - baseline mode
   - comparison mode
   - seed mode
   - sim count
   - overrides
4. Compute coverage summary for enabled external signals across the requested test seasons.
5. Run season validation.
6. Print season and weekly metrics plus a compact comparability and coverage summary.
7. Save a schema-versioned ledger entry.

This keeps the validation path explicit without introducing a second orchestration layer.

## Required Plumbing Fixes

### 1. Thread `td_tendency_config` through bare dual-arm validation

In the `arm_a_is_bare` branch of [`scripts/validate.py`](../../../scripts/validate.py), pass `td_tendency_config` to the dual-arm `build_games_parallel()` call along with the other enabled engine configs.

This is required so the Arm B "on" build actually reflects the default stack plus overrides.

### 2. Treat `baseline=defaults` as first-class

The `--baseline defaults` path already exists, but Phase 0 should make it first-class in semantics and reporting.

That means:

- labeled runs with `baseline=defaults` are expected, not exceptional
- ledger metadata explicitly marks them as marginal-lift runs
- terminal output clearly states that the run compares current defaults against current defaults plus overrides

## Run Metadata Contract

Each new ledger entry should record:

- `schema_version`: integer
- `baseline`: existing `"bare"` or `"defaults"` field retained
- `comparison_mode`:
  - `total_lift` for `baseline=bare`
  - `marginal_lift` for `baseline=defaults`
- `seed_mode`: explicit description of the seed strategy used by the run
- `sims`: existing field retained and surfaced as run-comparison metadata
- `overrides`: existing field retained
- `config_snapshot`: existing field retained

### Recommended `seed_mode`

Use a fixed label describing the current behavior:

- deterministic per-game seed derived from `game_id`
- shared across both arms for the same matchup

Phase 0 does not change seeding behavior. It only makes the behavior explicit in recorded metadata.

## Coverage Summary Contract

Coverage reporting should stay compact and descriptive.

For each relevant external signal, record:

- whether the signal was enabled for the run
- which tested seasons had historical data coverage
- a status:
  - `disabled`
  - `full`
  - `partial`
  - `none`
- a short note when needed, especially for forward-only or missing historical coverage

### Phase 0 signal list

- `props`
- `pff`
- `weather`
- `usage`
- `usage.ngs`
- `usage.route_rate`

This contract should answer:

- did the run try to use this signal?
- did historical data exist for the tested seasons?
- should the result be interpreted as exercised evidence, partial-data evidence, or no-data evidence?

It should not try to estimate effect size or confidence.

## Terminal Output

Every validation run should print a short comparability block that includes:

- baseline mode
- comparison mode
- seed mode
- sims
- compact per-signal coverage status

If a signal is enabled but has no historical data for the selected seasons, terminal output should say so plainly instead of implying the signal was meaningfully evaluated.

## Ledger Compatibility Rules

- old entries must still load
- old entries without `schema_version` should be treated as pre-schema-era records
- missing comparison metadata on old entries should remain absent rather than being guessed
- new output should make it obvious when an older record is not fully comparable to newer runs

This preserves existing directional evidence while preventing false apples-to-apples comparisons.

## Testing Strategy

### Coverage helper tests

Add focused unit tests for the new coverage helper to verify:

- disabled signals report `disabled`
- fully available signals report `full`
- partially available signals report `partial`
- absent historical coverage reports `none`
- notes clearly describe forward-only or missing-history cases

### Ledger compatibility tests

Add tests for [`ledger.py`](../../../src/fantasy_sim/validation/ledger.py) to verify:

- pre-schema ledger entries still load
- new schema-versioned entries round-trip through save/load
- missing optional metadata fields default safely

### Validation-path tests

Add focused tests proving:

- bare dual-arm validation passes `td_tendency_config`
- `--baseline defaults` runs are recorded as marginal-lift runs with the right metadata
- labeled runs include schema version, comparison mode, seed mode, sims, and coverage summary

Avoid broad simulation regression work unless a validation test needs a narrow fixture update.

## Acceptance Criteria

- bare dual-arm validation includes `td_tendency_config`
- `--baseline defaults` is a normal, first-class marginal validation path
- every new labeled run records schema version, comparison mode, baseline, seed mode, sims, and coverage summary
- terminal output makes historical coverage gaps explicit
- old ledger entries remain readable
- Phase 0 closes with updates to:
  - [`docs/archive/accuracy-roadmap.md`](../../../docs/archive/accuracy-roadmap.md)
  - [`docs/archive/accuracy-stack-audit.md`](../../../docs/archive/accuracy-stack-audit.md)

## Deliverables

- validation plumbing fix for `td_tendency_config`
- first-class marginal validation metadata for `baseline=defaults`
- explicit per-run data coverage reporting
- schema-versioned ledger entries with comparison metadata
- updated roadmap and audit docs reflecting the new validation contract and remaining caveats

## Deferred Work

Explicitly defer all of the following to later phases:

- repeated-seed or multi-run confidence execution
- historical props backfill
- richer evaluation dashboards
- any projection or modeling changes

Phase 0 ends once the evaluation path is trustworthy and comparable, not once the broader measurement system is fully mature.
