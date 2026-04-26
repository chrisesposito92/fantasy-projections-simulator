---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 03
type: execute
wave: 3
depends_on: ["01", "02"]
files_modified:
  - src/fantasy_sim/data/game_context.py
  - tests/test_data/test_game_context.py
autonomous: true
requirements: [KS-03]
must_haves:
  truths:
    - "Per D-16: _apply_matchup line 535 uses (factor - 1.0) * float(np.mean(player.outcomes.receiving_yards_dist)) — same pattern as _apply_weather lines 701-712"
    - "Per D-16: _apply_coverage line 591 uses (mods.ypr_modifier - 1.0) * float(np.mean(player.outcomes.receiving_yards_dist)) — same pattern as _apply_weather"
    - "Empty receiving_yards_dist guard preserved (matches _apply_weather predicate: target_share > 0 AND dist is not None AND len(dist) > 0)"
    - "p1.ks03.bare and p1.ks03.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-30"
    - "Per D-25/D-26: KS-03 commit chain ships after KS-04 lands (sequenced for clean ledger attribution; no file-touch overlap with KS-04)"
    - "Per D-34: test-after acceptable for KS-03 (existing 1,200+ test suite covers the changed branches; new tests target the specific changed predicates)"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/data/game_context.py"
      provides: "_apply_matchup and _apply_coverage use per-player dist mean instead of hardcoded 10.0 anchor"
      contains: "float(np.mean(player.outcomes.receiving_yards_dist))"
    - path: "tests/test_data/test_game_context.py"
      provides: "Tests for KS-03: _apply_matchup uses dist-mean shift, _apply_coverage uses dist-mean shift, both guard empty dists"
      contains: "def test_ks03_"
  key_links:
    - from: "_apply_matchup"
      to: "_apply_weather"
      via: "shared shift formula: shift = (factor - 1.0) * mean_yards"
      pattern: "shift = \\(.*- 1\\.0\\) \\* mean_yards"
    - from: "_apply_coverage"
      to: "_apply_weather"
      via: "shared shift formula"
      pattern: "shift = \\(mods\\.ypr_modifier - 1\\.0\\) \\* mean_yards"
---

<objective>
Implement KS-03 — replace the hardcoded `* 10.0` yard anchor in `_apply_matchup` (line 535) and `_apply_coverage` (line 591) with per-player `float(np.mean(player.outcomes.receiving_yards_dist))`. Mirror the correct reference implementation in `_apply_weather` at lines 701-712 (D-16). Single-mechanism fix; no variant choice.

Purpose: The hardcoded 10-yard anchor over-scales players with mean ~5 yd/reception (slot/possession WRs) and under-scales players with mean ~15 yd/reception (deep WRs). The weather engine already uses the correct per-player anchor. KS-03 brings matchup and coverage to parity.

Output: Two functions updated with mirror-pattern shifts; new tests confirming the behavior; both ledger entries pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@src/fantasy_sim/data/game_context.py

<interfaces>
From src/fantasy_sim/data/game_context.py (current — buggy):

```python
# Lines 533-544 — _apply_matchup (BUGGY: hardcoded 10.0)
if ctx.pass_yards_factor != 1.0:
    shift = (ctx.pass_yards_factor - 1.0) * 10.0
    for player in roster.players:
        if (
            player.usage.target_share > 0
            and player.outcomes.receiving_yards_dist is not None
            and len(player.outcomes.receiving_yards_dist) > 0
        ):
            player.outcomes.receiving_yards_dist = (
                player.outcomes.receiving_yards_dist + shift
            )
```

```python
# Line 591 — _apply_coverage (BUGGY: hardcoded 10.0)
if mods.ypr_modifier != 1.0:
    if (
        player.outcomes.receiving_yards_dist is not None
        and len(player.outcomes.receiving_yards_dist) > 0
    ):
        shift = (mods.ypr_modifier - 1.0) * 10.0
        player.outcomes.receiving_yards_dist = (
            player.outcomes.receiving_yards_dist + shift
        )
```

```python
# Lines 701-712 — _apply_weather (CORRECT — KS-03 mirrors this)
if ctx.pass_yards_factor != 1.0:
    for player in roster.players:
        if (
            player.usage.target_share > 0
            and player.outcomes.receiving_yards_dist is not None
            and len(player.outcomes.receiving_yards_dist) > 0
        ):
            mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
            shift = (ctx.pass_yards_factor - 1.0) * mean_yards
            player.outcomes.receiving_yards_dist = (
                player.outcomes.receiving_yards_dist + shift
            )
```

Key difference: weather computes `mean_yards` PER PLAYER inside the loop. KS-03 must do the same.
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Patch _apply_matchup and _apply_coverage to use per-player dist mean</name>
  <files>src/fantasy_sim/data/game_context.py</files>
  <read_first>
    - src/fantasy_sim/data/game_context.py (lines 533-544 _apply_matchup, 586-594 _apply_coverage, 701-712 _apply_weather reference)
    - .planning/research/HYPOTHESES.md lines 117-129 (KS-03 mechanism)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-16)
  </read_first>
  <action>
Modify `src/fantasy_sim/data/game_context.py`:

1. In `_apply_matchup` (around lines 533-544), replace the hardcoded `* 10.0` shift with a per-player computation. Move `mean_yards` calculation INSIDE the loop:

```python
# BEFORE:
if ctx.pass_yards_factor != 1.0:
    shift = (ctx.pass_yards_factor - 1.0) * 10.0
    for player in roster.players:
        if (
            player.usage.target_share > 0
            and player.outcomes.receiving_yards_dist is not None
            and len(player.outcomes.receiving_yards_dist) > 0
        ):
            player.outcomes.receiving_yards_dist = (
                player.outcomes.receiving_yards_dist + shift
            )

# AFTER (mirror _apply_weather lines 701-712 per D-16):
if ctx.pass_yards_factor != 1.0:
    for player in roster.players:
        if (
            player.usage.target_share > 0
            and player.outcomes.receiving_yards_dist is not None
            and len(player.outcomes.receiving_yards_dist) > 0
        ):
            mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
            shift = (ctx.pass_yards_factor - 1.0) * mean_yards
            player.outcomes.receiving_yards_dist = (
                player.outcomes.receiving_yards_dist + shift
            )
```

2. In the same `_apply_matchup` function, also fix the rushing-yards branch (lines 546-558) which uses the same hardcoded 10.0 anchor. Apply the same per-player pattern using `np.mean(player.outcomes.rushing_yards_dist)`:

```python
# BEFORE:
combined_rush = ctx.rush_yards_factor * ctx.ol_run_block_factor
if combined_rush != 1.0:
    shift = (combined_rush - 1.0) * 10.0
    for player in roster.players:
        if (
            player.usage.carry_share > 0
            and player.outcomes.rushing_yards_dist is not None
            and len(player.outcomes.rushing_yards_dist) > 0
        ):
            player.outcomes.rushing_yards_dist = (
                player.outcomes.rushing_yards_dist + shift
            )

# AFTER:
combined_rush = ctx.rush_yards_factor * ctx.ol_run_block_factor
if combined_rush != 1.0:
    for player in roster.players:
        if (
            player.usage.carry_share > 0
            and player.outcomes.rushing_yards_dist is not None
            and len(player.outcomes.rushing_yards_dist) > 0
        ):
            mean_yards = float(np.mean(player.outcomes.rushing_yards_dist))
            shift = (combined_rush - 1.0) * mean_yards
            player.outcomes.rushing_yards_dist = (
                player.outcomes.rushing_yards_dist + shift
            )
```

3. In `_apply_coverage` (around line 591), replace the hardcoded `* 10.0` with per-player dist mean:

```python
# BEFORE:
if mods.ypr_modifier != 1.0:
    if (
        player.outcomes.receiving_yards_dist is not None
        and len(player.outcomes.receiving_yards_dist) > 0
    ):
        shift = (mods.ypr_modifier - 1.0) * 10.0
        player.outcomes.receiving_yards_dist = (
            player.outcomes.receiving_yards_dist + shift
        )

# AFTER:
if mods.ypr_modifier != 1.0:
    if (
        player.outcomes.receiving_yards_dist is not None
        and len(player.outcomes.receiving_yards_dist) > 0
    ):
        mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))
        shift = (mods.ypr_modifier - 1.0) * mean_yards
        player.outcomes.receiving_yards_dist = (
            player.outcomes.receiving_yards_dist + shift
        )
```

4. Confirm `import numpy as np` is at the top of the file (it is — lines 1-12 area). If not, add it.

5. Run pytest:
```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: 1,200+ tests still pass (no test currently asserts the buggy 10.0 value).

Commit: `fix(01-03): KS-03 per-player dist-mean anchor in _apply_matchup and _apply_coverage per D-16`
  </action>
  <verify>
    <automated>uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "shift = (ctx.pass_yards_factor - 1.0) \\* 10.0" src/fantasy_sim/data/game_context.py` returns 0 (matchup hardcoded constant removed)
    - `grep -c "shift = (combined_rush - 1.0) \\* 10.0" src/fantasy_sim/data/game_context.py` returns 0 (matchup rushing hardcoded constant removed)
    - `grep -c "shift = (mods.ypr_modifier - 1.0) \\* 10.0" src/fantasy_sim/data/game_context.py` returns 0 (coverage hardcoded constant removed)
    - `grep -c "mean_yards = float(np.mean(player.outcomes.receiving_yards_dist))" src/fantasy_sim/data/game_context.py` returns AT LEAST 3 (one in _apply_matchup pass branch, one in _apply_coverage, one in the existing _apply_weather)
    - `grep -c "mean_yards = float(np.mean(player.outcomes.rushing_yards_dist))" src/fantasy_sim/data/game_context.py` returns 1 (in _apply_matchup rush branch)
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `fix(01-03): KS-03`
  </acceptance_criteria>
  <done>Both functions use per-player dist mean; numeric guards preserved; full suite green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add tests for KS-03 dist-mean shift behavior</name>
  <files>tests/test_data/test_game_context.py</files>
  <read_first>
    - tests/test_data/test_game_context.py (existing test patterns for matchup/coverage)
    - src/fantasy_sim/data/game_context.py (the patched _apply_matchup, _apply_coverage)
  </read_first>
  <behavior>
    - Test 1 (`test_ks03_apply_matchup_uses_dist_mean_for_pass_yards`): build a roster with one WR (target_share=0.25, receiving_yards_dist=np.array([5,10,15]) → mean 10) and one TE (target_share=0.20, receiving_yards_dist=np.array([2,4,6]) → mean 4). Apply matchup with `pass_yards_factor=1.10`. Assert WR dist shifted by `0.10 * 10 = +1.0` (new dist == [6,11,16]) and TE dist shifted by `0.10 * 4 = +0.4` (new dist == [2.4,4.4,6.4]). Distinct shifts prove per-player anchor.
    - Test 2 (`test_ks03_apply_matchup_uses_dist_mean_for_rush_yards`): build a roster with one RB (carry_share=0.6, rushing_yards_dist=np.array([1,5,9]) → mean 5). Apply matchup with `rush_yards_factor=1.10, ol_run_block_factor=1.0` (combined=1.10). Assert RB dist shifted by `0.10 * 5 = +0.5`.
    - Test 3 (`test_ks03_apply_coverage_uses_dist_mean_for_ypr`): build a roster with one WR (target_share=0.25, receiving_yards_dist=[5,10,15] → mean 10). Apply coverage with `CoverageModifiers(catch_rate_modifier=1.0, ypr_modifier=1.05)`. Assert dist shifted by `0.05 * 10 = +0.5`.
    - Test 4 (`test_ks03_apply_matchup_skips_empty_dist`): build a roster where one player has `receiving_yards_dist=None` and another has `len()==0`. Apply matchup; assert no crash and the two empty-dist players' dists remain unchanged (None / empty array).
    - Test 5 (`test_ks03_apply_coverage_skips_empty_dist`): same as Test 4 for coverage.
  </behavior>
  <action>
Append to `tests/test_data/test_game_context.py` under a new section header `# === KS-03: per-player dist-mean anchor ===`. Use existing fixture conventions (`sample_rosters`, helpers for building minimal `PlayerModel` / `TeamRoster`).

Reference imports likely needed:
```python
import numpy as np
from fantasy_sim.data.game_context import GameContextBuilder
from fantasy_sim.data.matchup import MatchupContext  # or wherever the factor object lives
from fantasy_sim.data.pff.models import CoverageModifiers  # or wherever
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster
```

(Inspect existing tests for the precise imports — patterns will be visible in the file.)

The static method `GameContextBuilder._apply_matchup` is the test target. Construct a minimal `MatchupContext`-like object (or use the actual class) with `pass_yards_factor=1.10`, `rush_yards_factor=1.0`, `ol_run_block_factor=1.0`, `sack_rate_factor=1.0`, `int_rate_factor=1.0`, etc. — set non-tested factors to 1.0 (no-op).

For the coverage test, construct a `CoverageModifiers` instance with `catch_rate_modifier=1.0` (no-op) and `ypr_modifier=1.05`.

Run pytest:
```bash
uv run pytest tests/test_data/test_game_context.py -v -k ks03
```

EXPECTED: All 5 tests PASS (Task 1 already implemented the fix).

Commit: `test(01-03): add KS-03 dist-mean anchor tests for _apply_matchup and _apply_coverage`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_game_context.py -v -k ks03</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_data/test_game_context.py` contains the literal string `def test_ks03_apply_matchup_uses_dist_mean_for_pass_yards`
    - `tests/test_data/test_game_context.py` contains the literal string `def test_ks03_apply_matchup_uses_dist_mean_for_rush_yards`
    - `tests/test_data/test_game_context.py` contains the literal string `def test_ks03_apply_coverage_uses_dist_mean_for_ypr`
    - `tests/test_data/test_game_context.py` contains the literal string `def test_ks03_apply_matchup_skips_empty_dist`
    - `tests/test_data/test_game_context.py` contains the literal string `def test_ks03_apply_coverage_skips_empty_dist`
    - `uv run pytest tests/test_data/test_game_context.py -v -k ks03` exits 0 with at least 5 tests passed
    - `git log -1 --pretty=%s` matches `test(01-03): add KS-03`
  </acceptance_criteria>
  <done>All 5 KS-03 tests pass; per-player anchor verified for both matchup and coverage paths.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-03 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-29 isolation+full-stack rule, D-30 small-gain promotion bar)
  </read_first>
  <action>
Run BOTH A/B passes per D-29:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --label "p1.ks03.bare"

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults --label "p1.ks03.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks03"
```

Capture logs to `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks03.{bare,full}.log`.

Promotion decision per D-30 (KS-03 is a bug fix; treat as small-gain bar — ship if hard floor passes AND any non-regression KS delta on WR/TE receiving_yards):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- KS delta: WR receiving_yards KS delta ≥ 0 (i.e., not worsening)

If hard floor fails on either entry → revert Task 1's commit, document under `## KS-03` in `logs/PROMOTION-NOTES.md`, mark `## PLAN BLOCKED`.

Append `## KS-03` section to `logs/PROMOTION-NOTES.md` with the decision.

Commit: `chore(01-03): record KS-03 A/B ledger entries (p1.ks03.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks03\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks03.bare` and `p1.ks03.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-03` with the decision
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-03): record KS-03 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision documented.</done>
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
| T-01-03-01 | T (Tampering) | Empty-dist guard predicate | mitigate | Tests 4 + 5 verify the guard prevents `np.mean()` on empty arrays. |
| T-01-03-02 | T (Tampering) | _apply_weather reference pattern | mitigate | grep enforces all three call sites (matchup pass, matchup rush, coverage) use the per-player computation. |
</threat_model>

<verification>
- `_apply_matchup` and `_apply_coverage` no longer contain hardcoded `* 10.0`
- All KS-03 tests pass
- `p1.ks03.bare` and `p1.ks03.full` ledger entries exist
- Promotion decision documented in PROMOTION-NOTES.md
</verification>

<success_criteria>
- KS-03 requirement deliverable
- Hard floor passes on both ledger entries (or BLOCKED + reverted)
- WR/TE receiving_yards KS delta ≥ 0 on `p1.ks03.full` (per D-30 small-gain promotion bar)
- 1,200+ existing test suite still green
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-03-SUMMARY.md`.
</output>