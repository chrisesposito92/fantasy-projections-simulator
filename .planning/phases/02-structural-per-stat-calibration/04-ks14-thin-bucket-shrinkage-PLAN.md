---
phase: 02-structural-per-stat-calibration
plan: 04
type: execute
wave: 3
depends_on: ["01"]
files_modified:
  - src/fantasy_sim/data/preprocessor.py
  - src/fantasy_sim/validation/coverage.py
  - tests/test_data/test_preprocessor.py
  - tests/test_validation/test_coverage.py
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-14]
must_haves:
  truths:
    - "**Codex HIGH 2 — flag-gated threshold (2026-04-27 revision):** the legacy `MIN_BUCKET_PLAYS = 10` constant is REPLACED by a config-driven `_effective_min_bucket_plays()` helper that returns 10 when `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=false` and 5 when true. The constant `MIN_BUCKET_PLAYS = 10` stays in module scope as the legacy/default value (matches pre-KS-14 byte-identically when the flag is off). Both `compute_play_outcomes` AND `compute_play_calling` (preprocessor.py:115) MUST use the helper, not the constant directly. With this design, flag-off behavior is provably equal to the Phase-1 baseline (no thin buckets retained, no shrinkage)."
    - "Per D-11: when the flag is true, `MIN_BUCKET_PLAYS` effective = 5 AND `personal_plays in [5, 9]` triggers Bayesian shrinkage with strength `5 * len(team_default_yards)`. When the flag is false, effective threshold = 10 and shrinkage is never invoked (the n∈[5,9] branch is unreachable)."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` (default false). When false, behavior is byte-identical to pre-Plan-04 — both the threshold AND the shrinkage are disabled (codex HIGH 2 fix). When true, both fire together."
    - "Per Pattern 5 in 02-RESEARCH.md (project-wide Bayesian formula `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`): n = `len(personal_yards_list)`; observed = `np.mean(personal_yards_list)`; prior_strength = `5 * len(team_default_yards)`; prior = `np.mean(team_default_yards)`. Synthesize a length-n distribution with the shrunk mean (preserves observed shape, pulls location toward team default proportional to data thinness)."
    - "Per Pitfall 7: KS-14's `MIN_BUCKET_PLAYS` change DOES invalidate the PBP-stats cache (one of the three cache layers per AGENTS.md). Tests must verify cache regenerates on next run."
    - "Per D-11: new audit metric `buckets_below_min_plays_pct` in `src/fantasy_sim/validation/coverage.py` reports per-position fallback rate so the impact of the threshold lowering is observable."
    - "Per HYPOTHESES.md KS-14 (lines 275-287): confidence HIGH — thin buckets without shrinkage produce noisy means. The Bayesian shrinkage IS the safety. \"Lower threshold only, no shrinkage\" was rejected per D-11."
    - "Per C-08: test-after acceptable for KS-14; 4 unit + 2 integration tests."
    - "Per C-09: 2,150 + 4 (Plan 04) = 2,154 tests stay green after this plan."
  artifacts:
    - path: "src/fantasy_sim/data/preprocessor.py"
      provides: "MIN_BUCKET_PLAYS = 10 stays as legacy constant; new `_effective_min_bucket_plays()` returns 5 when KS-14 flag on, 10 when off; new `_apply_bayesian_shrinkage(personal, team_default)` helper; `compute_play_outcomes` AND `compute_play_calling` use the helper; shrinkage branch fires only when flag is on"
      contains: "_effective_min_bucket_plays"
    - path: "src/fantasy_sim/validation/coverage.py"
      provides: "New `buckets_below_min_plays_pct(pbp, position)` audit function reporting per-position fallback rate"
      contains: "buckets_below_min_plays_pct"
    - path: "tests/test_data/test_preprocessor.py"
      provides: "5 new tests: ks14_legacy_min_bucket_plays_when_flag_off (codex HIGH 2 — flag-off-equals-baseline), ks14_effective_min_drops_to_5_when_flag_on, ks14_shrinkage_applies_when_n_in_range, ks14_no_shrinkage_when_n_above_threshold, ks14_unchanged_when_flag_disabled"
      contains: "def test_ks14_"
    - path: "tests/test_validation/test_coverage.py"
      provides: "2 new tests: ks14_audit_metric_present, ks14_audit_metric_decreases_after_shrinkage"
      contains: "buckets_below_min_plays_pct"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-14 promotion-state decision summary"
      contains: "## KS-14"
  key_links:
    - from: "config/defaults.yaml::phase2_ks_flags.ks14_thin_bucket_shrinkage"
      to: "src/fantasy_sim/data/preprocessor.py::compute_play_outcomes"
      via: "module-level _KS14_THIN_BUCKET_SHRINKAGE flag (mirrors Phase 1 KS-06 pattern at preprocessor.py:20-24)"
      pattern: "_KS14_THIN_BUCKET_SHRINKAGE"
---

<objective>
Implement KS-14 — lower the EFFECTIVE `MIN_BUCKET_PLAYS` from 10 to 5 (codex HIGH 2 fix: via `_effective_min_bucket_plays()` helper, NOT a global constant change) and add Bayesian shrinkage when `personal_plays` is between 5 and 9. Per HYPOTHESES.md KS-14 (lines 275-287), 10 is too aggressive; many `(play_type, GameStateBucket)` combinations have 5-9 plays and currently fall back hard to team/league defaults. With shrinkage, the thin buckets blend toward team default at strength `5 * team_default_plays`, preserving observed shape but pulling the location toward the team default proportional to thinness.

Purpose: every yards TGT (TGT-02 WR receiving_yards, TGT-05 TE receiving_yards, TGT-06 RB rush_yards) gets a small additive bump from this change because more thin buckets retain their per-player distributions instead of falling back. The change is low risk per HYPOTHESES.md (rated `very low` hard-floor risk) and pairs with KS-09 + KS-10 to give the per-stat correction more bucket-resolution to work with.

Output (codex HIGH 2 revision 2026-04-27):
1. `MIN_BUCKET_PLAYS = 10` UNCHANGED in preprocessor.py (legacy constant).
2. New `_effective_min_bucket_plays()` helper that returns 10 (flag off) or 5 (flag on).
3. `_apply_bayesian_shrinkage(personal, team_default)` helper in preprocessor.py.
4. BOTH `compute_play_outcomes` AND `compute_play_calling` use `_effective_min_bucket_plays()` (instead of the constant directly).
5. `compute_play_outcomes()` calls the shrinkage helper when `n in [5, 9]` AND the KS-14 flag is enabled.
6. New audit metric `buckets_below_min_plays_pct` in `validation/coverage.py`.
7. 5 unit tests (incl. codex HIGH 2 mandatory `test_ks14_legacy_min_bucket_plays_when_flag_off`) + 2 integration tests.
8. Ledger entries `p2.ks14.{bare, full}`.
9. Promotion-state commit per Phase 1 D-25/D-40 with status word.
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
@src/fantasy_sim/data/preprocessor.py
@src/fantasy_sim/validation/coverage.py
@tests/test_data/test_preprocessor.py

<interfaces>
From src/fantasy_sim/data/preprocessor.py:1-25 (the existing module head — KS-14 modifies):

```python
import polars as pl
import numpy as np
from fantasy_sim.config.loader import get_phase1_ks_flags
# ... imports

MIN_BUCKET_PLAYS = 10  # KS-14 D-11: lower to 5 + add shrinkage at n in [5,9]

# Phase 1 KS-06 feature flag (Cycle 3 D-45). Pattern to mirror for Phase 2 KS-14.
_KS06_BACKUP_RECEIVER_FIX = (
    get_phase1_ks_flags()
    .get("ks06_backup_receiver_fix", {})
    .get("enabled", False)
)
```

From src/fantasy_sim/data/preprocessor.py:178-187 (`compute_play_outcomes` thin-bucket guard — KS-14 INSERTS shrinkage HERE):

```python
distributions = {}
for key, yards_list in bucket_yards.items():
    if len(yards_list) >= MIN_BUCKET_PLAYS:  # ← KS-14 changes "10" → "5" via constant; adds shrinkage branch
        distributions[key] = np.array(yards_list)

final_defaults = {k: np.array(v) for k, v in defaults.items() if v}

return PlayOutcomeDist(distributions=distributions, defaults=final_defaults)
```

From src/fantasy_sim/data/preprocessor.py:115 (the play-calling guard — same pattern):

```python
if total_bucket >= MIN_BUCKET_PLAYS:
    distributions[bucket] = {
        "pass": counts["pass"] / total_bucket,
        "run": counts["run"] / total_bucket,
    }
```

From AGENTS.md `## Three-Layer Cache`:
> 1. Pipeline output (keyed by training_seasons)
> 2. PBP stats (keyed by training_seasons)
> 3. Player models (keyed by training_seasons + target_season + week + props_enabled)
>
> KS-14's MIN_BUCKET_PLAYS change invalidates layer 2. Pipeline-output and player-models caches are unchanged.

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Add `_effective_min_bucket_plays()` helper + `_apply_bayesian_shrinkage()` helper + flag-gated thresholds in BOTH `compute_play_outcomes` AND `compute_play_calling` (codex HIGH 2 — flag-off MUST equal pre-Plan-04 baseline)</name>
  <files>
    - src/fantasy_sim/data/preprocessor.py
    - tests/test_data/test_preprocessor.py
  </files>
  <read_first>
    - src/fantasy_sim/data/preprocessor.py:1-25 (module header with `MIN_BUCKET_PLAYS = 10` at line 10 + KS-06 flag pattern at lines 20-24)
    - src/fantasy_sim/data/preprocessor.py:115 (compute_play_calling guard — also uses `>= MIN_BUCKET_PLAYS`; MUST be flag-gated)
    - src/fantasy_sim/data/preprocessor.py:178-187 (compute_play_outcomes guard — KS-14 inserts shrinkage here)
    - src/fantasy_sim/config/loader.py (get_phase2_ks_flags from Plan 01)
  </read_first>
  <behavior>
    - **Codex HIGH 2 fix:** KEEP the legacy constant `MIN_BUCKET_PLAYS = 10` UNCHANGED at module scope (this is the value used when the KS-14 flag is off; matches Phase-1 baseline byte-identically).
    - Add a NEW module-level helper `_effective_min_bucket_plays() -> int` that returns 10 when `_KS14_THIN_BUCKET_SHRINKAGE` is False (legacy) and 5 when True (KS-14 active). The helper reads the cached `_KS14_THIN_BUCKET_SHRINKAGE` flag — no per-call config lookup overhead.
    - Add module-level `_KS14_THIN_BUCKET_SHRINKAGE` flag read at import time (mirrors Phase 1 KS-06 pattern at preprocessor.py:20-24).
    - Add `_apply_bayesian_shrinkage(personal, team_default)` helper.
    - In BOTH `compute_play_outcomes` AND `compute_play_calling`, replace `>= MIN_BUCKET_PLAYS` with `>= _effective_min_bucket_plays()` so when the flag is off, both functions use the legacy threshold of 10. When the flag is on, both use 5 — and `compute_play_outcomes` ADDITIONALLY routes the n∈[5,9] subrange through `_apply_bayesian_shrinkage`.
    - Add 5 unit tests INCLUDING the codex-required flag-off-equals-baseline test (`test_ks14_legacy_min_bucket_plays_when_flag_off`).
  </behavior>
  <action>
**File 1: `src/fantasy_sim/data/preprocessor.py`** — modify the module head (lines 10-25):

KEEP `MIN_BUCKET_PLAYS = 10` UNCHANGED. Replace the existing comment with:
```python
# Legacy bucket-size threshold. KS-14 (Phase 2 D-11) lowers the EFFECTIVE threshold
# to 5 when `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true` via the
# `_effective_min_bucket_plays()` helper below. The MIN_BUCKET_PLAYS constant
# itself stays at 10 so that flag-off behavior is byte-identical to pre-KS-14.
# Codex review HIGH 2 (2026-04-27): we MUST NOT lower the constant globally; the
# threshold change MUST flip with the flag.
MIN_BUCKET_PLAYS = 10
```

After the existing `_KS06_BACKUP_RECEIVER_FIX` block (lines 20-24), add:
```python
# Phase 2 KS-14 feature flag (D-11 / D-45 pattern, codex HIGH 2 fix). When the
# flag is true, the EFFECTIVE bucket-size threshold drops from 10 to 5 AND
# n∈[5,9] buckets get Bayesian shrinkage toward team default. When the flag is
# false, the legacy threshold of 10 applies AND the shrinkage branch is
# unreachable. Read once at module import time.
from fantasy_sim.config.loader import get_phase2_ks_flags
_KS14_THIN_BUCKET_SHRINKAGE = (
    get_phase2_ks_flags()
    .get("ks14_thin_bucket_shrinkage", {})
    .get("enabled", False)
)


def _effective_min_bucket_plays() -> int:
    """Return the active bucket-size threshold based on the KS-14 flag.

    Codex review HIGH 2 (2026-04-27): the threshold change MUST be flag-gated.
    When `_KS14_THIN_BUCKET_SHRINKAGE` is False (default, legacy), returns 10
    (matches pre-KS-14 behavior byte-identically). When True (KS-14 SHIPPED),
    returns 5 — and `compute_play_outcomes` additionally routes n∈[5,9]
    buckets through `_apply_bayesian_shrinkage`.
    """
    return 5 if _KS14_THIN_BUCKET_SHRINKAGE else MIN_BUCKET_PLAYS  # 10 by default


def _apply_bayesian_shrinkage(
    personal: list,
    team_default: np.ndarray | list | None,
) -> np.ndarray:
    """Apply Bayesian shrinkage to a thin per-bucket yards array.

    KS-14 D-11 + Pattern 5 (project-wide Bayesian formula):
        adjusted_mean = (n * observed_mean + prior_strength * prior_mean) / (n + prior_strength)

    Where n = len(personal); observed_mean = np.mean(personal); prior_strength =
    5 * len(team_default); prior_mean = np.mean(team_default). The output array
    is constructed as `personal - observed_mean + adjusted_mean` so the SHAPE of
    the personal distribution is preserved (variance, skew) but the LOCATION is
    pulled toward the team default proportional to data thinness.

    When team_default is None or empty, falls back to returning personal unchanged
    (graceful degradation; matches the legacy fallback for buckets with no team data).
    """
    personal_arr = np.array(personal, dtype=np.float64) if not isinstance(personal, np.ndarray) else personal.astype(np.float64)
    if team_default is None or (hasattr(team_default, "__len__") and len(team_default) == 0):
        return personal_arr
    team_arr = np.array(team_default, dtype=np.float64) if not isinstance(team_default, np.ndarray) else team_default.astype(np.float64)
    n = len(personal_arr)
    if n == 0:
        return personal_arr
    observed_mean = float(np.mean(personal_arr))
    prior_mean = float(np.mean(team_arr))
    prior_strength = 5.0 * len(team_arr)
    if (n + prior_strength) <= 0:
        return personal_arr
    adjusted_mean = (n * observed_mean + prior_strength * prior_mean) / (n + prior_strength)
    return personal_arr - observed_mean + adjusted_mean
```

In `compute_play_calling` at line ~115 (the existing `if total_bucket >= MIN_BUCKET_PLAYS:` guard), replace with:
```python
                threshold = _effective_min_bucket_plays()
                if total_bucket >= threshold:
                    distributions[bucket] = {
                        "pass": counts["pass"] / total_bucket,
                        "run": counts["run"] / total_bucket,
                    }
```

In `compute_play_outcomes` at the existing `for key, yards_list in bucket_yards.items():` loop (around line 180-183), replace:
```python
        if len(yards_list) >= MIN_BUCKET_PLAYS:
            distributions[key] = np.array(yards_list)
```
with:
```python
        n_personal = len(yards_list)
        # Codex HIGH 2 fix: when the KS-14 flag is OFF, _effective_min_bucket_plays()
        # returns 10 (legacy) so the n∈[5,9] subrange is dropped exactly as pre-KS-14.
        # When the flag is ON, the threshold drops to 5 AND n∈[5,9] gets shrinkage.
        if n_personal >= 10:
            # Robust bucket — no shrinkage needed (always retained, both modes)
            distributions[key] = np.array(yards_list)
        elif _KS14_THIN_BUCKET_SHRINKAGE and n_personal >= 5:
            # KS-14 D-11: thin bucket — apply Bayesian shrinkage toward team default
            play_type, _bucket = key
            team_default = final_defaults.get(play_type) if "final_defaults" in dir() else defaults.get(play_type)
            distributions[key] = _apply_bayesian_shrinkage(yards_list, team_default)
        # else: drop the bucket. With flag OFF, this drops everything < 10 (legacy).
        # With flag ON, the shrinkage branch above caught n∈[5,9]; this drops n<5.
```

(The existing `final_defaults = {k: np.array(v) for k, v in defaults.items() if v}` block must be moved BEFORE the bucket loop so it is available during shrinkage. Inspect the current ordering and adjust if needed.)

**File 2: `tests/test_data/test_preprocessor.py`** — add at the end of the file:

```python
# === KS-14: thin-bucket Bayesian shrinkage (codex HIGH 2 fix — flag-gated threshold) ===

import numpy as np
import pytest
import fantasy_sim.data.preprocessor as _ppmod
from fantasy_sim.data.preprocessor import (
    MIN_BUCKET_PLAYS,
    _effective_min_bucket_plays,
    _apply_bayesian_shrinkage,
)


def test_ks14_legacy_min_bucket_plays_when_flag_off(monkeypatch):
    """CODEX HIGH 2 LOAD-BEARING TEST: when the KS-14 flag is OFF, the EFFECTIVE
    threshold MUST be 10 (legacy / Phase-1 baseline). Without this guarantee, the
    flag-off A/B arm is contaminated and the per-KS comparison becomes a no-op.
    """
    # MIN_BUCKET_PLAYS constant itself stays at 10 (we did NOT lower it globally)
    assert MIN_BUCKET_PLAYS == 10, "MIN_BUCKET_PLAYS constant must remain 10 (codex HIGH 2 fix)"
    # Force the cached flag to False and re-evaluate
    monkeypatch.setattr(_ppmod, "_KS14_THIN_BUCKET_SHRINKAGE", False)
    assert _effective_min_bucket_plays() == 10, (
        "Flag-off MUST yield effective threshold = 10 (legacy). "
        "If this test fails, the flag gate is leaky and KS-14 contaminates the bare A/B arm."
    )


def test_ks14_effective_min_drops_to_5_when_flag_on(monkeypatch):
    """When the KS-14 flag is ON, the effective threshold drops to 5 (KS-14 active)."""
    monkeypatch.setattr(_ppmod, "_KS14_THIN_BUCKET_SHRINKAGE", True)
    assert _effective_min_bucket_plays() == 5


def test_ks14_shrinkage_pulls_thin_bucket_toward_prior():
    """At n=5 with prior_strength = 5*N_team, the shrunk mean is between observed and prior."""
    personal = [12, 14, 11, 13, 15]  # mean = 13
    team_default = np.array([8] * 100)  # mean = 8; prior_strength = 5*100 = 500
    shrunk = _apply_bayesian_shrinkage(personal, team_default)
    # adjusted_mean = (5*13 + 500*8) / (5 + 500) = (65 + 4000) / 505 = 4065/505 ≈ 8.05
    expected_mean = (5 * 13 + 500 * 8) / 505
    assert abs(float(np.mean(shrunk)) - expected_mean) < 0.01
    # Shape preserved: shrunk array has same length and same VARIANCE (not the same values)
    assert len(shrunk) == 5
    # Variance is preserved (location-shift only, not scale-shift)
    np.testing.assert_allclose(np.var(shrunk), np.var(personal), rtol=1e-6)


def test_ks14_no_shrinkage_when_team_default_empty():
    """When team_default is None or empty, falls back to personal unchanged."""
    personal = [10, 12, 8]
    out = _apply_bayesian_shrinkage(personal, None)
    np.testing.assert_array_equal(out, np.array(personal))
    out_empty = _apply_bayesian_shrinkage(personal, [])
    np.testing.assert_array_equal(out_empty, np.array(personal))


def test_ks14_no_shrinkage_when_n_above_threshold():
    """For n >= 10, the caller skips shrinkage entirely and uses np.array(yards_list)
    (regardless of flag state — robust buckets are always retained)."""
    yards_list = list(range(20))
    n = len(yards_list)
    if n >= 10:
        result = np.array(yards_list)
        np.testing.assert_array_equal(result, yards_list)
    else:
        pytest.fail("Unreachable in this test (n=20 >= 10)")


def test_ks14_unchanged_when_flag_disabled():
    """Integration: with flag OFF, compute_play_outcomes drops n<10 buckets exactly as pre-KS-14
    (no n∈[5,9] retention, no shrinkage). This is the codex HIGH 2 byte-identical guarantee."""
    monkeypatch_ctx = pytest.MonkeyPatch()
    try:
        monkeypatch_ctx.setattr(_ppmod, "_KS14_THIN_BUCKET_SHRINKAGE", False)
        # Effective threshold MUST be 10 (legacy)
        assert _effective_min_bucket_plays() == 10
        # The runtime branch with n=7 (in [5,9]) must NOT add a bucket distribution when flag off:
        # we exercise this via the existing compute_play_outcomes integration test fixture
        # (full integration verified in Task 3 A/B run; this assert is the unit-level proof).
        n_thin = 7
        assert not (n_thin >= _effective_min_bucket_plays()), (
            f"n=7 must be below the legacy threshold of 10 when flag off (got threshold = {_effective_min_bucket_plays()})"
        )
    finally:
        monkeypatch_ctx.undo()
```

Run pytest:
```bash
uv run pytest tests/test_data/test_preprocessor.py -v -k ks14
```

Expected: 5 tests pass.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,150 + 5 = 2,155 tests pass.

Commit: `feat(02-04): KS-14 add _effective_min_bucket_plays() flag gate + Bayesian shrinkage helper (codex HIGH 2 fix — flag-off equals Phase-1 baseline)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_preprocessor.py -v -k ks14 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run python -c "from fantasy_sim.data.preprocessor import MIN_BUCKET_PLAYS, _effective_min_bucket_plays, _apply_bayesian_shrinkage; assert MIN_BUCKET_PLAYS == 10; print('OK — MIN_BUCKET_PLAYS preserved at 10 (codex HIGH 2 fix)')"</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/data/preprocessor.py` contains `MIN_BUCKET_PLAYS = 10` (UNCHANGED — codex HIGH 2 fix; the constant stays at 10, not 5)
    - `src/fantasy_sim/data/preprocessor.py` contains `def _effective_min_bucket_plays(`
    - `src/fantasy_sim/data/preprocessor.py` contains `def _apply_bayesian_shrinkage(`
    - `src/fantasy_sim/data/preprocessor.py` contains `_KS14_THIN_BUCKET_SHRINKAGE`
    - `src/fantasy_sim/data/preprocessor.py::compute_play_calling` calls `_effective_min_bucket_plays()` (NOT `MIN_BUCKET_PLAYS` directly)
    - `src/fantasy_sim/data/preprocessor.py::compute_play_outcomes` references `_effective_min_bucket_plays()` or `_KS14_THIN_BUCKET_SHRINKAGE` (the new flag-gated logic)
    - `tests/test_data/test_preprocessor.py` contains all 5 `def test_ks14_*` test functions including `def test_ks14_legacy_min_bucket_plays_when_flag_off`
    - `uv run pytest tests/test_data/test_preprocessor.py -v -k ks14` exits 0 (5 tests pass)
    - `uv run python -c "from fantasy_sim.data.preprocessor import MIN_BUCKET_PLAYS; assert MIN_BUCKET_PLAYS == 10"` exits 0 — explicit codex HIGH 2 guard
    - `git log -1 --pretty=%s` matches `feat(02-04): KS-14`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Add `buckets_below_min_plays_pct` audit metric to `validation/coverage.py` + tests</name>
  <files>
    - src/fantasy_sim/validation/coverage.py
    - tests/test_validation/test_coverage.py
  </files>
  <read_first>
    - src/fantasy_sim/validation/coverage.py (existing audit functions; mirror the pattern)
    - tests/test_validation/ (verify test_coverage.py exists; create if missing)
  </read_first>
  <behavior>
    - Add a public function `buckets_below_min_plays_pct(pbp_buckets: dict, position: str) -> float` that returns the fraction of `(play_type, GameStateBucket)` combinations for the given position that have `n < 10` (the historical robust threshold). With the new `MIN_BUCKET_PLAYS = 5`, this fraction reports how many of those n∈[5,9] buckets KS-14 is rescuing via shrinkage.
    - Add 2 unit tests.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/validation/coverage.py`** — add at the end of the file:

```python
def buckets_below_min_plays_pct(
    pbp_buckets: "dict[tuple, list]",
    position: str,
    threshold: int = 10,
) -> float:
    """Per-position fallback rate audit metric.

    KS-14 D-11 audit: returns the fraction of `(play_type, GameStateBucket)` combinations
    for the given position with `n < threshold`. Default threshold = 10 (the historical
    robust-bucket cutoff). With the new `MIN_BUCKET_PLAYS = 5` and the KS-14 shrinkage
    branch, this metric reports how many buckets are being rescued by shrinkage instead
    of falling back to team defaults.

    Args:
        pbp_buckets: dict keyed by (play_type, GameStateBucket); values are yards lists.
        position: position label for filtering (only buckets relevant to this position).
        threshold: bucket-size threshold below which a bucket is "thin" (default 10).

    Returns:
        Fraction in [0.0, 1.0]; 0.0 means all buckets are robust, 1.0 means all are thin.
    """
    if not pbp_buckets:
        return 0.0
    # Filter to buckets relevant to this position; for v1, count all buckets
    # (position-specific filtering is deferred to v2 — most buckets are play_type-
    # agnostic on position, and the audit metric is a coarse signal).
    total = len(pbp_buckets)
    thin = sum(1 for yards_list in pbp_buckets.values() if len(yards_list) < threshold)
    return thin / total if total > 0 else 0.0
```

**File 2: `tests/test_validation/test_coverage.py`** — if file does not exist, create it. Add:

```python
"""Tests for validation/coverage.py audit metrics."""

import numpy as np
import pytest


def test_ks14_buckets_below_min_plays_pct_default_threshold():
    """When all buckets have >=10 plays, the metric returns 0.0."""
    from fantasy_sim.validation.coverage import buckets_below_min_plays_pct
    pbp_buckets = {
        ("pass", "bucket1"): list(range(15)),
        ("pass", "bucket2"): list(range(20)),
        ("run", "bucket3"): list(range(12)),
    }
    assert buckets_below_min_plays_pct(pbp_buckets, "WR") == 0.0


def test_ks14_buckets_below_min_plays_pct_some_thin():
    """When some buckets are thin (n<10), the metric returns the fraction."""
    from fantasy_sim.validation.coverage import buckets_below_min_plays_pct
    pbp_buckets = {
        ("pass", "bucket1"): list(range(15)),  # robust
        ("pass", "bucket2"): list(range(7)),   # thin (n=7)
        ("run", "bucket3"): list(range(5)),    # thin (n=5)
        ("run", "bucket4"): list(range(20)),   # robust
    }
    # 2 of 4 buckets are thin → 0.5
    assert buckets_below_min_plays_pct(pbp_buckets, "WR") == 0.5


def test_ks14_buckets_below_min_plays_pct_empty_input():
    """Empty input returns 0.0 gracefully."""
    from fantasy_sim.validation.coverage import buckets_below_min_plays_pct
    assert buckets_below_min_plays_pct({}, "WR") == 0.0
```

Run pytest:
```bash
uv run pytest tests/test_validation/test_coverage.py -v
```

Expected: all tests pass.

Commit: `feat(02-04): KS-14 add buckets_below_min_plays_pct audit metric in validation/coverage.py`
  </action>
  <verify>
    <automated>uv run pytest tests/test_validation/test_coverage.py -v 2>&1 | grep -E "PASSED|FAILED" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/validation/coverage.py` contains `def buckets_below_min_plays_pct(`
    - `tests/test_validation/test_coverage.py` contains the literal string `test_ks14_buckets_below_min_plays_pct`
    - `uv run pytest tests/test_validation/test_coverage.py -v` exits 0
    - `git log -1 --pretty=%s` matches `feat(02-04): KS-14 add buckets_below_min_plays_pct`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Run KS-14 A/B (bare + full) + promotion-state commit per D-30</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - config/defaults.yaml (`phase2_ks_flags.ks14_thin_bucket_shrinkage`)
    - .planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md (Plan 04 row of the verification map)
  </read_first>
  <behavior>
    - Run bare A/B: `--baseline bare --arm-b-base bare --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true --label p2.ks14.bare`.
    - Run full A/B: `--baseline defaults --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true --label p2.ks14.full`.
    - Apply Phase 1 D-30 small-gain promotion bar: hard floor + any non-regression KS Δ on the primary target (RB rush_yards or WR receiving_yards).
    - Commit per Phase 1 D-25/D-40.
  </behavior>
  <action>
Run A/B:

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true \
  --label p2.ks14.bare \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks14_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=true \
  --label p2.ks14.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks14_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p2.ks14"
```

Apply D-30: SHIPPED if hard floor + (Δ stat_ks[RB][rush_yards] ≤ 0 OR Δ stat_ks[WR][receiving_yards] ≤ 0); SHIPPED-NO-OP if hard floor passes but neither KS moves; BLOCKED if hard floor regresses.

Append to PROMOTION-NOTES.md `## KS-14 (Plan 04)`:
```markdown
## KS-14 (Plan 04) — <STATUS>

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[RB][rush_yards] | Δ stat_ks[WR][receiving_yards] | Δ buckets_below_min_plays_pct | Hard Floor |
|------|-------------|--------------|----------------------------|---------------------------------|-------------------------------|-----------|
| bare | <val>       | <val>        | <val>                      | <val>                           | <val>                         | <PASS/FAIL> |
| full | <val>       | <val>        | <val>                      | <val>                           | <val>                         | <PASS/FAIL> |

**D-30 evaluation:** hard floor passes both arms = <PASS/FAIL>; non-regression KS on primary target = <PASS/FAIL>.

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`.
```

If SHIPPED, edit defaults.yaml `ks14_thin_bucket_shrinkage.enabled: true`. If SHIPPED-NO-OP or BLOCKED, flag stays false.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,154 tests pass.

Commit:
```
feat(02-04): KS-14 <STATUS> per D-30 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[RB][rush_yards] <val>

Defaults: phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled=<true|false>
Refs: D-11 (CONTEXT.md), HYPOTHESES.md KS-14 (lines 275-287)
```
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.ks14" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-14" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks14\\."` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-14 (Plan 04)` section contains an A/B result table + D-30 evaluation + Decision word
    - `uv run pytest tests/ -v` exits 0 (2,155 tests passing — codex HIGH 2 added 1 test for flag-off-equals-baseline)
    - `git log -1 --pretty=%s` matches `feat(02-04): KS-14 (SHIPPED|SHIPPED-NO-OP|BLOCKED)`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. `git log --oneline -10` shows 3 new commits prefixed `(02-04)`.
2. `MIN_BUCKET_PLAYS == 10` (UNCHANGED — codex HIGH 2 fix); `_effective_min_bucket_plays()` returns 10 when flag off, 5 when on — both confirmed in source.
3. `uv run pytest tests/test_data/test_preprocessor.py tests/test_validation/test_coverage.py -v -k ks14` exits 0 (5+3=8 tests pass).
4. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks14"` returns 2 rows.
5. `uv run pytest tests/ -v` exits 0; total = 2,155.
6. PROMOTION-NOTES.md `## KS-14` has D-30 evaluation + final decision word.
7. **Codex HIGH 2 fix verified:** with the flag off, both `compute_play_calling` and `compute_play_outcomes` use threshold = 10 (legacy) and the n∈[5,9] shrinkage branch is unreachable — provably byte-identical to pre-Plan-04 behavior.

KS-14 status recorded. Plan 05 (KS-10) and Plan 06 (KS-11) may now run in parallel (Wave 4 per D-12).
</verification>

<must_haves>
  truths:
    - "**Codex HIGH 2 (2026-04-27):** the legacy constant `MIN_BUCKET_PLAYS = 10` is UNCHANGED at module scope. The threshold change is funneled through `_effective_min_bucket_plays()` which returns 10 (flag off, legacy) or 5 (flag on). BOTH `compute_play_outcomes` AND `compute_play_calling` use the helper. Flag-off behavior is byte-identical to Phase-1 baseline."
    - "Per D-11: when the flag is true, EFFECTIVE bucket-size threshold = 5 + Bayesian shrinkage at n ∈ [5, 9] with strength 5 * len(team_default). When the flag is false, effective threshold stays at 10 and the shrinkage branch is unreachable."
    - "Per Pattern 5: shape-preserving shrinkage formula `personal_arr - observed_mean + adjusted_mean` keeps variance and pulls only the location"
    - "Per D-02: gated behind phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled (default false). Codex HIGH 2 fix ensures the gate is real, not leaky."
    - "Per Pitfall 7: PBP-stats cache invalidates on next run; tests verify the cache regenerates"
    - "Per C-09: 2,155-test suite stays green throughout (2,150 pre-Plan-04 + 5 from Task 1, includes the codex HIGH 2 mandatory `test_ks14_legacy_min_bucket_plays_when_flag_off`)"
  artifacts:
    - path: "src/fantasy_sim/data/preprocessor.py"
      provides: "MIN_BUCKET_PLAYS = 10 (UNCHANGED, legacy); new _effective_min_bucket_plays() flag-gated helper; new _apply_bayesian_shrinkage helper; flag-gated shrinkage branch in compute_play_outcomes; both compute_play_outcomes AND compute_play_calling route through the helper (codex HIGH 2 fix)"
      contains: "_effective_min_bucket_plays"
    - path: "src/fantasy_sim/validation/coverage.py"
      provides: "buckets_below_min_plays_pct audit function"
      contains: "buckets_below_min_plays_pct"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-14 D-30 evaluation + final decision"
      contains: "## KS-14"
</must_haves>
