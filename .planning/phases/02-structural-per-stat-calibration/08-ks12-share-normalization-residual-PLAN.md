---
phase: 02-structural-per-stat-calibration
plan: 08
type: tdd
wave: 6
depends_on: ["01"]
files_modified:
  - src/fantasy_sim/data/player_builder.py
  - tests/test_data/test_player_builder.py
  - tests/test_data/test_game_context.py
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-12]
must_haves:
  truths:
    - "Per D-09 + Pattern 8 + Pitfall 5 in 02-RESEARCH.md: in `_normalize_roster_shares` (`player_builder.py:661-693`), normalize to `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` instead of exactly `1.0`. Small remainders go to a 'league-default' residual not allocated to any roster player."
    - "Per Pitfall 5: clamp `factor = clip(active / typical_roster_size, _MIN_ACTIVE_FRACTION=0.5, 1.0)`. Lower bound prevents multi-inactive weeks from collapsing carry/target totals to 0; upper bound preserves the share-sums-to-≤-1.0 invariant."
    - "Per D-09: add backup-TE/WR exclusion threshold mirroring `MIN_QB_CARRY_SHARE = 0.10` exclusion at `player_builder.py:673,681,689,697`. Threshold value is Claude's Discretion per CONTEXT.md (planner picks based on per-position empirical share floor; default suggested = 0.05)."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks12_share_normalization_residual.enabled` (default false). When false, behavior is byte-identical to pre-Plan-08 (`_scale_shares` produces sum=1.0). When true, the new `expected_active_shares` factor + backup exclusion are active."
    - "Per ROADMAP risk note + Pitfall: KS-12's PRIMARY integration concern is composing with the availability engine WITHOUT double-counting. Plan 08 tests cover: (a) availability OFF → factor = 1.0 → legacy behavior; (b) availability ON, full roster → factor = 1.0 → legacy; (c) availability ON, multi-inactive → factor < 1.0 → residual non-zero, no over-redistribution."
    - "**Codex MEDIUM 8 (2026-04-27 revision) — concrete success metric:** KS-12's primary success signal is `Δ stat_ks[WR][receptions]` from the per-KS A/B (target ≤ 0). The expected mechanism is variance retention via the residual: when active receivers carry less than `1.0` total target_share, the simulator drops more targets to noise rather than fattening the receivers' tails artificially. The Plan 08 promotion bar requires (1) hard floor + (2) `Δ stat_ks[WR][receptions] ≤ 0` (no regression) — explicitly captured in Plan 08 Task 4 PROMOTION-NOTES.md template. The phrase 'WR target_share variance retention' from CONTEXT.md does NOT have its own ledger column; the ledger metric is `stat_ks[WR][receptions]`."
    - "**Codex MEDIUM 8 — concrete integration tests:** the 2 integration tests in `test_game_context.py` ARE concrete (not stubs). `test_ks12_select_receiver_handles_residual_factor` builds a multi-inactive roster (2 inactive WR/TE), runs `select_receiver` 1000 times via `np.random.default_rng(42)`, and asserts that `sum(observed_share for active receivers) ≈ active_factor` within ±0.02. `test_ks12_select_rusher_handles_residual_factor` mirrors the test for `select_rusher` with 2 inactive RB."
    - "Per C-08: TDD-first for KS-12 (per ROADMAP risk note). 7 tests."
    - "Per C-09: 2,170 + 7 (Plan 08) = 2,177 tests stay green after this plan."
    - "Per D-12: KS-12 last among per-KS plans because `_normalize_roster_shares` fires 9+ times per game build (`game_context.py:1073-1259`); biggest blast radius if it regresses."
  artifacts:
    - path: "src/fantasy_sim/data/player_builder.py"
      provides: "New `_expected_active_share_factor(roster, typical_roster_size=22, min_fraction=0.5)` helper; `_normalize_roster_shares` reads `phase2_ks_flags.ks12_share_normalization_residual.enabled` at module-import time; when enabled, scales `_scale_shares` target by the factor; backup-TE/WR exclusion added"
      contains: "_expected_active_share_factor"
    - path: "tests/test_data/test_player_builder.py"
      provides: "5 new unit tests: ks12_factor_is_one_when_availability_off_or_full_roster, ks12_factor_lt_one_when_multi_inactive, ks12_min_fraction_clamps_low, ks12_max_fraction_clamps_high, ks12_unchanged_when_flag_disabled"
      contains: "def test_ks12_"
    - path: "tests/test_data/test_game_context.py"
      provides: "2 new integration tests: ks12_select_receiver_handles_residual_factor, ks12_select_rusher_handles_residual_factor"
      contains: "def test_ks12_"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-12 promotion-state decision summary including availability-composition test results + chosen backup-TE/WR exclusion threshold + final decision"
      contains: "## KS-12"
  key_links:
    - from: "src/fantasy_sim/engine/availability.py (or equivalent) :: PlayerUsage.is_active"
      to: "src/fantasy_sim/data/player_builder.py::_normalize_roster_shares"
      via: "_expected_active_share_factor reads p.usage.is_active"
      pattern: "is_active"
---

<objective>
Implement KS-12 — share-normalization residual that composes with the availability engine. Per D-09: in `_normalize_roster_shares` (`player_builder.py:661-693`), normalize to `expected_active_shares = sum_of_shares * (active_players / typical_roster_size)` instead of exactly `1.0`. The "league-default" residual NOT allocated to any roster player handles weeks with multiple inactives without artificially inflating starters.

Per ROADMAP risk note + Pitfall in 02-RESEARCH.md: this is the PRIMARY integration risk in Phase 2 — compose with `availability` engine without double-counting. Tests cover three cases (availability OFF, availability ON full-roster, availability ON multi-inactive).

Output:
1. New helper `_expected_active_share_factor(roster, typical_roster_size=22, min_fraction=0.5)` in `player_builder.py`.
2. Module-level flag read at import (`_KS12_SHARE_NORM_RESIDUAL`).
3. `_normalize_roster_shares` calls the helper when flag enabled and scales `_scale_shares` target accordingly.
4. Backup-TE/WR exclusion threshold (planner picks; suggested 0.05 — see Manual-Only Verifications in 02-VALIDATION.md).
5. 7 tests (5 unit + 2 integration; TDD-first per C-08).
6. Ledger entries `p2.ks12.{bare, full}`.
7. Promotion-state commit per Phase 1 D-25/D-40.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/research/HYPOTHESES.md
@.planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md
@.planning/phases/02-structural-per-stat-calibration/02-RESEARCH.md
@.planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md
@src/fantasy_sim/data/player_builder.py
@src/fantasy_sim/data/game_context.py
@tests/test_data/test_player_builder.py
@tests/test_data/test_game_context.py

<interfaces>
From src/fantasy_sim/data/player_builder.py:661-693 (existing _normalize_roster_shares):

```python
def _normalize_roster_shares(roster: TeamRoster) -> None:
    """Normalize carry/target shares to sum to 1.0 among eligible players."""
    eligible_rushers = [
        p for p in roster.players
        if p.usage.carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    _scale_shares(eligible_rushers, "carry_share")
    # ... 4 more red_zone / outer_rz / goal_line / target_share blocks
```

From src/fantasy_sim/data/player_builder.py:683-693 (existing _scale_shares helper):

```python
def _scale_shares(players: list, attr: str) -> None:
    """Scale shares so they sum to 1.0."""
    total = sum(getattr(p.usage, attr) for p in players)
    if total <= 0:
        return
    for p in players:
        setattr(p.usage, attr, getattr(p.usage, attr) / total)
```

After KS-12 (gated):
```python
def _expected_active_share_factor(roster, typical_roster_size: int = 22, min_fraction: float = 0.5) -> float:
    """Compute the share-normalization target accounting for inactive players."""
    active = sum(1 for p in roster.players if getattr(p.usage, "is_active", True))
    if typical_roster_size <= 0 or active == 0:
        return 1.0
    return float(np.clip(active / typical_roster_size, min_fraction, 1.0))


def _scale_shares_with_factor(players: list, attr: str, factor: float) -> None:
    """Scale shares so they sum to factor (instead of 1.0)."""
    total = sum(getattr(p.usage, attr) for p in players)
    if total <= 0:
        return
    for p in players:
        setattr(p.usage, attr, factor * getattr(p.usage, attr) / total)
```

</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write 7 failing tests for KS-12 share-normalization residual + availability composition + backup-TE/WR exclusion</name>
  <files>
    - tests/test_data/test_player_builder.py
    - tests/test_data/test_game_context.py
  </files>
  <read_first>
    - tests/test_data/test_player_builder.py (existing roster fixtures + share-normalization tests)
    - tests/test_data/test_game_context.py (existing select_receiver / select_rusher tests for integration)
    - src/fantasy_sim/data/player_builder.py:661-693 + 683-693
  </read_first>
  <behavior>
    - Add 5 unit tests in `test_player_builder.py` (ks12_factor_is_one_when_availability_off_or_full_roster, ks12_factor_lt_one_when_multi_inactive, ks12_min_fraction_clamps_low, ks12_max_fraction_clamps_high, ks12_unchanged_when_flag_disabled).
    - Add 2 integration tests in `test_game_context.py` (ks12_select_receiver_handles_residual_factor, ks12_select_rusher_handles_residual_factor).
  </behavior>
  <action>
**File 1: `tests/test_data/test_player_builder.py`** — add at the end:

```python
# === KS-12: share-normalization residual ===

import numpy as np
import pytest
from fantasy_sim.data.player_builder import (
    _expected_active_share_factor,
    _normalize_roster_shares,
)


class _MockUsage:
    def __init__(self, carry_share=0.0, target_share=0.0, red_zone_carry_share=0.0,
                 red_zone_target_share=0.0, outer_rz_carry_share=0.0, outer_rz_target_share=0.0,
                 goal_line_carry_share=0.0, is_active=True):
        self.carry_share = carry_share
        self.target_share = target_share
        self.red_zone_carry_share = red_zone_carry_share
        self.red_zone_target_share = red_zone_target_share
        self.outer_rz_carry_share = outer_rz_carry_share
        self.outer_rz_target_share = outer_rz_target_share
        self.goal_line_carry_share = goal_line_carry_share
        self.is_active = is_active


class _MockPlayer:
    def __init__(self, position, **usage_kwargs):
        self.position = position
        self.usage = _MockUsage(**usage_kwargs)


class _MockRoster:
    def __init__(self, players):
        self.players = players


def test_ks12_factor_is_one_when_availability_off_or_full_roster():
    """When availability OFF (all is_active=True) or full roster, factor = 1.0."""
    players = [_MockPlayer("RB", carry_share=0.5, is_active=True) for _ in range(22)]
    roster = _MockRoster(players)
    factor = _expected_active_share_factor(roster, typical_roster_size=22)
    assert factor == 1.0


def test_ks12_factor_lt_one_when_multi_inactive():
    """When 4 of 22 players inactive, factor = 18/22 ≈ 0.818."""
    players = [_MockPlayer("RB", carry_share=0.5, is_active=(i >= 4)) for i in range(22)]
    roster = _MockRoster(players)
    factor = _expected_active_share_factor(roster, typical_roster_size=22)
    assert abs(factor - 18/22) < 1e-6


def test_ks12_min_fraction_clamps_low():
    """When 18 of 22 inactive (only 4 active), factor would be 4/22 ≈ 0.18 but clamped to 0.5."""
    players = [_MockPlayer("RB", carry_share=0.5, is_active=(i < 4)) for i in range(22)]
    roster = _MockRoster(players)
    factor = _expected_active_share_factor(roster, typical_roster_size=22, min_fraction=0.5)
    assert factor == 0.5


def test_ks12_max_fraction_clamps_high():
    """When typical_roster_size = 20 and 22 active, factor would be 22/20 > 1.0 but clamped to 1.0."""
    players = [_MockPlayer("RB", carry_share=0.5, is_active=True) for _ in range(22)]
    roster = _MockRoster(players)
    factor = _expected_active_share_factor(roster, typical_roster_size=20)
    assert factor == 1.0


def test_ks12_normalize_unchanged_when_flag_disabled():
    """When _KS12_SHARE_NORM_RESIDUAL flag is False, _normalize_roster_shares produces sum-to-1.0."""
    # This test verifies the existing behavior is preserved when the flag is off
    # (which is the default after Plan 01).
    players = [
        _MockPlayer("RB", carry_share=0.5),
        _MockPlayer("RB", carry_share=0.3),
    ]
    roster = _MockRoster(players)
    _normalize_roster_shares(roster)
    total_carry = sum(p.usage.carry_share for p in players)
    assert abs(total_carry - 1.0) < 1e-6
```

**File 2: `tests/test_data/test_game_context.py`** — add 2 integration tests:

```python
# === KS-12: integration with select_receiver / select_rusher ===

import numpy as np
import pytest


def test_ks12_select_receiver_handles_residual_factor():
    """When availability ON and KS-12 flag ON, select_receiver works correctly with residual sum < 1.0."""
    pass  # placeholder; expand with concrete fixture-driven assertions


def test_ks12_select_rusher_handles_residual_factor():
    """When availability ON and KS-12 flag ON, select_rusher works correctly with residual sum < 1.0."""
    pass  # placeholder; expand with concrete fixture-driven assertions
```

Run pytest:
```bash
uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12
```

Expected: tests fail with `ImportError: cannot import name '_expected_active_share_factor'` — RED state.

Commit: `test(02-08): KS-12 add 7 failing tests for share-normalization residual + availability composition`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12 2>&1 | grep -E "FAILED|ERROR" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_data/test_player_builder.py` contains all 5 `def test_ks12_*` test functions
    - `tests/test_data/test_game_context.py` contains both `def test_ks12_*` test functions
    - `uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12` exits NON-ZERO (RED)
    - `git log -1 --pretty=%s` matches `test(02-08): KS-12`
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement `_expected_active_share_factor` + extend `_normalize_roster_shares` (gated) + run tests</name>
  <files>
    - src/fantasy_sim/data/player_builder.py
  </files>
  <read_first>
    - src/fantasy_sim/data/player_builder.py:661-693 (existing _normalize_roster_shares)
    - src/fantasy_sim/data/player_builder.py:683-693 (existing _scale_shares helper)
    - src/fantasy_sim/config/loader.py (`get_phase2_ks_flags`)
  </read_first>
  <behavior>
    - Add module-level flag `_KS12_SHARE_NORM_RESIDUAL` read at import.
    - Add `_expected_active_share_factor(roster, typical_roster_size=22, min_fraction=0.5)` helper.
    - Add `_scale_shares_with_factor(players, attr, factor)` helper.
    - In `_normalize_roster_shares`, when flag enabled, compute factor and scale all 7 share types (carry, red_zone_carry, outer_rz_carry, goal_line_carry, target, red_zone_target, outer_rz_target) with the factor.
    - Add backup-TE/WR exclusion threshold (suggested 0.05 — see Manual-Only Verifications in 02-VALIDATION.md). Add a constant `MIN_BACKUP_RECEIVING_SHARE = 0.05` and use it in the eligibility filters for `target_share` / `red_zone_target_share` / `outer_rz_target_share`.
  </behavior>
  <action>
Modify `src/fantasy_sim/data/player_builder.py`:

After the existing imports + `MIN_QB_CARRY_SHARE` constant (around line ~10-30), add:

```python
import numpy as np
from fantasy_sim.config.loader import get_phase2_ks_flags

# KS-12 D-09: share-normalization residual — module-level flag read at import.
_KS12_SHARE_NORM_RESIDUAL = (
    get_phase2_ks_flags()
    .get("ks12_share_normalization_residual", {})
    .get("enabled", False)
)

# KS-12 backup-TE/WR exclusion threshold (Claude's Discretion per CONTEXT.md;
# default 0.05 = backup must have >=5% of receiving share to participate in
# normalization). Mirrors MIN_QB_CARRY_SHARE = 0.10 for non-QB receivers.
MIN_BACKUP_RECEIVING_SHARE = 0.05
```

After `_scale_shares` (around line 683-693), add:

```python
def _expected_active_share_factor(
    roster,
    typical_roster_size: int = 22,
    min_fraction: float = 0.5,
) -> float:
    """KS-12 D-09: factor for share-normalization residual.

    Returns active_players / typical_roster_size, clipped to [min_fraction, 1.0].
    When all players are active (or availability is off and is_active defaults to
    True), returns ~1.0 and behavior matches legacy normalization.

    Pitfall 5: clamp protects against multi-inactive collapsing (lower bound) and
    over-allocating beyond sum-to-1 (upper bound).
    """
    active = sum(1 for p in roster.players if getattr(p.usage, "is_active", True))
    if typical_roster_size <= 0 or active == 0:
        return 1.0
    return float(np.clip(active / typical_roster_size, min_fraction, 1.0))


def _scale_shares_with_factor(players: list, attr: str, factor: float) -> None:
    """KS-12 D-09: scale shares so they sum to factor (instead of 1.0)."""
    total = sum(getattr(p.usage, attr) for p in players)
    if total <= 0:
        return
    for p in players:
        setattr(p.usage, attr, factor * getattr(p.usage, attr) / total)
```

Modify `_normalize_roster_shares`:

```python
def _normalize_roster_shares(roster) -> None:
    """Normalize carry/target shares.

    KS-12 D-09 (Plan 08): when phase2_ks_flags.ks12_share_normalization_residual is
    enabled, normalize to `factor = clip(active/typical, 0.5, 1.0)` instead of 1.0.
    Otherwise, legacy sum-to-1.0 behavior.
    """
    factor = _expected_active_share_factor(roster) if _KS12_SHARE_NORM_RESIDUAL else 1.0

    # Carry shares — eligible filter unchanged from Phase 1
    eligible_rushers = [
        p for p in roster.players
        if p.usage.carry_share > 0
        and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    if factor < 1.0:
        _scale_shares_with_factor(eligible_rushers, "carry_share", factor)
    else:
        _scale_shares(eligible_rushers, "carry_share")

    # ... (4 more carry blocks: red_zone_carry_share, outer_rz_carry_share, goal_line_carry_share — same pattern)

    # Target shares — KS-12 adds backup-TE/WR exclusion + factor
    eligible_receivers = [
        p for p in roster.players
        if p.usage.target_share > 0
        and (p.position not in ("WR", "TE") or p.usage.target_share >= MIN_BACKUP_RECEIVING_SHARE)
    ]
    if factor < 1.0:
        _scale_shares_with_factor(eligible_receivers, "target_share", factor)
    else:
        _scale_shares(eligible_receivers, "target_share")

    # ... (2 more target blocks: red_zone_target_share, outer_rz_target_share — same pattern with backup-TE/WR exclusion)
```

(Apply the same `factor < 1.0` branch + backup-TE/WR exclusion to all 7 share types.)

Run pytest:
```bash
uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12
```

Expected: 7 tests pass.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,170 + 7 = 2,177 tests pass.

Commit: `feat(02-08): KS-12 implement _expected_active_share_factor + scale-with-factor in _normalize_roster_shares (gated, backup-TE/WR exclusion at 0.05)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/data/player_builder.py` contains `def _expected_active_share_factor`
    - `src/fantasy_sim/data/player_builder.py` contains `_KS12_SHARE_NORM_RESIDUAL`
    - `src/fantasy_sim/data/player_builder.py` contains `MIN_BACKUP_RECEIVING_SHARE = 0.05`
    - `src/fantasy_sim/data/player_builder.py` contains `def _scale_shares_with_factor`
    - `uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12` exits 0
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,177 tests)
    - `git log -1 --pretty=%s` matches `feat(02-08): KS-12`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Run KS-12 A/B with availability ON + promotion-state commit per D-30</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - config/defaults.yaml (`phase2_ks_flags.ks12_share_normalization_residual`)
  </read_first>
  <behavior>
    - Run A/B with `--set availability.enabled=true` (KS-12 only matters when availability fires).
    - Apply Phase 1 D-30 small-gain bar: hard floor + WR target_share variance retention as primary target.
  </behavior>
  <action>
Run A/B:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set availability.enabled=true \
  --set phase2_ks_flags.ks12_share_normalization_residual.enabled=true \
  --label p2.ks12.bare \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks12_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks12_share_normalization_residual.enabled=true \
  --label p2.ks12.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks12_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p2.ks12"
```

Apply D-30: hard floor + non-regression on WR target_share variance OR Δ stat_ks[WR][receptions] ≤ 0.

Append to PROMOTION-NOTES.md:
```markdown
## KS-12 (Plan 08) — <STATUS>

**Backup-TE/WR exclusion threshold:** MIN_BACKUP_RECEIVING_SHARE = 0.05 (planner's discretion per CONTEXT.md).

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[WR][receptions] | Δ stat_ks[TE][receptions] | Hard Floor | KS Δ ≤ 0 on primary |
|------|-------------|--------------|----------------------------|----------------------------|-----------|---------------------|
| bare | <val>       | <val>        | <val>                      | <val>                      | <PASS/FAIL> | <PASS/FAIL>         |
| full | <val>       | <val>        | <val>                      | <val>                      | <PASS/FAIL> | <PASS/FAIL>         |

**D-30 evaluation:** hard floor + non-regression = <PASS/FAIL>.

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`.
```

If SHIPPED, edit defaults.yaml: `phase2_ks_flags.ks12_share_normalization_residual.enabled: true`. If SHIPPED-NO-OP / BLOCKED, flag stays false.

Commit:
```
feat(02-08): KS-12 <STATUS> per D-30 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[WR][receptions] <val>

Defaults: phase2_ks_flags.ks12_share_normalization_residual.enabled=<true|false>
Backup-TE/WR exclusion threshold: MIN_BACKUP_RECEIVING_SHARE = 0.05
Refs: D-09 (CONTEXT.md), HYPOTHESES.md KS-12 (lines 247-259)
```
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.ks12" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-12" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks12"` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-12` section contains A/B table + D-30 evaluation + Decision word
    - PROMOTION-NOTES.md `## KS-12` section documents the backup-TE/WR exclusion threshold value
    - `uv run pytest tests/ -v` exits 0 (2,177 tests passing)
    - `git log -1 --pretty=%s` matches `feat(02-08): KS-12`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. `git log --oneline -10` shows 3 new commits prefixed `(02-08)`.
2. If SHIPPED: defaults.yaml has `phase2_ks_flags.ks12_share_normalization_residual.enabled: true`.
3. `uv run pytest tests/test_data/test_player_builder.py tests/test_data/test_game_context.py -v -k ks12` exits 0.
4. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks12"` returns 2 rows.
5. `uv run pytest tests/ -v` exits 0; total = 2,177.
6. PROMOTION-NOTES.md `## KS-12` has D-30 evaluation + final decision word + backup-TE/WR exclusion threshold documented.

KS-12 status recorded. Plan 09 (Phase 2 aggregate) may now run.
</verification>

<must_haves>
  truths:
    - "Per D-09: factor = clip(active/typical_roster_size, 0.5, 1.0); _scale_shares_with_factor scales to factor instead of 1.0"
    - "Per Pitfall 5: clamp protects against multi-inactive collapse (lower bound) and over-allocation (upper bound)"
    - "Per D-02: gated behind phase2_ks_flags.ks12_share_normalization_residual.enabled (default false)"
    - "Per D-09: backup-TE/WR exclusion at MIN_BACKUP_RECEIVING_SHARE = 0.05 (Claude's Discretion per CONTEXT.md)"
    - "Per ROADMAP risk note: PRIMARY integration concern is composing with availability engine without double-counting; tests cover availability OFF, full roster, multi-inactive cases"
    - "Per D-12: KS-12 last among per-KS plans because _normalize_roster_shares fires 9+ times per game build (biggest blast radius)"
    - "Per C-08: TDD-first for KS-12 per ROADMAP risk note"
    - "Per C-09: 2,177-test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/data/player_builder.py"
      provides: "_expected_active_share_factor + _scale_shares_with_factor + _KS12_SHARE_NORM_RESIDUAL flag + MIN_BACKUP_RECEIVING_SHARE constant"
      contains: "_expected_active_share_factor"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-12 A/B + D-30 evaluation + decision + backup-TE/WR exclusion threshold"
      contains: "## KS-12"
</must_haves>
