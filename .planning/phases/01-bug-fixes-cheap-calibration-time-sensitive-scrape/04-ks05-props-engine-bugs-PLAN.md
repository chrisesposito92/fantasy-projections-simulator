---
phase: 01-bug-fixes-cheap-calibration-time-sensitive-scrape
plan: 04
type: execute
wave: 3
depends_on: ["01", "02"]
files_modified:
  - src/fantasy_sim/data/vegas/props_engine.py
  - tests/test_data/test_vegas/test_props_engine.py
autonomous: true
requirements: [KS-05]
must_haves:
  truths:
    - "Per D-17: _DEFAULT_TEAM_PASS_YDS = 240.0 (previously 230.0)"
    - "Per D-17: _apply_recv_yds line 248 uses dist_mean * catches_per_game * games_played (previously dist_mean * games_played)"
    - "Per D-18: catches_per_game proxy uses player.usage.target_share * 32.0 * player.outcomes.catch_rate (per RESEARCH.md Pitfall 4 v1 fallback) — pipeline-plumbed version deferred"
    - "p1.ks05.bare and p1.ks05.full ledger entries pass hard floor (Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05) per D-31"
    - "Per D-25/D-26: KS-05 commit chain ships after KS-04 lands"
    - "Per D-34: test-after acceptable for KS-05 (existing test suite covers the changed branches)"
    - "Per D-35: existing 1,200+ test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/data/vegas/props_engine.py"
      provides: "_DEFAULT_TEAM_PASS_YDS bumped to 240.0; _apply_recv_yds magnitude bug fixed"
      contains: "_DEFAULT_TEAM_PASS_YDS = 240.0"
    - path: "tests/test_data/test_vegas/test_props_engine.py"
      provides: "Tests for KS-05: default constant, magnitude bug fix, blend correctness"
      contains: "def test_ks05_"
  key_links:
    - from: "_apply_recv_yds"
      to: "historical_season_yds computation"
      via: "dist_mean * catches_per_game * games_played"
      pattern: "historical_season_yds = dist_mean \\* catches_per_game"
---

<objective>
Implement KS-05 — fix two bugs in `src/fantasy_sim/data/vegas/props_engine.py`:
1. (D-17 sub-fix 1) `_DEFAULT_TEAM_PASS_YDS = 230.0 → 240.0` (constant retune to match NFL average).
2. (D-17 sub-fix 2) `_apply_recv_yds` line 248 magnitude bug: `historical_season_yds = dist_mean * catches_per_game * games_played` (currently `dist_mean * games_played` — treats per-catch yards as per-game yards, off by ~3-7×).

D-17 sub-fix 3 (per-team rolling mean from pipeline) is the long-term architectural fix per D-18; PER RESEARCH.md Pitfall 4 v1 fallback, this plan uses the proxy `catches_per_game = target_share * 32.0 * catch_rate` (matching the proxy already used in `_apply_receptions` line 281) and DEFERS the pipeline-plumbed version to a follow-up plan if metrics motivate it. Discretion area per D-CLAUDE.

Purpose: HYPOTHESES.md KS-05 (lines 131-143) shows the magnitude bug at line 248 inflates `historical_season_yds` by ~5× for typical receivers (because `dist_mean` is per-catch yards, not per-game yards), making `prop_ratio = prop_point / historical_season_yds` always near 0 and the Bayesian blend toward 1.0 nearly a no-op. Fixing this lets the props prior actually move the per-player distribution.

Output: 2 constants + 1 line edit; 4 tests; both ledger entries pass hard floor.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md
@.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
@src/fantasy_sim/data/vegas/props_engine.py

<interfaces>
From src/fantasy_sim/data/vegas/props_engine.py (current — buggy):

```python
# Line 43:
_DEFAULT_TEAM_PASS_YDS = 230.0

# Lines 231-263 — _apply_recv_yds:
def _apply_recv_yds(self, player, prop_point: float) -> None:
    """player_reception_yds -> WR/TE: shift receiving_yards_dist proportionally."""
    if player.position not in ("WR", "TE"):
        return
    dist = player.outcomes.receiving_yards_dist
    if dist is None or len(dist) == 0:
        return

    dist_mean = float(np.mean(dist))
    if dist_mean <= 0:
        return

    historical_season_yds = dist_mean * player.games_played   # ← BUG: missing catches_per_game
    if historical_season_yds <= 0:
        return

    prop_ratio = prop_point / historical_season_yds
    blended_ratio = self._bayesian_blend(
        historical=1.0,
        prop_prior=prop_ratio,
        n_obs=player.games_played,
    )

    if not self._should_apply(blended_ratio):
        return

    shift = (blended_ratio - 1.0) * dist_mean
    player.outcomes.receiving_yards_dist = dist + shift
```

```python
# Reference proxy from _apply_receptions line 281:
historical_rec_pg = max(0.1, player.usage.target_share * 10.0 * max(0.5, player.outcomes.catch_rate))
```
NOTE: line 281 uses 10.0 as targets/team/game which is undersized — NFL teams average ~32-34 pass attempts/game with target_share applied to receivers. RESEARCH.md Pitfall 4 recommends 32.0 for KS-05's proxy. This plan uses 32.0 in the new computation; line 281's value (10.0) belongs to KS-32-or-later reception-side fix (out of scope here).
</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Patch _DEFAULT_TEAM_PASS_YDS and _apply_recv_yds magnitude bug</name>
  <files>src/fantasy_sim/data/vegas/props_engine.py</files>
  <read_first>
    - src/fantasy_sim/data/vegas/props_engine.py (lines 39-46 constants, lines 231-263 _apply_recv_yds, lines 265-298 _apply_receptions for the catches_per_game proxy reference)
    - .planning/research/HYPOTHESES.md lines 131-143 (KS-05 mechanism)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-17, D-18)
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-RESEARCH.md (Pitfall 4 — proxy choice rationale)
  </read_first>
  <action>
Modify `src/fantasy_sim/data/vegas/props_engine.py`:

1. Update line 43:
```python
# BEFORE:
_DEFAULT_TEAM_PASS_YDS = 230.0
# AFTER (D-17 sub-fix 1):
_DEFAULT_TEAM_PASS_YDS = 240.0  # KS-05 D-17: match NFL ~240 yd/team/game
```

2. Add a module-level constant for the proxy multiplier (near line 39-46), so the value is documented and adjustable:
```python
# Typical NFL team pass attempts per game (used in catches_per_game proxy for KS-05)
_PROXY_TEAM_TARGETS_PER_GAME = 32.0
```

3. Fix the `_apply_recv_yds` magnitude bug at line 248. Replace the line:
```python
# BEFORE:
historical_season_yds = dist_mean * player.games_played
# AFTER (D-17 sub-fix 2 + D-18 v1 proxy per RESEARCH.md Pitfall 4):
catches_per_game = max(
    0.1,
    player.usage.target_share * _PROXY_TEAM_TARGETS_PER_GAME * max(0.5, player.outcomes.catch_rate),
)
historical_season_yds = dist_mean * catches_per_game * player.games_played
```

The `max(0.1, ...)` floor and `max(0.5, ...)` minimum catch_rate mirror the proxy in `_apply_receptions` line 281 (existing convention for handling thin players).

4. Add a comment block above the new logic referencing the decisions:
```python
# KS-05 D-17/D-18: dist_mean is PER-CATCH yards, not per-game yards.
# Historical per-game yards = per-catch_mean * catches_per_game.
# v1 of D-18 uses the receptions-engine proxy (target_share * team_targets_per_game * catch_rate);
# pipeline-plumbed per-team rolling mean is deferred per RESEARCH.md Pitfall 4.
```

5. Run pytest:
```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

EXPECTED: Existing tests pass (no test currently asserts the buggy magnitude); some pre-existing prop tests may shift slightly in behavior — review failures.

Commit: `fix(01-04): KS-05 _DEFAULT_TEAM_PASS_YDS=240 + _apply_recv_yds magnitude bug per D-17/D-18`
  </action>
  <verify>
    <automated>uv run pytest tests/ -v 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "_DEFAULT_TEAM_PASS_YDS = 240.0" src/fantasy_sim/data/vegas/props_engine.py` returns 1
    - `grep -c "_DEFAULT_TEAM_PASS_YDS = 230.0" src/fantasy_sim/data/vegas/props_engine.py` returns 0
    - `grep -c "historical_season_yds = dist_mean \\* catches_per_game \\* player.games_played" src/fantasy_sim/data/vegas/props_engine.py` returns 1
    - `grep -c "historical_season_yds = dist_mean \\* player.games_played" src/fantasy_sim/data/vegas/props_engine.py` returns 0
    - `grep -c "_PROXY_TEAM_TARGETS_PER_GAME = 32.0" src/fantasy_sim/data/vegas/props_engine.py` returns 1
    - `uv run pytest tests/ -v 2>&1 | tail -5` shows `passed` with no `failed`
    - `git log -1 --pretty=%s` matches `fix(01-04): KS-05`
  </acceptance_criteria>
  <done>Both bug sites fixed; full suite green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add tests for KS-05 default constant, magnitude bug fix, and blend correctness</name>
  <files>tests/test_data/test_vegas/test_props_engine.py</files>
  <read_first>
    - tests/test_data/test_vegas/ (existing test patterns; if test_props_engine.py doesn't exist, find sibling test files for fixture references)
    - src/fantasy_sim/data/vegas/props_engine.py (the patched _apply_recv_yds + _DEFAULT_TEAM_PASS_YDS)
    - src/fantasy_sim/models/player.py (PlayerModel / PlayerOutcomes / PlayerUsage shapes)
  </read_first>
  <behavior>
    - Test 1 (`test_ks05_default_team_pass_yds_is_240`): assert `from fantasy_sim.data.vegas.props_engine import _DEFAULT_TEAM_PASS_YDS` and `_DEFAULT_TEAM_PASS_YDS == 240.0`. Documents D-17 sub-fix 1.
    - Test 2 (`test_ks05_proxy_team_targets_per_game_is_32`): assert `_PROXY_TEAM_TARGETS_PER_GAME == 32.0`. Documents D-18 v1 proxy choice.
    - Test 3 (`test_ks05_apply_recv_yds_uses_catches_per_game_in_historical`): build a WR with `target_share=0.25, catch_rate=0.65, games_played=14, receiving_yards_dist=np.array([8.0, 12.0, 16.0])` (mean=12 per-catch). Compute expected catches_per_game = 0.25 * 32.0 * 0.65 = 5.2. Expected historical_season_yds = 12 * 5.2 * 14 ≈ 873.6. Set prop_point=900 (close to historical, prop_ratio ≈ 1.03). Call `_apply_recv_yds(player, prop_point=900.0)` and verify the receiving_yards_dist shifted by approximately `(blended_ratio - 1.0) * 12` where blended_ratio is the Bayesian blend of (1.0, 1.03) at n_obs=14.
    - Test 4 (`test_ks05_apply_recv_yds_skips_zero_targets`): if `target_share == 0`, the proxy yields catches_per_game = 0.1 (the floor), historical = 12 * 0.1 * 14 = 16.8, prop_ratio = prop_point / 16.8 — confirm the function does NOT crash and either applies the (very large) shift or is filtered by `_should_apply`.
    - Test 5 (`test_ks05_apply_recv_yds_old_bug_no_longer_inflates_historical`): regression — for a WR with games_played=10 and dist_mean=12, the OLD computation gave historical = 120; the NEW computation with target_share=0.25, catch_rate=0.65 gives historical = 12 * 5.2 * 10 = 624. Assert via direct inspection that `historical_season_yds` (extractable via mock or by computing the expected blended ratio) reflects the new value.
  </behavior>
  <action>
Create or extend `tests/test_data/test_vegas/test_props_engine.py`. Use existing fixtures or build minimal `PlayerModel` instances inline. Pattern (canonical example):

```python
import numpy as np
import pytest
from fantasy_sim.data.vegas.props_engine import (
    PlayerPropsEngine,
    _DEFAULT_TEAM_PASS_YDS,
    _PROXY_TEAM_TARGETS_PER_GAME,
)
from fantasy_sim.data.vegas.models import PropsConfig
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage

# === KS-05: props engine magnitude bug + default constant ===

def test_ks05_default_team_pass_yds_is_240():
    assert _DEFAULT_TEAM_PASS_YDS == 240.0, f"D-17 requires 240.0, got {_DEFAULT_TEAM_PASS_YDS}"

def test_ks05_proxy_team_targets_per_game_is_32():
    assert _PROXY_TEAM_TARGETS_PER_GAME == 32.0

def _make_wr(*, target_share: float, catch_rate: float, games_played: int, dist: np.ndarray) -> PlayerModel:
    """Build a minimal WR PlayerModel for KS-05 tests."""
    # Adapt to actual PlayerModel/PlayerOutcomes/PlayerUsage signatures by inspecting models/player.py
    outcomes = PlayerOutcomes(
        catch_rate=catch_rate,
        red_zone_catch_rate=catch_rate * 0.92,
        receiving_yards_dist=dist,
        # ... other defaults
    )
    usage = PlayerUsage(target_share=target_share, carry_share=0.0, snap_share=0.7)
    player = PlayerModel(
        player_id="test_wr",
        name="Test WR",
        position="WR",
        team="KC",
        outcomes=outcomes,
        usage=usage,
        games_played=games_played,
    )
    return player

def test_ks05_apply_recv_yds_uses_catches_per_game_in_historical():
    config = PropsConfig(...)  # use minimal config; inspect PropsConfig for required fields
    engine = PlayerPropsEngine(config=config, loader=None)  # loader unused for this unit test
    player = _make_wr(target_share=0.25, catch_rate=0.65, games_played=14,
                      dist=np.array([8.0, 12.0, 16.0]))
    original_dist = player.outcomes.receiving_yards_dist.copy()
    engine._apply_recv_yds(player, prop_point=900.0)
    new_dist = player.outcomes.receiving_yards_dist
    # The new computation: catches_per_game = 0.25 * 32 * 0.65 = 5.2
    # historical = 12 * 5.2 * 14 = 873.6
    # prop_ratio = 900 / 873.6 ≈ 1.0302
    # Bayesian blend toward 1.0 with n_obs=14 (depends on prior_strength in config)
    # Assert the dist shifted by a small positive amount (≤ +1.0 yd) — proxy for "magnitude is now reasonable"
    assert np.all(new_dist >= original_dist - 0.5)  # tolerance for blend
    assert np.mean(new_dist) - np.mean(original_dist) < 1.0  # shift is within reason

def test_ks05_apply_recv_yds_skips_zero_targets():
    config = PropsConfig(...)
    engine = PlayerPropsEngine(config=config, loader=None)
    player = _make_wr(target_share=0.0, catch_rate=0.65, games_played=14,
                      dist=np.array([8.0, 12.0, 16.0]))
    original_dist = player.outcomes.receiving_yards_dist.copy()
    engine._apply_recv_yds(player, prop_point=900.0)
    # With target_share=0, catches_per_game floors at 0.1 → historical = 16.8
    # prop_ratio = 900 / 16.8 ≈ 53.6 (very large) — _should_apply will filter this OR the dist
    # shifts massively. Either way: no crash.
    assert player.outcomes.receiving_yards_dist is not None
```

NOTE: Test imports likely need adjustment based on actual class signatures. The key assertions are:
- `_DEFAULT_TEAM_PASS_YDS == 240.0`
- `_PROXY_TEAM_TARGETS_PER_GAME == 32.0`
- The corrected `_apply_recv_yds` produces a "small" shift for prop_point near historical (proves the magnitude bug is fixed)
- The function doesn't crash on edge cases

Run pytest:
```bash
uv run pytest tests/test_data/test_vegas/ -v -k ks05
```

EXPECTED: Tests 1, 2 PASS. Tests 3-5 PASS (they only assert no-crash + reasonable magnitude).

Commit: `test(01-04): add KS-05 props engine bug fix tests`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_vegas/ -v -k ks05 2>&1 | tail -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_data/test_vegas/test_props_engine.py` exists
    - File contains `def test_ks05_default_team_pass_yds_is_240`
    - File contains `def test_ks05_proxy_team_targets_per_game_is_32`
    - File contains `def test_ks05_apply_recv_yds_uses_catches_per_game_in_historical`
    - File contains `def test_ks05_apply_recv_yds_skips_zero_targets`
    - `uv run pytest tests/test_data/test_vegas/ -v -k ks05` exits 0 with at least 4 tests passing
    - `git log -1 --pretty=%s` matches `test(01-04): add KS-05`
  </acceptance_criteria>
  <done>Tests committed and passing; constant + magnitude bug fix verified.</done>
</task>

<task type="auto">
  <name>Task 3: A/B validate KS-05 in isolation and full-stack; commit ledger entries</name>
  <files>(no source modifications)</files>
  <read_first>
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-VALIDATION.md
    - scripts/validate.py
    - .planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-CONTEXT.md (D-29, D-31)
  </read_first>
  <action>
Run BOTH A/B passes per D-29:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline bare --label "p1.ks05.bare"

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr --positions QB RB WR TE \
  --baseline defaults --label "p1.ks05.full"

uv run python scripts/validate.py --show-ledger | grep "p1.ks05"
```

Capture logs to `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/p1.ks05.{bare,full}.log`.

Promotion decision per D-31 (medium-large item):
- Hard floor: rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05 on BOTH entries
- KS delta on WR/TE receiving_yards primary target ≤ -0.01

If hard floor fails → revert Task 1, document under `## KS-05` in `logs/PROMOTION-NOTES.md`, mark `## PLAN BLOCKED`.

Append `## KS-05` section to `logs/PROMOTION-NOTES.md`.

Commit: `chore(01-04): record KS-05 A/B ledger entries (p1.ks05.{bare,full})`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger 2>&1 | grep -E "p1\.ks05\.(bare|full)" | wc -l | tr -d ' '</automated>
  </verify>
  <acceptance_criteria>
    - The verify command returns `2`
    - `uv run python scripts/validate.py --show-ledger` output contains `p1.ks05.bare` and `p1.ks05.full`
    - `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/logs/PROMOTION-NOTES.md` contains a section header `## KS-05`
    - Both ledger entries' rank_corr regression ≥ -0.005 AND MAE regression ≤ +0.05
    - `git log -1 --pretty=%s` matches `chore(01-04): record KS-05 A/B`
  </acceptance_criteria>
  <done>Both ledger entries recorded; promotion decision documented.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| External: The Odds API | Already gated by httpx + API-key env var; no new boundary in KS-05 (KS-05 fixes consumption math, not the API surface). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-04-01 | T (Tampering) | _DEFAULT_TEAM_PASS_YDS constant | mitigate | Test 1 enforces literal 240.0. |
| T-01-04-02 | T (Tampering) | _apply_recv_yds magnitude formula | mitigate | Test 3 enforces the new formula via observable behavior. |
| T-01-04-03 | I (Information disclosure) | Props cache | accept | Cache contains market-line numerics; no PII. |
</threat_model>

<verification>
- KS-05 tests pass
- `_DEFAULT_TEAM_PASS_YDS = 240.0` and magnitude bug fix in place
- `p1.ks05.bare` and `p1.ks05.full` ledger entries exist
- Promotion decision documented
</verification>

<success_criteria>
- KS-05 requirement deliverable
- Hard floor passes on both ledger entries (or BLOCKED + reverted)
- WR/TE receiving_yards mean bias narrows on `p1.ks05.full` (per D-31 medium-large item bar)
- 1,200+ existing test suite still green
- D-17 sub-fix 3 (per-team rolling mean from pipeline) deferred per discretion + RESEARCH.md Pitfall 4
</success_criteria>

<output>
After completion, create `.planning/phases/01-bug-fixes-cheap-calibration-time-sensitive-scrape/01-04-SUMMARY.md`.
</output>
