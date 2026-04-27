---
phase: 02-structural-per-stat-calibration
plan: 09
type: execute
wave: 7
depends_on: ["02", "03", "04", "05", "06", "07", "08"]
files_modified:
  - .planning/PROJECT.md
  - .planning/STATE.md
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  - tests/test_validation/test_aggregate.py
autonomous: true
requirements: [KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14]
must_haves:
  truths:
    - "Per D-15: Phase 2 aggregate runs `validate.py --baseline bare --label p2.aggregate.full` AFTER all KS items have shipped to defaults.yaml (promoted or rolled back). Compute Phase-2-vs-Phase-1 delta from `p2.aggregate.full` Arm B vs `p1.aggregate.full` (#105) Arm B."
    - "Per D-15 walk-back trigger: hard-floor regression on the Phase-2-vs-Phase-1 delta (NOT Phase-2-vs-Phase-0). When `Δ rank_corr < -0.005 OR Δ weekly_mae > +0.05`, walk-back is triggered. Smallest-gain promotion candidate gets reverted first."
    - "Per Phase 1 D-46 + 02-VALIDATION.md: D-15 Phase-2-vs-Phase-1 delta computed via direct ledger reads of `SeasonMetrics.stat_mean_bias` and `SeasonMetrics.stat_ks` from both ledger entries. New file `tests/test_validation/test_aggregate.py` ships the delta-computation script tests."
    - "Per D-14: KS-09 success bar (KS Δ ≤ -0.03 on QB pass_yards + |bias Δ| ≤ 5 yd/g) is evaluated INSIDE the aggregate using the `p1.aggregate.full` Arm B baseline as the reference (regardless of KS-09's own per-KS A/B in Plan 03 because the aggregate considers the FULL post-Phase-2 stack, not isolated KS-09)."
    - "Per Phase 1 Plan 11 pattern: PROJECT.md `Current` column updates after Plan 09 success per D-15. STATE.md updates to reflect Phase 2 status (SHIPPED / SHIPPED-PARTIAL / WALKED-BACK)."
    - "Per HYPOTHESES.md KS Budget Sanity Check (lines 595-654): Phase 2's expected aggregate KS budget contribution = -0.04 to -0.10 on aggregate fpts KS (KS-08 -0.04 to -0.07; KS-13 -0.02 to -0.03; KS-09 -0.02 to -0.03; others smaller). Plan 09 evaluates whether the realized aggregate Δ matches the budget."
    - "Per Phase 1 D-32 walk-back rule: when hard floor regresses, revert the smallest-gain promotion candidate first; re-run aggregate; iterate until hard floor passes OR all promotions reverted."
    - "Per C-09: 2,177 + 1 (Plan 09 Task 1 delta-computation test) = 2,178 tests stay green after this plan."
  artifacts:
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "Phase 2 aggregate evaluation + Phase-2-vs-Phase-1 delta table + final phase status (SHIPPED / SHIPPED-PARTIAL / WALKED-BACK)"
      contains: "## Phase 2 Aggregate"
    - path: ".planning/PROJECT.md"
      provides: "Current TGT-XX values updated post-Phase-2 (only if SHIPPED)"
      contains: "post-Phase-2"
    - path: ".planning/STATE.md"
      provides: "Phase 2 status flag updated; Phase 3 entry baseline pinned (= p2.aggregate.full Arm B)"
      contains: "Phase 02"
    - path: "tests/test_validation/test_aggregate.py"
      provides: "New test file for delta-computation script reading stat_mean_bias and stat_ks from ledger entries"
      contains: "def test_phase2_vs_phase1_delta"
  key_links:
    - from: "src/fantasy_sim/validation/ledger.py::SeasonMetrics.stat_mean_bias"
      to: "Plan 09 Task 2 delta-computation script"
      via: "direct ledger reads of `p1.aggregate.full` and `p2.aggregate.full` entries"
      pattern: "stat_mean_bias"
---

<objective>
Run Phase 2 end-of-phase aggregate validation. Per D-15: this is the canonical "did Phase 2 work?" check. After all 7 KS items have shipped to `config/defaults.yaml` (promoted or rolled back), run `validate.py --baseline bare --label p2.aggregate.full` ONCE; the resulting Arm B is differenced against `p1.aggregate.full` (#105) Arm B to compute the Phase-2-vs-Phase-1 delta.

Per Phase 1 D-32 walk-back rule: if hard floor regresses on the differenced delta, revert the smallest-gain promotion candidate first, re-run the aggregate, and iterate. Plan 09 documents the walk-back decision tree explicitly so the executor can apply it deterministically.

Per D-14: KS-09's elevated promotion bar (KS Δ ≤ -0.03 on QB pass_yards + `|bias Δ| ≤ 5 yd/g`) is RE-EVALUATED at the aggregate level using the full post-Phase-2 stack. Per-KS Plan 03 may have shipped KS-09 as SHIPPED-PARTIAL or SHIPPED based on per-KS A/B; the aggregate may CONFIRM (final SHIPPED) or DOWNGRADE (final SHIPPED-PARTIAL even if Plan 03 was SHIPPED).

Output:
1. `p2.aggregate.full` ledger entry pinned.
2. Phase-2-vs-Phase-1 delta table in PROMOTION-NOTES.md.
3. Walk-back evaluation (and execution if triggered).
4. PROJECT.md `Current` column updates (only if SHIPPED).
5. STATE.md Phase 2 status flag updated; Phase 3 entry baseline pinned for the next initiative cycle.
6. Promotion-state commit per Phase 1 D-25/D-40 with phase-level status word.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/research/HYPOTHESES.md
@.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md
@.planning/phases/02-structural-per-stat-calibration/02-RESEARCH.md
@.planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/11-phase1-aggregate-validation-PLAN.md
@src/fantasy_sim/validation/ledger.py

<interfaces>
From src/fantasy_sim/validation/ledger.py (`SeasonMetrics` schema v5 from Phase 1 D-46):

```python
@dataclass
class SeasonMetrics:
    rank_corr: float
    weekly_mae: float
    season_mae: float
    fpts_ks: float
    stat_ks: dict[str, dict[str, dict[str, float]]]  # {position: {stat: {arm_a: float, arm_b: float}}}
    stat_mean_bias: dict[str, dict[str, dict[str, float]]]  # {position: {stat: {arm_a_bias: float, arm_b_bias: float}}}
    # ... other fields
```

From Phase 1 ledger entry `p1.aggregate.full` (#105) — Arm B fields:
- `rank_corr` ≈ 0.7XX (post-Phase-1 promoted defaults)
- `weekly_mae` ≈ 6.X
- `stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` = -39.29 (the Phase 1 headline miss; TGT-09 target ±5)
- `stat_ks["QB"]["pass_yards"]["arm_b"]` ≈ 0.36
- `stat_ks["TE"]["receptions"]["arm_b"]` ≈ 0.35 (TGT-04 target ≤ 0.27)
- `fpts_ks` (aggregate) ≈ 0.18-0.25 (TGT-08 target ≤ 0.18)

After Plan 09 succeeds with Phase 2 SHIPPED, the new `p2.aggregate.full` Arm B (post-Phase-2 promoted defaults) targets:
- TGT-04 TE receptions KS: ~0.35 → ≤ 0.27 (KS-08 floor + KS-09 per-stat + KS-10 TE elite tier)
- TGT-08 aggregate fpts KS: 0.15-0.25 → ≤ 0.18 (KS-08 sim weight floor + KS-13 ff_opportunity prior width)
- TGT-09 QB pass_yards mean bias: -39.29 → within ±5 yd/g (KS-09 per-stat correction; SHIPPED-PARTIAL acceptable per D-14)
- WR receptions KS: ~0.28 → ≤ 0.24 (intermediate target)

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Pin `p2.aggregate.full` ledger entry + write delta-computation test</name>
  <files>
    - tests/test_validation/test_aggregate.py
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/11-phase1-aggregate-validation-PLAN.md (Phase 1 aggregate pattern to mirror)
    - src/fantasy_sim/validation/ledger.py (SeasonMetrics schema v5)
  </read_first>
  <behavior>
    - Run `validate.py --baseline bare --label p2.aggregate.full` (no `--set` overrides — uses post-Phase-2 promoted defaults).
    - Add a new test file `tests/test_validation/test_aggregate.py` with a delta-computation test that reads `stat_mean_bias` and `stat_ks` from both `p1.aggregate.full` (#105) and `p2.aggregate.full` ledger entries and computes the differences.
  </behavior>
  <action>
**Step 1: pin the aggregate.**

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare \
  --label p2.aggregate.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_aggregate_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p1.aggregate.full|p2.aggregate.full"
```

**Step 2: write delta-computation test.** Create `tests/test_validation/test_aggregate.py`:

```python
"""Phase 2 aggregate validation: Phase-2-vs-Phase-1 delta computation."""

from __future__ import annotations

import pytest


def _read_ledger_entry(label: str):
    """Read a ledger entry by label, return its Arm B SeasonMetrics."""
    from fantasy_sim.validation.ledger import load_ledger
    ledger = load_ledger()
    matching = [e for e in ledger if e.label == label]
    if not matching:
        pytest.skip(f"Ledger entry {label} not present (likely Plan 09 has not been run yet)")
    return matching[-1]  # latest with this label


def test_phase2_vs_phase1_delta_within_hard_floor():
    """Phase-2-vs-Phase-1 delta (Arm B − Arm B): hard floor satisfied."""
    p1 = _read_ledger_entry("p1.aggregate.full")
    p2 = _read_ledger_entry("p2.aggregate.full")
    delta_rank_corr = p2.arm_b.rank_corr - p1.arm_b.rank_corr
    delta_weekly_mae = p2.arm_b.weekly_mae - p1.arm_b.weekly_mae
    assert delta_rank_corr >= -0.005, f"hard-floor rank_corr regression: Δ={delta_rank_corr}"
    assert delta_weekly_mae <= +0.05, f"hard-floor MAE regression: Δ={delta_weekly_mae}"


def test_phase2_qb_pass_yards_bias_d14_evaluation():
    """D-14 KS-09 promotion bar: |bias Δ| ≤ 5 yd/g for SHIPPED."""
    p1 = _read_ledger_entry("p1.aggregate.full")
    p2 = _read_ledger_entry("p2.aggregate.full")
    p1_bias = p1.arm_b.stat_mean_bias.get("QB", {}).get("pass_yards", {}).get("arm_b_bias", 0.0)
    p2_bias = p2.arm_b.stat_mean_bias.get("QB", {}).get("pass_yards", {}).get("arm_b_bias", 0.0)
    delta_bias = abs(p2_bias) - abs(p1_bias)
    # The per-stat mean bias should improve (smaller |bias| in p2 vs p1)
    # D-14 SHIPPED requires |Δ bias| ≤ 5 (i.e., bias closure within 5 yd/g)
    # This is an INFORMATIONAL test — the actual decision is in Plan 09 PROMOTION-NOTES.md
    print(f"p1.aggregate.full QB pass_yards bias: {p1_bias} yd/g")
    print(f"p2.aggregate.full QB pass_yards bias: {p2_bias} yd/g")
    print(f"|p2_bias|: {abs(p2_bias)} yd/g (target ≤ 5 yd/g per TGT-09)")
    # Test passes regardless of bias closure — the test exists to record the values, not to gate
```

Run pytest:
```bash
uv run pytest tests/test_validation/test_aggregate.py -v
```

Expected: 2 tests pass (or skip if ledger entries are missing — graceful skip per `pytest.skip` in the helper).

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,177 + 1 = 2,178 tests pass (counting the 2 in test_aggregate.py as a single addition since they're in a new file; actual count may be 2,179).

Commit: `chore(02-09): pin p2.aggregate.full ledger entry + add delta-computation test`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.aggregate.full" && uv run pytest tests/test_validation/test_aggregate.py -v 2>&1 | grep -E "PASSED|FAILED"</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.aggregate.full"` returns one row
    - `tests/test_validation/test_aggregate.py` exists and contains `def test_phase2_vs_phase1_delta_within_hard_floor`
    - `tests/test_validation/test_aggregate.py` contains `def test_phase2_qb_pass_yards_bias_d14_evaluation`
    - `uv run pytest tests/test_validation/test_aggregate.py -v` exits 0
    - `git log -1 --pretty=%s` matches `chore(02-09): pin p2.aggregate.full`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Compute Phase-2-vs-Phase-1 delta + walk-back evaluation</name>
  <files>
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json
  </files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md (per-KS sweep tables + final decisions for KS-08 through KS-14 and KS-12)
    - src/fantasy_sim/validation/ledger.py (SeasonMetrics schema)
  </read_first>
  <behavior>
    - Read both ledger entries (`p1.aggregate.full` Arm B and `p2.aggregate.full` Arm B) and compute the Phase-2-vs-Phase-1 delta.
    - Document the delta in PROMOTION-NOTES.md.
    - Apply Phase 1 D-32 walk-back rule: if hard floor regresses (`Δ rank_corr < -0.005 OR Δ weekly_mae > +0.05`), identify the smallest-gain promoted KS item and propose a walk-back.
    - If hard floor passes, record phase-level status word: SHIPPED (all 4 headline criteria pass) / SHIPPED-PARTIAL (hard floor + some criteria) / WALKED-BACK (one or more KS items reverted).
  </behavior>
  <action>
**Step 1: compute the delta.** Run a one-shot Python script (inline or as a tiny script) that reads both ledger entries:

```bash
uv run python -c "
from fantasy_sim.validation.ledger import load_ledger
ledger = load_ledger()
p1 = next((e for e in ledger if e.label == 'p1.aggregate.full'), None)
p2 = next((e for e in ledger if e.label == 'p2.aggregate.full'), None)
if not p1 or not p2:
    print('ERROR: missing aggregate entries')
    exit(1)
import json
delta = {
    'rank_corr': p2.arm_b.rank_corr - p1.arm_b.rank_corr,
    'weekly_mae': p2.arm_b.weekly_mae - p1.arm_b.weekly_mae,
    'fpts_ks': p2.arm_b.fpts_ks - p1.arm_b.fpts_ks,
}
delta['stat_ks'] = {}
for pos in ('QB', 'RB', 'WR', 'TE'):
    delta['stat_ks'][pos] = {}
    for stat in ('pass_yards', 'rush_yards', 'receiving_yards', 'receptions'):
        p1v = p1.arm_b.stat_ks.get(pos, {}).get(stat, {}).get('arm_b', None)
        p2v = p2.arm_b.stat_ks.get(pos, {}).get(stat, {}).get('arm_b', None)
        if p1v is not None and p2v is not None:
            delta['stat_ks'][pos][stat] = p2v - p1v
delta['stat_mean_bias'] = {}
for pos in ('QB', 'WR'):
    delta['stat_mean_bias'][pos] = {}
    for stat in ('pass_yards', 'receiving_yards'):
        p1v = p1.arm_b.stat_mean_bias.get(pos, {}).get(stat, {}).get('arm_b_bias', None)
        p2v = p2.arm_b.stat_mean_bias.get(pos, {}).get(stat, {}).get('arm_b_bias', None)
        if p1v is not None and p2v is not None:
            delta['stat_mean_bias'][pos][stat] = {'p1': p1v, 'p2': p2v, 'delta_abs': abs(p2v) - abs(p1v)}
print(json.dumps(delta, indent=2))
" > .planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json
```

**Step 2: apply hard-floor + walk-back evaluation.**

Read the delta JSON. Apply:
1. **Hard floor:** `delta.rank_corr ≥ -0.005 AND delta.weekly_mae ≤ +0.05`
2. **TGT-04 TE receptions:** `p2 stat_ks[TE][receptions] ≤ 0.27`
3. **TGT-08 aggregate fpts KS:** `p2 fpts_ks ≤ 0.18`
4. **WR receptions intermediate:** `p2 stat_ks[WR][receptions] ≤ 0.24`
5. **TGT-09 QB pass_yards bias (D-14):** `|p2 stat_mean_bias[QB][pass_yards].arm_b_bias| ≤ 5`

If hard floor passes AND all 4 headline criteria pass: status = `SHIPPED`.
If hard floor passes AND 1-3 headline criteria pass: status = `SHIPPED-PARTIAL`.
If hard floor regresses: status = `WALKED-BACK`. Identify the smallest-gain promoted KS item from PROMOTION-NOTES.md (the per-KS plan with the smallest Δ stat_ks improvement vs `p1.aggregate.full`); revert that item by editing defaults.yaml `phase2_ks_flags.<ks>.enabled = false`; re-run `p2.aggregate.full`; iterate until hard floor passes OR all promotions reverted.

**Step 3: append to PROMOTION-NOTES.md.**

```markdown
## Phase 2 Aggregate (Plan 09) — <STATUS>

**Phase-2-vs-Phase-1 delta (`p2.aggregate.full` Arm B − `p1.aggregate.full` Arm B):**

| Metric | p1.aggregate.full | p2.aggregate.full | Δ | Hard Floor Pass? | TGT |
|--------|---------------------|---------------------|---|------------------|-----|
| rank_corr | <p1>           | <p2>                | <Δ> | <PASS/FAIL> (≥ -0.005) | (TGT-X) |
| weekly_mae | <p1>          | <p2>                | <Δ> | <PASS/FAIL> (≤ +0.05) | |
| fpts_ks (aggregate) | <p1> | <p2>           | <Δ> | (TGT-08 target ≤ 0.18) — <PASS/FAIL> |
| stat_ks[TE][receptions] | <p1> | <p2>      | <Δ> | (TGT-04 target ≤ 0.27) — <PASS/FAIL> |
| stat_ks[WR][receptions] | <p1> | <p2>      | <Δ> | (intermediate target ≤ 0.24) — <PASS/FAIL> |
| stat_mean_bias[QB][pass_yards].abs | <p1> | <p2> | <Δ> | (TGT-09 target ±5 yd/g) — <PASS/FAIL> |

**Headline criteria (D-15 + D-14):**
1. Hard floor: <PASS/FAIL>
2. TGT-04 TE receptions ≤ 0.27: <PASS/FAIL>
3. TGT-08 fpts KS ≤ 0.18: <PASS/FAIL>
4. WR receptions ≤ 0.24: <PASS/FAIL>
5. TGT-09 |QB pass_yards bias| ≤ 5 yd/g (D-14): <PASS/FAIL>

**Promoted KS items (from per-KS plans):**
- KS-08: <SHIPPED|SHIPPED-NO-OP|BLOCKED> at floor=<value> (Δ stat_ks[TE][receptions] = <val>)
- KS-09: <SHIPPED|SHIPPED-PARTIAL|BLOCKED> (Δ KS QB pass_yards = <val>; |Δ bias| = <val>)
- KS-10: <SHIPPED|SHIPPED-NO-OP|BLOCKED> (Δ stat_ks[TE][receptions] = <val>)
- KS-11: <SHIPPED|SHIPPED-NO-OP|BLOCKED> (Δ stat_ks[WR][receiving_yards] = <val>)
- KS-12: <SHIPPED|SHIPPED-NO-OP|BLOCKED> (Δ stat_ks[WR][receptions] = <val>)
- KS-13: <SHIPPED|SHIPPED-NO-OP|BLOCKED> (Path <A|B>; Δ stat_ks[fpts] = <val>)
- KS-14: <SHIPPED|SHIPPED-NO-OP|BLOCKED> (Δ buckets_below_min_plays_pct = <val>)

**D-15 walk-back evaluation:** <NOT TRIGGERED | TRIGGERED — reverted KS-XX>.

**Final phase status:** `<SHIPPED | SHIPPED-PARTIAL | WALKED-BACK>`. Rationale: <one-paragraph>.
```

If walk-back triggered, after the revert:
```bash
# Revert the smallest-gain candidate; re-run aggregate
uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline bare --label p2.aggregate.full
# Re-evaluate; iterate
```

Commit: `chore(02-09): compute Phase-2-vs-Phase-1 delta + record headline criteria evaluation`
  </action>
  <verify>
    <automated>test -f .planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json && grep -q "## Phase 2 Aggregate" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && grep -E "Final phase status:.*(SHIPPED|SHIPPED-PARTIAL|WALKED-BACK)" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md | head -1</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json` exists and contains valid JSON with `rank_corr`, `weekly_mae`, `stat_ks`, `stat_mean_bias` keys
    - PROMOTION-NOTES.md `## Phase 2 Aggregate` section contains the delta table + 5 headline criteria + walk-back evaluation + final phase status word
    - `git log -1 --pretty=%s` matches `chore(02-09): compute Phase-2-vs-Phase-1 delta`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Update PROJECT.md `Current` column + STATE.md + final phase commit</name>
  <files>
    - .planning/PROJECT.md
    - .planning/STATE.md
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/PROJECT.md (TGT-XX `Current` column)
    - .planning/STATE.md (Phase 02 status)
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json
  </read_first>
  <behavior>
    - If status is SHIPPED or SHIPPED-PARTIAL: update PROJECT.md `Current` column for TGT-01 through TGT-10 with the post-Phase-2 values from `p2.aggregate.full` Arm B.
    - If status is WALKED-BACK: PROJECT.md unchanged.
    - Update STATE.md to reflect Phase 02 completion (SHIPPED / SHIPPED-PARTIAL / WALKED-BACK status); pin Phase 3 entry baseline = `p2.aggregate.full` Arm B.
    - Append a final summary to PROMOTION-NOTES.md.
    - Commit per Phase 1 D-25/D-40 phase-level format.
  </behavior>
  <action>
**Step 1: PROJECT.md `Current` column.** Locate the TGT-XX table in PROJECT.md (mirrors REQUIREMENTS.md `## Outcome Targets (TGT-XX)`). For each TGT, update the `Current` column with the post-Phase-2 value from the delta JSON:

```markdown
| ID | Description | Current | Target | Notes |
|----|-------------|---------|--------|-------|
| TGT-01 | QB pass_yards KS | <p2 stat_ks[QB][pass_yards]> | ≤ 0.20 | post-Phase-2 |
| TGT-02 | WR receiving_yards KS | <p2 stat_ks[WR][receiving_yards]> | ≤ 0.20 | post-Phase-2 |
| TGT-03 | WR receptions KS | <p2 stat_ks[WR][receptions]> | ≤ 0.22 | post-Phase-2 |
| TGT-04 | TE receptions KS | <p2 stat_ks[TE][receptions]> | ≤ 0.27 | post-Phase-2 |
| TGT-05 | TE receiving_yards KS | <p2 stat_ks[TE][receiving_yards]> | ≤ 0.25 | post-Phase-2 |
| TGT-06 | RB rush_yards KS | <p2 stat_ks[RB][rush_yards]> | ≤ 0.22 | post-Phase-2 |
| TGT-07 | RB receiving_yards KS | <p2 stat_ks[RB][receiving_yards]> | ≤ 0.34 | post-Phase-2 |
| TGT-08 | Aggregate fpts KS | <p2 fpts_ks> | ≤ 0.18 | post-Phase-2 |
| TGT-09 | QB pass_yards mean bias | <p2 stat_mean_bias[QB][pass_yards].arm_b_bias> yd/g | ±5 yd/g | post-Phase-2 |
| TGT-10 | WR receiving_yards mean bias | <p2 stat_mean_bias[WR][receiving_yards].arm_b_bias> yd/g | ±2 yd/g | post-Phase-2 |
```

(Skip this step if status is WALKED-BACK — PROJECT.md retains the post-Phase-1 values.)

**Step 2: STATE.md.** Update the frontmatter + body:

```yaml
---
gsd_state_version: 1.0
milestone: v1.0
status: Phase 02 <SHIPPED|SHIPPED-PARTIAL|WALKED-BACK> — Phase 03 not yet planned
last_updated: "2026-04-XX"
last_activity: 2026-04-XX
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 21  # 12 from Phase 1 + 9 from Phase 2
  completed_plans: 21
  percent: 100
---
```

In the body, append:
```markdown
- [Phase 02]: Phase 2 <STATUS> — aggregate `p2.aggregate.full` (#XXX) vs `p1.aggregate.full` (#105): hard floor <PASS/FAIL> (rank_corr Δ <val>, weekly_mae Δ <val>); headline criteria <X/4 met>. Phase 3 entry baseline = ledger entry `p2.aggregate.full` Arm B.
```

**Step 3: final summary in PROMOTION-NOTES.md.**

```markdown
## Phase 2 Wrap-up (Plan 09 final)

**Phase 02 status:** <SHIPPED | SHIPPED-PARTIAL | WALKED-BACK>.

**Total per-KS plans executed:** 7 (KS-08, KS-09, KS-10, KS-11, KS-12, KS-13, KS-14).

**Total promoted to defaults.yaml:** <N> of 7 (KS-XX list).

**TGT-XX `Current` updates (PROJECT.md):**
- TGT-01 (QB pass_yards KS): <pre> → <post>
- TGT-04 (TE receptions KS): <pre> → <post>
- TGT-08 (aggregate fpts KS): <pre> → <post>
- TGT-09 (QB pass_yards mean bias): <pre> → <post>
- (rest of TGT-XX in PROJECT.md table above)

**Phase 3 readiness:** entry baseline = `p2.aggregate.full` Arm B. Ready for `/gsd-discuss-phase 3`.
```

**Step 4: Run full suite final.**
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,178+ tests pass.

**Step 5: phase-level commit.**

```
feat(02-09): Phase 02 <SHIPPED|SHIPPED-PARTIAL|WALKED-BACK> — Δ rank_corr <val>, Δ weekly_mae <val>; <X/4> headline criteria met

Per-KS status: KS-08 <STATUS>, KS-09 <STATUS>, KS-10 <STATUS>, KS-11 <STATUS>, KS-12 <STATUS>, KS-13 <STATUS>, KS-14 <STATUS>
PROJECT.md Current updated for TGT-01..TGT-10 (only if SHIPPED or SHIPPED-PARTIAL)
STATE.md Phase 02 status flag updated
Refs: D-12, D-13, D-14, D-15 (CONTEXT.md), HYPOTHESES.md KS Budget Sanity Check
```
  </action>
  <verify>
    <automated>grep -E "Phase 02.*SHIPPED|Phase 02.*WALKED-BACK" .planning/STATE.md | head -1 && grep -q "post-Phase-2" .planning/PROJECT.md && grep -q "## Phase 2 Wrap-up" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - If SHIPPED or SHIPPED-PARTIAL: `.planning/PROJECT.md` contains `post-Phase-2` annotations on TGT-XX rows
    - `.planning/STATE.md` frontmatter `status:` field contains `Phase 02` AND one of `SHIPPED|SHIPPED-PARTIAL|WALKED-BACK`
    - `.planning/STATE.md` `last_updated` date matches the commit date
    - PROMOTION-NOTES.md `## Phase 2 Wrap-up` section contains per-KS status list + TGT-XX `Current` updates
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,178+ tests)
    - `git log -1 --pretty=%s` matches `feat(02-09): Phase 02 (SHIPPED|SHIPPED-PARTIAL|WALKED-BACK)`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. `git log --oneline -10` shows 3 new commits prefixed `(02-09)`.
2. `uv run python scripts/validate.py --show-ledger | grep -E "p1.aggregate.full|p2.aggregate.full"` shows both rows.
3. `tests/test_validation/test_aggregate.py` exists and passes.
4. `.planning/PROJECT.md` `Current` column reflects post-Phase-2 values (if SHIPPED or SHIPPED-PARTIAL).
5. `.planning/STATE.md` frontmatter shows Phase 02 status word.
6. `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` has `## Phase 2 Aggregate` + `## Phase 2 Wrap-up` sections with full evaluation.
7. `.planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json` exists with valid JSON.

Phase 02 status recorded. Phase 03 (Phase 5 Slice Activation — KS-02, KS-16, KS-17, KS-18) may now be planned via `/gsd-discuss-phase 3` then `/gsd-plan-phase 3`.
</verification>

<must_haves>
  truths:
    - "Per D-15: Plan 09 runs `validate.py --baseline bare --label p2.aggregate.full` (no --set); Phase-2-vs-Phase-1 delta = p2.aggregate.full Arm B − p1.aggregate.full Arm B (#105)"
    - "Per D-15 walk-back trigger: hard floor regression on Phase-2-vs-Phase-1 delta. Smallest-gain promotion candidate reverted first; iterate until hard floor passes."
    - "Per D-14: KS-09 elevated promotion bar (KS Δ ≤ -0.03 on QB pass_yards + |bias Δ| ≤ 5 yd/g) RE-EVALUATED at aggregate (per-KS Plan 03 may be SHIPPED while aggregate is SHIPPED-PARTIAL or vice-versa)"
    - "Per Phase 1 D-46: SeasonMetrics.stat_mean_bias + stat_ks read directly from ledger entries (no side script)"
    - "Per Phase 1 D-32: walk-back rule when hard floor regresses; smallest-gain promotion candidate first"
    - "Per HYPOTHESES KS Budget Sanity Check: expected aggregate KS budget contribution = -0.04 to -0.10 on aggregate fpts KS"
    - "Per C-09: 2,178-test suite stays green (2,177 pre-Plan-09 + 2 in test_aggregate.py)"
  artifacts:
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "Phase 2 Aggregate section + Phase 2 Wrap-up section + 5 headline criteria + final phase status word"
      contains: "## Phase 2 Aggregate"
    - path: ".planning/PROJECT.md"
      provides: "TGT-01 through TGT-10 Current column updated post-Phase-2 (only if SHIPPED or SHIPPED-PARTIAL)"
      contains: "post-Phase-2"
    - path: ".planning/STATE.md"
      provides: "Phase 02 status flag (SHIPPED / SHIPPED-PARTIAL / WALKED-BACK); Phase 3 entry baseline pinned"
      contains: "Phase 02"
    - path: "tests/test_validation/test_aggregate.py"
      provides: "Phase-2-vs-Phase-1 delta-computation tests reading SeasonMetrics from ledger"
      contains: "def test_phase2_vs_phase1_delta"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/p2_phase2_vs_phase1_delta.json"
      provides: "Machine-readable delta JSON for downstream tooling"
      contains: "rank_corr"
</must_haves>
