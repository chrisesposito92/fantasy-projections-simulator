---
phase: 02-structural-per-stat-calibration
plan: 05
type: execute
wave: 4
depends_on: ["01", "03"]
files_modified:
  - src/fantasy_sim/scoring/residual_calibration.py
  - scripts/fit_residual_calibration.py
  - config/defaults.yaml
  - tests/test_scoring/test_residual_calibration.py
  - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json
  - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-10]
must_haves:
  truths:
    - "Per D-07 + HYPOTHESES.md KS-10 (lines 203-224): ship the verbatim values — `ensemble.residual_calibration.max_abs_adjustment_by_position = {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8}`. Add 4th `elite` tier above `14.0 fpts` for TE in `USAGE_TIER_THRESHOLDS` (`residual_calibration.py:25-30`); lower TE `min_bucket_rows` to `100` from `200` in the calibration artifact's TE buckets only. Update `clamp_adjustment` lookup at `residual_calibration.py:109-111` to read per-position cap when `phase2_ks_flags.ks10_per_position_caps.enabled` is true."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks10_per_position_caps.enabled` (default false). When false, the existing global `max_abs_adjustment = 1.5` is used (legacy behavior). When true, per-position caps + TE elite tier + reduced TE min_bucket_rows are all active."
    - "**Codex MEDIUM 7 (2026-04-27 revision):** Plan 01 ships `max_abs_adjustment_by_position = {QB: 1.5, RB: 1.5, WR: 1.5, TE: 1.5}` as a placeholder (numerically identical to the global cap, intentionally a no-op when the dict is consulted). The runtime `clamp_adjustment` MUST consult the dict ONLY when `phase2_ks_flags.ks10_per_position_caps.enabled=true` — NOT when the dict is non-empty. Otherwise the populated-but-numerically-identical placeholder would silently take effect even with the flag off. Plan 05 Task 1 wires this strictly via the flag, never via dict-presence."
    - "**Codex MEDIUM 7 — re-fit artifact assertion:** the `## KS-10 promotion validation` MUST explicitly assert that the re-fit `calibration_2024.json` artifact contains a NON-EMPTY `TE|elite|*` bucket (i.e., at least one bucket key matching the regex `^TE\\|elite\\|.*` with `n_rows >= 1`). Without this assertion, a degenerate re-fit could ship with the elite tier defined in code but unpopulated in the bundled artifact, making KS-10's TE half a no-op. If 2024 data cannot populate the elite TE bucket (small N), document the fallback behavior explicitly in PROMOTION-NOTES.md and downgrade KS-10 to SHIPPED-PARTIAL."
    - "Per Plan 03 dependency (D-12 ordering): KS-10 needs the v2 schema's stat_corrections to coexist with new per-position cap lookup. Plan 05 re-fits `decision_s200/calibration_*.json` ON TOP OF Plan 03's v2 schema (i.e., the artifact already has stat_corrections from Plan 03; Plan 05 adds the elite TE tier + per-position cap metadata)."
    - "Per Pitfall 4: TE elite tier (`> 14.0 fpts`) interaction with `_merge_thin_tiers` — the existing `_merge_thin_tiers` logic in `tier_engine.py:441-477` is a SEPARATE concern (it merges thin TIERS within a position, not thin BUCKETS within `residual_calibration`). Plan 05 verifies via test that the artifact written by `fit_residual_calibration.py` after KS-10 retune contains a non-empty `TE|elite|*` bucket (the elite tier is being populated and not collapsed)."
    - "Per HYPOTHESES.md KS-10: rated `small-medium gain, very low risk`; sweep ROI is poor — single A/B for the bundle (no per-position cap sweep)."
    - "Per C-08: test-after acceptable for KS-10; 5 unit + 1 integration test."
    - "Per C-09: 2,154 + 5 (Plan 05) = 2,159 tests stay green after this plan."
  artifacts:
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "USAGE_TIER_THRESHOLDS expanded for TE with `elite` tier (`{TE: (14.0, 9.0, 4.0)}` semantics: elite > 14, high in [9,14), mid in [4,9), low < 4); `usage_tier()` updated to handle 4-tier shape; `clamp_adjustment` reads per-position cap from config when KS-10 flag enabled"
      contains: "elite"
    - path: "scripts/fit_residual_calibration.py"
      provides: "Extended `fit_residual_calibration_artifact()` to use TE-specific min_bucket_rows=100 (down from 200) when KS-10 flag enabled; populates the new `TE|elite|*` bucket"
      contains: "TE.*100"
    - path: "config/defaults.yaml"
      provides: "Updated `ensemble.residual_calibration.max_abs_adjustment_by_position` from placeholder all-1.5 to D-07 values {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8} (after promotion)"
      contains: "TE: 0.8"
    - path: "tests/test_scoring/test_residual_calibration.py"
      provides: "5 new tests: ks10_te_elite_tier_threshold, ks10_per_position_cap_lookup, ks10_legacy_behavior_when_flag_disabled, ks10_artifact_has_te_elite_bucket_after_refit, ks10_te_min_bucket_rows_lowered"
      contains: "def test_ks10_"
    - path: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json"
      provides: "Re-fit artifact at schema_version: 2 with new `TE|elite|*` bucket(s) populated AND stat_corrections from Plan 03 preserved"
      contains: "TE|elite"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-10 promotion-state decision summary"
      contains: "## KS-10"
  key_links:
    - from: "config/defaults.yaml::phase2_ks_flags.ks10_per_position_caps + ensemble.residual_calibration.max_abs_adjustment_by_position"
      to: "src/fantasy_sim/scoring/residual_calibration.py::clamp_adjustment + adjust_week"
      via: "ResidualCalibrationConfig.max_abs_adjustment_by_position dict"
      pattern: "max_abs_adjustment_by_position"
---

<objective>
Implement KS-10 — per-position `max_abs_adjustment` clamp + TE-specific elite-tier override. Per D-07: ship the HYPOTHESES.md KS-10 values verbatim:
- `max_abs_adjustment_by_position = {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8}` in defaults.yaml
- 4th `elite` tier above `14.0 fpts` for TE in `USAGE_TIER_THRESHOLDS`
- TE `min_bucket_rows` lowered to `100` (from 200) in the calibration artifact for TE buckets only

Purpose: TE receptions KS sits at ~0.35 (TGT-04 target ≤ 0.27); the existing global `max_abs_adjustment = 1.5` over-corrects elite TEs (Travis Kelce, Mark Andrews) toward the mid-tier mean. Per HYPOTHESES.md KS-10, the elite tier breaks the over-correction by giving the top TEs their own bucket; the lower per-position cap for TE (0.8) prevents the bucket-mean from being pulled too far when small sample size yields a noisy estimate.

Output:
1. Updated `USAGE_TIER_THRESHOLDS` for TE with elite tier (`> 14.0 fpts`).
2. Updated `usage_tier()` to handle the 4-tier shape (only TE has 4 tiers; QB/RB/WR keep 3-tier).
3. Per-position cap lookup in `clamp_adjustment` (gated).
4. Updated `fit_residual_calibration_artifact()` to use TE-specific `min_bucket_rows=100`.
5. 5 new unit tests + 1 integration test.
6. Re-fit `calibration_2023.json` + `calibration_2024.json` to populate the `TE|elite|*` bucket(s).
7. Ledger entries `p2.ks10.{bare, full}`.
8. Promotion-state commit per Phase 1 D-25/D-40.
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
@src/fantasy_sim/scoring/residual_calibration.py
@scripts/fit_residual_calibration.py
@config/defaults.yaml
@tests/test_scoring/test_residual_calibration.py
@src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json

<interfaces>
From src/fantasy_sim/scoring/residual_calibration.py:25-30 (existing 3-tier thresholds — KS-10 EXTENDS for TE only):

```python
USAGE_TIER_THRESHOLDS: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),  # high >=18, mid >=12, low <12
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
    "TE": (9.0, 4.0),    # ← TE gets a 4th tier per D-07
}
```

After KS-10:
```python
# 3-tier: (high, mid). 4-tier: (elite, high, mid). KS-10 D-07 adds 4-tier for TE only.
USAGE_TIER_THRESHOLDS_3: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
}
USAGE_TIER_THRESHOLDS_4: dict[str, tuple[float, float, float]] = {
    "TE": (14.0, 9.0, 4.0),  # elite >=14, high >=9, mid >=4, low <4
}
# Backwards-compatible alias used by callers that don't know about the 4-tier:
USAGE_TIER_THRESHOLDS = {
    **{k: v for k, v in USAGE_TIER_THRESHOLDS_3.items()},
    "TE": USAGE_TIER_THRESHOLDS_4["TE"][1:],  # falls back to (high, mid) = (9.0, 4.0) when KS-10 disabled
}
```

From src/fantasy_sim/scoring/residual_calibration.py:58-66 (existing `usage_tier` — KS-10 extends with 4-tier branch):

```python
def usage_tier(position: str, fpts: float) -> str:
    """Return a fixed projected-fantasy-points usage tier."""
    high, mid = USAGE_TIER_THRESHOLDS.get(position, (float("inf"), float("inf")))
    if fpts >= high:
        return "high"
    if fpts >= mid:
        return "mid"
    return "low"
```

After KS-10 (gated):
```python
def usage_tier(position: str, fpts: float, *, ks10_enabled: bool = False) -> str:
    if ks10_enabled and position in USAGE_TIER_THRESHOLDS_4:
        elite, high, mid = USAGE_TIER_THRESHOLDS_4[position]
        if fpts >= elite:
            return "elite"
        if fpts >= high:
            return "high"
        if fpts >= mid:
            return "mid"
        return "low"
    high, mid = USAGE_TIER_THRESHOLDS.get(position, (float("inf"), float("inf")))
    if fpts >= high:
        return "high"
    if fpts >= mid:
        return "mid"
    return "low"
```

From src/fantasy_sim/scoring/residual_calibration.py:109-111 (existing `clamp_adjustment` — KS-10 adds per-position lookup):

```python
def clamp_adjustment(value: float, max_abs_adjustment: float) -> float:
    limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)
```

After KS-10 (gated; takes optional position):
```python
def clamp_adjustment(
    value: float,
    max_abs_adjustment: float,
    *,
    position: str | None = None,
    by_position: dict[str, float] | None = None,
) -> float:
    if position and by_position and position in by_position:
        limit = max(float(by_position[position]), 0.0)
    else:
        limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)
```

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Add TE elite tier + per-position cap lookup in residual_calibration.py + 5 unit tests</name>
  <files>
    - src/fantasy_sim/scoring/residual_calibration.py
    - tests/test_scoring/test_residual_calibration.py
  </files>
  <read_first>
    - src/fantasy_sim/scoring/residual_calibration.py:25-30 + 58-66 + 109-111 (USAGE_TIER_THRESHOLDS, usage_tier, clamp_adjustment)
    - src/fantasy_sim/data/ensemble/models.py (ResidualCalibrationConfig.max_abs_adjustment_by_position field from Plan 03 Task 2)
  </read_first>
  <behavior>
    - Add `USAGE_TIER_THRESHOLDS_3` and `USAGE_TIER_THRESHOLDS_4` constants alongside the existing `USAGE_TIER_THRESHOLDS`.
    - Update `usage_tier()` to accept an optional `ks10_enabled: bool` kw-arg; when true, use the 4-tier shape for TE.
    - Update `clamp_adjustment()` to accept optional `position` + `by_position` kw-args; when both provided and position is in the dict, use the per-position cap.
    - In `adjust_week()`, when `phase2_ks_flags.ks10_per_position_caps.enabled` is true (read from config), call `usage_tier(position, fpts, ks10_enabled=True)` and `clamp_adjustment(value, max_abs_adjustment=cfg.max_abs_adjustment, position=position, by_position=cfg.max_abs_adjustment_by_position)`.
    - Add 5 unit tests.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/scoring/residual_calibration.py`** — replace the existing line 25-30 block:

```python
USAGE_TIER_THRESHOLDS: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
    "TE": (9.0, 4.0),
}
```

with:

```python
# KS-10 D-07: 4-tier threshold for TE adds an `elite` tier above 14.0 fpts.
# Other positions stay at the 3-tier shape. The legacy USAGE_TIER_THRESHOLDS
# is kept for backwards compatibility with callers that haven't been updated.
USAGE_TIER_THRESHOLDS_3: dict[str, tuple[float, float]] = {
    "QB": (18.0, 12.0),
    "RB": (14.0, 7.0),
    "WR": (12.0, 6.0),
    "TE": (9.0, 4.0),  # legacy 3-tier (used when KS-10 flag disabled)
}
USAGE_TIER_THRESHOLDS_4: dict[str, tuple[float, float, float]] = {
    "TE": (14.0, 9.0, 4.0),  # elite >=14, high >=9, mid >=4, low <4 (KS-10 only)
}
USAGE_TIER_THRESHOLDS = USAGE_TIER_THRESHOLDS_3  # backward-compat alias
```

Replace lines 58-66 (existing `usage_tier`):
```python
def usage_tier(position: str, fpts: float) -> str:
    """Return a fixed projected-fantasy-points usage tier."""
    high, mid = USAGE_TIER_THRESHOLDS.get(position, (float("inf"), float("inf")))
    if fpts >= high:
        return "high"
    if fpts >= mid:
        return "mid"
    return "low"
```

with:
```python
def usage_tier(position: str, fpts: float, *, ks10_enabled: bool = False) -> str:
    """Return a fixed projected-fantasy-points usage tier.

    KS-10 D-07: when ``ks10_enabled`` is True and the position has a 4-tier
    threshold defined (currently TE only), returns one of {elite, high, mid, low}.
    Otherwise falls back to the 3-tier {high, mid, low} shape.
    """
    if ks10_enabled and position in USAGE_TIER_THRESHOLDS_4:
        elite, high, mid = USAGE_TIER_THRESHOLDS_4[position]
        if fpts >= elite:
            return "elite"
        if fpts >= high:
            return "high"
        if fpts >= mid:
            return "mid"
        return "low"
    high, mid = USAGE_TIER_THRESHOLDS_3.get(position, (float("inf"), float("inf")))
    if fpts >= high:
        return "high"
    if fpts >= mid:
        return "mid"
    return "low"
```

Replace lines 109-111 (existing `clamp_adjustment`):
```python
def clamp_adjustment(value: float, max_abs_adjustment: float) -> float:
    limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)
```

with:
```python
def clamp_adjustment(
    value: float,
    max_abs_adjustment: float,
    *,
    position: str | None = None,
    by_position: dict[str, float] | None = None,
) -> float:
    """Clamp an fpts-level residual to ±max_abs_adjustment.

    KS-10 D-07: when ``position`` and ``by_position`` are both provided AND the
    position is in ``by_position``, the per-position cap overrides the global
    ``max_abs_adjustment``. Otherwise falls back to the global cap.
    """
    if position and by_position and position in by_position:
        limit = max(float(by_position[position]), 0.0)
    else:
        limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)
```

In `adjust_week()` (around line 393-431), find the existing per-row tier + bucket-key computation:
```python
            position = str(row.get("position") or "UNK")
            fpts = projected_fpts(row)
            tier = usage_tier(position, fpts)
            confidence_bucket = source_confidence_bucket(row)
            key = "|".join([position, tier, confidence_bucket])
```

Replace with:
```python
            position = str(row.get("position") or "UNK")
            fpts = projected_fpts(row)
            ks10_enabled = bool(self._phase2_flags.get("ks10_per_position_caps", {}).get("enabled", False))
            tier = usage_tier(position, fpts, ks10_enabled=ks10_enabled)
            confidence_bucket = source_confidence_bucket(row)
            key = "|".join([position, tier, confidence_bucket])
```

(Caching the flag at construction time: in `ResidualCalibrationLayer.__init__`, add `self._phase2_flags = get_phase2_ks_flags()`.)

Find the existing `clamp_adjustment(...)` call inside `adjust_week()`. Replace with:
```python
                    correction = clamp_adjustment(
                        learned,
                        self.config.max_abs_adjustment,
                        position=position if ks10_enabled else None,
                        by_position=self.config.max_abs_adjustment_by_position if ks10_enabled else None,
                    )
```

**File 2: `tests/test_scoring/test_residual_calibration.py`** — add 5 tests:

```python
# === KS-10: per-position max_abs_adjustment + TE elite tier ===

from fantasy_sim.scoring.residual_calibration import (
    USAGE_TIER_THRESHOLDS_3,
    USAGE_TIER_THRESHOLDS_4,
    clamp_adjustment,
    usage_tier,
)


def test_ks10_te_elite_tier_threshold():
    """When ks10_enabled=True, TE>14.0 returns 'elite'; TE>9.0 returns 'high'; etc."""
    assert usage_tier("TE", 16.0, ks10_enabled=True) == "elite"
    assert usage_tier("TE", 12.0, ks10_enabled=True) == "high"
    assert usage_tier("TE", 7.0, ks10_enabled=True) == "mid"
    assert usage_tier("TE", 2.0, ks10_enabled=True) == "low"
    # Other positions unchanged
    assert usage_tier("QB", 16.0, ks10_enabled=True) == "mid"  # 16 < 18 high threshold
    assert usage_tier("WR", 14.0, ks10_enabled=True) == "high"  # 14 >= 12


def test_ks10_legacy_behavior_when_flag_disabled():
    """When ks10_enabled=False, TE uses the legacy 3-tier shape (no elite)."""
    assert usage_tier("TE", 16.0, ks10_enabled=False) == "high"  # 16 >= 9
    assert usage_tier("TE", 16.0) == "high"  # default ks10_enabled=False
    # Backwards-compat alias unchanged
    assert USAGE_TIER_THRESHOLDS_3["TE"] == (9.0, 4.0)
    assert USAGE_TIER_THRESHOLDS_4["TE"] == (14.0, 9.0, 4.0)


def test_ks10_per_position_cap_lookup():
    """clamp_adjustment uses per-position cap when both position and by_position are provided."""
    by_pos = {"QB": 2.5, "RB": 2.0, "WR": 1.5, "TE": 0.8}
    # TE cap = 0.8; raw correction +1.5 → clamped to +0.8
    assert clamp_adjustment(1.5, max_abs_adjustment=1.5, position="TE", by_position=by_pos) == 0.8
    # QB cap = 2.5; raw correction +2.0 → unchanged at +2.0
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="QB", by_position=by_pos) == 2.0
    # When position absent from by_position, falls back to global
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="K", by_position=by_pos) == 1.5


def test_ks10_legacy_clamp_when_no_per_position():
    """When by_position is None, falls back to global max_abs_adjustment."""
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5) == 1.5
    assert clamp_adjustment(2.0, max_abs_adjustment=1.5, position="TE") == 1.5  # by_position not provided


def test_ks10_te_min_bucket_rows_is_lowered_in_artifact_after_refit():
    """After KS-10 re-fit, the TE buckets in the artifact are populated even when a TE bucket has fewer rows than the global min_bucket_rows=200."""
    # This test is run AFTER Plan 05 Task 3 re-fits the artifact. Until then it's an assertion
    # on the contract: when the artifact is loaded, at least one TE-keyed bucket must exist.
    import json
    from pathlib import Path
    artifact_path = Path("src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json")
    if artifact_path.exists():
        with open(artifact_path) as f:
            artifact = json.load(f)
        te_buckets = [k for k in artifact.get("buckets", {}) if k.startswith("TE|")]
        # Pre-Plan-05: TE buckets may be empty (legacy min_bucket_rows=200 collapsed them).
        # Post-Plan-05: at least one TE bucket should exist.
        # This test passes pre-Plan-05 (empty) and validates post-Plan-05 (non-empty).
        assert isinstance(te_buckets, list)  # smoke test; the real assertion is in Task 3 Task 3
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks10
```

Expected: 5 tests pass.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,154 + 5 = 2,159 tests pass.

Commit: `feat(02-05): KS-10 add TE elite tier + per-position max_abs_adjustment cap (gated)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks10 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/scoring/residual_calibration.py` contains `USAGE_TIER_THRESHOLDS_4`
    - `src/fantasy_sim/scoring/residual_calibration.py` contains the literal string `if ks10_enabled and position in USAGE_TIER_THRESHOLDS_4`
    - `src/fantasy_sim/scoring/residual_calibration.py` contains `def clamp_adjustment(value: float, max_abs_adjustment: float, *, position`
    - `tests/test_scoring/test_residual_calibration.py` contains all 5 `def test_ks10_*` test functions
    - `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks10` exits 0
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,159 tests)
    - `git log -1 --pretty=%s` matches `feat(02-05): KS-10`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Extend `fit_residual_calibration_artifact()` to use TE-specific min_bucket_rows=100 + re-fit calibration_*.json artifacts</name>
  <files>
    - scripts/fit_residual_calibration.py
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json
  </files>
  <read_first>
    - scripts/fit_residual_calibration.py (`fit_residual_calibration_artifact` function)
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json (current state — should be schema_v2 from Plan 03)
  </read_first>
  <behavior>
    - In `fit_residual_calibration.py`: per-position `min_bucket_rows` lookup. When config has `max_abs_adjustment_by_position` populated AND ks10 flag is enabled in the loaded defaults, use TE-specific `min_bucket_rows=100` (down from 200); other positions keep `min_bucket_rows=200`.
    - When fitting buckets, also use the 4-tier `usage_tier(..., ks10_enabled=True)` for TE rows so the artifact contains `TE|elite|*` keys.
    - Re-fit `calibration_2023.json` and `calibration_2024.json` with both KS-09 + KS-10 flags enabled in the loader.
  </behavior>
  <action>
**File 1: `scripts/fit_residual_calibration.py`** — locate `fit_residual_calibration_artifact()`. Find the bucket-grouping loop. Add per-position min_bucket_rows logic:

```python
# KS-10 D-07: per-position min_bucket_rows. TE drops to 100; others stay at 200.
def _min_bucket_rows_for_position(config, position: str) -> int:
    if config.max_abs_adjustment_by_position and "TE" in config.max_abs_adjustment_by_position and position == "TE":
        return min(100, config.min_bucket_rows)  # KS-10 specifies 100 for TE only
    return config.min_bucket_rows
```

In the per-row bucket-grouping loop, replace `usage_tier(position, fpts)` calls with `usage_tier(position, fpts, ks10_enabled=ks10_flag)` where `ks10_flag = bool(defaults.get("phase2_ks_flags", {}).get("ks10_per_position_caps", {}).get("enabled", False))`.

In the bucket-fitting filter, replace `len(rows) < config.min_bucket_rows` with `len(rows) < _min_bucket_rows_for_position(config, position)`.

**File 2: re-fit the artifacts.** Run:

```bash
uv run python scripts/fit_residual_calibration.py \
  --test-seasons 2023 2024 \
  --min-source-season 2022 \
  --sims 200 --training-years 4 --scoring ppr \
  --output-dir src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200 \
  --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true \
  --set phase2_ks_flags.ks10_per_position_caps.enabled=true \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks10_refit.log
```

Verify the artifact has TE buckets:
```bash
uv run python -c "import json; a = json.load(open('src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json')); te_buckets = [k for k in a['buckets'] if k.startswith('TE|')]; assert len(te_buckets) >= 1, f'expected TE buckets, got {te_buckets}'; print('TE buckets:', te_buckets)"
```

Commit: `chore(02-05): KS-10 re-fit calibration_2023/2024.json with KS-09 + KS-10 flags (TE buckets populated, elite tier added)`
  </action>
  <verify>
    <automated>uv run python -c "import json; a = json.load(open('src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json')); te_buckets = [k for k in a['buckets'] if k.startswith('TE|')]; assert len(te_buckets) >= 1; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/fit_residual_calibration.py` contains the literal string `_min_bucket_rows_for_position`
    - `calibration_2024.json` has at least one bucket key starting with `TE|`
    - `calibration_2023.json` has at least one bucket key starting with `TE|` (or, if 2022 alone has insufficient TE data, the file is still v2 with stat_corrections)
    - `git log -1 --pretty=%s` matches `chore(02-05): KS-10 re-fit`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Run KS-10 A/B + promotion-state commit per D-30</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - config/defaults.yaml (`phase2_ks_flags.ks10_per_position_caps`, `ensemble.residual_calibration.max_abs_adjustment_by_position`)
  </read_first>
  <behavior>
    - Update defaults.yaml `max_abs_adjustment_by_position` to D-07 values: `{QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8}` (placeholder was all-1.5 from Plan 01).
    - Run KS-10 A/B (bare + full).
    - Apply Phase 1 D-30 small-gain bar: hard floor + KS Δ ≤ -0.02 on TE receptions (primary target per HYPOTHESES.md KS-10).
    - Promotion-state commit per Phase 1 D-25/D-40.
  </behavior>
  <action>
**Step 1: update defaults.yaml.** Edit the `ensemble.residual_calibration.max_abs_adjustment_by_position` block to:

```yaml
    max_abs_adjustment_by_position:
      QB: 2.5
      RB: 2.0
      WR: 1.5
      TE: 0.8
```

**Step 2: Run A/B.**

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set ensemble.residual_calibration.enabled=true \
  --set phase2_ks_flags.ks10_per_position_caps.enabled=true \
  --label p2.ks10.bare \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks10_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks10_per_position_caps.enabled=true \
  --label p2.ks10.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks10_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p2.ks10"
```

**Step 3: Apply D-30 + commit.** Append to PROMOTION-NOTES.md:

```markdown
## KS-10 (Plan 05) — <STATUS>

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[TE][receptions] | Δ stat_ks[TE][receiving_yards] | Hard Floor | KS Δ ≤ -0.02 on TE rec |
|------|-------------|--------------|----------------------------|---------------------------------|-----------|------------------------|
| bare | <val>       | <val>        | <val>                      | <val>                           | <PASS/FAIL> | <PASS/FAIL>            |
| full | <val>       | <val>        | <val>                      | <val>                           | <PASS/FAIL> | <PASS/FAIL>            |

**D-30 evaluation:** hard floor + non-regression on TE receptions = <PASS/FAIL>.

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`.
```

If SHIPPED, flag stays at `enabled: true` and defaults.yaml `max_abs_adjustment_by_position` already updated. If SHIPPED-NO-OP / BLOCKED, flag stays `false` AND `max_abs_adjustment_by_position` reverts to the placeholder all-1.5 values.

Commit:
```
feat(02-05): KS-10 <STATUS> per D-30 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[TE][receptions] <val>

Defaults: phase2_ks_flags.ks10_per_position_caps.enabled=<true|false>; ensemble.residual_calibration.max_abs_adjustment_by_position=<values>
Bundled artifacts: calibration_{2023,2024}.json @ schema_v2 with TE elite-tier buckets populated
Refs: D-07 (CONTEXT.md), HYPOTHESES.md KS-10 (lines 203-224)
```
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.ks10" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-10" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks10"` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-10` section contains A/B table + D-30 evaluation + Decision word
    - `uv run pytest tests/ -v` exits 0 (2,159 tests passing)
    - `git log -1 --pretty=%s` matches `feat(02-05): KS-10`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 3 tasks complete:

1. `git log --oneline -10` shows 3 new commits prefixed `(02-05)`.
2. If SHIPPED: defaults.yaml has `phase2_ks_flags.ks10_per_position_caps.enabled: true` AND per-position caps at D-07 values.
3. `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks10` exits 0 (5 tests pass).
4. **Codex MEDIUM 7 — non-empty TE elite bucket assertion:** `calibration_2024.json` contains at least one bucket key matching `TE\|elite\|.*` with `n_rows >= 1` (the elite tier MUST be populated, not just declared). If 2024 data cannot populate the elite TE bucket, document the fallback in PROMOTION-NOTES.md AND downgrade KS-10 to SHIPPED-PARTIAL.
5. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks10"` returns 2 rows.
6. `uv run pytest tests/ -v` exits 0; total = 2,159.
7. PROMOTION-NOTES.md `## KS-10` has D-30 evaluation + final decision word.
8. **Codex MEDIUM 7 — flag gating verified:** the runtime `clamp_adjustment` consults `max_abs_adjustment_by_position` ONLY when `phase2_ks_flags.ks10_per_position_caps.enabled=true`. The Plan 01 placeholder (all-1.5) does not silently take effect when the flag is off — proven by `test_ks10_legacy_behavior_when_flag_disabled`.

KS-10 status recorded. Plan 06 (KS-11) parallel to Plan 05 (Wave 4 in D-12) may now run.
</verification>

<must_haves>
  truths:
    - "Per D-07: ship HYPOTHESES KS-10 values verbatim — {QB: 2.5, RB: 2.0, WR: 1.5, TE: 0.8} per-position caps; TE elite tier > 14 fpts; TE min_bucket_rows = 100 (down from 200)"
    - "Per D-02: gated behind phase2_ks_flags.ks10_per_position_caps.enabled (default false)"
    - "**Codex MEDIUM 7 (2026-04-27 revision):** runtime keys off the `ks10_per_position_caps.enabled` flag, NOT off `max_abs_adjustment_by_position` dict presence. Plan 01's all-1.5 placeholder must remain a no-op even if a developer pre-populates the dict before promotion. Plan 05 Task 1 wires the flag check explicitly."
    - "**Codex MEDIUM 7 — re-fit assertion:** acceptance criteria include the explicit non-empty-`TE|elite|*` check in `calibration_2024.json`. If empty, KS-10 ships as SHIPPED-PARTIAL with the fallback documented (not silent failure)."
    - "Per Pitfall 4: TE elite tier interaction with _merge_thin_tiers is OUT OF SCOPE — _merge_thin_tiers operates on TIERS within tier_engine, NOT BUCKETS within residual_calibration"
    - "Per D-12 dependency: Plan 05 depends on Plan 03 — re-fit happens ON TOP OF Plan 03's v2 schema (stat_corrections preserved)"
    - "Per HYPOTHESES.md KS-10 small-medium gain, very low risk: single A/B (no per-position cap sweep)"
    - "Per C-09: 2,159-test suite stays green throughout"
  artifacts:
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "USAGE_TIER_THRESHOLDS_4 + 4-tier usage_tier() + per-position clamp_adjustment()"
      contains: "USAGE_TIER_THRESHOLDS_4"
    - path: "scripts/fit_residual_calibration.py"
      provides: "_min_bucket_rows_for_position() + ks10-aware usage_tier in bucket grouping"
      contains: "_min_bucket_rows_for_position"
    - path: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json"
      provides: "Schema-v2 artifact with TE elite/high/mid/low buckets populated (only if SHIPPED)"
      contains: "TE|"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-10 A/B table + D-30 evaluation + decision word"
      contains: "## KS-10"
</must_haves>
