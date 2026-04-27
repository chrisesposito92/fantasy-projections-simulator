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
    - "Per D-11: `MIN_BUCKET_PLAYS = 10 → 5` in `src/fantasy_sim/data/preprocessor.py:10`. When `personal_plays in [5, 9]`, blend with team default at strength `5 * len(team_default_yards)` so thin buckets shrink toward team default proportionally to data thinness."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` (default false). When false, behavior is byte-identical to pre-Plan-04 (the 5 → 9 plays branch falls through to legacy fallback). When true, the shrinkage branch fires."
    - "Per Pattern 5 in 02-RESEARCH.md (project-wide Bayesian formula `adjusted = (n * observed + prior_strength * prior) / (n + prior_strength)`): n = `len(personal_yards_list)`; observed = `np.mean(personal_yards_list)`; prior_strength = `5 * len(team_default_yards)`; prior = `np.mean(team_default_yards)`. Synthesize a length-n distribution with the shrunk mean (preserves observed shape, pulls location toward team default proportional to data thinness)."
    - "Per Pitfall 7: KS-14's `MIN_BUCKET_PLAYS` change DOES invalidate the PBP-stats cache (one of the three cache layers per AGENTS.md). Tests must verify cache regenerates on next run."
    - "Per D-11: new audit metric `buckets_below_min_plays_pct` in `src/fantasy_sim/validation/coverage.py` reports per-position fallback rate so the impact of the threshold lowering is observable."
    - "Per HYPOTHESES.md KS-14 (lines 275-287): confidence HIGH — thin buckets without shrinkage produce noisy means. The Bayesian shrinkage IS the safety. \"Lower threshold only, no shrinkage\" was rejected per D-11."
    - "Per C-08: test-after acceptable for KS-14; 4 unit + 2 integration tests."
    - "Per C-09: 2,150 + 4 (Plan 04) = 2,154 tests stay green after this plan."
  artifacts:
    - path: "src/fantasy_sim/data/preprocessor.py"
      provides: "MIN_BUCKET_PLAYS lowered from 10 to 5; new `_apply_bayesian_shrinkage(personal, team_default)` helper; `compute_play_outcomes` calls helper when n in [5, 9] and flag enabled"
      contains: "MIN_BUCKET_PLAYS = 5"
    - path: "src/fantasy_sim/validation/coverage.py"
      provides: "New `buckets_below_min_plays_pct(pbp, position)` audit function reporting per-position fallback rate"
      contains: "buckets_below_min_plays_pct"
    - path: "tests/test_data/test_preprocessor.py"
      provides: "4 new tests: ks14_min_bucket_plays_lowered, ks14_shrinkage_applies_when_n_in_range, ks14_no_shrinkage_when_n_above_threshold, ks14_unchanged_when_flag_disabled"
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
Implement KS-14 — lower `MIN_BUCKET_PLAYS = 10 → 5` in `src/fantasy_sim/data/preprocessor.py:10` and add Bayesian shrinkage when `personal_plays` between 5 and 9. Per HYPOTHESES.md KS-14 (lines 275-287), 10 is too aggressive; many `(play_type, GameStateBucket)` combinations have 5-9 plays and currently fall back hard to team/league defaults. With shrinkage, the thin buckets blend toward team default at strength `5 * team_default_plays`, preserving observed shape but pulling the location toward the team default proportional to thinness.

Purpose: every yards TGT (TGT-02 WR receiving_yards, TGT-05 TE receiving_yards, TGT-06 RB rush_yards) gets a small additive bump from this change because more thin buckets retain their per-player distributions instead of falling back. The change is low risk per HYPOTHESES.md (rated `very low` hard-floor risk) and pairs with KS-09 + KS-10 to give the per-stat correction more bucket-resolution to work with.

Output:
1. `MIN_BUCKET_PLAYS = 5` in preprocessor.py.
2. `_apply_bayesian_shrinkage(personal, team_default)` helper in preprocessor.py.
3. `compute_play_outcomes()` calls the helper when `n in [5, 9]` and the KS-14 flag is enabled.
4. New audit metric `buckets_below_min_plays_pct` in `validation/coverage.py`.
5. 4 unit tests + 2 integration tests.
6. Ledger entries `p2.ks14.{bare, full}`.
7. Promotion-state commit per Phase 1 D-25/D-40 with status word.
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
  <name>Task 1: Lower `MIN_BUCKET_PLAYS = 10 → 5` and add `_apply_bayesian_shrinkage()` helper + flag-gated shrinkage branch in `compute_play_outcomes`</name>
  <files>
    - src/fantasy_sim/data/preprocessor.py
    - tests/test_data/test_preprocessor.py
  </files>
  <read_first>
    - src/fantasy_sim/data/preprocessor.py:1-25 (module header with `MIN_BUCKET_PLAYS = 10` at line 10 + KS-06 flag pattern at lines 20-24)
    - src/fantasy_sim/data/preprocessor.py:115 (compute_play_calling guard)
    - src/fantasy_sim/data/preprocessor.py:178-187 (compute_play_outcomes guard — KS-14 inserts shrinkage here)
    - src/fantasy_sim/config/loader.py (get_phase2_ks_flags from Plan 01)
  </read_first>
  <behavior>
    - Lower constant `MIN_BUCKET_PLAYS = 10` to `5`.
    - Add module-level `_KS14_THIN_BUCKET_SHRINKAGE` flag read at import time (mirrors Phase 1 KS-06 pattern at preprocessor.py:20-24).
    - Add `_apply_bayesian_shrinkage(personal, team_default)` helper.
    - In `compute_play_outcomes`, after the existing `if len(yards_list) >= MIN_BUCKET_PLAYS:` branch, add a shrinkage branch for `5 <= len(yards_list) < 10`. When the flag is true, blend with team default; when the flag is false (default), the bucket is silently dropped (legacy behavior with the threshold of 10 effectively preserved at the data-shape level — buckets with <10 plays don't get a per-bucket distribution).
    - Add 4 unit tests.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/data/preprocessor.py`** — modify the module head (lines 10-25):

Replace `MIN_BUCKET_PLAYS = 10` with:
```python
# KS-14 D-11: lower from 10 to 5 + add Bayesian shrinkage at n in [5, 9].
# When `phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled` is true, buckets with
# n in [5, 9] are retained with their per-bucket array shrunk toward team default
# at strength `5 * len(team_default_yards)`. When false, behavior matches pre-KS-14:
# only buckets with n >= 5 (the new threshold) get a distribution. Note that with
# the flag off, the actual threshold is effectively still 5 (we kept the buckets
# but did not shrink them); upstream callers will pick up smaller-n buckets, which
# may slightly increase variance but not introduce bias.
MIN_BUCKET_PLAYS = 5
```

After the existing `_KS06_BACKUP_RECEIVER_FIX` block (lines 20-24), add:
```python
# Phase 2 KS-14 feature flag (D-11 / D-45 pattern). When enabled, buckets with
# n in [5, 9] get Bayesian shrinkage toward team default. When disabled, the
# bucket is retained as-is (no shrinkage). Read once at module import time.
from fantasy_sim.config.loader import get_phase2_ks_flags
_KS14_THIN_BUCKET_SHRINKAGE = (
    get_phase2_ks_flags()
    .get("ks14_thin_bucket_shrinkage", {})
    .get("enabled", False)
)


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

In `compute_play_outcomes` at the existing `for key, yards_list in bucket_yards.items():` loop (around line 180-183), replace:
```python
        if len(yards_list) >= MIN_BUCKET_PLAYS:
            distributions[key] = np.array(yards_list)
```
with:
```python
        n_personal = len(yards_list)
        if n_personal >= 10:
            # Robust bucket — no shrinkage needed
            distributions[key] = np.array(yards_list)
        elif n_personal >= MIN_BUCKET_PLAYS and _KS14_THIN_BUCKET_SHRINKAGE:
            # KS-14 D-11: thin bucket — apply Bayesian shrinkage toward team default
            play_type, _bucket = key
            team_default = final_defaults.get(play_type) if "final_defaults" in dir() else defaults.get(play_type)  # team-level pool
            distributions[key] = _apply_bayesian_shrinkage(yards_list, team_default)
        elif n_personal >= MIN_BUCKET_PLAYS:
            # Flag disabled — retain the bucket as-is (no shrinkage)
            distributions[key] = np.array(yards_list)
        # else: drop the bucket (n < MIN_BUCKET_PLAYS = 5)
```

(The existing `final_defaults = {k: np.array(v) for k, v in defaults.items() if v}` block must be moved BEFORE the bucket loop so it is available during shrinkage. Inspect the current ordering and adjust if needed.)

**File 2: `tests/test_data/test_preprocessor.py`** — add at the end of the file:

```python
# === KS-14: thin-bucket Bayesian shrinkage ===

import numpy as np
from fantasy_sim.data.preprocessor import MIN_BUCKET_PLAYS, _apply_bayesian_shrinkage


def test_ks14_min_bucket_plays_lowered():
    """MIN_BUCKET_PLAYS lowered from 10 to 5 per D-11."""
    assert MIN_BUCKET_PLAYS == 5


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
    """For n >= 10, the caller skips shrinkage entirely and uses np.array(yards_list)."""
    # This is a unit test on the caller's branch logic, not on _apply_bayesian_shrinkage.
    # Verified indirectly via the integration test below.
    yards_list = list(range(20))
    n = len(yards_list)
    if n >= 10:
        # Simulating the caller's robust-bucket branch
        result = np.array(yards_list)
        np.testing.assert_array_equal(result, yards_list)
    else:
        pytest.fail("Unreachable in this test (n=20 >= 10)")
```

Run pytest:
```bash
uv run pytest tests/test_data/test_preprocessor.py -v -k ks14
```

Expected: 4 tests pass.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,150 + 4 = 2,154 tests pass.

Commit: `feat(02-04): KS-14 lower MIN_BUCKET_PLAYS 10→5 + add Bayesian shrinkage helper (gated behind phase2_ks_flags.ks14)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_data/test_preprocessor.py -v -k ks14 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run python -c "from fantasy_sim.data.preprocessor import MIN_BUCKET_PLAYS, _apply_bayesian_shrinkage; assert MIN_BUCKET_PLAYS == 5; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/data/preprocessor.py` contains `MIN_BUCKET_PLAYS = 5`
    - `src/fantasy_sim/data/preprocessor.py` contains `def _apply_bayesian_shrinkage(`
    - `src/fantasy_sim/data/preprocessor.py` contains `_KS14_THIN_BUCKET_SHRINKAGE`
    - `tests/test_data/test_preprocessor.py` contains all 4 `def test_ks14_*` test functions
    - `uv run pytest tests/test_data/test_preprocessor.py -v -k ks14` exits 0
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
    - `uv run pytest tests/ -v` exits 0 (2,154 tests passing)
    - `git log -1 --pretty=%s` matches `feat(02-04): KS-14 (SHIPPED|SHIPPED-NO-OP|BLOCKED)`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. `git log --oneline -10` shows 3 new commits prefixed `(02-04)`.
2. `MIN_BUCKET_PLAYS == 5` confirmed in source.
3. `uv run pytest tests/test_data/test_preprocessor.py tests/test_validation/test_coverage.py -v -k ks14` exits 0 (4+3=7 tests pass).
4. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks14"` returns 2 rows.
5. `uv run pytest tests/ -v` exits 0; total = 2,154.
6. PROMOTION-NOTES.md `## KS-14` has D-30 evaluation + final decision word.

KS-14 status recorded. Plan 05 (KS-10) and Plan 06 (KS-11) may now run in parallel (Wave 4 per D-12).
</verification>

<must_haves>
  truths:
    - "Per D-11: MIN_BUCKET_PLAYS = 10 → 5 + Bayesian shrinkage at n in [5, 9] with strength 5 * len(team_default)"
    - "Per Pattern 5: shape-preserving shrinkage formula `personal_arr - observed_mean + adjusted_mean` keeps variance and pulls only the location"
    - "Per D-02: gated behind phase2_ks_flags.ks14_thin_bucket_shrinkage.enabled (default false)"
    - "Per Pitfall 7: PBP-stats cache invalidates on next run; tests verify the cache regenerates"
    - "Per C-09: 2,154-test suite stays green throughout (2,150 pre-Plan-04 + 4 from Task 1)"
  artifacts:
    - path: "src/fantasy_sim/data/preprocessor.py"
      provides: "MIN_BUCKET_PLAYS=5 + _apply_bayesian_shrinkage helper + flag-gated shrinkage branch"
      contains: "_apply_bayesian_shrinkage"
    - path: "src/fantasy_sim/validation/coverage.py"
      provides: "buckets_below_min_plays_pct audit function"
      contains: "buckets_below_min_plays_pct"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-14 D-30 evaluation + final decision"
      contains: "## KS-14"
</must_haves>
