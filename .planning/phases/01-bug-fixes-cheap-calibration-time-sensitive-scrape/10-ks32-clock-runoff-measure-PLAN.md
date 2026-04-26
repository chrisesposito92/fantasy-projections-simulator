---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 10
type: execute
wave: 6
depends_on: ["01", "02", "03", "04", "05", "06", "07", "08"]
files_modified:
  - src/fantasy_sim/engine/play_resolver.py
  - tests/test_engine/test_clock.py
autonomous: true
requirements: [KS-32]
must_haves:
  truths:
    - "Per D-23: scripts/validate_passing.py is run against the post-bug-fix baseline (after KS-01..KS-29 ship); only retune CLOCK_PASS_INCOMPLETE from 5 → 3 if pass attempts are demonstrably low (32-33 instead of 35-36)"
    - "Per D-24: if measurement does not motivate change, document KS-32 as 'measured, no change' in the ledger via the p1.ks32.measure label"
    - "Per D-45 (Cycle 3 — Codex Cycle-2 NEW HIGH #1 fix; applies ONLY to the RETUNE branch): the `CLOCK_PASS_INCOMPLETE = 3` change is gated behind `phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled` (default false until promotion). The implementation in `src/fantasy_sim/engine/play_resolver.py` reads `get_phase1_ks_flags()['ks32_clock_pass_incomplete_3s']['enabled']` and branches: flag-on path uses `CLOCK_PASS_INCOMPLETE = 3`; flag-off path keeps the legacy `CLOCK_PASS_INCOMPLETE = 5`. RETUNE-branch A/B runs use `--set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true`. NO CHANGE branch (Task 3, p1.ks32.measure) is unaffected — it uses no `--set` flag because no code change ships in that branch. Promotion commit (RETUNE only) flips the default to true in `config/defaults.yaml`."
    - "If retune motivated, p1.ks32.bare and p1.ks32.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-30. Both runs invoke `--set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true` per Cycle 3 D-45."
  artifacts:
    - path: ".planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md"
      provides: "## KS-32 section with measurement results and decision (no change | retune to 3 | retune to N)"
      contains: "## KS-32"
  key_links:
    - from: "scripts/validate_passing.py"
      to: "the decision branch"
      via: "observed nfl_pass_attempts and plays_per_team"
      pattern: "nfl_pass_attempts"
---

<objective>
Implement KS-32 — **measure-then-decide** clock runoff calibration. Per D-23: run `scripts/validate_passing.py` against the post-bug-fix baseline (after KS-01..KS-29 have all shipped). Only reduce `CLOCK_PASS_INCOMPLETE = 5 → 3` if the measurement shows pass attempts are demonstrably low (32-33 instead of 35-36) and `plays_per_team` is below the (63, 65) target band. Per D-24: if no change is motivated, log a `p1.ks32.measure` ledger entry documenting the measurement.

Purpose: HYPOTHESES.md KS-32 (lines 561-573) shows the existing `CLOCK_PASS_INCOMPLETE = 5` may be over-tuned given the post-bug-fix RZ stack changes (which alter completion rate distributions). Avoid retuning on a moving target — measure FIRST.

Output: Either:
- (Branch A: no change motivated) `p1.ks32.measure` ledger entry; PROMOTION-NOTES.md `## KS-32` with "measured, no change" rationale.
- (Branch B: retune motivated) `CLOCK_PASS_INCOMPLETE = 3` in source; new tests; `p1.ks32.bare` and `p1.ks32.full` ledger entries; PROMOTION-NOTES.md `## KS-32` with retune justification.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md
@scripts/validate_passing.py
@src/fantasy_sim/engine/play_resolver.py

<interfaces>
From `src/fantasy_sim/engine/play_resolver.py`:

```python
# Lines 21-24:
CLOCK_RUN = 35
CLOCK_PASS_COMPLETE = 30
CLOCK_PASS_INCOMPLETE = 5
CLOCK_SACK = 35
```

`scripts/validate_passing.py` checks:
- `plays_per_team` should be in (63, 65)
- `nfl_pass_attempts` should be in [35, 36] (per AGENTS.md and HYPOTHESES.md KS-32)
- `sacks/team/game` should be ~2.0-2.5

If `nfl_pass_attempts` ≤ 33 OR `plays_per_team` ≤ 62 → retune motivated. Otherwise: no change.
</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Run validate_passing.py against the post-bug-fix baseline; record measurement</name>
  <files>(no source modifications)</files>
  <read_first>
    - scripts/validate_passing.py (current measurement gates)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-23, D-24)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (verify KS-01..KS-29 promotion entries exist)
  </read_first>
  <action>
Confirm KS-01..KS-29 have all shipped (PROMOTION-NOTES.md should have sections for each). If any KS is BLOCKED or SHIPPED OFF, that's OK — the measurement is against the current promoted defaults state.

Run `scripts/validate_passing.py`:

```bash
uv run python scripts/validate_passing.py \
  --sims 50 \
  --seasons 2024 \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks32_measurement.log

# Inspect key metrics
grep -E "plays_per_team|nfl_pass_attempts|sacks" \
  .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks32_measurement.log
```

Append the measurement to `.../logs/PROMOTION-NOTES.md` under `## KS-32 measurement`:

```markdown
## KS-32 measurement (post-Phase-1-bug-fixes baseline)

| Metric | Observed | Target band | In band? |
|--------|----------|-------------|----------|
| plays_per_team | ... | (63, 65) | YES/NO |
| nfl_pass_attempts | ... | [35, 36] | YES/NO |
| sacks/team/game | ... | ~2.0-2.5 | YES/NO |

**Decision:**
- If `plays_per_team` >= 62 AND `nfl_pass_attempts` >= 33 → **NO CHANGE** (measured, no change). Skip Tasks 2+3, jump to Task 4 (record p1.ks32.measure ledger entry).
- If `plays_per_team` < 62 OR `nfl_pass_attempts` < 33 → **RETUNE TO 3**. Proceed to Tasks 2+3.
```

Commit: `chore(01-10): KS-32 measurement against post-Phase-1 baseline`
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks32_measurement.log && grep -c "## KS-32 measurement" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/ks32_measurement.log` exists and contains output from validate_passing.py
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains `## KS-32 measurement` with the observed metrics + decision
    - Decision branch (NO CHANGE vs RETUNE TO 3) is explicitly recorded
    - `git log -1 --pretty=%s` matches `chore(01-10): KS-32 measurement`
  </acceptance_criteria>
  <done>Measurement complete; decision branch recorded; ready for Task 2 (if retune) or Task 4 (if no change).</done>
</task>

<task type="auto">
  <name>Task 2: [Conditional — RETUNE branch only] Set CLOCK_PASS_INCOMPLETE = 3 with TDD</name>
  <files>src/fantasy_sim/engine/play_resolver.py, tests/test_engine/test_clock.py</files>
  <read_first>
    - src/fantasy_sim/engine/play_resolver.py (lines 21-24)
    - tests/test_engine/test_clock.py (existing clock tests)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (the KS-32 decision from Task 1)
  </read_first>
  <action>
**SKIP THIS TASK if Task 1's decision is NO CHANGE.**

If the decision is RETUNE TO 3:

1. Add a failing test to `tests/test_engine/test_clock.py`:
```python
def test_ks32_clock_pass_incomplete_is_3():
    from fantasy_sim.engine.play_resolver import CLOCK_PASS_INCOMPLETE
    assert CLOCK_PASS_INCOMPLETE == 3, f"D-23 retune to 3 motivated by measurement; got {CLOCK_PASS_INCOMPLETE}"
```

Run pytest (RED expected):
```bash
uv run pytest tests/test_engine/test_clock.py -v -k ks32
```

Commit: `test(01-10): KS-32 add failing test for CLOCK_PASS_INCOMPLETE=3`

2. Edit `src/fantasy_sim/engine/play_resolver.py` line 23:
```python
# BEFORE:
CLOCK_PASS_INCOMPLETE = 5
# AFTER (D-23 retune motivated by Task 1 measurement):
CLOCK_PASS_INCOMPLETE = 3  # KS-32 D-23: retune motivated by post-Phase-1 measurement
```

Run pytest:
```bash
uv run pytest tests/test_engine/test_clock.py -v -k ks32
uv run pytest tests/ -v
```

EXPECTED: All tests pass.

Commit: `feat(01-10): KS-32 retune CLOCK_PASS_INCOMPLETE = 3 per D-23 measurement`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_clock.py -v -k ks32 2>&1 | tail -5 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - **If NO CHANGE branch**: Task skipped — no edits to play_resolver.py or test_clock.py. Acceptance is documented in PROMOTION-NOTES.md `## KS-32 measurement` decision: NO CHANGE.
    - **If RETUNE branch**: `grep -c "CLOCK_PASS_INCOMPLETE = 3" src/fantasy_sim/engine/play_resolver.py` returns 1
    - **If RETUNE branch**: `grep -c "CLOCK_PASS_INCOMPLETE = 5" src/fantasy_sim/engine/play_resolver.py` returns 0
    - **If RETUNE branch**: `tests/test_engine/test_clock.py` contains `def test_ks32_clock_pass_incomplete_is_3`
    - **If RETUNE branch**: `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - **If RETUNE branch**: `git log -1 --pretty=%s` matches `feat(01-10): KS-32 retune` OR `test(01-10): KS-32`
  </acceptance_criteria>
  <done>If NO CHANGE: skipped. If RETUNE: constant updated, tests pass.</done>
</task>

<task type="auto">
  <name>Task 3: [Conditional — RETUNE branch only] A/B validate KS-32 retune in isolation and full-stack</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (verify retune motivated)
  </read_first>
  <action>
**SKIP THIS TASK if Task 1's decision is NO CHANGE.** (In that case proceed directly to Task 4.)

**REVISED Cycle 3 (D-45 — Codex Cycle-2 NEW HIGH #1 fix):** if RETUNE branch fires, the new `CLOCK_PASS_INCOMPLETE = 3` value is gated behind `phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled` (default false; set in Plan 00 Task 8). Both arms use `--set phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true` for Arm B; Arm A keeps the legacy `CLOCK_PASS_INCOMPLETE = 5`.

If RETUNE branch: run BOTH A/B passes per D-29:

```bash
# True isolation: bare engines + KS-32 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --set "phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true" \
  --label "p1.ks32.bare"

# Full-stack overlay: defaults + KS-32 flag overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults \
  --set "phase1_ks_flags.ks32_clock_pass_incomplete_3s.enabled=true" \
  --label "p1.ks32.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks32"
```

NOTE: REVISED Cycle 3 — KS-32's edit to `CLOCK_PASS_INCOMPLETE` in `play_resolver.py` is now flag-gated. The Cycle-2 "no `--set` flag needed" pattern was a same-code no-op (Codex Cycle-2 NEW HIGH #1). The flag-on path uses `CLOCK_PASS_INCOMPLETE = 3`; the flag-off (default) path keeps `CLOCK_PASS_INCOMPLETE = 5`. The NO CHANGE branch (Task 3, p1.ks32.measure) is unaffected — it captures the post-Phase-1 baseline state without the KS-32 flag.

Capture logs to `.../logs/p1.ks32.{bare,full}.log`.

Promotion decision per D-30 (small-gain item):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- Any non-regression KS delta on QB pass_yards (≥ 0)

If hard floor fails → revert Task 2's commit, document under `## KS-32 — RETUNE BLOCKED` in PROMOTION-NOTES.md, mark `## PLAN BLOCKED`.

Append `## KS-32 retune A/B` section to PROMOTION-NOTES.md.

Commit: `chore(01-10): record KS-32 retune A/B ledger entries (p1.ks32.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks32\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - **If NO CHANGE branch**: Task skipped — no ledger entries for `p1.ks32.bare` or `p1.ks32.full`. Acceptance is documented in PROMOTION-NOTES.md.
    - **If RETUNE branch**: The verify command returns `2`
    - **If RETUNE branch**: `uv run python scripts/validate.py --show-ledger` output contains `p1.ks32.bare` and `p1.ks32.full`
    - **If RETUNE branch**: PROMOTION-NOTES.md contains `## KS-32 retune A/B` with the decision
    - **If RETUNE branch**: Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05 (or BLOCKED+reverted)
    - **If RETUNE branch**: `git log -1 --pretty=%s` matches `chore(01-10): record KS-32 retune A/B`
  </acceptance_criteria>
  <done>If NO CHANGE: skipped. If RETUNE: ledger entries recorded; promotion decision documented.</done>
</task>

<task type="auto">
  <name>Task 4: [Conditional — NO CHANGE branch only] Record p1.ks32.measure ledger entry</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (verify NO CHANGE branch)
  </read_first>
  <action>
**SKIP THIS TASK if Task 1's decision is RETUNE TO 3.** (In that case Tasks 2+3 are the ledger record.)

If NO CHANGE branch (per D-24): run a single `validate.py` invocation with the special `p1.ks32.measure` label to record the measurement-only entry. This documents that KS-32 was evaluated and not promoted, satisfying the REQUIREMENTS.md "delivered" definition.

**REVISED 2026-04-26 (HIGH-4 fix):** Use `--baseline bare` (no `--set`) instead of `--baseline defaults` (no `--set`) — the latter would produce Arm A == Arm B (defaults vs defaults) and yield a no-op snapshot identical in structure to the broken Plan 11 in the original. The `--baseline bare` form gives Arm A=bare, Arm B=current promoted defaults, which is a real delta-baring snapshot equivalent to `phase0.baseline.full` from Plan 00 (and may even differ from `phase0.baseline.full` if KS-32 has any incidental effect; if so, that's the KS-32 measurement signal).

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare \
  --label "p1.ks32.measure" \
  2>&1 | tee .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks32.measure.log

uv run python scripts/validate.py --show-ledger | grep "p1.ks32"
```

NOTE: This records the post-Phase-1 baseline against bare — a real delta. Compare against `phase0.baseline.full` from Wave 0 (Plan 00) to confirm KS-32's measurement decision had ~zero net effect on the headline metrics (the validation is meant to confirm "no change motivated").

Append to PROMOTION-NOTES.md under `## KS-32 final decision`:
```markdown
## KS-32 final decision: NO CHANGE (measured, no change per D-24)

Measurement (Task 1) showed plays_per_team and nfl_pass_attempts within the target band; CLOCK_PASS_INCOMPLETE=5 retained. Ledger entry p1.ks32.measure records the post-Phase-1 baseline state.
```

Commit: `chore(01-10): KS-32 measure-only ledger entry per D-24 (no change motivated)`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks32\.(measure|bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - **If RETUNE branch**: Task skipped — Tasks 2+3's ledger entries (`p1.ks32.bare` and `p1.ks32.full`) are the record.
    - **If NO CHANGE branch**: The verify command returns `1` (only `p1.ks32.measure` exists)
    - **If NO CHANGE branch**: `uv run python scripts/validate.py --show-ledger` contains `p1.ks32.measure`
    - **If NO CHANGE branch**: PROMOTION-NOTES.md contains `## KS-32 final decision: NO CHANGE`
    - **If NO CHANGE branch**: `git log -1 --pretty=%s` matches `chore(01-10): KS-32 measure-only`
  </acceptance_criteria>
  <done>Either p1.ks32.measure recorded (NO CHANGE) or p1.ks32.{bare,full} recorded (RETUNE). KS-32 requirement deliverable per D-24.</done>
</task>

<task type="auto">
  <name>Task 5: Promotion-state commit + SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (## KS-32 sections)
  </read_first>
  <action>
Per D-25 (revised), create the final promotion commit + SUMMARY. Determine state from PROMOTION-NOTES `## KS-32` sections:
- RETUNE branch + hard floor pass + KS Δ ≥ 0 → `PROMOTED`
- RETUNE branch + hard floor pass + KS doesn't move → `SHIPPED-NO-OP`
- RETUNE branch + hard floor fail → `BLOCKED` (Task 2 reverted)
- NO CHANGE branch → `MEASURED-NO-CHANGE` (per D-24)

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md`:

```markdown
# Plan 10 Summary — KS-32 clock runoff calibration (measure-then-decide)

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED|MEASURED-NO-CHANGE>
**Phase:** 1
**Wave:** 6
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

- Task 1 measurement: validate_passing.py output recorded; decision branch chosen
- If RETUNE: CLOCK_PASS_INCOMPLETE = 3 in play_resolver.py + ledger entries p1.ks32.{bare,full}
- If NO CHANGE: ledger entry p1.ks32.measure (Arm A=bare, Arm B=current defaults — gives a real delta vs phase0.baseline.full)

## Codex HIGH-4 fix note (NO CHANGE branch only)

The original Plan 10 NO CHANGE branch used `--baseline defaults` which produces
a no-op A/B (Arm A=Arm B=defaults). Replan switched to `--baseline bare` so the
Arm B metrics in the ledger entry can be compared against `phase0.baseline.full`
from Wave 0 to confirm KS-32 had ~zero net effect on headline metrics.
```

Commit (per D-25 revised):

```bash
PROMO_STATE="MEASURED-NO-CHANGE"  # or PROMOTED / SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md
git commit -m "feat(01-10): KS-32 ${PROMO_STATE} — clock runoff calibration measure-then-decide

Wave 6. Per D-23: validate_passing.py measurement against post-bug-fix
baseline; promotion conditional on observed pass attempts.

Bare-isolation A/B (RETUNE branch only) uses --baseline bare --arm-b-base bare per Plan 00.
NO CHANGE branch uses --baseline bare (real delta) per HIGH-4 fix."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED|MEASURED-NO-CHANGE" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - `git log -1 --pretty=%s` matches `feat(01-10): KS-32 PROMOTED|SHIPPED-NO-OP|BLOCKED|MEASURED-NO-CHANGE`
  </acceptance_criteria>
  <done>KS-32 promotion-state commit landed; SUMMARY captures the decision and the HIGH-4 fix.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Pure simulation code change; measurement is the same A/B harness already used. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-10-01 | T (Tampering) | Measure-then-decide discipline | mitigate | Task 1's decision branch is hard-coded against measured thresholds (33 attempts, 62 plays); no judgment call leakage. |
| T-01-10-02 | T (Tampering) | "Shipping no-op without ledger" foot-gun | mitigate | D-24 + Task 4 explicitly require the p1.ks32.measure ledger entry to satisfy "delivered" — prevents silent skip. |
</threat_model>

<verification>
- Task 1 measurement complete; decision branch recorded
- Either Tasks 2+3 ran (RETUNE) OR Task 4 ran (NO CHANGE) — exactly one path
- Ledger contains either `p1.ks32.measure` (NO CHANGE) or `p1.ks32.bare` + `p1.ks32.full` (RETUNE)
- PROMOTION-NOTES.md `## KS-32` section reflects the final decision
- 1,200+ existing test suite still green (regardless of branch)
</verification>

<success_criteria>
- KS-32 requirement deliverable per REQUIREMENTS.md "delivered" definition (implementation + tests + ledgered + promotion decision)
- Either: documented "measured, no change" with p1.ks32.measure ledger entry
- Or: CLOCK_PASS_INCOMPLETE=3 promoted with hard-floor-passing p1.ks32.bare + p1.ks32.full ledger entries
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-10-SUMMARY.md`.
</output>
