---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 01
type: tdd
wave: 1
depends_on: ["00"]
files_modified:
  - src/fantasy_sim/engine/play_resolver.py
  - config/defaults.yaml
  - tests/test_engine/test_play_resolver.py
autonomous: true
requirements: [KS-01]
must_haves:
  truths:
    - "Per D-09: when RZ TD-gate fails, yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp)) — preserves the sampled distribution and reserves 1 yard short of the goal"
    - "Per D-45 (Cycle 3 — Codex Cycle-2 NEW HIGH #1 fix): the new behavior is gated behind config flag `phase1_ks_flags.ks01_preserve_distribution.enabled` (default false until promotion). The legacy `_tackled_short` code path remains the default until the promotion commit flips the flag to `true` in `config/defaults.yaml`. This makes the per-KS A/B a real two-arm comparison (Arm A = legacy code path, Arm B = new code path with `--set phase1_ks_flags.ks01_preserve_distribution.enabled=true`) rather than the same-code no-op the Cycle-2 plans produced."
    - "PASS_TD_GATE calibration unchanged after the fix (RZ pass-TD rate still ~55% at yard_line in (1,3))"
    - "RUN_TD_GATE calibration unchanged after the fix (RZ run-TD rate still ~35% at yard_line in (1,3))"
    - "Both _resolve_pass and _resolve_run thread the pre-clamp sampled value through to the new failure-branch helper (when the flag is true)"
    - "p1.ks01.bare and p1.ks01.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-31, with KS delta ≤ -0.01 on QB pass_yards. The bare entry uses `--baseline bare --arm-b-base bare --set phase1_ks_flags.ks01_preserve_distribution.enabled=true`; the full entry uses `--baseline defaults --set phase1_ks_flags.ks01_preserve_distribution.enabled=true`."
    - "Per D-25/D-26: this plan ships as a single KS-XX commit chain (Task 1 RED, Task 2 GREEN behind flag, Task 3 ledger A/B, Task 4 promotion-state commit incl. flag-default flip)"
    - "Per D-33: TDD-first for KS-01 RZ-stack work; failing tests committed before the implementation; new tests cover BOTH flag-off (legacy behavior preserved) AND flag-on (new behavior) branches"
    - "Per D-35: existing 1,200+ test suite stays green throughout (verified after Task 2 with `uv run pytest tests/ -v`)"
    - "Per D-10: no calibrated goal-line-only variant for v1; if subsequent measurements show goal-line distortion, revisit as a follow-up — not blocking Phase 1"
  artifacts:
    - path: "src/fantasy_sim/engine/play_resolver.py"
      provides: "Replaced _tackled_short() variant honoring D-09; CATCH_YARDS_BOOST and clamp logic untouched (those are KS-04 / KS-15)"
      contains: "max(1, min(yard_line - 1"
    - path: "tests/test_engine/test_play_resolver.py"
      provides: "RED→GREEN tests for KS-01: ks01_tackled_short_preserves_distribution_at_goal_line, ks01_pass_td_gate_calibration_unchanged_after_fix, ks01_run_td_gate_calibration_unchanged_after_fix"
      contains: "def test_ks01_"
  key_links:
    - from: "src/fantasy_sim/engine/play_resolver.py::_resolve_pass"
      to: "the new tackled-short variant"
      via: "the pre-clamp player_yards value (before _clamp_yards on line ~274)"
      pattern: "max\\(1, min\\(state\\.yard_line - 1"
    - from: "src/fantasy_sim/engine/play_resolver.py::_resolve_run"
      to: "the new tackled-short variant"
      via: "raw_yards (before _clamp_yards on line ~364)"
      pattern: "max\\(1, min\\(state\\.yard_line - 1"
---

<objective>
Implement KS-01 — fix the punitive `_tackled_short()` rewrite that fires when the red-zone TD gate denies a touchdown. Per D-09: when the gate fails, yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp)) — preserves the sampled distribution and stops the ball 1 yard short of the goal. This unblocks the rest of the RZ stack (KS-04 boost retune, KS-15 clamping fix) by removing the largest mean-bias mechanism (HYPOTHESES.md KS-01 lines 103-115).

Purpose: QB pass_yards mean bias is currently ~-28 yd/game (TGT-09 target ±5). The biggest contributor is `_tackled_short()` overwriting realistic catch yardage with `rng.integers(1, max(2, yard_line // 3))`, which truncates the upper tail of the receiver's distribution every time a long catch in the RZ doesn't pass the gate.

Output: Updated play_resolver.py with new tackled-short variant; new tests (RED→GREEN→REFACTOR) for the variant; existing pytest suite stays green; `p1.ks01.bare` and `p1.ks01.full` ledger entries pass hard floor.
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
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@src/fantasy_sim/engine/play_resolver.py
@tests/test_engine/test_play_resolver.py

<interfaces>
From src/fantasy_sim/engine/play_resolver.py (current, pre-fix):

```python
# Lines 21-49 — RZ-stack constants (DO NOT MODIFY in this plan; KS-04/KS-15 own them)
CLOCK_RUN = 35
CLOCK_PASS_COMPLETE = 30
CLOCK_PASS_INCOMPLETE = 5
CLOCK_SACK = 35
CATCH_YARDS_BOOST = 1
SACK_YARDS = np.array([-3, -4, -5, -5, -6, -7, -7, -8, -8, -10])
HOME_FIELD_YARDS_BONUS = 0.5
PASS_TD_GATE = {(1, 3): 0.55, (4, 5): 0.50, (6, 10): 0.45, (11, 15): 0.25, (16, 20): 0.15}
RUN_TD_GATE = {(1, 3): 0.35, (4, 5): 0.30, (6, 10): 0.20, (11, 15): 0.12, (16, 20): 0.08}

# Lines 421-424 — current punitive variant (REPLACE in this plan)
def _tackled_short(yard_line: int, rng: np.random.Generator) -> int:
    """Determine yards gained when a player is tackled short of the goal line."""
    short_amount = int(rng.integers(1, max(2, yard_line // 3)))
    return max(0, yard_line - short_amount)

# Lines 263-284 — _resolve_pass call site for _tackled_short
# Currently: yards = _clamp_yards(state.yard_line, yards) on line 274,
# THEN line 283: yards = _tackled_short(state.yard_line, rng)
# Note: by line 283, the original sampled value (player_yards from line 267 or 271) has already
# been overwritten by _clamp_yards. The fix must thread player_yards (PRE-clamp) through to the
# new variant, OR rename so the failure-branch reads the pre-clamp value directly.

# Lines 362-377 — _resolve_run call site for _tackled_short
# Same pattern: raw_yards on line 362 is pre-clamp; line 364 clamps; line 376 calls _tackled_short.
# Fix must thread raw_yards through.
```

From tests/test_engine/test_play_resolver.py (existing patterns to mirror):
- Module imports: `from fantasy_sim.engine.play_resolver import _tackled_short, _red_zone_td_gate, _resolve_pass, _resolve_run, PASS_TD_GATE, RUN_TD_GATE`
- Random seeding: `rng = np.random.default_rng(<int>)`
- Fixture usage: `sample_pbp`, `sample_rosters` from `tests/conftest.py`
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write failing tests for KS-01 distribution preservation and PASS/RUN gate calibration regression</name>
  <files>tests/test_engine/test_play_resolver.py</files>
  <read_first>
    - tests/test_engine/test_play_resolver.py (current test conventions: imports, fixture names, seeding style)
    - src/fantasy_sim/engine/play_resolver.py (current _tackled_short signature, PASS_TD_GATE / RUN_TD_GATE values, _red_zone_td_gate signature)
    - tests/conftest.py (sample_pbp / sample_rosters fixtures)
    - .planning/research/HYPOTHESES.md lines 103-115 (KS-01 mechanism description)
  </read_first>
  <behavior>
    - Test 1 (`test_ks01_tackled_short_variant_preserves_distribution_at_goal_line`): for yard_line=3 and sampled_yards_pre_clamp=8, the new variant returns 2 (== yard_line - 1). For sampled_yards_pre_clamp=1, returns 1 (== sampled value). For sampled_yards_pre_clamp=20, returns 2 (cap at yard_line - 1).
    - Test 2 (`test_ks01_tackled_short_variant_clamps_zero_to_one`): for sampled_yards_pre_clamp=0, returns 1 (the max(1, ...) floor). Documents D-09 "1 yard short" semantics.
    - Test 3 (`test_ks01_pass_td_gate_calibration_unchanged_after_fix`): runs _red_zone_td_gate(yard_line=3, "pass", rng, td_factor=1.0) over 100_000 trials and asserts true-rate ∈ [0.54, 0.56] (matches PASS_TD_GATE[(1,3)]=0.55 ± 0.01). Regression guard against accidental gate edits.
    - Test 4 (`test_ks01_run_td_gate_calibration_unchanged_after_fix`): same as Test 3 but for "run" — asserts true-rate ∈ [0.34, 0.36] (matches RUN_TD_GATE[(1,3)]=0.35).
    - Test 5 (`test_ks01_resolve_pass_failed_gate_yields_yards_in_safe_band`): builds a roster with a high-mean WR receiving_yards_dist (mean 12), runs _resolve_pass at state.yard_line=3 over 5000 trials with td_factor=0.0001 (force every gate to fail), asserts ALL returned yards values are in [1, 2] AND sample mean of yards is in (1.0, 2.0) — proves the variant is sampling, not always returning yard_line-1.
    - Test 6 (`test_ks01_resolve_run_failed_gate_yields_yards_in_safe_band`): same as Test 5 but for _resolve_run with a high-mean RB rushing_yards_dist; assert yards ∈ [1, 2] over 5000 trials.
  </behavior>
  <action>
Add the 6 tests above to `tests/test_engine/test_play_resolver.py` in a new section near the end of the file titled `# === KS-01: RZ TD-gate distribution preservation ===`. Use existing patterns:

```python
# === KS-01: RZ TD-gate distribution preservation ===

import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import (
    PASS_TD_GATE,
    RUN_TD_GATE,
    _red_zone_td_gate,
    _resolve_pass,
    _resolve_run,
)
# After Task 2 lands, also import the new variant. Until then, tests reference a function
# that does not yet exist — RED is expected.
from fantasy_sim.engine.play_resolver import _tackled_short_preserve_distribution  # KS-01 new helper

def test_ks01_tackled_short_variant_preserves_distribution_at_goal_line():
    rng = np.random.default_rng(42)
    # yard_line=3, sample within band → returns the sample
    assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=1) == 1
    # yard_line=3, sample exceeds band → returns yard_line - 1
    assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=8) == 2
    assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=20) == 2

def test_ks01_tackled_short_variant_clamps_zero_to_one():
    # sample == 0 (or negative) → floor at 1 per D-09 "1 yard short"
    assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=0) == 1
    assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=-2) == 1

def test_ks01_pass_td_gate_calibration_unchanged_after_fix():
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "pass", rng))
    rate = successes / n
    assert 0.54 <= rate <= 0.56, f"PASS_TD_GATE[(1,3)] regressed: rate={rate}"

def test_ks01_run_td_gate_calibration_unchanged_after_fix():
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "run", rng))
    rate = successes / n
    assert 0.34 <= rate <= 0.36, f"RUN_TD_GATE[(1,3)] regressed: rate={rate}"

# Tests 5 + 6 use sample_rosters fixture from conftest; mock state.yard_line=3,
# loop 5000 trials with td_factor=0.0001 to force every gate to fail; collect yards.
# Assertion structure: yards_arr = np.array([...]); assert yards_arr.min() >= 1 and yards_arr.max() <= 2
# Plan-level note: if conftest fixture for high-mean WR/RB does not exist, skip Tests 5+6 with
# pytest.mark.skip("requires high-mean WR/RB fixture") and add as TODO; the unit tests above
# (Tests 1-4) are sufficient for KS-01 acceptance.
```

Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01
```

EXPECTED: Tests 1-2 fail with ImportError (`_tackled_short_preserve_distribution` doesn't exist yet). Tests 3-4 PASS (calibration baseline check). Tests 5-6 fail OR skip. This is the RED state.

Commit: `test(01-01): add failing tests for KS-01 RZ TD-gate distribution preservation`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01 2>&1 | grep -E "FAILED|PASSED|ERROR" | head -20</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks01_tackled_short_variant_preserves_distribution_at_goal_line(`
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks01_pass_td_gate_calibration_unchanged_after_fix(`
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks01_run_td_gate_calibration_unchanged_after_fix(`
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01_tackled_short_variant_preserves` exits non-zero (RED)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01_pass_td_gate_calibration` exits 0 (calibration baseline check passes)
    - `git log -1 --pretty=%s` matches `test(01-01): add failing tests for KS-01`
  </acceptance_criteria>
  <done>RED tests committed; calibration regression-guard tests pass; new variant tests fail with the expected ImportError.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement _tackled_short_preserve_distribution per D-09 and rewire call sites</name>
  <files>src/fantasy_sim/engine/play_resolver.py</files>
  <read_first>
    - src/fantasy_sim/engine/play_resolver.py (current _resolve_pass / _resolve_run / _tackled_short / _clamp_yards)
    - tests/test_engine/test_play_resolver.py (the RED tests just added)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-09, D-10)
    - .planning/research/HYPOTHESES.md lines 103-115
  </read_first>
  <action>
**REVISED Cycle 3 (Codex Cycle-2 NEW HIGH #1 fix):** the implementation is gated behind the `phase1_ks_flags.ks01_preserve_distribution.enabled` flag (added to `config/defaults.yaml` by Plan 00 Task 8, default `false`). Both code paths coexist; runtime branches on the flag read at module import time. This makes the Plan 00 → Plan 01 A/B contract a real two-arm comparison.

Modify `src/fantasy_sim/engine/play_resolver.py`:

1. Add the import at the top of the file (after the existing imports):

```python
from fantasy_sim.config.loader import get_phase1_ks_flags

# Read flag once at module import (validate.py runs both arms in a single
# Python process; flag flips during a process require a restart, which the
# bare-isolation A/B harness already does between arms via fresh GameContextBuilder).
_KS01_PRESERVE_DIST = (
    get_phase1_ks_flags()
    .get("ks01_preserve_distribution", {})
    .get("enabled", False)
)
```

2. Add a new helper function near the existing `_tackled_short` (around line 421), BEFORE the existing function:

```python
def _tackled_short_preserve_distribution(yard_line: int, sampled_yards_pre_clamp: int) -> int:
    """KS-01: when the RZ TD gate fails, preserve the sampled distribution.

    Returns yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp)) per D-09.
    Reserves 1 yard short of the goal so the play does not score; preserves the
    rest of the catch/run distribution.

    Gated behind ``phase1_ks_flags.ks01_preserve_distribution.enabled`` (default
    false) per Cycle 3 D-45 — so the per-KS A/B genuinely measures the marginal
    effect of this code path vs. the legacy ``_tackled_short`` rewrite.
    """
    return max(1, min(yard_line - 1, sampled_yards_pre_clamp))
```

3. Keep the existing `_tackled_short` AS THE LEGACY PATH (do NOT remove). Both call sites branch on `_KS01_PRESERVE_DIST` to pick which helper runs.

4. Rewire `_resolve_pass` (around line 283) — branch on the flag:
```python
# BEFORE (current line 283):
yards = _tackled_short(state.yard_line, rng)
# AFTER (Cycle 3 — flag-gated; legacy path preserved as the default branch):
if _KS01_PRESERVE_DIST:
    yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)
else:
    yards = _tackled_short(state.yard_line, rng)
```
NOTE: `player_yards` is the variable defined on line 267 (`int(rng.choice(full_dist)) + boost`) or line 271 (`(team_yards if team_yards > 0 else int(rng.integers(3, 12))) + boost`). It is the pre-`_clamp_yards`, pre-`_apply_home_field` value WITH the boost included. For KS-01, this is the correct pre-clamp source. (The boost will be 0 in non-RZ paths but state.yard_line ≤ 20 here so we're inside the RZ; per current code line 265, boost=0 in RZ. So player_yards in the RZ branch == raw sample without boost. Correct.)

5. Rewire `_resolve_run` (around line 376) — same flag-gated pattern:
```python
# BEFORE (current line 376):
yards = _tackled_short(state.yard_line, rng)
# AFTER (Cycle 3 — flag-gated):
if _KS01_PRESERVE_DIST:
    yards = _tackled_short_preserve_distribution(state.yard_line, raw_yards)
else:
    yards = _tackled_short(state.yard_line, rng)
```
NOTE: `raw_yards` on line 362 is `_apply_home_field(player_yards, is_home, rng)` — pre-clamp, post-home-field. Correct pre-clamp source.

6. Run the new tests + the existing full suite:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01
```

EXPECTED with flag default false: Tests 3-4 (PASS_TD_GATE / RUN_TD_GATE calibration regression guards) pass; Tests 1-2 still pass (the new helper exists; the test calls it directly without going through the flag-gated path, so the helper's behavior is testable regardless of flag state); Tests 5-6 PASS or SKIP.

To verify the flag-on path works, add a quick interactive check:
```bash
uv run python -c "
import os
# Force-flip the flag for this verify check via env or by inspecting the module import.
# Simplest: assert the helper exists and produces the documented output.
from fantasy_sim.engine.play_resolver import _tackled_short_preserve_distribution
assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=8) == 2
assert _tackled_short_preserve_distribution(yard_line=3, sampled_yards_pre_clamp=1) == 1
print('KS-01 helper round-trip OK')
"
```

7. Run the full play_resolver test suite to catch regressions:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v
```

EXPECTED: All existing tests still pass. With flag default false, the legacy `_tackled_short` path is the active one — existing test expectations are unchanged.

8. Run full pytest suite:
```bash
uv run pytest tests/ -v
```

EXPECTED: 1,200+ tests pass (per D-35).

Commit: `feat(01-01): implement KS-01 _tackled_short_preserve_distribution per D-09 (gated behind phase1_ks_flags.ks01_preserve_distribution per Cycle 3 D-45)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01 && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `def _tackled_short_preserve_distribution(yard_line: int, sampled_yards_pre_clamp: int) -> int:`
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `return max(1, min(yard_line - 1, sampled_yards_pre_clamp))`
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `_KS01_PRESERVE_DIST` (flag read at module import — REVISED Cycle 3)
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `if _KS01_PRESERVE_DIST:` (flag-gated branch — REVISED Cycle 3)
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)` (in `_resolve_pass`)
    - `src/fantasy_sim/engine/play_resolver.py` contains the literal string `yards = _tackled_short_preserve_distribution(state.yard_line, raw_yards)` (in `_resolve_run`)
    - `grep -c "yards = _tackled_short(state.yard_line, rng)" src/fantasy_sim/engine/play_resolver.py` returns 2 (legacy path PRESERVED in both _resolve_pass and _resolve_run as the else-branch — REVISED Cycle 3, was 0 in earlier draft)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01` exits 0
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-01): implement KS-01`
  </acceptance_criteria>
  <done>GREEN — all KS-01 tests pass, full suite green, both call sites have flag-gated branches with the legacy path preserved as the default.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-01 in isolation and full-stack; commit ledger entries</name>
  <files>(no source code modifications — runs scripts/validate.py and writes ledger entries)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md (per-plan A/B labels and hard-floor criteria)
    - scripts/validate.py (CLI flags; --baseline {bare,defaults}, --label, --sims, --seasons, --scoring, --positions)
    - src/fantasy_sim/validation/ledger.py (ledger schema + format_ledger_table)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-26 dependency order, D-27 label scheme, D-28 validation set, D-29 isolation+full-stack rule, D-31 promotion bar for medium-large items)
  </read_first>
  <action>
Run BOTH A/B passes per D-29 (REVISED Cycle 3 — uses Plan 00's `--arm-b-base bare` AND the `phase1_ks_flags.ks01_preserve_distribution.enabled` feature flag from D-45 for a real two-arm comparison). Run sequentially (the harness shares an internal cache).

```bash
# True isolation: bare baseline + KS-01 flag flipped on → marginal impact of KS-01 code path
# Arm A = bare engines + KS-01 flag default (false, legacy code path)
# Arm B = bare engines + KS-01 flag overridden true (new code path)
# This is now a REAL two-arm comparison per Cycle-3 D-45.
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline bare --arm-b-base bare \
  --set "phase1_ks_flags.ks01_preserve_distribution.enabled=true" \
  --label "p1.ks01.bare"

# Full-stack: promoted defaults + KS-01 flag overlay → compatibility check vs full stack
# Arm A = current promoted defaults (KS-01 flag still false)
# Arm B = current promoted defaults + KS-01 flag overridden true
uv run python scripts/validate.py \
  --sims 200 \
  --seasons 2022 2023 2024 \
  --scoring ppr \
  --positions QB RB WR TE \
  --baseline defaults \
  --set "phase1_ks_flags.ks01_preserve_distribution.enabled=true" \
  --label "p1.ks01.full"

# Inspect ledger
uv run python scripts/validate.py --show-ledger | grep "p1.ks01"
```

NOTE: REVISED Cycle 3 — KS-01 is now flag-gated per Cycle-2 NEW HIGH #1 fix. Both arms still execute the same patched code, but the flag flip in Arm B is what genuinely picks the new branch via the `if _KS01_PRESERVE_DIST:` guard. The earlier Cycle-2 plan (no flag) had both arms execute identical code — that was structurally a no-op and is now fixed.

Capture stdout/stderr to per-run logs at `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks01.bare.log` and `.../logs/p1.ks01.full.log` for the SUMMARY.md.

Evaluate per D-31 (medium-large item):
- Hard floor: `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05` for BOTH the bare AND full ledger entries
- Promotion bar: KS delta on QB pass_yards primary target ≤ -0.01 (i.e., distribution improves by at least 0.01)

Promotion decision tree:
1. If both ledger entries pass hard floor AND QB pass_yards KS delta ≤ -0.01 → **PROMOTE** (KS-01 stays in main branch; proceed to Plan 02 KS-04)
2. If hard floor passes but QB pass_yards KS doesn't move ≤ -0.01 → mark "shipped no-op" per D-31 and proceed
3. If hard floor fails on EITHER entry → **REVERT** Task 2's commit (`git revert HEAD`), document the failure mode in SUMMARY, and STOP this plan with `## PLAN BLOCKED`. Re-engage discussion (D-09 chosen variant may need re-evaluation; per D-10, the calibrated goal-line variant is explicitly deferred).

Commit no code (this is a validation-only task). Append a single ledger-entry note to `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` (create if missing) with the promotion decision and key metrics.

Commit: `chore(01-01): record KS-01 A/B ledger entries (p1.ks01.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks01\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger` output contains the literal string `p1.ks01.bare`
    - `uv run python scripts/validate.py --show-ledger` output contains the literal string `p1.ks01.full`
    - The above grep verify command returns `2` (both entries present)
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` exists and contains a section header `## KS-01` with the promotion decision (PROMOTE / SHIPPED NO-OP / BLOCKED)
    - Both ledger entries' rank_corr regression is ≥ -0.005 (i.e., not worse than -0.005) AND MAE regression is ≤ +0.05 — verifiable by inspecting the ledger printout
    - `git log -1 --pretty=%s` matches `chore(01-01): record KS-01 A/B`
  </acceptance_criteria>
  <done>Both p1.ks01.bare and p1.ks01.full ledger entries exist; promotion decision recorded; if BLOCKED, KS-01 commit reverted and plan halted.</done>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit + SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (## KS-01 section)
  </read_first>
  <action>
Per D-25 (revised — promotion-state commit per KS plan), create the final promotion commit + SUMMARY.

**REVISED Cycle 3 (D-45):** if the A/B passes, the promotion commit ALSO flips `phase1_ks_flags.ks01_preserve_distribution.enabled` from `false` to `true` in `config/defaults.yaml` so downstream defaults runs (incl. Plan 11's `p1.aggregate.full`) automatically pick up the new code path. The flag REMAINS in defaults.yaml (we don't delete the block) so emergency rollback is just flipping it back to `false`.

Determine promotion state from PROMOTION-NOTES `## KS-01` section per D-31 medium-large bar:
- Hard floor passes + QB pass_yards KS Δ ≤ -0.01 → `PROMOTED` (flip flag default to `true` in defaults.yaml)
- Hard floor passes but KS doesn't move → `SHIPPED-NO-OP` (still flip flag — the bug fix is correct even if KS doesn't budge per D-31)
- Hard floor fails → `BLOCKED` (do NOT flip flag; flag stays `false`; Task 2's code change stays in the tree but inert)

If `PROMOTED` or `SHIPPED-NO-OP`, edit `config/defaults.yaml`:

```yaml
# BEFORE (default after Plan 00 Task 8):
phase1_ks_flags:
  ks01_preserve_distribution:
    enabled: false

# AFTER (Plan 01 promotion):
phase1_ks_flags:
  ks01_preserve_distribution:
    enabled: true   # KS-01 PROMOTED 2026-04-26 — see logs/PROMOTION-NOTES.md ## KS-01
```

If `BLOCKED`, do not edit defaults.yaml; leave the flag default `false`.

Run the full test suite to confirm the flag flip doesn't break anything:
```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-01-SUMMARY.md`:

```markdown
# Plan 01 Summary — KS-01 RZ TD-gate truncation fix

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED>
**Phase:** 1
**Wave:** 1
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. Replaced `_tackled_short()` rewrite with `max(1, min(yard_line - 1, sampled_yards_pre_clamp))` (D-09)
2. NEW Cycle 3 (D-45): gated behind `phase1_ks_flags.ks01_preserve_distribution.enabled` for a genuine two-arm A/B
3. PASS_TD_GATE / RUN_TD_GATE calibration regression tests as a guard
4. RED→GREEN test pair (TDD per D-33)
5. (If PROMOTED/SHIPPED-NO-OP): flag default flipped from `false` to `true` in `config/defaults.yaml`

## Ledger results

| Entry | rank_corr Δ | MAE Δ | QB pass_yards KS Δ | Hard floor? | Promotion bar? |
|-------|-------------|-------|---------------------|-------------|----------------|
| p1.ks01.bare | ... | ... | ... | ✅/❌ | ✅/❌ |
| p1.ks01.full | ... | ... | ... | ✅/❌ | ✅/❌ |

## Codex review fixes addressed by this plan

- **Cycle-2 NEW HIGH #1** (per-KS code-change A/B is no-op): KS-01 ships behind `phase1_ks_flags.ks01_preserve_distribution.enabled`. Both A/B runs use `--set phase1_ks_flags.ks01_preserve_distribution.enabled=true` so Arm B genuinely flips the new code path on while Arm A stays on the legacy default. Marginal effect of KS-01 is now genuinely measured.
```

Commit:

```bash
PROMO_STATE="PROMOTED"  # or SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-01-SUMMARY.md
# If PROMOTED or SHIPPED-NO-OP, also stage the defaults.yaml flag flip
if [ "$PROMO_STATE" != "BLOCKED" ]; then
  git add config/defaults.yaml
fi
git commit -m "feat(01-01): KS-01 ${PROMO_STATE} — RZ TD-gate truncation fix

Wave 1. Replaces _tackled_short() with distribution-preserving variant
per D-09 (gated behind phase1_ks_flags.ks01_preserve_distribution per
Cycle 3 D-45). Bare-isolation A/B uses --baseline bare --arm-b-base bare
--set phase1_ks_flags.ks01_preserve_distribution.enabled=true per Plan 00
+ Cycle-3 D-45 (real two-arm comparison; closes Codex Cycle-2 NEW HIGH #1
for KS-01).

If PROMOTED/SHIPPED-NO-OP: flag default flipped to true in defaults.yaml."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-01-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-01-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - SUMMARY's ledger results table is filled in
    - `git log -1 --pretty=%s` matches `feat(01-01): KS-01 PROMOTED|SHIPPED-NO-OP|BLOCKED`
  </acceptance_criteria>
  <done>KS-01 promotion-state commit landed; SUMMARY captures the decision.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | This is offline simulation code; no untrusted input crosses any boundary. The change is a pure Python function modification. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01-01 | T (Tampering) | RZ TD-gate calibration constants (PASS_TD_GATE, RUN_TD_GATE) | mitigate | Task 1 adds calibration regression tests (test_ks01_pass_td_gate_calibration_unchanged_after_fix, test_ks01_run_td_gate_calibration_unchanged_after_fix). Any unintentional gate edit is caught by the 100k-trial rate check ±0.01. |
| T-01-01-02 | I (Information disclosure) | Ledger entries written to `~/.fantasy-sim/ledger/` | accept | Local-file ledger contains only synthetic projection metrics, no PII. |
| T-01-01-03 | D (Denial of service via runtime) | A/B validation run wall-clock | accept | --sims 200 × 3 seasons is bounded (~30 min per run). No external services in this plan. |
</threat_model>

<verification>
- All 3 tasks complete and committed in order
- `uv run pytest tests/ -v` exits 0 with all 1,200+ tests passing
- `uv run python scripts/validate.py --show-ledger | grep "p1.ks01" | wc -l` returns 2
- Promotion decision documented in `logs/PROMOTION-NOTES.md` under `## KS-01`
- If PROMOTED: KS-01 commit is HEAD~3 (Task 1 RED commit, Task 2 GREEN commit, Task 3 ledger commit)
- If BLOCKED: Task 2 reverted, only Task 1 RED commit + revert commit + Task 3 ledger commit remain
</verification>

<success_criteria>
- KS-01 requirement (REQUIREMENTS.md) marked deliverable: implementation + tests + ledger pair + promotion decision documented per "delivered" definition in REQUIREMENTS.md
- QB pass_yards KS delta on the `p1.ks01.full` ledger row is ≤ -0.01 (medium-large promotion bar per D-31), OR documented "shipped no-op" rationale
- Hard floor (rank_corr Δ ≥ -0.005, weekly_mae Δ ≤ +0.05) passes on BOTH bare AND full ledger entries
- PASS_TD_GATE and RUN_TD_GATE calibration tests still pass (regression guard)
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-01-SUMMARY.md` with:
- Frontmatter: phase, plan, subsystem (engine.play_resolver), tags (ks-01, rz-stack, bug-fix), key-files, metrics
- Commits table (Task 1 RED, Task 2 GREEN, Task 3 ledger)
- Deviations: any (e.g., if Tests 5/6 were skipped) or "None"
- Self-Check: PASSED or FAILED with details
- Promotion decision summary: PROMOTE / SHIPPED NO-OP / BLOCKED, with the QB pass_yards KS delta value and rank_corr/MAE deltas from both ledger entries
</output>
