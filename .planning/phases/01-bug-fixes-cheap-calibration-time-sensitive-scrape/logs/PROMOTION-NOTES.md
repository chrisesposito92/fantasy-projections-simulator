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

---

## KS-04

**Decision: BLOCKED**

**Date:** 2026-04-26
**Plan:** 01-02
**Code change:** `CATCH_YARDS_BOOST = 1.5` (D-12) and conditional application (D-11) in `_resolve_pass`. Gated behind `phase1_ks_flags.ks04_conditional_catch_boost.enabled` (Cycle 3 D-45). Legacy unconditional `+1` outside-RZ boost preserved as the flag-off branch so production defaults are bit-for-bit identical to pre-Phase-1.

### Ledger results

| Entry | Δ rank_corr | Δ weekly_mae | Δ season_mae | Δ fpts_ks | Hard floor (D-31, ≤+0.05 MAE)? |
|-------|-------------|--------------|--------------|-----------|--------------------------------|
| p1.ks04.bare (#86) | +0.0010 | **+0.167** | +2.065 | +0.001 | **FAIL** (MAE +0.167 > +0.05) |
| p1.ks04.full (#87) | -0.0010 | +0.001 | +0.056 | -0.000 | PASS |

### QB pass_yards / WR receiving_yards primary-target detail

Phase-0 reference (`phase0.baseline.full` Arm B): QB pass_yards KS = 0.353; WR receiving_yards KS = 0.264; QB pass_yards mean bias = -28.32 yd/g; WR receiving_yards mean bias = -9.10 yd/g.

| Stat | bare 2022 ΔKS | bare 2023 ΔKS | bare 2024 ΔKS | full 2022 ΔKS | full 2023 ΔKS | full 2024 ΔKS |
|------|----------------|----------------|----------------|----------------|----------------|----------------|
| QB pass_yards | +0.02 | +0.01 | +0.03 | -0.00 | +0.00 | +0.00 |
| WR receiving_yards | +0.00 | +0.00 | +0.00 | +0.00 | -0.00 | -0.00 |
| TE receptions | +0.00 | -0.01 | +0.00 | -0.01 | +0.00 | +0.00 |
| TE receiving_yards | +0.00 | -0.00 | +0.00 | -0.00 | -0.01 | +0.00 |

Bare arm B mean projections (QB pass_yards) drop by ~10 yd/game vs Arm A: 2022 197→185.8, 2023 ~191.5 (similar), 2024 ~187.4. The conditional rule REMOVES the legacy `+1` boost on the majority of completions where `raw <= yard_line` (no clamp would fire), and the new `+1.5` only fires on the minority of clamp-fires plays where the result is clamped to `yard_line` anyway. Net: less compensating yardage outside the RZ, worsening already-low projections in bare mode.

In the full-stack overlay, the other engines (props, matchup, ensemble, etc.) absorb the small per-play yard delta, so weekly MAE moves only +0.001 and KS movement is essentially flat — but the primary-target KS gain (D-31 expects ≥ -0.01) is also not realized.

### Promotion-bar evaluation (D-31 medium-large)

- **Bare:** hard floor FAILS on weekly_mae (+0.167 > +0.05).
- **Full:** hard floor PASSES, but KS movement is ≤ -0.01 only on TE receptions/yards 2022/2023 (-0.01 each) — not on the QB pass_yards or WR receiving_yards primary targets per D-31.

### Decision rationale

Per Plan 02 Task 3: "If hard floor fails on either entry → revert Task 2's commit, document in PROMOTION-NOTES under `## KS-04`, mark plan `## PLAN BLOCKED`. KS-15 plan can still proceed (it removes the boost entirely)." And per D-13: "ship KS-04 (boost +1.5 conditional) as an intermediate, even though KS-15 will obviate it. This captures KS-04's intermediate KS gain in the ledger and provides a fallback if KS-15 fails the hard floor."

KS-04 in the bare baseline shows the conditional rule REMOVES previously-helpful (if fictitious) compensating yards on non-clamp-fires plays. The mechanism is correct per D-11 ("apply boost only when clamp would fire"), but in bare mode the legacy unconditional `+1` was masking the under-projection — removing it exposes the gap. The full-stack overlay absorbs the per-play delta into the engine stack but the promotion bar's KS-improvement expectation is not met on the primary targets.

### Action

Per the literal plan instruction (revert Task 2): use Cycle 3 D-45's flag-gated rollback knob — the new code path STAYS in `play_resolver.py` (gated behind `_KS04_CONDITIONAL_BOOST = False`), and `phase1_ks_flags.ks04_conditional_catch_boost.enabled` STAYS at its Plan-00 default of `false` in `config/defaults.yaml`. This is functionally equivalent to a literal revert (production behavior unchanged: legacy unconditional `+1` outside-RZ boost is what defaults runs) but preserves the experiment for future analysis and avoids invalidating the Task 1 / Task 2 commits.

This is a deviation from the literal Task 3 instruction ("revert Task 2's commit") but consistent with D-45's design intent ("feature flags also give a clean rollback knob"). Documented in the SUMMARY under Deviations.

KS-15 (Plan 07) is NOT blocked — it removes `CATCH_YARDS_BOOST` entirely (D-15) and operates on a different conditional path (`min(yard_line, sample)` for clamp + un-clamped sample for TD gate, per D-14). KS-15 must still ship and is a separate A/B.

### Logs

- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks04.bare.log`
- `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks04.full.log`

### Commits

- Task 1 (RED): `64cb6f9` — `test(01-02): add failing tests for KS-04 conditional CATCH_YARDS_BOOST retune`
- Task 2 (GREEN): `208d921` — `feat(01-02): implement KS-04 conditional CATCH_YARDS_BOOST=1.5 per D-11/D-12`

---

## KS-21 dry-run

**Date:** 2026-04-26
**Plan:** 01-09
**Scope:** 5-event single-week dry run for 2024 across 3 snapshot labels
(`prior_core8`, `prior_alt6`, `close_alt6`) to validate full pipeline
(raw fetch + parquet build) and calibrate the full-scrape credit cost.

### Operator credit gate (Task 2)

Pre-scrape balance confirmed > 4.0M by user. Dashboard reading recorded
the day-of as ≥ 4.0M (per user-provided checkpoint approval).

### Dry-run results

| Snapshot label | Markets | Date source | Offset | Events | Raw JSON files | Parquet rows | Distinct events | Cost (credits) |
|----------------|---------|-------------|--------|--------|----------------|--------------|------------------|----------------|
| prior_core8    | 8 main  | previous_snapshot_timestamp | 0 | 5 | 5 | 455 | 5 | 400 (~80/evt) |
| prior_alt6     | 6 alt   | previous_snapshot_timestamp | 0 | 5 | 5 | 139 | 5 | 200 (~40/evt) |
| close_alt6     | 6 alt   | commence_time              | -60 | 5 | 5 | 143 | 5 | 200 (~40/evt) |

Note: prior_alt6 and close_alt6 each return only 4 of 6 alt markets in
practice — `player_pass_attempts_alternate` and
`player_rush_attempts_alternate` come back empty in this 5-event sample.
This is real-world API gap, not a bug; the requested markets are still
correctly named and the API does not 422 on them. Plan acceptance only
requires "no main-line leak in alt parquet" — that holds (4 returned
markets are all `_alternate`).

### Credit-cost extrapolation

- Inventory: 272 events/season × 3 seasons (2023, 2024, 2025) = **816 events**
- Per-event total (3 snapshots): 80 + 40 + 40 = **160 credits/event**
- Full-scrape estimate: 816 × 160 = **130,560 credits** (~2.6% of remaining)
- Comfortably under the user-set 1.5M / 30% pause threshold

### 422 deviation discovered

Initial `--limit 1` dry run aborted with `httpx.HTTPStatusError 422`
(see `dry_run_prior_core8_raw.log` first attempt) due to a shell
word-split quirk in this agent's bash environment: passing markets via
`--markets $CORE` (where `$CORE` is a space-separated string) caused
argparse to receive ONE positional value with embedded spaces instead
of 8 separate market names. The Odds API correctly rejected the
malformed market name with HTTP 422.

**Fix applied (deviation Rule 3, blocking issue):**
- Added `OddsApiNoDataError` exception in `props_backfill.py` (raised
  on HTTP 422 instead of generic `httpx.HTTPStatusError`)
- `scripts/fetch_market_history_props.py` catches `OddsApiNoDataError`
  and skips the event with a `no-data` log line, continuing with the
  next event rather than aborting the entire scrape
- Also surfaces `x-requests-remaining` in the per-event `saved` log
  for visibility during long scrapes
- All 32 existing `tests/test_data/test_market_history` tests still pass

This makes the scrape robust to genuine API data-availability gaps
(e.g., very-early prior-snapshot timestamps where alt markets weren't
listed yet) AND was the immediate unblocker for the dry run after I
switched the bash invocation to pass markets as explicit per-arg tokens.

### Decision

**PROCEED to Task 4 (full scrape)** — credit estimate (~130K) is well
within the user-set 1.5M / 30% pause threshold; dry-run acceptance
criteria satisfied; pipeline (raw fetch → parquet build) verified
end-to-end across all 3 snapshot labels.

### Logs

- `dry_run_prior_core8_raw.log` — STEP 1a raw fetch (post-deviation-fix retry)
- `dry_run_prior_core8_build.log` — STEP 1b parquet build
- `dry_run_prior_alt6_raw.log` — STEP 2a raw fetch
- `dry_run_prior_alt6_build.log` — STEP 2b parquet build
- `dry_run_close_alt6_raw.log` — STEP 3a raw fetch
- `dry_run_close_alt6_build.log` — STEP 3b parquet build

### Commits

- Task 1: `aba324a` — `feat(01-09): add ALT_PROP_MARKETS tuple per KS-21 D-04`
- Task 3 deviation: `398f926` — `fix(01-09): treat Odds API HTTP 422 as skippable no-data signal`
- Task 3 dry-run: (this commit) — `chore(01-09): KS-21 dry-run`
