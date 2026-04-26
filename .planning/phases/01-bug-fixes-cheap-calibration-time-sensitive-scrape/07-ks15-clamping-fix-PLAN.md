---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 07
type: tdd
wave: 4
depends_on: ["00", "01", "02", "03", "04", "05", "06"]
files_modified:
  - src/fantasy_sim/engine/play_resolver.py
  - tests/test_engine/test_play_resolver.py
autonomous: true
requirements: [KS-15]
must_haves:
  truths:
    - "Per D-14: yards path uses min(yard_line, sample) for clamping; the un-clamped sample drives the TD probability gate (i.e., raw_sample > yard_line means a would-be TD even if final yards = yard_line)"
    - "Per D-15: CATCH_YARDS_BOOST is dropped to 0 in the same change (KS-04's tuned value becomes archival)"
    - "Per D-15b (added 2026-04-26 — MEDIUM-4 from 01-REVIEWS.md): the legacy non-roster paths in _resolve_pass (lines 302-321) and _resolve_run (lines 392-410) are patched to use the same min(yard_line, sample) + would-be-TD detection pattern. Tests added for both roster and non-roster paths. Codex MEDIUM-4 flagged that keeping two divergent clamping semantics in the same module is a foot-gun even if the validation harness only hits the roster path."
    - "PASS_TD_GATE and RUN_TD_GATE calibration unchanged (regression guard from KS-01 tests still passes)"
    - "Per D-29 (revised 2026-04-26 — HIGH-1): p1.ks15.bare uses --baseline bare --arm-b-base bare (true isolation, requires Plan 00); p1.ks15.full uses --baseline defaults"
    - "p1.ks15.bare and p1.ks15.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-31"
    - "Per D-25 (revised 2026-04-26 — MEDIUM-2): final commit message format `feat(01-07): KS-15 [PROMOTED|SHIPPED-NO-OP|BLOCKED] — field-position clamping fix + CATCH_YARDS_BOOST=0`"
    - "Per D-26: KS-15 commit chain ships after the post-KS-01/02/03/04/05/06/07 baseline lands (dependency-mandatory order; final RZ-stack commit). Plan 00 must land first."
    - "Per D-33: TDD-first for KS-15 RZ-stack work — RED tests + PASS_TD_GATE / RUN_TD_GATE regression guards committed first"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/engine/play_resolver.py"
      provides: "Field-position clamping fix per D-14 + CATCH_YARDS_BOOST = 0 per D-15; legacy non-roster paths patched per D-15b"
      contains: "CATCH_YARDS_BOOST = 0"
    - path: "tests/test_engine/test_play_resolver.py"
      provides: "RED→GREEN tests for KS-15: would-be-TD detection from raw_sample, clamping preserves yard_line as max yards, no double-counted yards regression, legacy-path semantics align with roster-path semantics"
      contains: "def test_ks15_"
  key_links:
    - from: "_resolve_pass _resolve_run (roster path AND legacy non-roster path)"
      to: "the TD-gate decision"
      via: "raw_sample (pre-clamp) — if raw_sample > yard_line, the play is a would-be TD that goes through the gate"
      pattern: "would_be_td = "
---

<objective>
Implement KS-15 — fix the field-position clamping bug that drops upper-tail values from QB pass_yards and WR receiving_yards distributions. Per D-14: convert truncated samples into TDs (via the gate) rather than truncating to the goal line. Per D-15: in the same change, drop `CATCH_YARDS_BOOST` to 0 — KS-15 obviates the boost's original justification (band-aid for clamping-induced under-counting).

Purpose: HYPOTHESES.md KS-15 (lines 159-171) shows the existing `_clamp_yards` truncates a 30-yard catch from the 20-yard line to a 20-yard catch (no TD), losing the upper tail. The fix: detect that the un-clamped sample would have scored, route through the TD gate, and preserve the distribution shape.

This is the BUG-FIX-CLASS change that makes KS-04's boost archival. Ship as a single commit (D-15).

Output: `_clamp_yards` semantics refactored; `CATCH_YARDS_BOOST = 0`; new TDD tests; PASS_TD_GATE / RUN_TD_GATE calibration regression tests still green; both ledger entries pass hard floor.
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
Post-KS-01 + post-KS-04 + post-KS-06 + post-KS-07 state of `_resolve_pass` (relevant section):

```python
# Sample raw yards (post-KS-04 conditional boost)
if full_dist is not None and len(full_dist) > 0:
    raw_sample = int(rng.choice(full_dist))
else:
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
    raw_sample = team_yards if team_yards > 0 else int(rng.integers(5, 18))  # post-KS-06

if state.yard_line > 20 and raw_sample > state.yard_line:  # post-KS-04
    player_yards = raw_sample + CATCH_YARDS_BOOST  # 1.5 currently; → 0 after KS-15
else:
    player_yards = raw_sample

yards = _apply_home_field(player_yards, is_home, rng)
yards = _clamp_yards(state.yard_line, yards)  # ← KS-15: replace this whole block

# TD determination with red zone gate (current — only fires for state.yard_line ≤ 20)
if is_complete and state.yard_line <= 20 and (state.yard_line - yards) <= 0:
    if _red_zone_td_gate(state.yard_line, "pass", rng, receiver.outcomes.receiving_td_factor):
        is_td = True
    else:
        yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)  # post-KS-01
        is_td = False
else:
    is_td = is_complete and (state.yard_line - yards) <= 0
```

KS-15 must:
1. Compute `would_be_td = (state.yard_line - raw_yards_with_home_field) <= 0` BEFORE clamping
2. If `would_be_td` AND outside the RZ → it's a TD (no gate needed; gate only applies inside the 20)
3. If `would_be_td` AND inside the RZ → run the gate; if pass, TD; if fail, use `_tackled_short_preserve_distribution`
4. If NOT `would_be_td` → yards = raw_yards_with_home_field (no clamp needed because the play didn't reach the goal)
5. Same logic for `_resolve_run` (with safety check for yard losses past own end zone)
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write failing tests for KS-15 distribution preservation and gate calibration</name>
  <files>tests/test_engine/test_play_resolver.py</files>
  <read_first>
    - tests/test_engine/test_play_resolver.py (existing tests, especially KS-01 / KS-04 sections)
    - src/fantasy_sim/engine/play_resolver.py (post-KS-04 _resolve_pass and _resolve_run)
    - .planning/research/HYPOTHESES.md lines 159-171 (KS-15 mechanism)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-14, D-15)
  </read_first>
  <behavior>
    - Test 1 (`test_ks15_catch_yards_boost_is_zero`): assert `CATCH_YARDS_BOOST == 0` (D-15).
    - Test 2 (`test_ks15_pass_long_catch_outside_rz_yields_td`): build state at yard_line=30 with WR dist that always samples 35; run _resolve_pass over 1000 trials; assert ALL plays are TDs (raw_sample > yard_line outside RZ → unconditional TD per D-14).
    - Test 3 (`test_ks15_pass_long_catch_inside_rz_routes_through_gate`): state at yard_line=10, WR dist samples 25; run _resolve_pass over 5000 trials with td_factor=1.0; assert TD rate ≈ PASS_TD_GATE[(6,10)] = 0.45 ± 0.02 (the gate fires for would-be TDs in RZ).
    - Test 4 (`test_ks15_pass_short_catch_no_double_counted_yards`): state at yard_line=80, WR dist samples 5; run over 1000 trials; assert observed mean yards ≈ 5.0 + 0.5 (home-field expected) ≈ 5.5; NOT 5 + boost = 6.5.
    - Test 5 (`test_ks15_pass_td_gate_calibration_unchanged`): regression — same as KS-01 Test 3 (re-run 100k trials at yard_line=3, "pass", assert rate ∈ [0.54, 0.56]).
    - Test 6 (`test_ks15_run_long_carry_outside_rz_yields_td`): state at yard_line=20 (just outside RZ for run; or state at yard_line=25), RB dist samples 30; assert all TDs.
    - Test 7 (`test_ks15_run_safety_branch_preserved`): state at yard_line=98 (own 2), RB dist samples 100 (massive loss / safety scenario); assert is_safety=True is detected before any clamping.
    - **Test 8 (`test_ks15_legacy_pass_path_preserves_distribution`) — NEW per D-15b (MEDIUM-4):** call `_resolve_pass` with `roster=None` (forces the legacy non-roster branch at lines 302-321) at yard_line=30 with `play_outcomes` that returns 35-yard pass samples; assert the observed yardage distribution preserves values up to and including 30 (TD scored), not arbitrarily clamped. Specifically: over 1000 trials, the TD rate is ~100% AND the recorded yards are NOT capped at some pre-fix lower value.
    - **Test 9 (`test_ks15_legacy_run_path_preserves_distribution`) — NEW per D-15b (MEDIUM-4):** symmetric test for `_resolve_run` legacy path at lines 392-410 with `roster=None`, yard_line=25, RB-bucket sampler returns 30 yards. Assert TDs land at 100% rate; safety branch still fires for yard_line=98 + raw_yards=100.
  </behavior>
  <action>
Append to `tests/test_engine/test_play_resolver.py` under `# === KS-15: field-position clamping fix ===`:

```python
# === KS-15: field-position clamping fix (D-14 + D-15) ===

def test_ks15_catch_yards_boost_is_zero():
    from fantasy_sim.engine.play_resolver import CATCH_YARDS_BOOST
    assert CATCH_YARDS_BOOST == 0, f"D-15 requires CATCH_YARDS_BOOST=0, got {CATCH_YARDS_BOOST}"

def test_ks15_pass_long_catch_outside_rz_yields_td():
    """state.yard_line=30, WR dist always samples 35 → would-be TD outside RZ → unconditional TD."""
    # Build minimal roster with a deterministic WR (receiving_yards_dist = np.array([35,35,35]))
    # state.yard_line = 30, run _resolve_pass 1000 times
    # Assert: all results have is_touchdown=True
    pass

def test_ks15_pass_long_catch_inside_rz_routes_through_gate():
    """state.yard_line=10, WR dist samples 25 → would-be TD inside RZ → gate fires.
    Expected TD rate matches PASS_TD_GATE[(6,10)] = 0.45 ± 0.02 over 5000 trials."""
    pass

def test_ks15_pass_short_catch_no_double_counted_yards():
    """state.yard_line=80, WR dist samples 5 → observed yards ~5.5 (home-field), NOT ~6.5."""
    pass

def test_ks15_pass_td_gate_calibration_unchanged():
    rng = np.random.default_rng(0)
    n = 100_000
    successes = sum(1 for _ in range(n) if _red_zone_td_gate(3, "pass", rng))
    rate = successes / n
    assert 0.54 <= rate <= 0.56, f"PASS_TD_GATE[(1,3)] regressed: rate={rate}"

def test_ks15_run_long_carry_outside_rz_yields_td():
    """state.yard_line=25, RB dist always samples 30 → would-be TD → unconditional TD outside RZ."""
    pass

def test_ks15_run_safety_branch_preserved():
    """state.yard_line=98 (own 2), RB raw_yards=100 → is_safety=True (clamping must not mask this)."""
    pass

def test_ks15_legacy_pass_path_preserves_distribution():
    """KS-15 D-15b (MEDIUM-4): legacy non-roster _resolve_pass path (roster=None) preserves
    distribution semantics consistent with the roster path. yard_line=30, sampler returns 35,
    over 1000 trials the play scores TDs and does not silently truncate to a smaller value."""
    # Use a play_outcomes mock or fixture whose sample_yards("pass", bucket, rng) returns 35
    # _resolve_pass(state, play_outcomes, turnover_rates, rng, roster=None, ...) must produce TD outside RZ
    # Assert TD rate ~100% AND yards never < state.yard_line (they may equal state.yard_line — that's the TD)
    pass

def test_ks15_legacy_run_path_preserves_distribution():
    """KS-15 D-15b (MEDIUM-4): legacy non-roster _resolve_run path (roster=None) preserves
    semantics. yard_line=25, RB sampler returns 30; assert TD rate ~100%. Also test
    yard_line=98 + raw_yards=100 still triggers is_safety=True."""
    pass
```

Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15
```

EXPECTED: Test 1 fails (CATCH_YARDS_BOOST is currently 1.5, not 0). Other tests may pass or fail depending on current behavior; collectively they assert the new policy.

Commit: `test(01-07): add failing tests for KS-15 field-position clamping fix`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15 2>&1 | grep -E "FAILED|PASSED" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_catch_yards_boost_is_zero`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_pass_long_catch_outside_rz_yields_td`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_pass_long_catch_inside_rz_routes_through_gate`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_pass_short_catch_no_double_counted_yards`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_pass_td_gate_calibration_unchanged`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_run_long_carry_outside_rz_yields_td`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_run_safety_branch_preserved`
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_legacy_pass_path_preserves_distribution` (D-15b legacy path test)
    - `tests/test_engine/test_play_resolver.py` contains `def test_ks15_legacy_run_path_preserves_distribution` (D-15b legacy path test)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15_catch_yards_boost_is_zero` exits non-zero (RED — boost is still 1.5)
    - `git log -1 --pretty=%s` matches `test(01-07): add failing tests for KS-15`
  </acceptance_criteria>
  <done>RED tests committed; at minimum the boost-is-zero test fails confirming the implementation work needed.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — set CATCH_YARDS_BOOST=0 and refactor _resolve_pass / _resolve_run to detect would-be TD pre-clamp</name>
  <files>src/fantasy_sim/engine/play_resolver.py</files>
  <read_first>
    - src/fantasy_sim/engine/play_resolver.py (current _resolve_pass / _resolve_run / _clamp_yards / _red_zone_td_gate / _tackled_short_preserve_distribution)
    - tests/test_engine/test_play_resolver.py (RED tests added in Task 1)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-14, D-15)
  </read_first>
  <action>
Modify `src/fantasy_sim/engine/play_resolver.py`:

1. Set the boost to 0 (D-15):
```python
# Lines 26-32 (post-KS-04 — replace the entire comment block + constant):
# Calibration: per-player yards distributions are field-position-independent,
# but the sim samples them at specific field positions. After KS-15 (D-14/D-15),
# the field-position clamping is applied as min(yard_line, sample) for yards
# while the un-clamped sample drives the TD probability gate. The additive
# boost is no longer needed — KS-15 fixes the underlying mechanism.
CATCH_YARDS_BOOST = 0  # KS-15 D-15: obviated by clamping fix
```

2. Refactor the `_resolve_pass` yards/TD branch (post-KS-01/04 state). The new flow:

```python
# Sample raw (per-catch sample post-KS-04 conditional boost; boost is now 0 so no change in arithmetic)
if full_dist is not None and len(full_dist) > 0:
    raw_sample = int(rng.choice(full_dist))
else:
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
    raw_sample = team_yards if team_yards > 0 else int(rng.integers(5, 18))

# KS-04 conditional boost stays in code but evaluates to 0 always (boost=0).
# Keep the conditional skeleton so future tuning can re-enable per-mechanism if needed.
if state.yard_line > 20 and raw_sample > state.yard_line:
    player_yards = raw_sample + CATCH_YARDS_BOOST
else:
    player_yards = raw_sample

# Apply home-field BEFORE the would-be-TD check (home-field can push a 19-yd catch over the goal at the 20)
raw_yards_post_home_field = _apply_home_field(player_yards, is_home, rng)

# KS-15 D-14: detect would-be TD from the un-clamped value
would_be_td = (state.yard_line - raw_yards_post_home_field) <= 0

if would_be_td:
    if state.yard_line <= 20:
        # Inside RZ: run through the TD gate
        if _red_zone_td_gate(state.yard_line, "pass", rng, receiver.outcomes.receiving_td_factor):
            yards = state.yard_line  # cap at goal (TD scored)
            is_td = True
        else:
            # Gate failed: tackled short, preserve distribution
            yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)
            is_td = False
    else:
        # Outside RZ: would-be TD always scores
        yards = state.yard_line
        is_td = True
else:
    # Not a would-be TD: just take the sample (no clamping needed)
    yards = raw_yards_post_home_field
    is_td = False
```

NOTE: This replaces the previous `yards = _clamp_yards(state.yard_line, yards)` line. The clamping is now logical (`yards = state.yard_line` when TD scores), not numeric.

3. Refactor `_resolve_run` similarly. Important: preserve the `is_safety` branch (yard_line - raw_yards >= 100):

```python
context_yards = ...  # existing (QB designed run path)
if context_yards is not None:
    player_yards = int(context_yards)
elif rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
    player_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
else:
    player_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)

raw_yards = _apply_home_field(player_yards, is_home, rng)

# Safety check on raw yards BEFORE any clamping (preserved from existing code)
is_safety = (state.yard_line - raw_yards) >= 100

# KS-15 D-14: detect would-be TD from the un-clamped value
would_be_td = (state.yard_line - raw_yards) <= 0 and not is_safety

if would_be_td:
    if state.yard_line <= 20:
        if state.yard_line <= 5 and rusher.outcomes.i5_rushing_td_factor != 1.0:
            td_factor = rusher.outcomes.i5_rushing_td_factor
        else:
            td_factor = rusher.outcomes.rushing_td_factor
        if _red_zone_td_gate(state.yard_line, "run", rng, td_factor):
            yards = state.yard_line
            is_td = True
        else:
            yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)
            is_td = False
    else:
        yards = state.yard_line
        is_td = True
elif is_safety:
    yards = -(99 - state.yard_line)  # max loss for safety case (existing _clamp_yards behavior)
    is_td = False
else:
    yards = raw_yards
    is_td = False
```

4. **NEW per D-15b (MEDIUM-4):** Apply the same min(yard_line, sample) + would-be-TD detection to the legacy non-roster paths. The current legacy paths use the old `_clamp_yards`-based semantics:

```python
# CURRENT legacy _resolve_pass (lines ~302-321 — no-roster fallback):
team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
team_yards = _apply_home_field(team_yards, is_home, rng)
yards = _clamp_yards(state.yard_line, team_yards)

is_complete = yards > 0
is_td = (state.yard_line - yards) <= 0
# ...

# NEW legacy _resolve_pass (KS-15 D-15b):
team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
raw_yards = _apply_home_field(team_yards, is_home, rng)

would_be_td = (state.yard_line - raw_yards) <= 0
if would_be_td:
    yards = state.yard_line
    is_td = True
else:
    yards = raw_yards
    is_td = False

is_complete = yards > 0  # legacy semantic preserved (any positive yards = completion)
# ... (fumble check, return)
```

```python
# CURRENT legacy _resolve_run (lines ~392-410 — no-roster fallback):
raw_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)
raw_yards = _apply_home_field(raw_yards, is_home, rng)
is_safety = (state.yard_line - raw_yards) >= 100
yards = _clamp_yards(state.yard_line, raw_yards)
is_td = (state.yard_line - yards) <= 0
# ...

# NEW legacy _resolve_run (KS-15 D-15b):
raw_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)
raw_yards = _apply_home_field(raw_yards, is_home, rng)

is_safety = (state.yard_line - raw_yards) >= 100
would_be_td = (state.yard_line - raw_yards) <= 0 and not is_safety

if would_be_td:
    yards = state.yard_line
    is_td = True
elif is_safety:
    yards = -(99 - state.yard_line)  # max loss; matches existing _clamp_yards behavior for safety
    is_td = False
else:
    yards = raw_yards
    is_td = False
# ... (fumble check, return — preserve is_safety in PlayResult)
```

NOTE: The legacy paths do NOT route through the RZ TD gate — they have no roster/receiver/rusher to look up `td_factor` on. Per Codex MEDIUM-4 review note, the legacy paths only run when `roster is None`, which the current validation harness does not exercise; the change is for codebase-consistency hygiene. If a future feature reintroduces non-roster execution, the engineer can add a roster-less RZ-gate variant separately.

5. After both roster and legacy paths are patched, `_clamp_yards` may have no remaining callers in `_resolve_pass`/`_resolve_run`. Run `grep -n "_clamp_yards" src/fantasy_sim/engine/play_resolver.py` to confirm. If unused, leave the helper definition in place (it's small and may be useful for future tests) but add a comment marking it as deprecated for the resolve paths.

6. Run pytest:
```bash
uv run pytest tests/test_engine/test_play_resolver.py -v -k "ks01 or ks04 or ks06 or ks07 or ks15"
uv run pytest tests/ -v
```

EXPECTED: All tests pass (KS-01 calibration tests still green per regression guard; KS-04 boost-zero test now passes since boost=0; KS-15 roster path AND legacy path tests pass).

Commit: `feat(01-07): KS-15 field-position clamping fix per D-14 + CATCH_YARDS_BOOST=0 per D-15 + legacy paths per D-15b`
  </action>
  <verify>
    <automated>uv run pytest tests/test_engine/test_play_resolver.py -v -k "ks01 or ks04 or ks06 or ks07 or ks15" && uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "CATCH_YARDS_BOOST = 0$" src/fantasy_sim/engine/play_resolver.py` returns 1
    - `grep -c "CATCH_YARDS_BOOST = 1.5" src/fantasy_sim/engine/play_resolver.py` returns 0
    - `grep -c "would_be_td = " src/fantasy_sim/engine/play_resolver.py` returns at least 4 (one in roster-path _resolve_pass, one in roster-path _resolve_run, one in legacy _resolve_pass per D-15b, one in legacy _resolve_run per D-15b)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15_catch_yards_boost_is_zero` exits 0
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15_pass_td_gate_calibration_unchanged` exits 0 (regression guard still passes)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15_legacy_pass_path_preserves_distribution` exits 0 (legacy path patched per D-15b)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k ks15_legacy_run_path_preserves_distribution` exits 0 (legacy path patched per D-15b)
    - `uv run pytest tests/test_engine/test_play_resolver.py -v -k "ks01 or ks04 or ks15"` exits 0 (no RZ-stack regression)
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `feat(01-07): KS-15`
  </acceptance_criteria>
  <done>GREEN — clamping fix in place, boost=0, all RZ-stack tests still pass, full suite green.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-15 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-29, D-31)
  </read_first>
  <action>
Run BOTH A/B passes per D-29 (revised 2026-04-26 — uses Plan 00's `--arm-b-base bare` for true isolation):

```bash
# True isolation
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --arm-b-base bare --label "p1.ks15.bare"

# Full-stack overlay
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults --label "p1.ks15.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks15"
```

NOTE: KS-15 changes module constants and resolve-function bodies — no `--set` flag needed; the change ships as the source code itself.

Capture logs to `.../logs/p1.ks15.{bare,full}.log`.

Promotion decision per D-31 (medium-large item):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- KS delta on QB pass_yards / WR receiving_yards primary targets ≤ -0.01

If hard floor fails → revert Task 2's commit, document under `## KS-15` in `logs/PROMOTION-NOTES.md`. Note that KS-04's boost retune remains in code (per D-13's contingency); the partial-progress fallback keeps KS-04's intermediate gain.

Append `## KS-15` section to `logs/PROMOTION-NOTES.md`.

Commit: `chore(01-07): record KS-15 A/B ledger entries (p1.ks15.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks15\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks15.bare` and `p1.ks15.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-15`
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-07): record KS-15 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision documented; KS-04 partial-progress fallback active if KS-15 BLOCKED.</done>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit + SUMMARY (per D-25 revised)</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md (## KS-15 section from Task 3)
  </read_first>
  <action>
Per D-25 (revised), create the final promotion commit + SUMMARY.

Determine promotion state from PROMOTION-NOTES `## KS-15` section per D-31 medium-large bar.

Create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-07-SUMMARY.md`:

```markdown
# Plan 07 Summary — KS-15 field-position clamping fix

**Promotion state:** <PROMOTED|SHIPPED-NO-OP|BLOCKED>
**Phase:** 1
**Wave:** 4 (final RZ-stack commit)
**Final commit:** $(git log -1 --pretty=%H)

## What shipped

1. `CATCH_YARDS_BOOST = 0` in `play_resolver.py` (D-15 — boost obviated by clamping fix)
2. Roster-path `_resolve_pass` and `_resolve_run` use `min(yard_line, sample)` for yards while un-clamped sample drives the TD gate (D-14)
3. Legacy non-roster `_resolve_pass` (lines 302-321) and `_resolve_run` (lines 392-410) patched with the same `min(yard_line, raw_yards)` + would-be-TD pattern (D-15b — addresses Codex MEDIUM-4)
4. 9 KS-15 tests (7 roster-path + 2 legacy-path)

## Codex MEDIUM-4 fix note

Original Plan 07 only patched the roster paths. Codex review flagged that
keeping two divergent clamping semantics in the same module is a foot-gun
even if the validation harness only exercises the roster path. Resolution:
patch BOTH paths with the same semantics; add 2 new tests (Test 8 / Test 9)
that exercise the legacy non-roster code path explicitly.

## Ledger results

| Entry | rank_corr Δ | MAE Δ | QB pass_yards KS Δ | WR recv_yards KS Δ | Hard floor? | Promotion bar? |
|-------|-------------|-------|---------------------|---------------------|-------------|----------------|
| p1.ks15.bare | ... | ... | ... | ... | ✅/❌ | ✅/❌ |
| p1.ks15.full | ... | ... | ... | ... | ✅/❌ | ✅/❌ |
```

Commit:

```bash
PROMO_STATE="PROMOTED"  # or SHIPPED-NO-OP / BLOCKED
git add .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-07-SUMMARY.md
git commit -m "feat(01-07): KS-15 ${PROMO_STATE} — field-position clamping fix + CATCH_YARDS_BOOST=0 + legacy paths

Wave 4 (final RZ-stack commit). Roster path AND legacy non-roster path
both now use min(yard_line, sample) + would-be-TD detection per D-14.
CATCH_YARDS_BOOST set to 0 per D-15 (KS-04 boost obviated).

Bare-isolation A/B uses --baseline bare --arm-b-base bare per Plan 00.
Legacy paths patched per D-15b (Codex MEDIUM-4 fix)."
```
  </action>
  <verify>
    <automated>test -f .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-07-SUMMARY.md && grep -cE "PROMOTED|SHIPPED-NO-OP|BLOCKED" .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-07-SUMMARY.md</automated>
  </verify>
  <acceptance_criteria>
    - SUMMARY exists with explicit promotion state header
    - SUMMARY's ledger results table is filled in
    - `git log -1 --pretty=%s` matches `feat(01-07): KS-15 PROMOTED|SHIPPED-NO-OP|BLOCKED`
  </acceptance_criteria>
  <done>KS-15 promotion-state commit landed; SUMMARY captures the decision and the legacy-paths fix rationale.</done>
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
| T-01-07-01 | T (Tampering) | RZ TD-gate calibration during refactor | mitigate | Test 5 (`ks15_pass_td_gate_calibration_unchanged`) catches any drift in PASS_TD_GATE rates over 100k trials. |
| T-01-07-02 | T (Tampering) | Safety branch (yard_line - raw_yards >= 100) | mitigate | Test 7 (`ks15_run_safety_branch_preserved`) confirms safety detection survives the refactor. |
| T-01-07-03 | T (Tampering) | CATCH_YARDS_BOOST=0 (D-15) | mitigate | Test 1 enforces literal value 0. |
</threat_model>

<verification>
- All KS-15 tests pass
- KS-01 / KS-04 / KS-06 / KS-07 tests still pass (no RZ-stack regression)
- `CATCH_YARDS_BOOST = 0` in play_resolver.py
- `would_be_td` variable used in both _resolve_pass and _resolve_run
- `p1.ks15.bare` and `p1.ks15.full` ledger entries exist
- Promotion decision documented
</verification>

<success_criteria>
- KS-15 requirement deliverable
- Hard floor passes on both ledger entries (or BLOCKED — KS-04 fallback retained)
- QB pass_yards KS delta ≤ -0.01 on `p1.ks15.full` (per success criterion #2: ≤ 0.28)
- WR receiving_yards KS delta ≤ -0.01 on `p1.ks15.full`
- 1,200+ existing test suite still green
- PASS_TD_GATE / RUN_TD_GATE calibration unchanged (regression guard)
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-07-SUMMARY.md`.
</output>
