---
phase: 02-structural-per-stat-calibration
plan: 02
type: tdd
wave: 1
depends_on: ["01"]
files_modified:
  - src/fantasy_sim/scoring/dynamic_blend.py
  - scripts/fit_dynamic_blend_weights.py
  - config/defaults.yaml
  - tests/test_scoring/test_dynamic_blend.py
  - src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json
  - src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-08]
must_haves:
  truths:
    - "Per D-05: KS-08 sweep is 3-point {0.20, 0.30, 0.40}; selection rule = SMALLEST passing where (a) hard floor `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05` AND (b) non-zero KS Δ improvement on TE/WR fpts. Six ledger entries produced: `p2.ks08.s020.{bare,full}`, `p2.ks08.s030.{bare,full}`, `p2.ks08.s040.{bare,full}`."
    - "**Codex LOW 9 (2026-04-27 revision) — sweep alignment with phase-level criteria:** in addition to the TE/WR fpts KS criterion above, the sweep selection ALSO checks aggregate `Δ stat_ks[fpts]` (TGT-08) and primary stat-level targets (TGT-04 TE receptions, TGT-09 QB pass_yards bias). When two floors both pass the local TE/WR fpts criterion, prefer the floor whose aggregate `fpts KS` Δ is smaller (more negative). This avoids picking a locally-good floor that does not feed Phase 2's aggregate targets. The Plan 02 Task 3 sweep table records all four metric Δs per floor so the selection rationale is auditable. If aggregate Δ disagrees with TE/WR Δ at the chosen floor, document explicitly in PROMOTION-NOTES.md."
    - "Per D-06 + Pitfall 2 in 02-RESEARCH.md: floor + renormalize happens AFTER `normalize_weights(...)` in `_artifact_weights()` (dynamic_blend.py:529-542). Pre-`normalize_weights` flooring would not be mathematically equivalent. The floor lifts simulator weight to at least `floor` and pulls down ff_opportunity + market_history proportionally to preserve sum=1.0."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` (default false). Promotion commit per D-12 / per Phase 1 D-25 flips both `enabled = true` AND `floor = <smallest-passing-value>` in defaults.yaml; updates the bundled `decision_s200/weights_*.json` artifacts re-fit with the chosen floor."
    - "Per D-06 + Pitfall 7 in 02-RESEARCH.md (mirroring Phase 1 D-08): the runtime floor change AND the artifact re-fit must both ship in this plan. `scripts/fit_dynamic_blend_weights.py` is extended with `--simulator-weight-floor <value>` so the re-fit's training distribution accounts for the new floor as a constraint."
    - "Per Phase 1 D-46: KS-08 success measured via `validate.py` ledger entries; primary target = TE/WR fpts KS Δ < 0 (simulator brings variance back into the post-sim blend); secondary = rank_corr / weekly_mae hard floor."
    - "Per C-08: TDD-first for KS-08 (6 unit tests for the floor + renormalize math; standard distribution preserved when sim ≥ floor; lift mechanic when sim < floor; CLI flag wired; artifact schema includes floor; etc.)"
    - "Per C-09: 2,131 + 5 (Plan 01) = 2,136 tests stay green; Plan 02 adds 6 more (target: 2,142 after this plan)."
    - "Per C-10: KS-08 affects post-sim blend weights at the bucket level (`bucket_key = (position, week_bucket, source_mask, market_confidence_bucket)`); QB-untouched invariants from `feedback_qb_calibration.md` are unaffected because tier_engine carry/scramble/yards blending is upstream of dynamic_blend."
  artifacts:
    - path: "src/fantasy_sim/scoring/dynamic_blend.py"
      provides: "Floor + renormalize logic in `_artifact_weights()` after the existing `normalize_weights()` call; reads `simulator_weight_floor` from `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor` when the flag is enabled, else 0.0"
      contains: "weights[SIMULATOR_SOURCE] = max"
    - path: "scripts/fit_dynamic_blend_weights.py"
      provides: "New `--simulator-weight-floor <value>` CLI flag; the value is passed through to `fit_dynamic_blend_artifact()` and stored in the artifact's metadata; the candidate weight grid in `candidate_weight_grid()` is filtered to compositions where simulator weight ≥ floor"
      contains: "--simulator-weight-floor"
    - path: "config/defaults.yaml"
      provides: "`phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled = true` (after promotion); `ensemble.dynamic_blend.simulator_weight_floor = <chosen>` (after promotion)"
      contains: "ks08_dynamic_blend_simulator_floor:"
    - path: "tests/test_scoring/test_dynamic_blend.py"
      provides: "6 new tests: ks08_floor_unchanged_when_sim_above_floor, ks08_floor_lifts_when_sim_below_floor, ks08_floor_preserves_sum_to_one, ks08_floor_zero_is_no_op, ks08_artifact_records_floor_in_metadata, ks08_cli_flag_wired"
      contains: "def test_ks08_"
    - path: "src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json"
      provides: "Re-fit artifact with chosen floor baked into the training run; schema_version unchanged (1); new top-level field `simulator_weight_floor: <chosen>` in artifact metadata"
      contains: "simulator_weight_floor"
    - path: "src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json"
      provides: "Re-fit artifact with chosen floor baked into the training run"
      contains: "simulator_weight_floor"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-08 promotion-state decision summary including the 6-row sweep table, smallest-passing selection, and the bundled artifact regeneration record"
      contains: "## KS-08"
  key_links:
    - from: "config/defaults.yaml::phase2_ks_flags.ks08_dynamic_blend_simulator_floor"
      to: "src/fantasy_sim/scoring/dynamic_blend.py::_artifact_weights"
      via: "DynamicBlendConfig.simulator_weight_floor (read at config-load time from defaults.yaml)"
      pattern: "simulator_weight_floor"
    - from: "scripts/fit_dynamic_blend_weights.py::main"
      to: "src/fantasy_sim/scoring/dynamic_blend.py::candidate_weight_grid"
      via: "--simulator-weight-floor CLI flag → constraint passed to grid filter"
      pattern: "if weights\\[SIMULATOR_SOURCE\\] >= floor"
---

<objective>
Implement KS-08 — add a simulator-weight floor to the post-sim `dynamic_blend` ensemble. Per D-05/D-06: sweep three floor values {0.20, 0.30, 0.40} via `validate.py` A/B at each, select the smallest that clears the hard floor AND shows non-zero KS improvement on TE/WR fpts. Per HYPOTHESES.md KS-08 (lines 175-187), the post-Phase-1 `weights_2024.json` shows simulator weight at near-zero for many WR/TE buckets — `ff_opportunity` is dominating, which compresses Monte Carlo variance and inflates fpts KS. The floor restores variance.

Purpose: aggregate fpts KS sits at 0.15-0.25 (TGT-08 target ≤ 0.18); the post-Phase-1 ledger Arm B already shows TE/WR distributions compressed because dynamic_blend's learned simulator weights collapse to ~0 for many buckets. The floor lifts simulator weight back to a configurable minimum and proportionally reduces ff_opportunity + market_history.

Output:
1. Floor + renormalize logic in `dynamic_blend.py::_artifact_weights()` (gated behind `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled`).
2. `scripts/fit_dynamic_blend_weights.py` extended with `--simulator-weight-floor` flag so the bundled artifact's training run respects the constraint.
3. 6 new unit tests for the floor + renormalize math (TDD-first per C-08).
4. Sweep ledger entries `p2.ks08.s{020,030,040}.{bare,full}` (6 entries total).
5. Re-fit `weights_2023.json` and `weights_2024.json` with the chosen floor.
6. Promotion-state commit per Phase 1 D-25/D-40 pattern: SHIPPED / SHIPPED-NO-OP / BLOCKED based on sweep outcome.
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
@src/fantasy_sim/scoring/dynamic_blend.py
@scripts/fit_dynamic_blend_weights.py
@config/defaults.yaml
@tests/test_scoring/test_dynamic_blend.py
@src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json

<interfaces>
From src/fantasy_sim/scoring/dynamic_blend.py:212-225 (existing `normalize_weights` — no change):

```python
def normalize_weights(
    raw_weights: Mapping[str, float],
    available_sources: Mapping[str, float],
) -> dict[str, float] | None:
    """Normalize non-negative artifact weights across currently available sources."""
    weights = {
        source: max(float(raw_weights.get(source, 0.0)), 0.0)
        for source in SOURCE_ORDER
        if source in available_sources
    }
    total = sum(weights.values())
    if total <= 0:
        return None
    return {source: weight / total for source, weight in weights.items()}
```

From src/fantasy_sim/scoring/dynamic_blend.py:529-542 (existing `_artifact_weights` — TARGET FOR FLOOR LOGIC):

```python
def _artifact_weights(
    self,
    artifact: dict | None,
    context: SourceContext,
) -> dict[str, float] | None:
    if artifact is None:
        return None
    bucket = artifact.get("buckets", {}).get(context.bucket_key)
    if not isinstance(bucket, dict):
        return None
    raw_weights = bucket.get("weights")
    if not isinstance(raw_weights, dict):
        return None
    return normalize_weights(raw_weights, context.sources)  # ← INSERT FLOOR + RENORMALIZE AFTER THIS
```

From src/fantasy_sim/scoring/dynamic_blend.py:23-25 (constants):

```python
SIMULATOR_SOURCE = "simulator"
FF_OPPORTUNITY_SOURCE = "ff_opportunity"
MARKET_HISTORY_SOURCE = "market_history"
SOURCE_ORDER = (SIMULATOR_SOURCE, FF_OPPORTUNITY_SOURCE, MARKET_HISTORY_SOURCE)
```

From src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json (sample bucket showing the compression):

```json
{
  "schema_version": 1,
  "test_season": 2024,
  "source_seasons": [2022, 2023],
  "sims": 200,
  "scoring": "ppr",
  "week_buckets": ["1-4", "5-12", "13-18"],
  "grid_step": 0.05,
  "min_bucket_rows": 200,
  "min_bucket_weeks": 6,
  "fallback": "fixed_defaults",
  "buckets": {
    "QB|5-12|simulator+ff_opportunity+market_history|medium": {
      "weights": {"simulator": 0.0, "ff_opportunity": 0.85, "market_history": 0.15}
    }
  }
}
```

From scripts/fit_dynamic_blend_weights.py:43 + the CLI builder (existing flags to mirror):

```python
parser = argparse.ArgumentParser(description="Fit dynamic post-sim blend weights from historical source rows.")
# ... existing flags: --test-seasons, --min-source-season, --sims, --training-years, --scoring, --output-dir, --workers
# NEW: --simulator-weight-floor <float> (default 0.0)
```

From src/fantasy_sim/scoring/dynamic_blend.py:271-286 (existing `candidate_weight_grid` — Plan 02 filters compositions):

```python
def candidate_weight_grid(
    sources: tuple[str, ...],
    grid_step: float,
) -> list[dict[str, float]]:
    """Generate a convex weight grid for available sources."""
    if not sources:
        return []
    total = max(int(round(1.0 / max(grid_step, 1e-9))), 1)
    return [
        {
            source: value / total
            for source, value in zip(sources, composition, strict=True)
        }
        for composition in _weight_compositions(len(sources), total)
    ]
```

</interfaces>

</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: RED — write 6 failing tests for KS-08 floor + renormalize math + CLI flag wiring</name>
  <files>tests/test_scoring/test_dynamic_blend.py</files>
  <read_first>
    - tests/test_scoring/test_dynamic_blend.py (current test conventions: imports, fixture names, seeding style)
    - src/fantasy_sim/scoring/dynamic_blend.py (`normalize_weights` at line 212-225; `_artifact_weights` at line 529-542; SIMULATOR_SOURCE / FF_OPPORTUNITY_SOURCE / MARKET_HISTORY_SOURCE constants)
    - .planning/research/HYPOTHESES.md lines 175-187 (KS-08 mechanism description)
  </read_first>
  <behavior>
    - Test 1 (`test_ks08_floor_unchanged_when_sim_above_floor`): with `weights = {simulator: 0.40, ff: 0.30, market: 0.30}` and `floor = 0.20`, the floored output equals the input (no change).
    - Test 2 (`test_ks08_floor_lifts_when_sim_below_floor`): with `weights = {simulator: 0.05, ff: 0.65, market: 0.30}` and `floor = 0.20`, the floored output has `simulator = 0.20` AND the others are scaled down proportionally so the sum is still 1.0. Specifically, slack = 0.20 - 0.05 = 0.15; other_total = 0.95; scale = (0.95 - 0.15) / 0.95 = 0.8421; new ff = 0.65 * 0.8421 ≈ 0.5474; new market = 0.30 * 0.8421 ≈ 0.2526; sum = 0.20 + 0.5474 + 0.2526 = 1.0.
    - Test 3 (`test_ks08_floor_preserves_sum_to_one`): property test (random raw weights via hypothesis) — for any non-zero raw_weights and floor in [0.0, 0.5], the floored output sums to 1.0 ± 1e-9.
    - Test 4 (`test_ks08_floor_zero_is_no_op`): with `floor = 0.0`, the floored output equals the input regardless of simulator weight (the "flag-off" path is mathematically identical to no-floor).
    - Test 5 (`test_ks08_artifact_metadata_records_floor`): after running `fit_dynamic_blend_artifact(...)` with `simulator_weight_floor=0.30` (kw-arg), the returned artifact dict has `artifact["simulator_weight_floor"] == 0.30`.
    - Test 6 (`test_ks08_cli_flag_wired`): import `scripts/fit_dynamic_blend_weights.py::build_cli`, parse args `["--simulator-weight-floor", "0.25"]`, assert the namespace has `args.simulator_weight_floor == 0.25` (default 0.0 if absent).
  </behavior>
  <action>
Add the following tests to `tests/test_scoring/test_dynamic_blend.py` in a new section near the end of the file titled `# === KS-08: dynamic_blend simulator-weight floor ===`. Use existing patterns:

```python
# === KS-08: dynamic_blend simulator-weight floor ===

import math
import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from fantasy_sim.scoring.dynamic_blend import (
    SIMULATOR_SOURCE,
    FF_OPPORTUNITY_SOURCE,
    MARKET_HISTORY_SOURCE,
)
# After Task 2, the helper exists. Until then RED.
from fantasy_sim.scoring.dynamic_blend import apply_simulator_weight_floor  # KS-08 new helper


def test_ks08_floor_unchanged_when_sim_above_floor():
    """When simulator weight >= floor, the output is identical to the input."""
    weights = {SIMULATOR_SOURCE: 0.40, FF_OPPORTUNITY_SOURCE: 0.30, MARKET_HISTORY_SOURCE: 0.30}
    out = apply_simulator_weight_floor(weights, floor=0.20)
    assert math.isclose(out[SIMULATOR_SOURCE], 0.40, abs_tol=1e-9)
    assert math.isclose(out[FF_OPPORTUNITY_SOURCE], 0.30, abs_tol=1e-9)
    assert math.isclose(out[MARKET_HISTORY_SOURCE], 0.30, abs_tol=1e-9)


def test_ks08_floor_lifts_when_sim_below_floor():
    """When simulator weight < floor, simulator is lifted to floor and others scale down proportionally."""
    weights = {SIMULATOR_SOURCE: 0.05, FF_OPPORTUNITY_SOURCE: 0.65, MARKET_HISTORY_SOURCE: 0.30}
    out = apply_simulator_weight_floor(weights, floor=0.20)
    assert math.isclose(out[SIMULATOR_SOURCE], 0.20, abs_tol=1e-9)
    # slack = 0.15; other_total = 0.95; scale = 0.80/0.95 ≈ 0.8421
    expected_ff = 0.65 * (0.80 / 0.95)
    expected_market = 0.30 * (0.80 / 0.95)
    assert math.isclose(out[FF_OPPORTUNITY_SOURCE], expected_ff, abs_tol=1e-9)
    assert math.isclose(out[MARKET_HISTORY_SOURCE], expected_market, abs_tol=1e-9)
    # Sum-to-one preserved
    assert math.isclose(sum(out.values()), 1.0, abs_tol=1e-9)


@given(
    raw_sim=st.floats(min_value=0.0, max_value=1.0),
    raw_ff=st.floats(min_value=0.0, max_value=1.0),
    raw_market=st.floats(min_value=0.0, max_value=1.0),
    floor=st.floats(min_value=0.0, max_value=0.5),
)
@settings(max_examples=200, deadline=None)
def test_ks08_floor_preserves_sum_to_one(raw_sim, raw_ff, raw_market, floor):
    """For any normalized weights and floor in [0, 0.5], the floored output sums to 1.0."""
    total = raw_sim + raw_ff + raw_market
    if total <= 1e-9:
        return  # skip degenerate (caller would have hit normalize_weights' total <= 0 guard)
    weights = {
        SIMULATOR_SOURCE: raw_sim / total,
        FF_OPPORTUNITY_SOURCE: raw_ff / total,
        MARKET_HISTORY_SOURCE: raw_market / total,
    }
    out = apply_simulator_weight_floor(weights, floor=floor)
    assert math.isclose(sum(out.values()), 1.0, abs_tol=1e-6)
    # Floor is enforced (allowing for the case where other_total = 0 — degenerate)
    if weights[SIMULATOR_SOURCE] + sum(w for s, w in weights.items() if s != SIMULATOR_SOURCE) > 0:
        assert out[SIMULATOR_SOURCE] >= floor - 1e-6 or out[SIMULATOR_SOURCE] >= weights[SIMULATOR_SOURCE] - 1e-6


def test_ks08_floor_zero_is_no_op():
    """When floor = 0.0, the output equals the input."""
    weights = {SIMULATOR_SOURCE: 0.05, FF_OPPORTUNITY_SOURCE: 0.65, MARKET_HISTORY_SOURCE: 0.30}
    out = apply_simulator_weight_floor(weights, floor=0.0)
    assert math.isclose(out[SIMULATOR_SOURCE], 0.05, abs_tol=1e-9)
    assert math.isclose(out[FF_OPPORTUNITY_SOURCE], 0.65, abs_tol=1e-9)
    assert math.isclose(out[MARKET_HISTORY_SOURCE], 0.30, abs_tol=1e-9)


def test_ks08_artifact_metadata_records_floor():
    """Re-fit artifact records the simulator_weight_floor in metadata for auditability."""
    from fantasy_sim.scoring.dynamic_blend import fit_dynamic_blend_artifact
    from fantasy_sim.data.ensemble import load_ensemble_config
    from fantasy_sim.config.loader import load_defaults
    defaults = load_defaults()
    ensemble_config = load_ensemble_config(defaults)
    # Empty source rows → no buckets fit, but the artifact metadata still records the floor
    artifact = fit_dynamic_blend_artifact(
        [],
        test_season=2024,
        source_seasons=[2022, 2023],
        sims=200,
        scoring="ppr",
        ensemble_config=ensemble_config,
        market_history_config=None,
        simulator_weight_floor=0.30,  # NEW kw-arg in Plan 02 Task 2
    )
    assert artifact.get("simulator_weight_floor") == 0.30


def test_ks08_cli_flag_wired():
    """fit_dynamic_blend_weights.py CLI accepts --simulator-weight-floor."""
    import importlib
    spec = importlib.util.spec_from_file_location(
        "fit_dyn_blend",
        "scripts/fit_dynamic_blend_weights.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parser = module.build_cli()
    args = parser.parse_args(
        [
            "--test-seasons", "2024",
            "--min-source-season", "2022",
            "--sims", "10",
            "--training-years", "4",
            "--scoring", "ppr",
            "--output-dir", "/tmp/test_output",
            "--simulator-weight-floor", "0.25",
        ]
    )
    assert hasattr(args, "simulator_weight_floor")
    assert args.simulator_weight_floor == 0.25
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08
```

Expected: Tests 1, 2, 3, 4 fail with `ImportError: cannot import name 'apply_simulator_weight_floor'` (helper doesn't exist yet). Tests 5, 6 fail because `simulator_weight_floor` kw-arg / CLI flag doesn't exist yet. This is the RED state.

Commit: `test(02-02): add 6 failing tests for KS-08 simulator-weight floor + renormalize math`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08 2>&1 | grep -E "FAILED|ERROR" | head -10</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_floor_unchanged_when_sim_above_floor`
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_floor_lifts_when_sim_below_floor`
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_floor_preserves_sum_to_one`
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_floor_zero_is_no_op`
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_artifact_metadata_records_floor`
    - `tests/test_scoring/test_dynamic_blend.py` contains the literal string `def test_ks08_cli_flag_wired`
    - `uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08` exits NON-ZERO (RED state)
    - `git log -1 --pretty=%s` matches `test(02-02): add 6 failing tests for KS-08`
  </acceptance_criteria>
</task>

<task type="auto" tdd="true">
  <name>Task 2: GREEN — implement `apply_simulator_weight_floor()` helper + plumb into `_artifact_weights()` (flag-gated) + extend `fit_dynamic_blend_artifact()` with `simulator_weight_floor` kw-arg + CLI flag</name>
  <files>
    - src/fantasy_sim/scoring/dynamic_blend.py
    - scripts/fit_dynamic_blend_weights.py
  </files>
  <read_first>
    - src/fantasy_sim/scoring/dynamic_blend.py (`normalize_weights` at 212-225; `_artifact_weights` at 529-542; `fit_dynamic_blend_artifact` at 325-...; `candidate_weight_grid` at 271-286)
    - scripts/fit_dynamic_blend_weights.py (CLI builder + main; pass-through to `fit_dynamic_blend_artifact`)
    - src/fantasy_sim/config/loader.py (`get_phase2_ks_flags` from Plan 01)
    - src/fantasy_sim/data/ensemble/models.py (DynamicBlendConfig — verify `simulator_weight_floor` field; if missing, add it as `simulator_weight_floor: float = 0.0`)
  </read_first>
  <behavior>
    - In `dynamic_blend.py`: add a new module-level helper `apply_simulator_weight_floor(weights, floor) -> dict` that implements the floor + renormalize math.
    - In `dynamic_blend.py::_artifact_weights()`: AFTER the existing `normalize_weights()` call, conditionally apply the floor when `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` is `True`. The floor value comes from either `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor` (preferred, self-contained) OR from `DynamicBlendConfig.simulator_weight_floor` (fallback for callers like `fit_dynamic_blend_artifact` that don't go through the flag).
    - In `dynamic_blend.py::fit_dynamic_blend_artifact()`: add new kw-arg `simulator_weight_floor: float = 0.0`; record it in artifact metadata; constrain the candidate weight grid to compositions with `simulator >= floor` (no other source can offset it).
    - In `scripts/fit_dynamic_blend_weights.py::build_cli()`: add `--simulator-weight-floor <float>` flag (default 0.0); thread it through to `fit_dynamic_blend_artifact()` in `main()`.
    - The runtime `_artifact_weights()` change is gated by the Phase-2 flag; when disabled, behavior is byte-identical to pre-Plan-02.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/scoring/dynamic_blend.py`** — locate the `normalize_weights` function at line 212-225. Insert IMMEDIATELY AFTER it:

```python
def apply_simulator_weight_floor(
    weights: Mapping[str, float],
    floor: float,
) -> dict[str, float]:
    """Apply a simulator-weight floor to a normalized weight dict.

    KS-08 D-06: when ``floor > 0`` and the input simulator weight is below floor,
    lift simulator to floor and proportionally scale down ff_opportunity +
    market_history so the result still sums to 1.0. When the input simulator
    weight is already >= floor, returns a copy unchanged. When ``floor == 0`` or
    the input dict has only the simulator source, returns a copy unchanged.

    Pre-condition: ``weights`` must be normalized (sum to 1.0, all non-negative)
    — this is the post-state of ``normalize_weights(...)``.
    """
    out = dict(weights)
    if floor <= 0 or SIMULATOR_SOURCE not in out:
        return out
    sim = float(out[SIMULATOR_SOURCE])
    if sim >= floor:
        return out
    # Lift simulator to floor; pull others down proportionally
    slack = floor - sim
    other_total = sum(float(w) for s, w in out.items() if s != SIMULATOR_SOURCE)
    if other_total <= 0:
        # Degenerate: only the simulator has weight; can't add to it without violating sum=1
        out[SIMULATOR_SOURCE] = 1.0  # fallback: everything to simulator
        return out
    scale = max(0.0, (other_total - slack) / other_total)
    for source in list(out.keys()):
        if source != SIMULATOR_SOURCE:
            out[source] = float(out[source]) * scale
    out[SIMULATOR_SOURCE] = floor
    return out
```

Locate `_artifact_weights` at line 529-542. Replace its body with:

```python
def _artifact_weights(
    self,
    artifact: dict | None,
    context: SourceContext,
) -> dict[str, float] | None:
    if artifact is None:
        return None
    bucket = artifact.get("buckets", {}).get(context.bucket_key)
    if not isinstance(bucket, dict):
        return None
    raw_weights = bucket.get("weights")
    if not isinstance(raw_weights, dict):
        return None
    normalized = normalize_weights(raw_weights, context.sources)
    if normalized is None:
        return None
    # KS-08 D-06: apply simulator-weight floor when phase2_ks_flags is enabled.
    # The flag block is read once at construction time via DynamicBlendConfig.
    floor = float(self.config.simulator_weight_floor or 0.0)
    if floor > 0:
        normalized = apply_simulator_weight_floor(normalized, floor)
    return normalized
```

Locate `fit_dynamic_blend_artifact` at line 325. Add `simulator_weight_floor: float = 0.0` to its signature (kw-only arg, after `market_history_config`):

```python
def fit_dynamic_blend_artifact(
    source_rows: list[Mapping[str, object]],
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
    ensemble_config: EnsembleConfig,
    market_history_config: MarketHistoryConfig | None,
    simulator_weight_floor: float = 0.0,  # NEW for KS-08 D-06 — Plan 02
) -> dict:
```

In the function body, BEFORE the `for key, rows in sorted(grouped.items()):` loop, add:

```python
# KS-08 D-06: filter the candidate weight grid to compositions that satisfy
# simulator >= floor. The grid is generated per-bucket inside the loop, so we
# define a closure that filters it at use-time.
def _filter_grid(candidates: list[dict[str, float]]) -> list[dict[str, float]]:
    if simulator_weight_floor <= 0:
        return candidates
    return [
        c for c in candidates
        if c.get(SIMULATOR_SOURCE, 0.0) >= simulator_weight_floor - 1e-9
    ]
```

Find the line `for candidate in candidate_weight_grid(sources, config.grid_step):` inside the loop. Replace with:

```python
for candidate in _filter_grid(candidate_weight_grid(sources, config.grid_step)):
```

After the loop concludes and before the `return` statement, find the artifact dict construction. Add `simulator_weight_floor` to the metadata block:

```python
artifact = {
    "schema_version": 1,
    "test_season": test_season,
    "source_seasons": list(source_seasons),
    "sims": sims,
    "scoring": scoring,
    "week_buckets": list(config.week_buckets),
    "grid_step": config.grid_step,
    "min_bucket_rows": config.min_bucket_rows,
    "min_bucket_weeks": config.min_bucket_weeks,
    "fallback": config.fallback,
    "simulator_weight_floor": simulator_weight_floor,  # NEW for KS-08
    "buckets": buckets,
    "fallback_buckets": fallback_buckets,
}
```

(Adapt to the existing local variable names in the file; the goal is a new `simulator_weight_floor` key in the output dict.)

**File 2: `src/fantasy_sim/data/ensemble/models.py`** — verify `DynamicBlendConfig` has a `simulator_weight_floor` field. If absent, add:

```python
@dataclass(frozen=True)
class DynamicBlendConfig:
    enabled: bool = False
    weights_dir: Path | None = None
    week_buckets: tuple[str, ...] = ("1-4", "5-12", "13-18")
    min_bucket_rows: int = 200
    min_bucket_weeks: int = 6
    grid_step: float = 0.05
    fallback: str = "fixed_defaults"
    simulator_weight_floor: float = 0.0  # KS-08 D-06 — Plan 02
```

Update the loader (likely `data/ensemble/__init__.py::load_ensemble_config` or similar) so it reads `ensemble.dynamic_blend.simulator_weight_floor` from defaults.yaml:

```python
DynamicBlendConfig(
    enabled=...,
    weights_dir=...,
    week_buckets=...,
    min_bucket_rows=...,
    min_bucket_weeks=...,
    grid_step=...,
    fallback=...,
    simulator_weight_floor=float(dyn.get("simulator_weight_floor", 0.0)),
)
```

When `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` is true, the loader OVERRIDES `simulator_weight_floor` from the flag block's `floor` field (per Pitfall 8 — the flag block is self-contained). Implementation:

```python
# In the loader
phase2_flags = defaults.get("phase2_ks_flags", {})
ks08_block = phase2_flags.get("ks08_dynamic_blend_simulator_floor", {})
if ks08_block.get("enabled"):
    simulator_weight_floor = float(ks08_block.get("floor", 0.0))
else:
    simulator_weight_floor = float(dyn.get("simulator_weight_floor", 0.0))
```

**File 3: `scripts/fit_dynamic_blend_weights.py`** — locate `build_cli()` (line 41-...). Add to the parser:

```python
parser.add_argument(
    "--simulator-weight-floor",
    type=float,
    default=0.0,
    help="KS-08 D-06: lift simulator weight to at least this value during fit; defaults.yaml ks08 flag block respected at runtime.",
)
```

In `main()`, find the `fit_dynamic_blend_artifact(...)` call. Add the new arg:

```python
artifact = fit_dynamic_blend_artifact(
    source_rows,
    test_season=test_season,
    source_seasons=source_seasons,
    sims=args.sims,
    scoring=args.scoring,
    ensemble_config=ensemble_config,
    market_history_config=market_history_config,
    simulator_weight_floor=args.simulator_weight_floor,
)
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08
```

Expected: All 6 tests pass.

Run full suite to confirm no regressions:
```bash
uv run pytest tests/ -v 2>&1 | tail -5
```

Expected: full suite green; total tests = 2,136 + 6 = 2,142.

Commit: `feat(02-02): KS-08 implement apply_simulator_weight_floor() + plumb into _artifact_weights() + fit_dynamic_blend_weights.py CLI flag (gated behind phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/scoring/dynamic_blend.py` contains the literal string `def apply_simulator_weight_floor(`
    - `src/fantasy_sim/scoring/dynamic_blend.py` contains the literal string `simulator_weight_floor=simulator_weight_floor`
    - `src/fantasy_sim/scoring/dynamic_blend.py` contains the literal string `apply_simulator_weight_floor(normalized, floor)`
    - `scripts/fit_dynamic_blend_weights.py` contains the literal string `--simulator-weight-floor`
    - `src/fantasy_sim/data/ensemble/models.py` (or equivalent) has `simulator_weight_floor: float = 0.0` in `DynamicBlendConfig`
    - `uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08` exits 0 (all 6 tests pass)
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,142 tests)
    - `git log -1 --pretty=%s` matches `feat(02-02): KS-08 implement apply_simulator_weight_floor`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Run KS-08 sweep — 6 ledger A/B entries (3 floors × {bare, full})</name>
  <files>.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md</files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/02-VALIDATION.md (sweep command template)
    - .planning/phases/02-structural-per-stat-calibration/02-CONTEXT.md (D-05 selection rule + ledger label scheme)
  </read_first>
  <behavior>
    - Run 6 A/B validation runs: 3 floors × {bare, full}.
    - Bare entries: `--baseline bare --arm-b-base bare --set ensemble.dynamic_blend.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=<v>`.
    - Full entries: `--baseline defaults --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=<v>`.
    - Tabulate the 6 results; apply D-05 selection rule (smallest floor with hard floor cleared AND non-zero KS Δ improvement on TE/WR fpts).
    - Document the chosen floor + rationale in PROMOTION-NOTES.md ## KS-08.
  </behavior>
  <action>
For each floor `v` in `{0.20, 0.30, 0.40}`, run the bare and full A/B:

```bash
for v in 0.20 0.30 0.40; do
  label_suffix=$(echo $v | sed 's/\.//' | sed 's/^0*//' | xargs printf "%03d")  # 0.20 -> "020"; this becomes "p2.ks08.s020"
  echo "=== Floor $v (label suffix $label_suffix) ==="

  uv run python scripts/validate.py \
    --sims 200 --seasons 2022 2023 2024 --scoring ppr \
    --baseline bare --arm-b-base bare \
    --set ensemble.dynamic_blend.enabled=true \
    --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true \
    --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=$v \
    --label "p2.ks08.s${label_suffix}.bare" \
    2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_s${label_suffix}_bare.log

  uv run python scripts/validate.py \
    --sims 200 --seasons 2022 2023 2024 --scoring ppr \
    --baseline defaults \
    --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=true \
    --set phase2_ks_flags.ks08_dynamic_blend_simulator_floor.floor=$v \
    --label "p2.ks08.s${label_suffix}.full" \
    2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_s${label_suffix}_full.log
done
```

After all 6 runs complete, inspect the ledger:

```bash
uv run python scripts/validate.py --show-ledger | grep -E "^p2\.ks08\." | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_sweep_table.txt
```

For each of the 6 entries, extract:
- `Δ rank_corr` (Arm B − Arm A; hard floor: ≥ -0.005)
- `Δ weekly_mae` (hard floor: ≤ +0.05)
- `Δ stat_ks["TE"]["receptions"]` (primary target — non-zero improvement = negative delta)
- `Δ stat_ks["WR"]["receiving_yards"]` (secondary target)
- `Δ stat_ks["fpts"]` (aggregate fpts KS — TGT-08)

Apply D-05 selection rule:

1. Filter to floors where BOTH bare AND full entries pass hard floor `Δ rank_corr ≥ -0.005 AND Δ weekly_mae ≤ +0.05`.
2. Filter to floors with non-zero KS improvement on TE receptions OR WR receiving_yards (ideally both) in the FULL entry.
3. Pick the SMALLEST passing floor.

Append to `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` under the `## KS-08 (Plan 02)` section:

```markdown
## KS-08 (Plan 02) — <STATUS>

**Sweep results (2026-04-26):**

| Floor | Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[TE][receptions] | Δ stat_ks[WR][receiving_yards] | Δ stat_ks[fpts] | Hard Floor |
|-------|------|-------------|--------------|---------------------------|-------------------------------|-----------------|-----------|
| 0.20  | bare | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |
| 0.20  | full | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |
| 0.30  | bare | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |
| 0.30  | full | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |
| 0.40  | bare | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |
| 0.40  | full | <val>       | <val>        | <val>                     | <val>                         | <val>           | <PASS/FAIL> |

**D-05 Selection:** smallest floor where (a) hard floor passes both arms AND (b) non-zero KS improvement on TE/WR fpts = `<chosen_value>`.

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`. Rationale: <one-sentence>.
```

If NO floor passes BOTH conditions, status = `BLOCKED`. The flag stays `enabled: false`; the runtime helper stays in tree but dormant; document the failure mode and proceed to Plan 03.

If the smallest floor passes ONLY hard floor but NOT KS improvement (a "hard floor passes but KS doesn't move" case), status = `SHIPPED-NO-OP` per Phase 1 D-31 pattern. The flag DOES NOT flip to `true`; document and continue.

If a passing floor is found, status = `SHIPPED`. Proceed to Task 4.

Commit: `chore(02-02): KS-08 sweep — record 6 ledger entries p2.ks08.s{020,030,040}.{bare,full} + sweep selection`
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -c "^p2.ks08." | tr -d ' ' | grep -E "^6$" && grep -q "## KS-08" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && grep -E "Decision:.*(SHIPPED|SHIPPED-NO-OP|BLOCKED)" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md | head -1</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks08."` returns exactly 6 rows (3 floors × 2 modes)
    - Logs directory contains 6 files: `p2_ks08_s{020,030,040}_{bare,full}.log`
    - `.planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md` contains `## KS-08 (Plan 02)` section
    - PROMOTION-NOTES.md `## KS-08` section contains a 6-row sweep table with all four delta columns populated
    - PROMOTION-NOTES.md `## KS-08` section contains a `Decision:` line with one of {SHIPPED, SHIPPED-NO-OP, BLOCKED}
    - `git log -1 --pretty=%s` matches `chore(02-02): KS-08 sweep`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 4: Promotion-state commit — flip flag default + re-fit decision_s200/weights_*.json artifacts (only if SHIPPED)</name>
  <files>
    - config/defaults.yaml
    - src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json
    - src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md (the Task 3 sweep selection)
    - config/defaults.yaml (`phase2_ks_flags.ks08_dynamic_blend_simulator_floor` block from Plan 01)
    - scripts/fit_dynamic_blend_weights.py (CLI with --simulator-weight-floor flag from Task 2)
  </read_first>
  <behavior>
    - Branch on Task 3's status:
      - If `SHIPPED`: flip `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled = true` AND set `floor = <chosen_value>` in defaults.yaml. Re-fit `weights_2023.json` and `weights_2024.json` via `fit_dynamic_blend_weights.py --simulator-weight-floor <chosen_value>`. Verify the new artifacts have `simulator_weight_floor: <chosen_value>` in their metadata.
      - If `SHIPPED-NO-OP`: flag stays `enabled: false`; no artifact re-fit; document the no-op rationale.
      - If `BLOCKED`: flag stays `enabled: false`; runtime code stays in tree but dormant; document the blocker.
    - Append final decision summary to PROMOTION-NOTES.md.
  </behavior>
  <action>
**If status from Task 3 is `SHIPPED`:**

Edit `config/defaults.yaml` `phase2_ks_flags.ks08_dynamic_blend_simulator_floor` block to:

```yaml
  ks08_dynamic_blend_simulator_floor:
    enabled: true   # KS-08 SHIPPED 2026-04-26 — see logs/PROMOTION-NOTES.md ## KS-08
    floor: <chosen_value>  # Smallest passing floor from {0.20, 0.30, 0.40} sweep
```

Re-fit the bundled artifacts:

```bash
uv run python scripts/fit_dynamic_blend_weights.py \
  --test-seasons 2023 2024 \
  --min-source-season 2022 \
  --sims 200 --training-years 4 --scoring ppr \
  --output-dir src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200 \
  --simulator-weight-floor <chosen_value> \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks08_refit.log
```

Verify the artifacts:

```bash
uv run python -c "import json; a23 = json.load(open('src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2023.json')); a24 = json.load(open('src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json')); assert a23['simulator_weight_floor'] == <chosen_value> and a24['simulator_weight_floor'] == <chosen_value>; print('OK')"
```

Run a sanity-check A/B with the promoted defaults to confirm the smallest-passing run still passes (no drift between sweep and post-promotion):

```bash
uv run python scripts/validate.py --sims 200 --seasons 2022 2023 2024 --scoring ppr --baseline defaults --label p2.ks08.promoted
uv run python scripts/validate.py --show-ledger | grep -E "p2.ks08.promoted"
```

The promoted A/B should match the sweep entry within ledger noise (rank_corr Δ < 1e-3). If it diverges by more than 1e-3, the artifact re-fit changed behavior unexpectedly — investigate before commit.

**If status is `SHIPPED-NO-OP` or `BLOCKED`:** flag stays `enabled: false`, no artifact re-fit, no commit changes to defaults.yaml or artifacts.

**Append to PROMOTION-NOTES.md (regardless of status):**

```markdown
**Final decision (2026-04-26):** Status = <STATUS>. <Rationale paragraph including chosen floor (if SHIPPED), bundled artifact regeneration record (if SHIPPED), or rollback rationale (if SHIPPED-NO-OP / BLOCKED).>

**Phase 1 D-25/D-40 commit message format:**
> feat(02-02): KS-08 <STATUS> per D-31 — <Δ rank_corr> rank_corr, <Δ weekly_mae> weekly_mae, <KS Δ on primary target>
>
> Defaults: phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=<true|false>; floor=<value if true>
> Refs: D-05, D-06 (CONTEXT.md)
```

**Run final A/B + full suite + commit:**

```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Final commit:

```
feat(02-02): KS-08 <SHIPPED|SHIPPED-NO-OP|BLOCKED> per D-31 — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[TE][receptions] <val>

Defaults: phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled=<true|false>; floor=<val if SHIPPED>
Bundled artifact regeneration: src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_{2023,2024}.json
Refs: D-05, D-06 (CONTEXT.md), HYPOTHESES.md KS-08 (lines 175-187)
```
  </action>
  <verify>
    <automated>uv run pytest tests/ -v 2>&1 | tail -3 | grep -E "passed|failed" && grep -E "Final decision" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md | head -1 && uv run python -c "import json; a = json.load(open('src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json')); print('floor=', a.get('simulator_weight_floor', 'absent'))"</automated>
  </verify>
  <acceptance_criteria>
    - If status is SHIPPED: `config/defaults.yaml` has `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled: true` AND `floor: <chosen>`
    - If status is SHIPPED: `weights_2023.json` and `weights_2024.json` both contain `"simulator_weight_floor": <chosen>` at top level
    - If status is SHIPPED: `uv run python scripts/validate.py --show-ledger | grep p2.ks08.promoted` returns one row matching the sweep entry within rank_corr Δ < 1e-3
    - If status is SHIPPED-NO-OP or BLOCKED: `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled` stays `false` in defaults.yaml; artifacts unchanged
    - PROMOTION-NOTES.md `## KS-08` section contains a `Final decision` paragraph with the status word
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,142 tests)
    - `git log -1 --pretty=%s` matches `feat(02-02): KS-08 (SHIPPED|SHIPPED-NO-OP|BLOCKED)`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 4 tasks complete:

1. `git log --oneline -10` shows 4 new commits prefixed `(02-02)` (test, feat, chore, feat).
2. If SHIPPED: `cat config/defaults.yaml | grep -A 2 "ks08_dynamic_blend_simulator_floor:"` shows `enabled: true` and `floor: <chosen>`.
3. `uv run pytest tests/test_scoring/test_dynamic_blend.py -v -k ks08` exits 0 (6 tests pass).
4. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks08."` returns 6 sweep rows + 1 promoted row (if SHIPPED) = 7 total, or 6 (if SHIPPED-NO-OP/BLOCKED).
5. `uv run pytest tests/ -v` exits 0; total test count = 2,142.
6. `cat .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md | grep -E "## KS-08|Decision:|Final decision"` shows the sweep table + decisions.

KS-08 status recorded. Plan 03 (KS-09) may now proceed.
</verification>

<must_haves>
  truths:
    - "Per D-05: KS-08 sweep is 3-point {0.20, 0.30, 0.40} smallest-passing — pickup must clear hard floor AND show non-zero KS Δ improvement on TE/WR fpts"
    - "Per D-06 + Pitfall 2: floor + renormalize MUST happen AFTER `normalize_weights(...)` — pre-normalize flooring is mathematically wrong because raw artifact weights are not yet sum-to-1"
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled`; per Phase 1 D-25/D-40 promotion-state commit message captures status word + Δ values"
    - "Per Pitfall 7: re-fit `decision_s200/weights_*.json` artifacts with the chosen floor — without re-fit, the artifacts retain the unconstrained-fit weights and the runtime floor will fight against them at inference time, producing inconsistent A/B results"
    - "Per Pitfall 8: BOTH `phase2_ks_flags.ks08_dynamic_blend_simulator_floor.enabled = true` AND `floor = <chosen>` ship in the same promotion commit; runtime reads `floor` directly from the flag block"
    - "Per C-09: 2,142-test suite stays green throughout (2,131 pre-Phase-2 + 5 from Plan 01 + 6 from Plan 02 Task 1)"
    - "Per C-10: KS-08 affects post-sim blend weights at the bucket level only — QB carry/scramble/yards invariants from `feedback_qb_calibration.md` are upstream and unaffected"
  artifacts:
    - path: "src/fantasy_sim/scoring/dynamic_blend.py"
      provides: "apply_simulator_weight_floor() helper + plumbed into _artifact_weights() (gated behind phase2_ks_flags.ks08); fit_dynamic_blend_artifact() accepts simulator_weight_floor kw-arg + records in artifact metadata"
      contains: "def apply_simulator_weight_floor"
    - path: "scripts/fit_dynamic_blend_weights.py"
      provides: "--simulator-weight-floor CLI flag wired through to fit_dynamic_blend_artifact()"
      contains: "--simulator-weight-floor"
    - path: "src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/weights_2024.json"
      provides: "Re-fit artifact with chosen floor baked in (only if SHIPPED)"
      contains: "simulator_weight_floor"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-08 sweep table (6 rows) + D-05 selection + final decision word + decision rationale"
      contains: "Final decision"
</must_haves>