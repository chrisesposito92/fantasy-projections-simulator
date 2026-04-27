---
phase: 02-structural-per-stat-calibration
plan: 03
type: tdd
wave: 2
depends_on: ["01", "02"]
files_modified:
  - src/fantasy_sim/scoring/residual_calibration.py
  - scripts/fit_residual_calibration.py
  - config/defaults.yaml
  - tests/test_scoring/test_residual_calibration.py
  - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json
  - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-09]
must_haves:
  truths:
    - "Per D-01 (two-stage layered fpts) + Pitfall 1 in 02-RESEARCH.md: per-stat correction writes NEW columns `corrected_<stat>` (e.g. `corrected_pass_yards`, `corrected_receiving_yards`) BEFORE the existing `row[\"fpts\"]` write at `residual_calibration.py:422`. The `fpts` field continues to use the existing fpts-level correction (unchanged). Per-stat and fpts corrections may diverge (e.g., `corrected_pass_yards * 0.04 != corrected fpts contribution`). Documented and not chased in v1."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled` (default false). When the flag is false, `adjust_week()` behaves byte-identically to pre-Plan-03; when true, it ALSO writes per-stat corrected columns. Promotion commit per D-12 + Phase 1 D-25 flips default to true; rollback = flip flag back to false; existing fpts-level calibration continues to work."
    - "Per D-03: stat coverage = 14 scoring-impacting stats per CONTEXT.md `<decisions>` D-03 (QB: pass_yards, pass_tds, interceptions, rush_yards, rush_tds, fumbles_lost; RB: rush_yards, rush_tds, receiving_yards, receptions, fumbles_lost; WR/TE: receiving_yards, receptions, receiving_tds, fumbles_lost). The list lives in `config/defaults.yaml` under `ensemble.residual_calibration.stat_level.covered_stats` (already populated at Plan 01)."
    - "Per D-04 + Pattern 4 in 02-RESEARCH.md: per-row clamp = std-scaled at `±2 * sqrt(actual_var)` where `actual_var` is computed from the training-season hold-out distribution per `(position, usage_tier, stat)` bucket. Stored per-bucket in `stat_corrections.{stat}.clamps[bucket_key].clamp_std` in the calibration artifact. Adapts to stat scale (QB pass_yards std ~80 vs WR receptions std ~2)."
    - "Per Plan 01 Task 3: artifact schema_version = 2 already supported by the runtime loader; v1 artifacts continue to load (loader supplies an empty `stat_corrections: {}` block). Plan 03 produces v2 artifacts with non-empty `stat_corrections` populated."
    - "Per D-14 (KS-09 elevated promotion bar): SHIPPED requires hard floor + KS Δ ≤ -0.03 on QB pass_yards + QB pass_yards mean bias `|Δ| ≤ 5 yd/g`. SHIPPED-PARTIAL = hard floor + KS Δ pass but bias `|Δ| > 5 yd/g` (architecture stays for Phase 3/4 levers to layer on top); flag flips to true and the residual gap is documented in PROMOTION-NOTES.md. BLOCKED = hard floor regresses; flag stays false."
    - "Per Phase 1 D-46 / 02-VALIDATION.md: KS-09 success measured via `SeasonMetrics.stat_mean_bias[\"QB\"][\"pass_yards\"][\"arm_b_bias\"]` and `SeasonMetrics.stat_ks[\"QB\"][\"pass_yards\"][\"arm_b\"]` from the persisted ledger entry `p2.ks09.full`. Direct ledger-read; no side script needed."
    - "Per C-08: TDD-first for KS-09 (8 unit tests for: per-stat correction writes new columns, fpts unchanged when flag off, fpts unchanged when flag on (D-01 two-stage), std-scaled clamp applies, missing-bucket fallback returns 0 correction, schema-v2 artifact has stat_corrections, training-script writes per-stat block, integration test that corrected_<stat> != raw <stat> for non-fallback rows)."
    - "Per C-09: 2,142 + 8 (Plan 03 Task 1) = 2,150 tests stay green after this plan."
    - "Per Pitfall 3: re-fit `decision_s200/calibration_2023.json` and `calibration_2024.json` MUST honor the holdout discipline. Training data for `calibration_2024.json` = seasons [2022..2023]; for `calibration_2023.json` = season [2022]. Never include the test season in the training set."
  artifacts:
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "New helper `stat_clamp_adjustment(value, clamp_std)`; new helper `_per_stat_corrections(...)` reads the v2 artifact's stat_corrections block; `adjust_week()` writes `corrected_<stat>` columns BEFORE the existing `row[\"fpts\"]` write at line 422 when flag is enabled; ARTIFACT_SCHEMA_VERSION already at 2 from Plan 01"
      contains: "def stat_clamp_adjustment"
    - path: "scripts/fit_residual_calibration.py"
      provides: "Extended `fit_residual_calibration_artifact(...)` to ALSO compute per-stat corrections + per-bucket clamp_std when `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled` is true in the loaded defaults; writes `stat_corrections` block + bumps artifact schema_version to 2"
      contains: "stat_corrections"
    - path: "config/defaults.yaml"
      provides: "`phase2_ks_flags.ks09_per_stat_residual_calibration.enabled = true` (after promotion); existing `ensemble.residual_calibration.stat_level.covered_stats` list (from Plan 01) is the authoritative coverage list"
      contains: "ks09_per_stat_residual_calibration:"
    - path: "tests/test_scoring/test_residual_calibration.py"
      provides: "8 new tests: ks09_writes_corrected_columns_when_enabled, ks09_fpts_unchanged_when_disabled, ks09_fpts_unchanged_when_enabled (D-01), ks09_std_clamp_applied, ks09_missing_bucket_fallback_zero, ks09_schema_v2_artifact_has_stat_corrections, ks09_training_script_writes_per_stat_block, ks09_corrected_differs_from_raw_for_non_fallback_rows"
      contains: "def test_ks09_"
    - path: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json"
      provides: "Re-fit artifact at schema_version: 2 with new top-level `stat_corrections` block populated for the 14 covered stats × N buckets each"
      contains: "stat_corrections"
    - path: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json"
      provides: "Re-fit artifact at schema_version: 2 with stat_corrections (training data = season [2022])"
      contains: "stat_corrections"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-09 promotion-state decision summary including D-14 elevated promotion bar evaluation (3 conditions stacked: hard floor + KS Δ ≤ -0.03 on QB pass_yards + bias |Δ| ≤ 5 yd/g)"
      contains: "## KS-09"
  key_links:
    - from: "config/defaults.yaml::phase2_ks_flags.ks09_per_stat_residual_calibration"
      to: "src/fantasy_sim/scoring/residual_calibration.py::adjust_week"
      via: "ResidualCalibrationConfig.stat_level.enabled"
      pattern: "stat_level\\.enabled"
    - from: "src/fantasy_sim/scoring/residual_calibration.py::adjust_week"
      to: "the new corrected_<stat> writes"
      via: "for stat in self.config.stat_level.covered_stats: row[f\"corrected_{stat}\"] = ..."
      pattern: "corrected_"
    - from: "scripts/fit_residual_calibration.py::fit_residual_calibration_artifact"
      to: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_*.json"
      via: "stat_corrections.{stat}.{corrections, clamps} block"
      pattern: "stat_corrections"
---

<objective>
Implement KS-09 — extend `residual_calibration` from fpts-only to per-stat correction. Per D-01: the per-stat correction writes NEW `corrected_<stat>` columns BEFORE the existing fpts write; the existing fpts-level correction continues to operate on raw `fpts` (unchanged). Per D-03: 14 scoring-impacting stats are covered (QB, RB, WR, TE). Per D-04: per-row clamp = std-scaled at `±2 * sqrt(actual_var)` from training-season hold-out distribution per `(position, usage_tier, stat)` bucket.

Purpose: Phase 1's aggregate validation (`p1.aggregate.full` #105) showed QB pass_yards mean bias REGRESSED to -39.29 yd/g (target ±5 per TGT-09); this is the headline Phase 1 miss. KS-09 is the architectural lever — without per-stat correction, there is no remediation path for stat-level KS regressions or stat-level mean bias. The two-stage layered approach (D-01) keeps the change rollback-safe: corrected stat columns are NEW (additive) and the existing fpts-level correction is unchanged.

Output:
1. New helper `stat_clamp_adjustment(value, clamp_std)` and `_per_stat_corrections(...)` in `residual_calibration.py`.
2. Extended `adjust_week()` writes `corrected_<stat>` columns BEFORE the existing `row["fpts"]` write at line 422 (gated behind `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled`).
3. Extended `scripts/fit_residual_calibration.py` to fit per-stat corrections + per-bucket clamp_std and write `stat_corrections` block to v2 artifacts.
4. 8 new unit tests (TDD-first per C-08).
5. Re-fit `calibration_2023.json` + `calibration_2024.json` at schema_version: 2 with `stat_corrections` populated.
6. Ledger entries `p2.ks09.bare` + `p2.ks09.full` evaluated against D-14 elevated promotion bar.
7. Promotion-state commit per Phase 1 D-25/D-40 with status word: SHIPPED / SHIPPED-PARTIAL / BLOCKED.
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
@.planning/phases/02-structural-per-stat-calibration/01-phase2-scaffolding-and-entry-baseline-PLAN.md
@.planning/phases/02-structural-per-stat-calibration/02-ks08-dynamic-blend-simulator-floor-PLAN.md
@src/fantasy_sim/scoring/residual_calibration.py
@scripts/fit_residual_calibration.py
@config/defaults.yaml
@tests/test_scoring/test_residual_calibration.py
@src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json

<interfaces>
From src/fantasy_sim/scoring/residual_calibration.py:97-111 (existing fpts bucket-keying — KS-09 reuses):

```python
def bucket_key_for_projection(row: Mapping[str, object]) -> str:
    position = str(row.get("position") or "UNK")
    fpts = projected_fpts(row)
    return "|".join([
        position,
        usage_tier(position, fpts),
        source_confidence_bucket(row),
    ])

def clamp_adjustment(value: float, max_abs_adjustment: float) -> float:
    limit = max(float(max_abs_adjustment), 0.0)
    return min(max(float(value), -limit), limit)
```

From src/fantasy_sim/scoring/residual_calibration.py:367-431 (the existing `adjust_week` — KS-09 EXTENDS BEFORE the `row["fpts"]` write at line 422):

```python
def adjust_week(self, projections, *, season, week):
    # ... existing setup
    for projection in projections:
        row = dict(projection)
        # ... existing fpts-level correction logic
        # *** KS-09 INSERTS PER-STAT CORRECTIONS HERE (BEFORE the row["fpts"] write) ***
        row["fpts"] = round(max(fpts + correction, 0.0), 1)  # Line 422 — UNCHANGED
        self._stamp_metadata(...)
```

From src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json (schema v1 sample to extend):

```json
{
  "schema_version": 1,
  "test_season": 2024,
  "source_seasons": [2022, 2023],
  "sims": 200,
  "scoring": "ppr",
  "positions": ["QB", "RB", "WR", "TE"],
  "min_bucket_rows": 200,
  "min_bucket_weeks": 6,
  "shrinkage_prior_rows": 200,
  "max_abs_adjustment": 1.5,
  "min_training_mae_delta": -0.01,
  "fallback": "zero",
  "usage_tier_thresholds": {"QB": {"high": 18.0, "mid": 12.0}, ...},
  "buckets": {
    "QB|low|simulator_only": {"correction": -0.5, "n_rows": 250, ...},
    "QB|mid|simulator_only": {"correction": -0.3, "n_rows": 180, ...}
  }
}
```

KS-09 v2 schema adds a new top-level `stat_corrections` block alongside the existing `buckets` block:

```json
{
  ...existing v1 fields...,
  "schema_version": 2,
  "stat_corrections": {
    "pass_yards": {
      "corrections": {
        "QB|low|simulator_only": {"correction": -2.5, "n_rows": 250},
        "QB|mid|simulator_only": {"correction": -1.8, "n_rows": 180},
        "QB|high|simulator_only": {"correction": -0.9, "n_rows": 150}
      },
      "clamps": {
        "QB|low|simulator_only": {"clamp_std": 45.2},
        "QB|mid|simulator_only": {"clamp_std": 52.7},
        "QB|high|simulator_only": {"clamp_std": 65.3}
      }
    },
    "receiving_yards": {
      "corrections": {"WR|low|simulator_only": {...}, ...},
      "clamps": {"WR|low|simulator_only": {...}, ...}
    },
    ... 12 more stats
  }
}
```

From src/fantasy_sim/data/ensemble/models.py (ResidualCalibrationConfig — verify it has a stat_level sub-config; if not, add):

```python
@dataclass(frozen=True)
class StatLevelConfig:
    enabled: bool = False
    covered_stats: tuple[str, ...] = ()  # populated from defaults.yaml ensemble.residual_calibration.stat_level.covered_stats

@dataclass(frozen=True)
class ResidualCalibrationConfig:
    enabled: bool = False
    artifacts_dir: Path | None = None
    positions: tuple[str, ...] = ()
    min_bucket_rows: int = 200
    min_bucket_weeks: int = 6
    shrinkage_prior_rows: int = 200
    max_abs_adjustment: float = 1.5
    min_training_mae_delta: float = -0.01
    fallback: str = "zero"
    stat_level: StatLevelConfig = field(default_factory=StatLevelConfig)  # NEW for KS-09 — Plan 03
    max_abs_adjustment_by_position: dict[str, float] = field(default_factory=dict)  # NEW for KS-10 — Plan 05 (placeholder; Plan 03 not used)
```

</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write 8 failing tests for KS-09 per-stat correction + std-scaled clamp + schema-v2 artifact + training-script per-stat block</name>
  <files>tests/test_scoring/test_residual_calibration.py</files>
  <read_first>
    - tests/test_scoring/test_residual_calibration.py (existing test conventions: imports, fixture names, projection-row construction)
    - src/fantasy_sim/scoring/residual_calibration.py (current `adjust_week`, `clamp_adjustment`, `bucket_key_for_projection`)
    - .planning/research/HYPOTHESES.md lines 189-201 (KS-09 mechanism description)
    - .planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md (D-03 stat coverage list, D-04 std-scaled clamp formula, D-14 promotion bar)
  </read_first>
  <behavior>
    - Test 1 (`test_ks09_writes_corrected_columns_when_enabled`): with `stat_level.enabled=True` and a non-empty `stat_corrections` block in the test artifact, `adjust_week(...)` adds `corrected_pass_yards`, `corrected_receiving_yards`, etc. to each row. The 14 covered stats per D-03 are all written.
    - Test 2 (`test_ks09_fpts_unchanged_when_flag_disabled`): with `stat_level.enabled=False`, `adjust_week(...)` produces byte-identical output to pre-Plan-03 (legacy behavior; only `fpts` is corrected; no `corrected_<stat>` columns appear).
    - Test 3 (`test_ks09_two_stage_layered_fpts_unchanged_with_flag_enabled`): with `stat_level.enabled=True`, the `row["fpts"]` field is COMPUTED FROM raw_sim_fpts + existing fpts-level correction (UNCHANGED from D-01). The new `corrected_<stat>` columns are ADDITIVE; they do NOT propagate into the fpts via the scoring formula.
    - Test 4 (`test_ks09_std_scaled_clamp_applies`): for a bucket with `clamp_std=10.0`, a raw correction of `+25.0` is clamped to `+20.0` (= 2 * 10.0); a raw correction of `-15.0` stays at `-15.0` (within ±20.0).
    - Test 5 (`test_ks09_missing_bucket_fallback_zero`): for a row whose bucket_key is NOT in the artifact's `stat_corrections.{stat}.corrections`, the corrected_<stat> column equals the raw <stat> (no correction applied; falls back to zero adjustment).
    - Test 6 (`test_ks09_schema_v2_artifact_has_stat_corrections`): after Plan 01, `ARTIFACT_SCHEMA_VERSIONS_SUPPORTED == (1, 2)`. A v2 artifact constructed with a `stat_corrections` block loads, exposes the block, and is consumed by `adjust_week`.
    - Test 7 (`test_ks09_training_script_writes_per_stat_block`): unit test on `fit_residual_calibration_artifact(...)` with `stat_level_enabled=True` + `covered_stats=("pass_yards", "receiving_yards", ...)`; the returned dict has `stat_corrections.pass_yards.corrections` and `stat_corrections.pass_yards.clamps` populated for at least one bucket.
    - Test 8 (`test_ks09_corrected_differs_from_raw_for_non_fallback_rows`): integration test with `stat_level.enabled=True` and a populated `stat_corrections` block; for at least one row, `row["corrected_pass_yards"] != row["pass_yards"]` (proves per-stat correction is firing, not silent-fallthrough).
  </behavior>
  <action>
Add to `tests/test_scoring/test_residual_calibration.py` in a new section near the end of the file titled `# === KS-09: per-stat residual_calibration ===`. Use existing patterns:

```python
# === KS-09: per-stat residual_calibration ===

import json
import math
from pathlib import Path
import numpy as np
import pytest
from fantasy_sim.data.ensemble.models import ResidualCalibrationConfig, StatLevelConfig
from fantasy_sim.scoring.residual_calibration import (
    ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_SCHEMA_VERSIONS_SUPPORTED,
    ResidualCalibrationLayer,
    bucket_key_for_projection,
    stat_clamp_adjustment,  # NEW helper from Task 2 — RED until then
)


def _build_v2_artifact_for_tests():
    """Construct a minimal schema-v2 artifact with stat_corrections for KS-09 testing."""
    return {
        "schema_version": 2,
        "test_season": 2024,
        "source_seasons": [2022, 2023],
        "sims": 200,
        "scoring": "ppr",
        "positions": ["QB", "RB", "WR", "TE"],
        "min_bucket_rows": 200,
        "min_bucket_weeks": 6,
        "shrinkage_prior_rows": 200,
        "max_abs_adjustment": 1.5,
        "min_training_mae_delta": -0.01,
        "fallback": "zero",
        "usage_tier_thresholds": {
            "QB": {"high": 18.0, "mid": 12.0},
            "RB": {"high": 14.0, "mid": 7.0},
            "WR": {"high": 12.0, "mid": 6.0},
            "TE": {"high": 9.0, "mid": 4.0},
        },
        "buckets": {
            "QB|low|simulator_only": {"correction": -0.5, "n_rows": 250, "n_weeks": 8},
        },
        "stat_corrections": {
            "pass_yards": {
                "corrections": {
                    "QB|low|simulator_only": {"correction": -10.0, "n_rows": 250},
                    "QB|mid|simulator_only": {"correction": -8.0, "n_rows": 180},
                },
                "clamps": {
                    "QB|low|simulator_only": {"clamp_std": 50.0},
                    "QB|mid|simulator_only": {"clamp_std": 60.0},
                },
            },
            "receiving_yards": {
                "corrections": {
                    "WR|low|simulator_only": {"correction": 4.0, "n_rows": 220},
                },
                "clamps": {
                    "WR|low|simulator_only": {"clamp_std": 30.0},
                },
            },
        },
    }


def _build_qb_row(fpts: float = 16.0, pass_yards: float = 240.0):
    return {
        "player_id": "00-0036971",
        "name": "Test QB",
        "position": "QB",
        "team": "KC",
        "fpts": fpts,
        "pass_yards": pass_yards,
        "pass_tds": 1.5,
        "interceptions": 0.6,
        "rush_yards": 12.0,
        "rush_tds": 0.1,
        "fumbles_lost": 0.05,
        "dynamic_blend_source_mask": "simulator",
    }


def _build_wr_row(fpts: float = 8.0, receiving_yards: float = 70.0):
    return {
        "player_id": "00-0036900",
        "name": "Test WR",
        "position": "WR",
        "team": "KC",
        "fpts": fpts,
        "receiving_yards": receiving_yards,
        "receptions": 5.0,
        "receiving_tds": 0.4,
        "fumbles_lost": 0.02,
        "dynamic_blend_source_mask": "simulator",
    }


def _build_layer_with_stat_level_enabled():
    """Build a ResidualCalibrationLayer with stat_level.enabled=True + the v2 test artifact."""
    config = ResidualCalibrationConfig(
        enabled=True,
        artifacts_dir=None,  # we'll inject the artifact directly
        positions=("QB", "RB", "WR", "TE"),
        min_bucket_rows=200,
        min_bucket_weeks=6,
        shrinkage_prior_rows=200,
        max_abs_adjustment=1.5,
        min_training_mae_delta=-0.01,
        fallback="zero",
        stat_level=StatLevelConfig(
            enabled=True,
            covered_stats=(
                "pass_yards", "pass_tds", "interceptions",
                "rush_yards", "rush_tds",
                "receiving_yards", "receptions", "receiving_tds",
                "fumbles_lost",
            ),
        ),
    )
    layer = ResidualCalibrationLayer(config)
    # Inject the v2 artifact directly into the cache
    layer._artifact_cache = {2024: _build_v2_artifact_for_tests()}  # noqa: SLF001
    return layer


def test_ks09_writes_corrected_columns_when_enabled():
    """When stat_level.enabled=True, adjust_week writes corrected_<stat> columns for covered stats."""
    layer = _build_layer_with_stat_level_enabled()
    rows, _stats = layer.adjust_week([_build_qb_row()], season=2024, week=1)
    row = rows[0]
    # 9 covered stats from StatLevelConfig.covered_stats above
    assert "corrected_pass_yards" in row
    assert "corrected_pass_tds" in row
    assert "corrected_interceptions" in row
    assert "corrected_rush_yards" in row
    assert "corrected_rush_tds" in row
    assert "corrected_fumbles_lost" in row


def test_ks09_fpts_unchanged_when_flag_disabled():
    """When stat_level.enabled=False, no corrected_<stat> columns appear."""
    config = ResidualCalibrationConfig(
        enabled=True,
        positions=("QB", "RB", "WR", "TE"),
        min_bucket_rows=200,
        min_bucket_weeks=6,
        max_abs_adjustment=1.5,
        stat_level=StatLevelConfig(enabled=False),
    )
    layer = ResidualCalibrationLayer(config)
    layer._artifact_cache = {2024: _build_v2_artifact_for_tests()}  # noqa: SLF001
    rows, _stats = layer.adjust_week([_build_qb_row()], season=2024, week=1)
    row = rows[0]
    # No corrected_<stat> columns
    for stat in ("pass_yards", "pass_tds", "interceptions", "rush_yards", "rush_tds", "fumbles_lost"):
        assert f"corrected_{stat}" not in row, f"corrected_{stat} unexpectedly present when flag disabled"


def test_ks09_two_stage_layered_fpts_unchanged_with_flag_enabled():
    """D-01: row['fpts'] is computed from raw_sim_fpts + existing fpts-level correction; per-stat corrections do NOT propagate."""
    layer = _build_layer_with_stat_level_enabled()
    raw_fpts = 16.0
    rows, _stats = layer.adjust_week([_build_qb_row(fpts=raw_fpts)], season=2024, week=1)
    row = rows[0]
    # Expected fpts = raw + bucket correction at bucket "QB|mid|simulator_only" = ... (some artifact-derived value)
    # The QB-mid bucket above has correction=-0.5 (from buckets dict, not stat_corrections)
    expected_fpts = max(raw_fpts + (-0.5), 0.0)
    assert math.isclose(float(row["fpts"]), round(expected_fpts, 1), abs_tol=1e-6)
    # And corrected_pass_yards is independently computed (not derived from fpts)
    # raw pass_yards = 240, correction = -10.0 (from artifact), clamped at ±2*50=100
    assert "corrected_pass_yards" in row
    assert math.isclose(float(row["corrected_pass_yards"]), 240.0 + (-10.0), abs_tol=1e-6)


def test_ks09_std_scaled_clamp_applies():
    """stat_clamp_adjustment clamps to ±2 * clamp_std."""
    # raw correction = +25, clamp_std = 10, limit = 20 → clamped to +20
    assert stat_clamp_adjustment(25.0, clamp_std=10.0) == 20.0
    # raw correction = -15, clamp_std = 10, limit = 20 → unchanged at -15
    assert stat_clamp_adjustment(-15.0, clamp_std=10.0) == -15.0
    # raw correction = -30, clamp_std = 10 → clamped to -20
    assert stat_clamp_adjustment(-30.0, clamp_std=10.0) == -20.0
    # clamp_std = 0 → limit = 0 → any input clamped to 0
    assert stat_clamp_adjustment(5.0, clamp_std=0.0) == 0.0


def test_ks09_missing_bucket_fallback_zero():
    """For a bucket_key NOT in stat_corrections, corrected_<stat> equals the raw <stat>."""
    layer = _build_layer_with_stat_level_enabled()
    # WR with low fpts → bucket_key = "WR|low|simulator_only"; stat_corrections has WR|low|simulator_only for receiving_yards only
    # Other WR-covered stats (receptions, receiving_tds, fumbles_lost) have NO entry — fallback to raw
    rows, _stats = layer.adjust_week([_build_wr_row(fpts=5.0)], season=2024, week=1)
    row = rows[0]
    # receiving_yards has correction; should differ from raw
    raw_recv = 70.0
    assert math.isclose(float(row["corrected_receiving_yards"]), raw_recv + 4.0, abs_tol=1e-6)  # correction=4.0 from fixture
    # receptions has NO correction → corrected == raw (zero adjustment)
    assert math.isclose(float(row["corrected_receptions"]), 5.0, abs_tol=1e-6)


def test_ks09_schema_v2_artifact_has_stat_corrections():
    """V2 artifact carries a stat_corrections block."""
    artifact = _build_v2_artifact_for_tests()
    assert artifact["schema_version"] == 2
    assert "stat_corrections" in artifact
    assert "pass_yards" in artifact["stat_corrections"]
    assert "corrections" in artifact["stat_corrections"]["pass_yards"]
    assert "clamps" in artifact["stat_corrections"]["pass_yards"]


def test_ks09_training_script_writes_per_stat_block():
    """fit_residual_calibration_artifact with stat_level_enabled=True populates stat_corrections."""
    from fantasy_sim.scoring.residual_calibration import fit_residual_calibration_artifact

    # Minimal training rows: simulate two QB rows with raw stats + actuals
    source_rows = [
        {
            "player_id": "p1", "position": "QB",
            "season": 2022, "week": 1,
            "simulator_fpts": 18.0, "actual_fpts": 22.0,
            "fpts": 18.0, "pass_yards": 250.0,
            "actual_pass_yards": 280.0,  # KS-09 needs actual stat values
            "dynamic_blend_source_mask": "simulator",
        },
        {
            "player_id": "p1", "position": "QB",
            "season": 2022, "week": 2,
            "simulator_fpts": 17.0, "actual_fpts": 19.0,
            "fpts": 17.0, "pass_yards": 230.0,
            "actual_pass_yards": 250.0,
            "dynamic_blend_source_mask": "simulator",
        },
    ] * 200  # repeat to satisfy min_bucket_rows
    artifact = fit_residual_calibration_artifact(
        source_rows,
        test_season=2024,
        source_seasons=[2022, 2023],
        sims=200,
        scoring="ppr",
        config=ResidualCalibrationConfig(
            enabled=True,
            positions=("QB",),
            min_bucket_rows=200,
            min_bucket_weeks=6,
            stat_level=StatLevelConfig(enabled=True, covered_stats=("pass_yards",)),
        ),
    )
    assert "stat_corrections" in artifact
    assert "pass_yards" in artifact["stat_corrections"]
    # At least one bucket-correction populated
    assert len(artifact["stat_corrections"]["pass_yards"]["corrections"]) >= 1
    assert len(artifact["stat_corrections"]["pass_yards"]["clamps"]) >= 1


def test_ks09_corrected_differs_from_raw_for_non_fallback_rows():
    """For rows whose bucket has a correction, corrected_<stat> != raw <stat>."""
    layer = _build_layer_with_stat_level_enabled()
    rows, _stats = layer.adjust_week([_build_qb_row(fpts=10.0, pass_yards=240.0)], season=2024, week=1)
    row = rows[0]
    # QB|low at fpts=10.0 → bucket "QB|low|simulator_only"; correction for pass_yards = -10.0
    raw_pass_yards = 240.0
    corrected = float(row["corrected_pass_yards"])
    assert corrected != raw_pass_yards, "corrected_pass_yards must differ from raw for a populated bucket"
    assert math.isclose(corrected, 230.0, abs_tol=1e-6)  # 240 + (-10) clamped at ±100
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09
```

Expected: all 8 tests fail with ImportError (`stat_clamp_adjustment` not yet defined) or AssertionError (the runtime path doesn't yet write corrected_<stat> columns; the training script doesn't yet write stat_corrections). RED state.

Commit: `test(02-03): add 8 failing tests for KS-09 per-stat residual_calibration`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09 2>&1 | grep -E "FAILED|ERROR" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_scoring/test_residual_calibration.py` contains all 8 `def test_ks09_*` test functions (literal substring match)
    - `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09` exits NON-ZERO (RED state)
    - `git log -1 --pretty=%s` matches `test(02-03): add 8 failing tests for KS-09`
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement `stat_clamp_adjustment()` + `_per_stat_corrections()` + extend `adjust_week()` (gated) + extend `fit_residual_calibration_artifact()` to write per-stat block + update training script defaults loading</name>
  <files>
    - src/fantasy_sim/scoring/residual_calibration.py
    - scripts/fit_residual_calibration.py
    - src/fantasy_sim/data/ensemble/models.py
  </files>
  <read_first>
    - src/fantasy_sim/scoring/residual_calibration.py (current `adjust_week`, `clamp_adjustment`, `bucket_key_for_projection`, `_artifact()`)
    - scripts/fit_residual_calibration.py (`fit_residual_calibration_artifact` and `main` flow)
    - src/fantasy_sim/data/ensemble/models.py (current `ResidualCalibrationConfig` definition)
    - src/fantasy_sim/config/loader.py (`load_defaults`)
  </read_first>
  <behavior>
    - In `models.py`: add `StatLevelConfig` dataclass and `stat_level: StatLevelConfig = field(default_factory=StatLevelConfig)` to `ResidualCalibrationConfig`. The loader (likely in `data/ensemble/__init__.py` or `data/ensemble/config.py`) reads `defaults["ensemble"]["residual_calibration"]["stat_level"]` from defaults.yaml.
    - In `residual_calibration.py`: add `stat_clamp_adjustment(value, clamp_std)` helper; add private `_per_stat_corrections(self, row, position, tier, confidence_bucket, artifact)` method that returns a dict `{stat: corrected_value}`; extend `adjust_week()` to call this method and write `corrected_<stat>` columns BEFORE the existing `row["fpts"]` write (gated).
    - In `fit_residual_calibration.py`: extend `fit_residual_calibration_artifact()` to ALSO compute per-stat corrections + per-bucket clamp_std when `config.stat_level.enabled` is True; bump output schema_version to 2 (was 1); add `stat_corrections` block to the artifact dict.
    - Loader override: when `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled` is true in defaults.yaml, set `stat_level.enabled = True` regardless of `ensemble.residual_calibration.stat_level.enabled` (the flag is the master toggle for testability).
  </behavior>
  <action>
**File 1: `src/fantasy_sim/data/ensemble/models.py`** — add `StatLevelConfig` and extend `ResidualCalibrationConfig`:

```python
@dataclass(frozen=True)
class StatLevelConfig:
    """Per-stat residual_calibration config block for KS-09 (Plan 03)."""
    enabled: bool = False
    covered_stats: tuple[str, ...] = ()
```

In `ResidualCalibrationConfig`, add:
```python
    stat_level: StatLevelConfig = field(default_factory=StatLevelConfig)
    max_abs_adjustment_by_position: dict[str, float] = field(default_factory=dict)  # placeholder for KS-10 Plan 05
```

**File 2: Loader** (in `src/fantasy_sim/data/ensemble/__init__.py` OR `src/fantasy_sim/data/ensemble/config.py`) — find where `ResidualCalibrationConfig` is constructed from `defaults["ensemble"]["residual_calibration"]`. Extend with:

```python
res_cal_raw = defaults["ensemble"]["residual_calibration"]
stat_level_raw = res_cal_raw.get("stat_level", {})
phase2_flags = defaults.get("phase2_ks_flags", {})
ks09_block = phase2_flags.get("ks09_per_stat_residual_calibration", {})
# Phase 2 D-02: flag is master toggle. When enabled, force stat_level.enabled = True.
stat_level_enabled = bool(ks09_block.get("enabled", False)) or bool(stat_level_raw.get("enabled", False))
covered_stats = tuple(stat_level_raw.get("covered_stats", ()))

residual_calibration_config = ResidualCalibrationConfig(
    enabled=res_cal_raw.get("enabled", False),
    artifacts_dir=...,
    positions=...,
    min_bucket_rows=...,
    min_bucket_weeks=...,
    shrinkage_prior_rows=...,
    max_abs_adjustment=res_cal_raw.get("max_abs_adjustment", 1.5),
    min_training_mae_delta=...,
    fallback=...,
    stat_level=StatLevelConfig(
        enabled=stat_level_enabled,
        covered_stats=covered_stats,
    ),
    max_abs_adjustment_by_position=dict(res_cal_raw.get("max_abs_adjustment_by_position", {})),
)
```

**File 3: `src/fantasy_sim/scoring/residual_calibration.py`** — add the helper after `clamp_adjustment` at line 109-111:

```python
def stat_clamp_adjustment(value: float, clamp_std: float) -> float:
    """Clamp a per-stat residual to ±2 * clamp_std (per-bucket std from training).

    KS-09 D-04 + Pattern 4: clamp_std comes from artifact["stat_corrections"][stat]["clamps"][bucket_key]["clamp_std"].
    Caller falls back to zero adjustment when clamp_std is None / missing (graceful
    degradation for buckets with no training data for the stat).
    """
    limit = max(2.0 * float(clamp_std), 0.0)
    return min(max(float(value), -limit), limit)
```

Locate `adjust_week` at line 367. Inside the per-row loop (around line 393-431), after the existing `correction = ...` lookup but BEFORE the `row["fpts"] = round(...)` line (which is line 422 currently), insert:

```python
            # KS-09 D-01: per-stat correction writes corrected_<stat> columns.
            # Two-stage layered fpts (D-01): the existing row["fpts"] correction is unchanged
            # (computed from raw_sim_fpts + bucket correction below); the per-stat columns are
            # additive and do NOT propagate into fpts.
            if self.config.stat_level.enabled and artifact is not None:
                stat_corrections_block = artifact.get("stat_corrections", {})
                for stat in self.config.stat_level.covered_stats:
                    raw = row.get(stat)
                    if not isinstance(raw, (int, float)):
                        # Stat not present on this row (e.g., RB row missing pass_yards) → skip
                        continue
                    stat_block = stat_corrections_block.get(stat, {})
                    bucket_corrections = stat_block.get("corrections", {})
                    bucket_clamps = stat_block.get("clamps", {})
                    correction_entry = bucket_corrections.get(key)
                    clamp_entry = bucket_clamps.get(key)
                    if not correction_entry:
                        # Missing bucket → fallback zero adjustment (corrected == raw)
                        row[f"corrected_{stat}"] = round(float(raw), 4)
                        continue
                    raw_correction = float(correction_entry.get("correction", 0.0))
                    clamp_std = float(clamp_entry.get("clamp_std", 0.0)) if clamp_entry else 0.0
                    if clamp_std > 0:
                        applied = stat_clamp_adjustment(raw_correction, clamp_std)
                    else:
                        # No clamp_std available → fallback to position-level cap (KS-10 will retune)
                        applied = clamp_adjustment(raw_correction, self.config.max_abs_adjustment)
                    corrected = float(raw) + applied
                    # Stats are non-negative (yards, TDs, receptions, fumbles_lost) — clamp to 0
                    row[f"corrected_{stat}"] = round(max(corrected, 0.0), 4)
```

(The above inserts BEFORE `row["fpts"] = round(max(fpts + correction, 0.0), 1)` — line 422 stays unchanged.)

**File 4: `scripts/fit_residual_calibration.py`** — locate `fit_residual_calibration_artifact()` (search for its definition). Extend the function signature with a config kw-arg (or accept the StatLevelConfig directly):

```python
def fit_residual_calibration_artifact(
    source_rows: list[Mapping[str, object]],
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
    config: ResidualCalibrationConfig,  # already passed; verify the path
) -> dict:
    # ... existing logic that fits per-bucket fpts corrections (unchanged)

    artifact = {
        "schema_version": 2 if config.stat_level.enabled else 1,
        # ... existing fields
        "buckets": buckets,
    }

    # KS-09 D-03: when stat_level enabled, fit per-stat corrections + clamps
    if config.stat_level.enabled and config.stat_level.covered_stats:
        stat_corrections: dict[str, dict[str, dict]] = {}
        for stat in config.stat_level.covered_stats:
            stat_block: dict[str, dict] = {"corrections": {}, "clamps": {}}
            # Group rows by (position, usage_tier, source_confidence_bucket) bucket key
            by_bucket: dict[str, list[Mapping[str, object]]] = {}
            for row in source_rows:
                if not isinstance(row.get(f"actual_{stat}"), (int, float)):
                    continue
                key = bucket_key_for_projection(row)
                by_bucket.setdefault(key, []).append(row)
            for key, rows in by_bucket.items():
                if len(rows) < config.min_bucket_rows:
                    continue
                # Mean correction = mean(actual - simulator) for this stat
                deltas = []
                for row in rows:
                    raw = float(row.get(stat, 0.0))
                    actual = float(row.get(f"actual_{stat}", 0.0))
                    deltas.append(actual - raw)
                mean_delta = float(np.mean(deltas))
                std_delta = float(np.std([float(row.get(f"actual_{stat}", 0.0)) for row in rows]))  # actual std for clamp
                stat_block["corrections"][key] = {"correction": mean_delta, "n_rows": len(rows)}
                stat_block["clamps"][key] = {"clamp_std": std_delta}
            stat_corrections[stat] = stat_block
        artifact["stat_corrections"] = stat_corrections

    return artifact
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09
```

Expected: all 8 tests pass (GREEN).

Run the full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: full suite green; total tests = 2,142 + 8 = 2,150.

Commit: `feat(02-03): KS-09 implement stat_clamp_adjustment() + per-stat correction in adjust_week() + stat_corrections block in fit_residual_calibration_artifact() (gated behind phase2_ks_flags.ks09)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/scoring/residual_calibration.py` contains `def stat_clamp_adjustment(`
    - `src/fantasy_sim/scoring/residual_calibration.py` contains the literal string `corrected_{stat}`
    - `src/fantasy_sim/data/ensemble/models.py` contains `class StatLevelConfig`
    - `src/fantasy_sim/data/ensemble/models.py` contains `stat_level: StatLevelConfig`
    - `scripts/fit_residual_calibration.py` contains the literal string `stat_corrections`
    - `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09` exits 0 (8 tests pass)
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,150 tests)
    - `git log -1 --pretty=%s` matches `feat(02-03): KS-09 implement`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Re-fit `decision_s200/calibration_*.json` artifacts with KS-08 floor active + KS-09 stat_corrections + run KS-09 A/B (bare + full)</name>
  <files>
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md (Plan 02 KS-08 status; KS-09 fit happens with KS-08 floor ACTIVE if SHIPPED)
    - scripts/fit_residual_calibration.py (the extended training script from Task 2)
    - src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json (current schema_version: 1; will become 2)
  </read_first>
  <behavior>
    - Re-fit `calibration_2023.json` and `calibration_2024.json` with `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true` so the training run produces v2 artifacts with `stat_corrections` populated. If KS-08 is SHIPPED, the fit ALSO uses the KS-08 floor (Pitfall 7 requires the artifacts to be consistent with the runtime stack).
    - Run KS-09 A/B: `p2.ks09.bare` and `p2.ks09.full` ledger entries.
    - Bare entry: `--baseline bare --arm-b-base bare --set ensemble.residual_calibration.enabled=true --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true`.
    - Full entry: `--baseline defaults --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true`.
    - Read D-14 promotion bar conditions from the ledger.
  </behavior>
  <action>
**Step 1: Re-fit calibration artifacts.** Per Pitfall 3, training data for `calibration_2024.json` is seasons [2022, 2023] and for `calibration_2023.json` is season [2022]. Use:

```bash
uv run python scripts/fit_residual_calibration.py \
  --test-seasons 2023 2024 \
  --min-source-season 2022 \
  --sims 200 --training-years 4 --scoring ppr \
  --output-dir src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200 \
  --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks09_refit.log
```

(Note: if `fit_residual_calibration.py` does not yet support `--set` to override defaults, use an environment variable or temporary YAML override. Alternatively, edit `config/defaults.yaml` to set `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true` BEFORE running the fitter, then revert that change AFTER the fit so per-KS A/B runs go through the explicit `--set` path. Document the chosen mechanic in the plan summary.)

Verify the re-fit:
```bash
uv run python -c "import json; a23 = json.load(open('src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2023.json')); a24 = json.load(open('src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json')); assert a23['schema_version'] == 2 and a24['schema_version'] == 2; assert 'stat_corrections' in a23 and 'stat_corrections' in a24; print('OK', list(a24['stat_corrections'].keys())[:5])"
```

Expected output:
```
OK ['pass_yards', 'pass_tds', ...]
```

**Step 2: Run KS-09 A/B.**

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set ensemble.residual_calibration.enabled=true \
  --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true \
  --label "p2.ks09.bare" \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks09_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true \
  --label "p2.ks09.full" \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks09_full.log
```

Inspect the ledger:
```bash
uv run python scripts/validate.py --show-ledger | grep -E "p1.aggregate.full|p2.ks09\."
```

**Step 3: Read D-14 promotion-bar conditions.** Extract from the ledger:
- `Δ rank_corr` (hard floor: ≥ -0.005)
- `Δ weekly_mae` (hard floor: ≤ +0.05)
- `Δ stat_ks["QB"]["pass_yards"]["arm_b"]` vs `p1.aggregate.full` Arm B (D-14 condition: `≤ -0.03` for SHIPPED)
- `Δ stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]` vs `p1.aggregate.full` Arm B (D-14 condition: `|Δ| ≤ 5 yd/g` for SHIPPED)

Apply D-14 logic:
- All 4 conditions pass → `SHIPPED`
- Hard floor + KS Δ pass but bias `|Δ| > 5 yd/g` → `SHIPPED-PARTIAL`
- Hard floor regresses → `BLOCKED`

**Step 4: Document in PROMOTION-NOTES.md.** Append to `## KS-09 (Plan 03)`:

```markdown
## KS-09 (Plan 03) — <STATUS>

**Re-fit (2026-04-26):** `calibration_2023.json` + `calibration_2024.json` re-fit with phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true (and KS-08 floor active if SHIPPED). Schema bumped 1→2; new stat_corrections block populated for <N> stats × <M> buckets each.

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[QB][pass_yards] | Δ stat_mean_bias[QB][pass_yards] | Hard Floor | KS Δ ≤ -0.03 | \|bias Δ\| ≤ 5 |
|------|-------------|--------------|----------------------------|-----------------------------------|-----------|--------------|----------------|
| bare | <val>       | <val>        | <val>                      | <val>                             | <PASS/FAIL> | <PASS/FAIL>  | <PASS/FAIL>    |
| full | <val>       | <val>        | <val>                      | <val>                             | <PASS/FAIL> | <PASS/FAIL>  | <PASS/FAIL>    |

**D-14 evaluation:**
1. Hard floor (rank_corr Δ ≥ -0.005 AND MAE Δ ≤ +0.05): <PASS/FAIL>
2. KS Δ ≤ -0.03 on QB pass_yards: <PASS/FAIL>
3. QB pass_yards mean bias |Δ| ≤ 5 yd/g: <PASS/FAIL>

**Decision:** `<SHIPPED | SHIPPED-PARTIAL | BLOCKED>`. Rationale: <one-paragraph>.
```

Commit: `chore(02-03): KS-09 re-fit calibration artifacts (schema_v2) + run A/B (p2.ks09.{bare,full})`
  </action>
  <verify>
    <automated>uv run python -c "import json; a = json.load(open('src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json')); assert a['schema_version']==2 and 'stat_corrections' in a; print('OK')" && uv run python scripts/validate.py --show-ledger | grep -E "p2.ks09" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-09" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json` has `schema_version: 2`
    - `calibration_2024.json` contains a top-level `stat_corrections` field with at least 9 stat keys (the 9-element StatLevelConfig.covered_stats from defaults.yaml)
    - `calibration_2023.json` has `schema_version: 2` and contains `stat_corrections`
    - `uv run python scripts/validate.py --show-ledger | grep "p2.ks09\\."` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-09` section contains the A/B result table with the 3 D-14 evaluation rows
    - `git log -1 --pretty=%s` matches `chore(02-03): KS-09`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit per D-14 + full suite green</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md (Task 3's D-14 evaluation)
    - config/defaults.yaml (`phase2_ks_flags.ks09_per_stat_residual_calibration` block)
  </read_first>
  <behavior>
    - If D-14 evaluation = `SHIPPED`: flip `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled = true` AND `ensemble.residual_calibration.stat_level.enabled = true` in defaults.yaml.
    - If D-14 evaluation = `SHIPPED-PARTIAL`: flip `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled = true` AND document the bias gap in PROMOTION-NOTES.md.
    - If D-14 evaluation = `BLOCKED`: flag stays `enabled: false`; runtime code stays in tree but dormant.
    - Run full pytest suite to confirm no regressions.
    - Commit per Phase 1 D-25/D-40 standardized format.
  </behavior>
  <action>
Branch on Task 3's status from PROMOTION-NOTES.md:

**If `SHIPPED`:** edit `config/defaults.yaml` so:
```yaml
  ks09_per_stat_residual_calibration:
    enabled: true   # KS-09 SHIPPED 2026-04-26 — see logs/PROMOTION-NOTES.md ## KS-09 (D-14 all 3 conditions met)
```
AND:
```yaml
ensemble:
  residual_calibration:
    ...
    stat_level:
      enabled: true   # KS-09 SHIPPED 2026-04-26
      covered_stats: [...]  # unchanged
```

**If `SHIPPED-PARTIAL`:** edit defaults.yaml the same way as SHIPPED (flag flips), but add a comment:
```yaml
  ks09_per_stat_residual_calibration:
    enabled: true   # KS-09 SHIPPED-PARTIAL 2026-04-26 — hard floor + KS Δ ≤ -0.03 met, but |bias Δ| > 5 yd/g (residual gap documented in PROMOTION-NOTES.md ## KS-09; Phase 3/4 levers will close)
```

**If `BLOCKED`:** flag stays false; defaults.yaml unchanged from Plan 01.

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -5
```

Expected: 2,150 tests pass.

Run a sanity-check A/B with promoted defaults (only if SHIPPED or SHIPPED-PARTIAL):
```bash
uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p2.ks09.promoted
uv run python scripts/validate.py --show-ledger | grep -E "p2.ks09.promoted"
```

The promoted entry's Arm B should match the `p2.ks09.full` Arm B within ledger noise.

Append to PROMOTION-NOTES.md `## KS-09`:
```markdown
**Final decision (2026-04-26):** Status = <STATUS>. Defaults.yaml updated: phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=<true|false>. Test suite (2,150) green. Bundled artifacts shipped at schema_version: 2.
```

Commit:
```
feat(02-03): KS-09 <SHIPPED|SHIPPED-PARTIAL|BLOCKED> per D-14 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[QB][pass_yards] <val>, Δ bias[QB][pass_yards] <val>

Defaults: phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=<true|false>; ensemble.residual_calibration.stat_level.enabled=<true|false>
Bundled artifacts: src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_{2023,2024}.json @ schema_version: 2 with stat_corrections block
Refs: D-01, D-02, D-03, D-04, D-14 (CONTEXT.md), HYPOTHESES.md KS-09 (lines 189-201)
```
  </action>
  <verify>
    <automated>uv run pytest tests/ -v 2>&1 | tail -3 | grep -E "passed|failed" && grep -E "Final decision" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md | grep -i "ks-09\|status" | head -1</automated>
  </verify>
  <acceptance_criteria>
    - If status SHIPPED or SHIPPED-PARTIAL: `config/defaults.yaml` has `phase2_ks_flags.ks09_per_stat_residual_calibration.enabled: true` AND `ensemble.residual_calibration.stat_level.enabled: true`
    - If status BLOCKED: defaults.yaml flag stays false
    - PROMOTION-NOTES.md `## KS-09` section ends with a `Final decision` paragraph
    - `uv run pytest tests/ -v` exits 0 (2,150 tests passing)
    - `git log -1 --pretty=%s` matches `feat(02-03): KS-09 (SHIPPED|SHIPPED-PARTIAL|BLOCKED)`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 4 tasks complete:

1. `git log --oneline -10` shows 4 new commits prefixed `(02-03)` (test, feat, chore, feat).
2. If SHIPPED/SHIPPED-PARTIAL: defaults.yaml has both flags flipped; bundled calibration_*.json artifacts at schema_v2 with stat_corrections.
3. `uv run pytest tests/test_scoring/test_residual_calibration.py -v -k ks09` exits 0 (8 tests pass).
4. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks09"` returns 2 (or 3 if SHIPPED) rows.
5. `uv run pytest tests/ -v` exits 0; total = 2,150.
6. PROMOTION-NOTES.md `## KS-09` has D-14 3-condition evaluation + final decision word.

KS-09 status recorded. Plan 04 (KS-14) may now proceed.
</verification>

<must_haves>
  truths:
    - "Per D-01: two-stage layered fpts — corrected_<stat> columns are NEW (additive) and NOT propagated into row['fpts']. row['fpts'] = max(raw_sim_fpts + existing_fpts_correction, 0.0); per-stat corrections live in corrected_<stat> columns only."
    - "Per D-02: gated behind phase2_ks_flags.ks09_per_stat_residual_calibration.enabled (default false). Loader override: when phase2 flag is true, ResidualCalibrationConfig.stat_level.enabled is forced to True."
    - "Per D-03: 14 covered stats from defaults.yaml ensemble.residual_calibration.stat_level.covered_stats. Position-specific (RB has receiving stats, WR/TE don't have rush stats); skip stats not present on the row."
    - "Per D-04 + Pattern 4: per-bucket clamp_std lives in artifact[stat_corrections][<stat>][clamps][<bucket_key>][clamp_std]. Falls back to global max_abs_adjustment when clamp_std is None."
    - "Per D-14 elevated promotion bar: SHIPPED requires hard floor + KS Δ ≤ -0.03 on QB pass_yards + |bias Δ| ≤ 5 yd/g. SHIPPED-PARTIAL = hard floor + KS Δ pass but bias miss; flag still flips and gap documented. BLOCKED = hard floor regresses."
    - "Per Pitfall 3: holdout discipline — calibration_2024 trains on [2022, 2023]; calibration_2023 trains on [2022]. Never include test_season in training."
    - "Per Pitfall 1: per-stat and fpts corrections may diverge (e.g., corrected_pass_yards * 0.04 != corrected fpts contribution). Documented and not chased in v1."
    - "Per C-09: 2,150-test suite stays green throughout (2,142 pre-Plan-03 + 8 from Task 1)."
  artifacts:
    - path: "src/fantasy_sim/scoring/residual_calibration.py"
      provides: "stat_clamp_adjustment() helper + per-stat correction logic in adjust_week() (gated)"
      contains: "def stat_clamp_adjustment"
    - path: "scripts/fit_residual_calibration.py"
      provides: "Extended fit_residual_calibration_artifact() to write stat_corrections block + bump artifact schema_version to 2"
      contains: "stat_corrections"
    - path: "src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/calibration_2024.json"
      provides: "v2 artifact with populated stat_corrections (only if SHIPPED or SHIPPED-PARTIAL)"
      contains: "stat_corrections"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-09 D-14 3-condition evaluation table + final decision word"
      contains: "## KS-09"
</must_haves>
