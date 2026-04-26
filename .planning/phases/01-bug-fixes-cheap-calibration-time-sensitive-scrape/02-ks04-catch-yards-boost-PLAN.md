---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 02
type: tdd
wave: 2
depends_on: ["01"]
files_modified:
  - src/fantasy_sim/engine/play_resolver.py
  - tests/test_engine/test_play_resolver.py
autonomous: true
requirements: [KS-04]
must_haves:
  truths:
    - "Per D-11/D-12: CATCH_YARDS_BOOST is +1.5 (float), applied conditionally only when raw_yards > yard_line (i.e., when _clamp_yards would actually fire)"
    - "Per D-13: ship the conditional boost as an intermediate even though KS-15 will obviate it later — captures the intermediate ledger entry"
    - "p1.ks04.bare and p1.ks04.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-31"
    - "Per D-25/D-26: KS-04 commit chain ships immediately after KS-01 lands (dependency-mandatory order)"
    - "Per D-33: TDD-first for KS-04 RZ-stack work"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/engine/play_resolver.py"
      provides: "CATCH_YARDS_BOOST = 1.5 with conditional application in _resolve_pass — boost added only when the un-clamped sample would have been clamped"
      contains: "CATCH_YARDS_BOOST = 1.5"
    - path: "tests/test_engine/test_play_resolver.py"
      provides: "RED→GREEN tests for KS-04: ks04_boost_conditional_when_clamp_fires, ks04_boost_zero_when_no_clamp, ks04_boost_zero_in_red_zone"
      contains: "def test_ks04_"
  key_links:
    - from: "_resolve_pass yard-sampling branch"
      to: "the conditional boost"
      via: "checking raw_yards > state.yard_line BEFORE _clamp_yards is applied"
      pattern: "if .*raw.*> .*yard_line.*:"
---

<objective>
Implement KS-04 — retune `CATCH_YARDS_BOOST` from `+1` to `+1.5` (per D-12) AND apply it conditionally only when `_clamp_yards` would actually fire (per D-11). This captures the intermediate KS gain in the ledger before KS-15 obviates the boost entirely (D-13/D-15).

Purpose: HYPOTHESES.md KS-04 (lines 491-503) shows the existing boost is undersized for WRs with high-mean receiving distributions. Conditional application prevents spurious yardage when `_clamp_yards` was never going to fire (i.e., raw_yards ≤ yard_line, no clamping happens, no compensation needed).

Output: Updated `CATCH_YARDS_BOOST = 1.5` constant; conditional check in `_resolve_pass`; new tests; both ledger entries pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@.planning/research/HYPOTHESES.md
@src/fantasy_sim/engine/play_resolver.py

<interfaces>
From src/fantasy_sim/engine/play_resolver.py (post-KS-01):

```python
# Line 32 (CURRENT): CATCH_YARDS_BOOST = 1
# Lines 263-271 (CURRENT _resolve_pass yards branch):
#   boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0
#   if full_dist is not None and len(full_dist) > 0:
#       player_yards = int(rng.choice(full_dist)) + boost
#   else:
#       team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
#       player_yards = (team_yards if team_yards > 0 else int(rng.integers(3, 12))) + boost
#   yards = _apply_home_field(player_yards, is_home, rng)
#   yards = _clamp_yards(state.yard_line, yards)
```

The boost is unconditional in non-RZ paths. KS-04 changes the policy: the boost is added only when `raw_sample > state.yard_line` (i.e., the field-position clamp would actually clip the sample). This prevents over-counting yardage on plays where the sample fits inside the field.
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write failing tests for KS-04 conditional boost behavior</name>
  <files>tests/test_engine/test_play_resolver.py</files>
  <read_first>
    - tests/test_engine/test_play_resolver.py (existing test file post-KS-01)
    - src/fantasy_sim/engine/play_resolver.py (current CATCH_YARDS_BOOST = 1, lines 32 + 263-265)
    - .planning/research/HYPOTHESES.md lines 491-503 (KS-04 mechanism description)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-11, D-12, D-13)
  </read_first>
  <behavior>
    - Test 1 (`test_ks04_boost_value_is_1_5`): assert `from fantasy_sim.engine.play_resolver import CATCH_YARDS_BOOST` and `CATCH_YARDS_BOOST == 1.5`. Documents D-12.
    - Test 2 (`test_ks04_boost_conditional_when_clamp_fires`): build a roster + state at yard_line=10 with a WR receiving_yards_dist that always samples 25; run _resolve_pass over many trials; assert player_yards observed includes `25 + 1.5` (or close) when the boost fires (i.e., before the clamp clips the sample). Practical assertion: across 1000 trials, the OBSERVED yards should be `int(min(yard_line, raw_sample))` where raw_sample includes the boost — so observed yards == 10 (clamp wins) but the BOOST WAS APPLIED before clamp. Verifiable via debug logging or by checking that an "additive shift" is detectable in the per-play resolution path.
    - Test 3 (`test_ks04_boost_zero_when_no_clamp`): build a roster + state at yard_line=80 with a WR receiving_yards_dist that always samples 5; run _resolve_pass over 1000 trials with seed; assert observed mean yards is ~5.5 (5 base + 0.5 home-field expected) and NOT ~6.5 (which would be 5 + 1 boost + 0.5 home-field per OLD policy). The new conditional policy: raw_sample (5) ≤ yard_line (80), so no boost.
    - Test 4 (`test_ks04_boost_zero_in_red_zone`): same as Test 3 but state at yard_line=15 (RZ), assert observed mean is ~5.5 (no RZ boost per existing line-265 logic, preserved).
  </behavior>
  <action>
Append the 4 tests under a new section header `# === KS-04: CATCH_YARDS_BOOST conditional retune ===` in `tests/test_engine/test_play_resolver.py`:

```python
# === KS-04: CATCH_YARDS_BOOST conditional retune ===

def test_ks04_boost_value_is_1_5():
    from fantasy_sim.engine.play_resolver import CATCH_YARDS_BOOST
    assert CATCH_YARDS_BOOST == 1.5, f"D-12 requires +1.5 boost, got {CATCH_YARDS_BOOST}"

def test_ks04_boost_zero_when_no_clamp():
    """If raw_sample <= yard_line, no clamp would fire → no boost (D-11)."""
    # Build a deterministic-WR fixture with receiving_yards_dist = np.array([5, 5, 5])
    # Run _resolve_pass at state.yard_line=80 over 2000 trials with rng seed 0
    # Observed mean yards should be 5.0 + 0.5 (home-field expected) = 5.5
    # NOT 5.0 + 1.5 + 0.5 = 7.0
    # Tolerance: ±0.1 over 2000 trials
    # ... (use sample_rosters fixture pattern; mock or build a minimal roster inline)
    pass  # implementation in this task uses local fixture builder; see existing tests for pattern

def test_ks04_boost_zero_in_red_zone():
    """RZ branch (yard_line ≤ 20) keeps boost=0 per existing line-265 logic — KS-04 doesn't change RZ behavior."""
    # Same as Test 3 but state.yard_line=15
    # Expected mean yards ~5.5 (5 + 0.5 home-field), not 6.5
    pass

def test_ks04_boost_conditional_when_clamp_fires():
    """If raw_sample > yard_line, clamp WOULD fire → boost IS applied (D-11)."""
    # state.yard_line=10, WR dist always samples 25 (so raw + boost = 26.5, then clamp to 10)
    # Observed yards == 10 (clamp wins on the result), but the path through play_resolver
    # MUST add the boost before clamp. Easiest assertion: dispatch one resolve and inspect
    # the intermediate value via a monkeypatch of _clamp_yards that records its input.
    # Alternative: when raw_sample is just barely above yard_line (e.g., raw=11 at yard_line=10),
    # observed yards is 10 (clamped from raw+boost=12.5→10) — same as without boost.
    # This test relies on monkeypatching to verify the BRANCH was taken; without monkeypatch,
    # use Test 3's negative (boost not applied) to indirectly confirm the conditional.
    pass
```

For Tests 2-4, use existing fixtures (search for `sample_rosters`, `expanded_pbp` in `tests/conftest.py`; build a minimal one-WR roster inline if needed). The tests should be enough to make the BRANCH detectable in `_resolve_pass`.

Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks04
```

EXPECTED: Test 1 fails with AssertionError (`CATCH_YARDS_BOOST` is still `1`). Tests 2-4 may pass or fail depending on current behavior; the precise expected outcome with `+1` unconditional is mean ~6.5 in non-clamp scenarios, so Tests 3+4 fail (observed ~6.5 vs expected ~5.5). RED state.

Commit: `test(01-02): add failing tests for KS-04 conditional CATCH_YARDS_BOOST retune`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k ks04 2>&1 | grep -E "FAILED|PASSED" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks04_boost_value_is_1_5`
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks04_boost_conditional_when_clamp_fires`
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks04_boost_zero_when_no_clamp`
    - `tests/test_engine/test_play_resolver.py` contains the literal string `def test_ks04_boost_zero_in_red_zone`
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks04_boost_value_is_1_5` exits non-zero (RED — boost is still 1)
    - `git log -1 --pretty=%s` matches `test(01-02): add failing tests for KS-04`
  </acceptance_criteria>
  <done>RED tests committed; at minimum Test 1 fails confirming the constant change is required.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — set CATCH_YARDS_BOOST = 1.5 and apply conditionally in _resolve_pass</name>
  <files>src/fantasy_sim/engine/play_resolver.py</files>
  <read_first>
    - src/fantasy_sim/engine/play_resolver.py (lines 32, 263-274 — current boost site)
    - tests/test_engine/test_play_resolver.py (Tests added in Task 1)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-11, D-12)
  </read_first>
  <action>
Modify `src/fantasy_sim/engine/play_resolver.py`:

1. Change line 32:
```python
# BEFORE:
CATCH_YARDS_BOOST = 1
# AFTER (D-12):
CATCH_YARDS_BOOST = 1.5
```

2. Update the comment block above (lines 26-31) to reflect the conditional policy:
```python
# Calibration: per-player yards distributions are field-position-independent,
# but the sim samples them at specific field positions where _clamp_yards()
# truncates long catches (e.g., a 30-yard catch at the 20 is clamped to 20).
# This systematically reduces yards/completion vs the distribution mean.
# A conditional additive boost compensates without changing the distribution
# shape or game physics — applied only when the un-clamped sample would have
# been clipped by _clamp_yards (per KS-04 D-11). KS-15 will obviate this.
CATCH_YARDS_BOOST = 1.5
```

3. In `_resolve_pass` (lines 263-274), replace the boost computation. The current code:
```python
boost = CATCH_YARDS_BOOST if state.yard_line > 20 else 0
if full_dist is not None and len(full_dist) > 0:
    player_yards = int(rng.choice(full_dist)) + boost
else:
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
    player_yards = (team_yards if team_yards > 0 else int(rng.integers(3, 12))) + boost

yards = _apply_home_field(player_yards, is_home, rng)
yards = _clamp_yards(state.yard_line, yards)
```

Becomes (KS-04):
```python
# Sample raw yards first
if full_dist is not None and len(full_dist) > 0:
    raw_sample = int(rng.choice(full_dist))
else:
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
    raw_sample = team_yards if team_yards > 0 else int(rng.integers(3, 12))

# KS-04 D-11: apply boost ONLY when _clamp_yards would actually fire
# (i.e., raw_sample > yard_line) AND we are outside the red zone.
# Inside the RZ, the TD gate controls scoring and the boost would inflate TDs.
if state.yard_line > 20 and raw_sample > state.yard_line:
    player_yards = raw_sample + CATCH_YARDS_BOOST
else:
    player_yards = raw_sample

yards = _apply_home_field(player_yards, is_home, rng)
yards = _clamp_yards(state.yard_line, yards)
```

NOTE: `player_yards` may now be a float (because boost is 1.5). `_apply_home_field` and `_clamp_yards` both handle ints — convert at the boundary if needed:
```python
player_yards = int(round(player_yards)) if isinstance(player_yards, float) else player_yards
```

Then update `yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)` (the KS-01 line) to ensure `player_yards` matches the parameter type expected by the helper (int). The KS-01 helper signature was `(yard_line: int, sampled_yards_pre_clamp: int) -> int`.

4. Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks04
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks01  # KS-01 must still pass
uv run pytest tests/ -v
```

EXPECTED: All KS-01 + KS-04 tests pass; full suite green.

Commit: `feat(01-02): implement KS-04 conditional CATCH_YARDS_BOOST=1.5 per D-11/D-12`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k "ks01 or ks04" && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "CATCH_YARDS_BOOST = 1.5" src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c "CATCH_YARDS_BOOST = 1$" src/fantasy_sim/engine/play_resolver.py` returns 0 (old value removed)
    - `grep -c "raw_sample > state.yard_line" src/fantasy_sim/engine/play_resolver.py` returns 1 (conditional check exists)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks04_boost_value_is_1_5` exits 0
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k "ks01 or ks04"` exits 0 (no regression on KS-01)
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-02): implement KS-04`
  </acceptance_criteria>
  <done>GREEN — conditional boost in place; KS-01 unchanged; full suite green.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-04 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-13, D-29, D-31)
  </read_first>
  <action>
Run BOTH A/B passes per D-29:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --label "p1.ks04.bare"

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults --label "p1.ks04.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks04"
```

Capture logs to `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks04.{bare,full}.log`.

Promotion decision per D-31 (medium-large item):
- Hard floor on both entries: rank_corr Δ ≥ -0.005, MAE Δ ≤ +0.05
- KS delta on QB pass_yards / WR receiving_yards primary targets ≤ -0.01 — OR documented "shipped no-op" per D-31

Per D-13 explicitly: "ship KS-04 (boost +1.5 conditional) as an intermediate, even though KS-15 will obviate it. This captures KS-04's intermediate KS gain in the ledger and provides a fallback if KS-15 fails the hard floor." So the bar is intentionally loose — even a "shipped no-op" is OK because KS-15 is the real fix.

If hard floor fails on either entry → revert Task 2's commit, document in `logs/PROMOTION-NOTES.md` under `## KS-04`, mark plan `## PLAN BLOCKED`. KS-15 plan can still proceed (it removes the boost entirely).

Append `## KS-04` section to `.../logs/PROMOTION-NOTES.md` with the decision.

Commit: `chore(01-02): record KS-04 A/B ledger entries (p1.ks04.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks04\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks04.bare` and `p1.ks04.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-04` with the decision
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-02): record KS-04 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision in PROMOTION-NOTES; if BLOCKED, code reverted.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| (n/a) | Pure simulation code change. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-02-01 | T (Tampering) | CATCH_YARDS_BOOST constant | mitigate | Test 1 enforces the literal value 1.5 — accidental edits caught immediately. |
| T-01-02-02 | T (Tampering) | RZ boost = 0 invariant | mitigate | Test 4 (`ks04_boost_zero_in_red_zone`) confirms RZ branch unaffected. |
</threat_model>

<verification>
- KS-01 + KS-04 tests both pass
- `grep "CATCH_YARDS_BOOST = 1.5" src/fantasy_sim/engine/play_resolver.py` returns 1 hit
- `p1.ks04.bare` and `p1.ks04.full` ledger entries exist
- Promotion decision documented
</verification>

<success_criteria>
- KS-04 requirement deliverable per REQUIREMENTS.md "delivered" definition
- Hard floor passes on both ledger entries (or BLOCKED + reverted)
- KS-01 still passing (no RZ-stack regression)
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-02-SUMMARY.md`.
</output>
