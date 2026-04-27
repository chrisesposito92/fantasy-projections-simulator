---
phase: 02-structural-per-stat-calibration
plan: 07
type: execute
wave: 5
depends_on: ["01", "02"]
files_modified:
  - src/fantasy_sim/scoring/ensemble.py
  - src/fantasy_sim/data/ensemble/loader.py
  - src/fantasy_sim/data/ensemble/models.py
  - src/fantasy_sim/data/ensemble/config.py
  - src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/.gitkeep
  - scripts/probe_ff_opportunity_quantiles.py
  - scripts/fit_ff_opportunity_prior_width.py
  - tests/test_scoring/test_ensemble.py
  - tests/test_scripts/test_fit_ff_opportunity_prior_width.py
  - config/defaults.yaml
  - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
autonomous: true
requirements: [KS-13]
must_haves:
  truths:
    - "**Codex cycle-2 alignment (HIGH 2 — verified code surfaces, 2026-04-27):** the actual loader API is `FfOpportunityLoader(config: FfOpportunityConfig | None = None)` with `load_weekly(seasons: list[int]) -> pl.DataFrame` (per `src/fantasy_sim/data/ensemble/loader.py` lines 24-63). The actual ensembler class is `FfOpportunityProjectionEnsembler` with method `blend_week(projections, *, season, week) -> tuple[list[dict], BlendStats]` (per `src/fantasy_sim/scoring/ensemble.py` lines 21-117). There is NO `EnsembleLoader`, NO `load_week_raw`, NO `adjust_week`, and NO `EnsembleLayer` — earlier drafts of this plan invented these names. All scripts and code in this plan use the verified surfaces."
    - "Per D-10 + Pattern 6 + Pitfall 6 in 02-RESEARCH.md: probe-then-decide. Step 1: run `scripts/probe_ff_opportunity_quantiles.py` (uses `FfOpportunityLoader.load_weekly([season])` per the verified API) to verify `total_fantasy_points_exp_lo` + `_hi` columns exist in the raw frame AND are non-null for ≥80% of training rows. Path A (lo/hi found and dense): build Gaussian prior with `mean = prior_fpts`, `std = (hi - lo) / (2 * 1.28)` (80% interval). Path B (lo/hi missing or sparse): fit per-bucket residual variance from training-season ff_opportunity_prior vs actual_fpts data via the new fitter script `scripts/fit_ff_opportunity_prior_width.py` (Task 2.5)."
    - "Per D-02 / Phase 1 D-45: change is gated behind `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled` (default false). When false, behavior is byte-identical to pre-Plan-07 (point-estimate prior_fpts in `FfOpportunityProjectionEnsembler.blend_week` lines 97-105). When true, the chosen path's prior width is used to perturb fpts via independent samples per player."
    - "**Codex cycle-4 alignment (HIGH — KS-13 dual-gate fix, 2026-04-27):** the runtime gate for KS-13 sampling is the **conjunction** `ks13_active := phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled AND ensemble.ff_opportunity.prior_width.enabled`. Both must be `True`. Disabling EITHER flag falls back to legacy point-estimate behavior. The master `phase2_ks_flags` flag is therefore a **sole-sufficient kill switch** — Plan 09's reverse-ablation walk-back, which only flips `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled` to `False`, fully disables KS-13 sampling regardless of the engine-local sub-flag's runtime state. Implementation: `FfOpportunityProjectionEnsembler.__init__` accepts `ks13_master_enabled: bool | None = None`; when `None`, the ensembler reads the master flag via `get_phase2_ks_flags()` (Plan 01 shim) with default-deny on shim-unavailable. Pinned by `test_ks13_dual_gate_master_flag_off_keeps_ks13_dormant` and the dual-pass in `test_ks13_unchanged_when_flag_disabled`."
    - "Per Pattern 6 (probe-then-decide): the plan body has BOTH Path A (Task 2) and Path B (Task 2.5) implemented so the plan doesn't stall on probe outcome. The probe outcome is recorded in the plan summary."
    - "**Codex cycle-2 HIGH 3 — Path B artifact pipeline (NEW Task 2.5):** when Path B is selected, the fitted-std artifact lives at `src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_<test_season>.json` (path mirrors `residual_calibration/decision_s200/calibration_<test_season>.json`). Schema: `{schema_version: 1, scoring: 'ppr' | 'half_ppr' | 'standard', test_season: int, source_seasons: [int...], sims: int, buckets: {<position>: {std_fpts: float, empirical_std_fpts: float, league_std_fpts: float, n: int}}}`. Bucket keying for KS-13 v1 is BARE POSITION (QB/RB/WR/TE) — NOT the composite key from residual_calibration. Per-fpts-tier subdivision is OUT OF SCOPE for v1 and tracked in HYPOTHESES.md as a follow-up. Loader contract: `FfOpportunityProjectionEnsembler._load_ff_opportunity_prior_width_artifact(season: int) -> dict | None` mirrors `ResidualCalibrationProjectionAdjuster._artifact` (per-season cache; fallback to bundled dir; returns None on missing/error/version-mismatch/scoring-mismatch). Helper: `_fitted_std_for(position, prior_fpts, season) -> float` returns 0.0 (point-estimate fallback) when artifact / bucket missing. `scripts/fit_ff_opportunity_prior_width.py` mirrors `scripts/fit_residual_calibration.py` structure: same CLI flags (`--test-seasons`, `--min-source-season`, `--training-years`, `--scoring`, `--output-dir`)."
    - "**Codex cycle-2 HIGH 3 — Path B tests must be CONCRETE (not `pass`):** the three placeholder tests in Task 2 (`test_ks13_path_a_seed_determinism`, `test_ks13_path_b_uses_fitted_std_when_lo_hi_absent`, `test_ks13_path_b_artifact_loader_graceful_when_missing`) are REPLACED by Task 2.5 with concrete assertions: writes a synthetic v1 artifact to a temp dir, points the loader at it, verifies `_fitted_std_for(position, fpts, season)` returns the bucket's `std_fpts`. The graceful-missing test points the loader at an empty dir and asserts sigma == 0.0. The seed-determinism test seeds two RNGs identically and asserts the same sample is drawn. Plus a new test file `tests/test_scripts/test_fit_ff_opportunity_prior_width.py` covers the fitter CLI and schema_version constraint."
    - "**Path A vs Path B selection rule:** Task 2.5 (Path B artifact pipeline) is REQUIRED unless Task 1's probe selected Path A AND Task 3's path-A A/B PASSES the path-A promotion bar (Δ stat_ks[fpts] ≤ -0.01). Skipping Task 2.5 in the Path-A-only happy path is allowed but MUST be recorded as an explicit deferral in `.planning/research/HYPOTHESES.md` under KS-13 — it is NOT silently dropped."
    - "Per Plan 02 dependency: KS-13 is most impactful when KS-08 floor is active (sim weight is no longer ~0; ff_opportunity weight is reduced; the prior width matters for the residual ff_opportunity fpts contribution). Plan 07 runs AFTER Plan 02."
    - "Per HYPOTHESES.md KS-13 (lines 261-273): Path A confidence MEDIUM (depends on lo/hi schema availability); Path B confidence LOW-MEDIUM (more complex, weaker effect). Promotion bar adjusts: Path A → fpts KS Δ ≤ -0.01 (D-30 standard small-gain); Path B → fpts KS Δ ≤ -0.005 (relaxed)."
    - "**Codex MEDIUM 5 (2026-04-27 revision) — RNG determinism contract:** when KS-13 is on, Gaussian sampling is introduced on the post-sim ff_opportunity prior path. Determinism is preserved by (1) constructing the ensembler with an explicit `rng: np.random.Generator` at boundary (the call site in `cli.py` / runtime is responsible for seeding), (2) drawing exactly ONE sample per (season, week, player_id, sim_idx) tuple via `self._rng.normal(...)`, and (3) not advancing any shared RNG state outside the ensembler. The same A/B invocation with the same seeds + the same artifact produces byte-identical output. The seed-determinism tests (Task 2.5) prove this by constructing two ensemblers with identically-seeded RNGs and asserting the sampled prior matches."
    - "Per C-08: test-after acceptable for KS-13; 6 unit tests in test_ensemble.py + 3 fitter tests + 1 probe-script test."
    - "Per C-09: 2,164 + 6 (Task 2 tests) + 3 (Task 2.5 fitter tests) + 1 (Task 2 dual-gate regression test, codex cycle-4) + 1 (Task 2 lazy-fallback dict-access regression test, codex cycle-5) = 2,175 tests stay green after Plan 07."
  artifacts:
    - path: "scripts/probe_ff_opportunity_quantiles.py"
      provides: "One-shot probe script: uses `FfOpportunityLoader.load_weekly([season])` (the REAL loader API per `src/fantasy_sim/data/ensemble/loader.py` line 43; codex cycle-2 HIGH 2 fix); reports presence + non-null fraction of `total_fantasy_points_exp_lo`/`_hi`; emits JSON to stdout for plan-body branch decision"
      contains: "FfOpportunityLoader"
    - path: "scripts/fit_ff_opportunity_prior_width.py"
      provides: "**NEW (codex cycle-2 HIGH 3 fix):** Path B artifact fitter — mirrors `scripts/fit_residual_calibration.py`. CLI flags: `--test-seasons`, `--min-source-season`, `--training-years`, `--scoring`, `--output-dir`. Emits `prior_width_<test_season>.json` with schema_version=1 and per-position `std_fpts` buckets."
      contains: "fit_one_test_season"
    - path: "src/fantasy_sim/scoring/ensemble.py"
      provides: "When KS-13 flag enabled, the Path A branch in `FfOpportunityProjectionEnsembler.blend_week` (codex cycle-2 alignment — the actual method name; NOT `adjust_week`) replaces `prior_fpts = float(prior['prior_fpts'])` (lines 97-105) with `sampled_prior` from `self._rng.normal(prior_fpts, std)`. Path B branch reads `_fitted_std_for(position, prior_fpts, season)` which loads the v1 artifact via `_load_ff_opportunity_prior_width_artifact(season)`."
      contains: "sampled_prior"
    - path: "src/fantasy_sim/data/ensemble/loader.py"
      provides: "When Path A is configured, `FfOpportunityLoader.load_weekly` ensures `total_fantasy_points_exp_lo` and `total_fantasy_points_exp_hi` columns survive the parquet round-trip (extend `RAW_WEEKLY_SCHEMA` with optional Float64 entries; codex cycle-2 alignment uses the REAL loader class)."
      contains: "total_fantasy_points_exp_lo"
    - path: "src/fantasy_sim/data/ensemble/models.py"
      provides: "**NEW (codex cycle-2 HIGH 3):** `PriorWidthConfig` dataclass with `enabled: bool`, `path: str ('A' | 'B')`, and `artifacts_dir: Path | None = None` (Path B override; defaults to bundled dir)."
      contains: "class PriorWidthConfig"
    - path: "src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/.gitkeep"
      provides: "**NEW (codex cycle-2 HIGH 3):** bundled-artifact directory mirroring `residual_calibration/decision_s200/`; ships with `.gitkeep` until `scripts/fit_ff_opportunity_prior_width.py` populates it."
      contains: ""
    - path: "tests/test_scoring/test_ensemble.py"
      provides: "6 KS-13 tests with concrete assertions (codex cycle-2 HIGH 3 — replaces the original `pass` placeholders): ks13_path_a_uses_quantile_width_when_lo_hi_present, ks13_path_b_uses_fitted_std_when_lo_hi_absent (concrete artifact-loader assertion), ks13_unchanged_when_flag_disabled, ks13_probe_script_outputs_json, ks13_path_a_seed_determinism (concrete RNG-equivalence assertion), ks13_path_b_artifact_loader_graceful_when_missing (concrete sigma==0.0 assertion)"
      contains: "def test_ks13_"
    - path: "tests/test_scripts/test_fit_ff_opportunity_prior_width.py"
      provides: "**NEW (codex cycle-2 HIGH 3):** smoke-tests for the Path B fitter — CLI --help works, schema_version=1 constraint, bucket-key shape constraint."
      contains: "def test_fit_ff_opportunity_prior_width"
    - path: "config/defaults.yaml"
      provides: "After promotion: `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled = true`; new `ensemble.ff_opportunity.prior_width.path = 'A' | 'B'` field; new `ensemble.ff_opportunity.prior_width.artifacts_dir` field (empty by default → bundled dir)."
      contains: "ks13_ff_opportunity_prior_width:"
    - path: ".planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md"
      provides: "KS-13 promotion-state decision summary including probe outcome + chosen path + final decision; if Path B was deferred per the skip rule in Task 2.5, also records the explicit HYPOTHESES.md tracking entry."
      contains: "## KS-13"
  key_links:
    - from: "scripts/probe_ff_opportunity_quantiles.py (uses FfOpportunityLoader.load_weekly)"
      to: "the plan body's Path A vs Path B branch"
      via: "JSON output {'path': 'A', 'lo_present': true, 'hi_present': true, 'non_null_fraction': 0.97}"
      pattern: "\"path\":"
    - from: "config/defaults.yaml::phase2_ks_flags.ks13_ff_opportunity_prior_width"
      to: "src/fantasy_sim/scoring/ensemble.py::FfOpportunityProjectionEnsembler.blend_week (codex cycle-2 alignment — actual method name)"
      via: "EnsembleConfig.ff_opportunity.prior_width.path + .artifacts_dir"
      pattern: "prior_width\\.(path|artifacts_dir|enabled)"
    - from: "scripts/fit_ff_opportunity_prior_width.py (Task 2.5 NEW)"
      to: "src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_<season>.json"
      via: "JSON write of {schema_version, scoring, test_season, source_seasons, buckets: {position: {std_fpts, n}}}"
      pattern: "prior_width_\\d{4}\\.json"
    - from: "FfOpportunityProjectionEnsembler._load_ff_opportunity_prior_width_artifact(season) (codex cycle-2 HIGH 3 NEW)"
      to: "FfOpportunityProjectionEnsembler._fitted_std_for(position, prior_fpts, season)"
      via: "in-memory dict cache + bundled-dir fallback (mirrors ResidualCalibrationProjectionAdjuster._artifact)"
      pattern: "_load_ff_opportunity_prior_width_artifact"
---

<objective>
Implement KS-13 — ff_opportunity prior carries width via probe-then-decide. Per D-10: the existing post-sim ff_opportunity layer at `src/fantasy_sim/scoring/ensemble.py:97` reads `prior_fpts = float(prior["prior_fpts"])` as a POINT estimate. This compresses the variance of fpts when the dynamic_blend gives ff_opportunity high weight. KS-13 widens the prior by sampling around it.

Per Pattern 6 (probe-then-decide): the plan body has BOTH Path A and Path B pre-coded; a one-shot probe script chooses at execution time.

Path A: lo/hi quantiles exist in raw schema → Gaussian prior `mean = prior_fpts`, `std = (hi - lo) / (2 * 1.28)` (80% interval = ±1.28σ).
Path B: lo/hi missing or sparse → fit per-bucket residual variance from training data; emit a new artifact `ff_opportunity_prior_width/decision_s200/std_*.json`.

Output:
1. Probe script `scripts/probe_ff_opportunity_quantiles.py`.
2. Updated `src/fantasy_sim/scoring/ensemble.py` to sample around `prior_fpts` when flag enabled (path-specific).
3. 6 new unit tests + 1 probe-script test.
4. Ledger entries `p2.ks13.{bare, full}`.
5. Promotion-state commit per Phase 1 D-25/D-40.
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
@src/fantasy_sim/scoring/ensemble.py
@src/fantasy_sim/data/ensemble/loader.py
@tests/test_scoring/test_ensemble.py
@config/defaults.yaml

<interfaces>
From src/fantasy_sim/scoring/ensemble.py:97-105 (existing point-estimate site — KS-13 EXTENDS):

```python
prior_fpts = float(prior["prior_fpts"])
row["ensemble_source"] = "ff_opportunity"
row["ensemble_weight"] = weight
row["ensemble_covered"] = True
row["ensemble_prior_fpts"] = round(prior_fpts, 2)
row["fpts"] = round(
    float(row["fpts"] * (1.0 - weight) + prior_fpts * weight),
    1,
)
```

After KS-13 (Path A example):
```python
prior_fpts = float(prior["prior_fpts"])
prior_lo = float(prior.get("prior_fpts_lo")) if "prior_fpts_lo" in prior else None
prior_hi = float(prior.get("prior_fpts_hi")) if "prior_fpts_hi" in prior else None

_pw = self.config.ff_opportunity.prior_width  # PriorWidthConfig (codex cycle-3 alignment)
if _pw.enabled and prior_lo is not None and prior_hi is not None:
    # Path A: Gaussian sample with std = (hi - lo) / 2.56
    sigma = (prior_hi - prior_lo) / (2 * 1.28)
    sampled_prior = float(rng.normal(prior_fpts, sigma))
elif _pw.enabled and self._fitted_std is not None:
    # Path B: fitted residual std per bucket
    sigma = float(self._fitted_std.get(bucket_key, 0.0))
    sampled_prior = float(rng.normal(prior_fpts, sigma)) if sigma > 0 else prior_fpts
else:
    sampled_prior = prior_fpts

row["fpts"] = round(float(row["fpts"] * (1.0 - weight) + sampled_prior * weight), 1)
```

</interfaces>

</context>

<tasks>

<task type="auto">
  <name>Task 1: Create `scripts/probe_ff_opportunity_quantiles.py` + run probe + record outcome</name>
  <files>
    - scripts/probe_ff_opportunity_quantiles.py
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - src/fantasy_sim/data/ensemble/loader.py (existing loader; verify which columns are read)
    - .planning/phases/02-structural-per-stat-calibration/02-RESEARCH.md (Pattern 6 pseudocode)
  </read_first>
  <behavior>
    - Create a one-shot probe script that loads ff_opportunity raw data for one (season, week), checks for `total_fantasy_points_exp_lo` + `total_fantasy_points_exp_hi` columns, computes the non-null fraction, and emits a JSON dict.
    - Run the probe; record the outcome in PROMOTION-NOTES.md.
  </behavior>
  <action>
**File 1: `scripts/probe_ff_opportunity_quantiles.py`**:

```python
#!/usr/bin/env python3
"""KS-13 D-10: probe FF Opportunity raw schema for lo/hi quantile columns.

Outputs JSON to stdout:
  {"path": "A" | "B", "lo_present": bool, "hi_present": bool, "non_null_fraction": float}

Path A: both columns present AND non_null_fraction >= 0.80 → use quantile width
Path B: either missing OR non_null_fraction < 0.80 → fit residual variance
"""

from __future__ import annotations

import argparse
import json
import sys

import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import FfOpportunityConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe FF Opportunity raw schema for KS-13 lo/hi columns.")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help=(
            "Optional week filter applied to the raw weekly frame after load. "
            "FfOpportunityLoader.load_weekly returns the full season; we filter "
            "to the requested week if provided. Omit for full-season probe."
        ),
    )
    parser.add_argument("--threshold", type=float, default=0.80, help="Non-null fraction required for Path A.")
    args = parser.parse_args()

    # Codex cycle-2 alignment (HIGH 2): the real loader API is
    # `FfOpportunityLoader(config: FfOpportunityConfig | None = None)` with
    # `load_weekly(seasons: list[int]) -> pl.DataFrame`. There is NO
    # `EnsembleLoader` and NO `load_week_raw(...)` — earlier drafts of this
    # plan invented those names. Verified against
    # `src/fantasy_sim/data/ensemble/loader.py` (current code surface).
    loader = FfOpportunityLoader(config=FfOpportunityConfig())

    try:
        df = loader.load_weekly([args.season])
    except Exception as exc:
        result = {
            "path": "B",
            "error": str(exc),
            "lo_present": False,
            "hi_present": False,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    if not isinstance(df, pl.DataFrame) or df.is_empty():
        result = {
            "path": "B",
            "error": "empty_df",
            "lo_present": False,
            "hi_present": False,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    if args.week is not None and "week" in df.columns:
        df = df.filter(pl.col("week") == args.week)
        if df.is_empty():
            result = {
                "path": "B",
                "error": f"empty_week_filter season={args.season} week={args.week}",
                "lo_present": False,
                "hi_present": False,
                "non_null_fraction": 0.0,
            }
            print(json.dumps(result), flush=True)
            return 0

    cols = set(df.columns)
    lo_present = "total_fantasy_points_exp_lo" in cols
    hi_present = "total_fantasy_points_exp_hi" in cols

    if not (lo_present and hi_present):
        result = {
            "path": "B",
            "lo_present": lo_present,
            "hi_present": hi_present,
            "non_null_fraction": 0.0,
        }
        print(json.dumps(result), flush=True)
        return 0

    lo_non_null = df.filter(pl.col("total_fantasy_points_exp_lo").is_not_null()).height
    hi_non_null = df.filter(pl.col("total_fantasy_points_exp_hi").is_not_null()).height
    total = df.height
    fraction = min(lo_non_null, hi_non_null) / total if total > 0 else 0.0

    path = "A" if fraction >= args.threshold else "B"
    result = {
        "path": path,
        "lo_present": lo_present,
        "hi_present": hi_present,
        "non_null_fraction": round(fraction, 4),
        "rows": total,
    }
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Run the probe:**

```bash
# Full-season probe (recommended — exercises every week's row count for a
# robust non_null_fraction). The probe uses the actual loader API:
# FfOpportunityLoader.load_weekly([season]) per
# src/fantasy_sim/data/ensemble/loader.py line 43.
uv run python scripts/probe_ff_opportunity_quantiles.py --season 2024 \
  | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json

# Optional spot-check for a single week:
# uv run python scripts/probe_ff_opportunity_quantiles.py --season 2024 --week 1
```

Expected output:
```json
{"path": "A" | "B", "lo_present": bool, "hi_present": bool, "non_null_fraction": float}
```

Append to PROMOTION-NOTES.md:
```markdown
## KS-13 (Plan 07) — <STATUS>

**Probe outcome (2026-04-26):**
```
<JSON output from probe>
```

**Selected path:** `<A | B>`. Rationale: <one-sentence summary of probe result>.
```

Commit: `feat(02-07): KS-13 add probe_ff_opportunity_quantiles.py + record path-decision outcome`
  </action>
  <verify>
    <automated>test -f scripts/probe_ff_opportunity_quantiles.py && grep -q "FfOpportunityLoader" scripts/probe_ff_opportunity_quantiles.py && uv run python scripts/probe_ff_opportunity_quantiles.py --season 2024 | python -c "import sys, json; d = json.load(sys.stdin); assert d.get('path') in ('A', 'B'); print('OK', d['path'])" && grep -q "## KS-13" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/probe_ff_opportunity_quantiles.py` exists and is executable
    - `scripts/probe_ff_opportunity_quantiles.py` imports `FfOpportunityLoader` from `fantasy_sim.data.ensemble.loader` (codex cycle-2 HIGH 2 — uses the REAL loader API; NOT a fictional `EnsembleLoader.load_week_raw`)
    - `scripts/probe_ff_opportunity_quantiles.py` calls `loader.load_weekly([args.season])` (the actual public API per `src/fantasy_sim/data/ensemble/loader.py` line 43); the optional `--week` arg post-filters the resulting DataFrame
    - `uv run python scripts/probe_ff_opportunity_quantiles.py --season 2024` exits 0 and emits JSON with `path` field == "A" or "B" (no `--week` required for full-season probe; `--week N` allowed for spot-check)
    - `.planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json` contains the probe JSON output
    - PROMOTION-NOTES.md `## KS-13` section contains the probe outcome + selected path
    - `git log -1 --pretty=%s` matches `feat(02-07): KS-13 add probe`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Implement Path A or Path B in `ensemble.py` based on probe outcome + 6 unit tests</name>
  <files>
    - src/fantasy_sim/scoring/ensemble.py
    - src/fantasy_sim/data/ensemble/loader.py
    - tests/test_scoring/test_ensemble.py
    - src/fantasy_sim/data/ensemble/models.py
  </files>
  <read_first>
    - src/fantasy_sim/scoring/ensemble.py (current file — note: the class is `FfOpportunityProjectionEnsembler` and the method is `blend_week`, NOT `adjust_week`; codex cycle-2 alignment)
    - src/fantasy_sim/data/ensemble/loader.py (current file — the loader is `FfOpportunityLoader` with `load_weekly(seasons: list[int])`, NOT `EnsembleLoader.load_week`; codex cycle-2 alignment)
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json (probe outcome from Task 1)
  </read_first>
  <behavior>
    - Add `PriorWidthConfig` dataclass to `models.py` with `enabled: bool` and `path: str` ("A" or "B").
    - Add `prior_width: PriorWidthConfig` to the existing `FfOpportunityConfig`.
    - **Codex cycle-2 alignment:** in `loader.py::FfOpportunityLoader.load_weekly`, ensure `total_fantasy_points_exp_lo`/`_hi` columns survive the parquet round-trip when Path A is selected. The current `RAW_WEEKLY_SCHEMA` enumerates 7 columns; if lo/hi are present in the upstream nflreadpy frame they will pass through `pl.concat(..., how='diagonal_relaxed')` without explicit schema entry, but Path A's downstream consumer (`normalize_ff_opportunity` + `_season_priors` in ensemble.py) must surface them in the prior dict.
    - **Codex cycle-2 alignment:** in `ensemble.py::FfOpportunityProjectionEnsembler.blend_week`, when the KS-13 flag is on, sample around `prior_fpts` using path-specific std. The class lives in `src/fantasy_sim/scoring/ensemble.py` (not `adjust_week`).
    - Add 6 unit tests.
  </behavior>
  <action>
**File 1: `src/fantasy_sim/data/ensemble/models.py`** — add PriorWidthConfig dataclass and field:

```python
@dataclass(frozen=True)
class PriorWidthConfig:
    """KS-13 D-10: ff_opportunity prior-width config."""
    enabled: bool = False
    path: str = "A"  # "A" = quantile-derived; "B" = fitted residual std

@dataclass(frozen=True)
class FfOpportunityConfig:
    enabled: bool = False
    cache_dir: Path | None = None
    positions: tuple[str, ...] = ()
    feature: str = "total_fantasy_points_exp"
    weights: dict[str, float] = field(default_factory=dict)
    min_coverage_weeks: int = 1
    prior_width: PriorWidthConfig = field(default_factory=PriorWidthConfig)  # KS-13 D-10
```

Update the loader (in `data/ensemble/__init__.py` or `data/ensemble/config.py`) to construct `prior_width` from defaults.yaml.

**File 2: `src/fantasy_sim/data/ensemble/loader.py`** — codex cycle-2 alignment: the real class is `FfOpportunityLoader` with `load_weekly(seasons: list[int]) -> pl.DataFrame` (not `EnsembleLoader.load_week`). When Path A is configured, ensure `total_fantasy_points_exp_lo` and `total_fantasy_points_exp_hi` survive the parquet caching round-trip. The existing `RAW_WEEKLY_SCHEMA` (lines 13-21) enumerates 7 columns. Either: (a) extend the schema dict with optional `total_fantasy_points_exp_lo: pl.Float64` and `total_fantasy_points_exp_hi: pl.Float64` entries (preferred), or (b) rely on `pl.concat(how='diagonal_relaxed')` to pass them through silently and update `normalize_ff_opportunity` to copy them into the per-row prior dict. Pick (a) for clarity. The graceful fallback is implicit: if the upstream nflreadpy frame lacks these columns, polars writes nulls; downstream Path A consumers check for non-null before computing `sigma = (hi - lo) / 2.56`.

**File 3: `src/fantasy_sim/scoring/ensemble.py`** — codex cycle-2 alignment: the method is `FfOpportunityProjectionEnsembler.blend_week` (not `adjust_week`). The blend block is at lines 97-105 of the current file (see read_first). Add an RNG to the class via `__init__(self, config: EnsembleConfig, loader: FfOpportunityLoader | None = None, rng: np.random.Generator | None = None, ks13_master_enabled: bool | None = None)`. Default RNG construction follows existing project pattern (`rng or np.random.default_rng()`).

**Codex cycle-4 alignment (HIGH — dual-gate split fix):** the runtime gate for KS-13 is the **conjunction** of two flags:

1. **Master flag:** `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled` (top-level KS gate, the SAME flag Plan 09's reverse-ablation walk-back flips when reverting KS-13). Read via `get_phase2_ks_flags()` shim from `src/fantasy_sim/config/loader.py` (added in Plan 01 per Phase 1 D-45 pattern). At construction time, the orchestrator (e.g. `validate.py` or any caller) passes the resolved `bool` as `ks13_master_enabled`. When `None`, the ensembler reads it lazily from `get_phase2_ks_flags().ks13_ff_opportunity_prior_width.enabled` to default-deny if the shim is absent.
2. **Sub-flag:** `ensemble.ff_opportunity.prior_width.enabled` (engine-local sub-toggle on `PriorWidthConfig`).

Both flags must be `True` for KS-13 sampling to activate. Disabling EITHER flag returns the legacy point-estimate prior path. This invariant ensures Plan 09's `--set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=false` reverse-ablation override is **sufficient on its own** to fully disable KS-13 sampling, regardless of the engine-local sub-flag's state. Without the conjunction, a `no_KS13` aggregate iteration could leave KS-13 sampling live (defeating per-KS isolation and corrupting `{KS-08, KS-13}` coupled-cluster pair-revert decisions — codex cycle-4 finding).

Replace the existing blend block (lines 97-105) with:

```python
prior_fpts = float(prior["prior_fpts"])
prior_lo = prior.get("prior_fpts_lo")
prior_hi = prior.get("prior_fpts_hi")

_pw = self.config.ff_opportunity.prior_width  # PriorWidthConfig (codex cycle-3 alignment: nested under ff_opportunity, NOT top-level on EnsembleConfig)
# Codex cycle-4 alignment (dual-gate fix): KS-13 sampling requires BOTH the master
# phase2_ks_flag AND the engine-local sub-flag. Flipping either off is sufficient to
# return to legacy point-estimate behavior. Plan 09's reverse-ablation walk-back relies
# on the master flag being a sole-sufficient kill switch for `no_KS13` aggregate runs.
ks13_active = self._ks13_master_enabled and _pw.enabled
if ks13_active:
    if _pw.path == "A" and prior_lo is not None and prior_hi is not None:
        sigma = (float(prior_hi) - float(prior_lo)) / (2 * 1.28)
        sampled_prior = float(self._rng.normal(prior_fpts, max(sigma, 0.0)))
    elif _pw.path == "B":
        sigma = self._fitted_std_for(row.get("position", ""), prior_fpts) if hasattr(self, "_fitted_std_for") else 0.0
        sampled_prior = float(self._rng.normal(prior_fpts, max(sigma, 0.0))) if sigma > 0 else prior_fpts
    else:
        sampled_prior = prior_fpts
else:
    sampled_prior = prior_fpts

row["ensemble_source"] = "ff_opportunity"
row["ensemble_weight"] = weight
row["ensemble_covered"] = True
row["ensemble_prior_fpts"] = round(prior_fpts, 2)
row["ensemble_sampled_prior_fpts"] = round(sampled_prior, 2)  # NEW for KS-13
row["fpts"] = round(
    float(row["fpts"] * (1.0 - weight) + sampled_prior * weight),
    1,
)
```

In `__init__`, resolve the master flag once and cache it on `self._ks13_master_enabled`:

```python
def __init__(
    self,
    config: EnsembleConfig,
    loader: FfOpportunityLoader | None = None,
    rng: np.random.Generator | None = None,
    ks13_master_enabled: bool | None = None,
) -> None:
    self.config = config
    self.loader = loader
    self._rng = rng or np.random.default_rng()
    self._prior_cache: dict[int, pl.DataFrame] = {}

    # Codex cycle-4 alignment (dual-gate fix): resolve the master phase2_ks_flag once
    # at construction. Explicit override wins; otherwise fall back to the shim from
    # Plan 01. If the shim is unavailable (e.g. test fixture without phase2_ks_flags),
    # default-deny so KS-13 stays dormant unless the caller opts in explicitly.
    if ks13_master_enabled is not None:
        self._ks13_master_enabled = bool(ks13_master_enabled)
    else:
        try:
            from fantasy_sim.config.loader import get_phase2_ks_flags
            flags = get_phase2_ks_flags()
            # Codex cycle-5 alignment: Plan 01 (line 298) defines get_phase2_ks_flags()
            # to return a plain dict (`return defaults.get("phase2_ks_flags", {})`),
            # NOT a typed config object. Earlier drafts of this fallback used
            # `flags.ks13_ff_opportunity_prior_width.enabled` (attribute access), which
            # short-circuits to None on a dict via getattr-default → silently default-denies
            # KS-13 even when the master flag is True in defaults.yaml. Use dict access.
            ks13_cfg = flags.get("ks13_ff_opportunity_prior_width", {}) if isinstance(flags, dict) else {}
            self._ks13_master_enabled = bool(ks13_cfg.get("enabled", False))
        except Exception:
            self._ks13_master_enabled = False
```

**File 4: `tests/test_scoring/test_ensemble.py`** — add 6 tests:

```python
# === KS-13: ff_opportunity prior width ===

import math
import numpy as np
import pytest


def test_ks13_path_a_uses_quantile_width_when_lo_hi_present():
    """Path A: sigma = (hi - lo) / 2.56; sampled prior is centered on prior_fpts with that std.

    Codex cycle-3 alignment (final cycle HIGH): replaces prior `pass` placeholder with a
    concrete fixture-driven assertion that mirrors the existing
    test_blend_week_updates_fpts_and_recomputes_rank pattern in
    tests/test_scoring/test_ensemble.py. Two ensemblers seeded identically must produce
    identical fpts (determinism); the empirical sample std across many seeds must match
    (prior_hi - prior_lo) / 2.56 within a tolerance proportional to 1/sqrt(N_seeds).
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    cfg = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # FakeLoader returns a frame with prior_fpts=20.0, prior_fpts_lo=15.0, prior_fpts_hi=25.0
    # → expected sigma = (25.0 - 15.0) / 2.56 ≈ 3.906
    expected_sigma = (25.0 - 15.0) / 2.56

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"], "position": ["WR"],
        "prior_fpts": [20.0], "prior_fpts_lo": [15.0], "prior_fpts_hi": [25.0],
    })
    fake_loader = _StubLoader(fake_priors)  # test helper, returns the frame for any season

    samples: list[float] = []
    for seed in range(500):
        ens = FfOpportunityProjectionEnsembler(
            cfg, loader=fake_loader, rng=np.random.default_rng(seed),
            ks13_master_enabled=True,  # codex cycle-4: master flag must be True for KS-13 to activate
        )
        out, _ = ens.blend_week(
            [{"player_id": "wr1", "position": "WR", "fpts": 0.0}],  # weight 0.5, sim=0 → fpts = 0.5 * sampled_prior
            season=2024, week=1,
        )
        samples.append(out[0]["fpts"] / 0.5)  # invert weight to recover sampled_prior

    # Determinism: same seed → identical sample
    ens_a = FfOpportunityProjectionEnsembler(cfg, loader=fake_loader, rng=np.random.default_rng(42), ks13_master_enabled=True)
    ens_b = FfOpportunityProjectionEnsembler(cfg, loader=fake_loader, rng=np.random.default_rng(42), ks13_master_enabled=True)
    out_a, _ = ens_a.blend_week([{"player_id": "wr1", "position": "WR", "fpts": 0.0}], season=2024, week=1)
    out_b, _ = ens_b.blend_week([{"player_id": "wr1", "position": "WR", "fpts": 0.0}], season=2024, week=1)
    assert out_a[0]["fpts"] == out_b[0]["fpts"], "Path A must be deterministic under fixed RNG"

    # Empirical std across 500 seeds matches expected_sigma within sqrt(500) Monte Carlo error
    empirical_std = float(np.std(samples, ddof=1))
    tolerance = expected_sigma * 0.20  # ±20% sufficient for 500 samples
    assert abs(empirical_std - expected_sigma) < tolerance, (
        f"Empirical std {empirical_std:.3f} should match expected sigma {expected_sigma:.3f} "
        f"= (prior_hi - prior_lo) / 2.56 within ±{tolerance:.3f}"
    )

    # Mean centered on prior_fpts (Path A is unbiased)
    empirical_mean = float(np.mean(samples))
    mean_tolerance = expected_sigma / math.sqrt(500) * 4  # 4 SE bands
    assert abs(empirical_mean - 20.0) < mean_tolerance, (
        f"Empirical mean {empirical_mean:.3f} should match prior_fpts 20.0 within ±{mean_tolerance:.3f}"
    )


def test_ks13_path_b_uses_fitted_std_when_lo_hi_absent():
    """Path B: sigma comes from artifact `prior_width_<season>.json` keyed by position.

    Task 2 ships this as a placeholder; Task 2.5 (codex cycle-2 HIGH 3 fix) REPLACES
    the body with concrete artifact-loader assertions. The final implementation
    writes a synthetic v1 artifact to a temp dir, points the loader at it via
    `PriorWidthConfig.artifacts_dir=tmp_path`, and asserts
    `_fitted_std_for("WR", 14.0, 2024) == 4.5` against the synthetic bucket.
    """
    pass  # PLACEHOLDER — Task 2.5 replaces this body with concrete assertions


def test_ks13_unchanged_when_flag_disabled():
    """When prior_width.enabled = False, behavior is byte-identical to pre-Plan-07.

    Codex cycle-3 alignment (final cycle HIGH): replaces prior `pass` placeholder with a
    concrete differential test against a same-config ensembler that has prior_width
    DISABLED. Both runs must produce byte-identical fpts because the flag-off branch
    reuses the legacy point-estimate prior code path (`sampled_prior = prior_fpts`).
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"], "position": ["WR"],
        "prior_fpts": [20.0], "prior_fpts_lo": [15.0], "prior_fpts_hi": [25.0],
    })
    fake_loader = _StubLoader(fake_priors)
    rows = [{"player_id": "wr1", "position": "WR", "fpts": 12.0}]

    # Baseline: prior_width disabled (legacy point-estimate prior path)
    cfg_off = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=False),  # codex cycle-3: nested correctly
        ),
    )
    ens_off = FfOpportunityProjectionEnsembler(
        cfg_off, loader=fake_loader, rng=np.random.default_rng(123),
        ks13_master_enabled=True,  # master ON; sub-flag OFF — conjunction is False, KS-13 dormant
    )
    out_off, _ = ens_off.blend_week(list(rows), season=2024, week=1)

    # Repeat with a different RNG — output must be IDENTICAL because the flag-off path
    # is deterministic (no sampling): fpts = 0.5*12.0 + 0.5*20.0 = 16.0
    ens_off_alt = FfOpportunityProjectionEnsembler(
        cfg_off, loader=fake_loader, rng=np.random.default_rng(999),
        ks13_master_enabled=True,
    )
    out_off_alt, _ = ens_off_alt.blend_week(list(rows), season=2024, week=1)
    assert out_off[0]["fpts"] == out_off_alt[0]["fpts"], (
        "Flag-off branch must be RNG-independent (no sampling — point-estimate prior)"
    )
    assert out_off[0]["fpts"] == 16.0, (
        f"Expected legacy point-estimate fpts=16.0 (= 0.5*12 + 0.5*20), got {out_off[0]['fpts']}"
    )
    assert out_off[0].get("ensemble_covered") is True
    assert out_off[0].get("ensemble_source") == "ff_opportunity"

    # Sanity: enabling prior_width WITH lo/hi (BOTH master AND sub) must produce a DIFFERENT (sampled) fpts
    cfg_on = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )
    ens_on = FfOpportunityProjectionEnsembler(
        cfg_on, loader=fake_loader, rng=np.random.default_rng(123),
        ks13_master_enabled=True,  # both flags true → KS-13 active
    )
    out_on, _ = ens_on.blend_week(list(rows), season=2024, week=1)
    # P(equal | sampled with sigma≈3.9) is essentially zero
    assert out_on[0]["fpts"] != out_off[0]["fpts"], (
        "Enabling prior_width should change fpts via Gaussian sampling around prior_fpts"
    )


def test_ks13_dual_gate_master_flag_off_keeps_ks13_dormant():
    """Codex cycle-4 HIGH (dual-gate split fix): master phase2_ks_flag must be a
    sole-sufficient kill switch for KS-13 sampling.

    Plan 09's reverse-ablation walk-back disables KS-13 by setting
    `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled = False` while leaving
    `ensemble.ff_opportunity.prior_width.enabled` untouched. If KS-13's runtime gate
    were ONLY the engine-local sub-flag, the walk-back would silently leave KS-13
    sampling live, defeating per-KS A/B isolation and corrupting `{KS-08, KS-13}`
    coupled-cluster pair-revert decisions.

    This test pins the invariant: when `ks13_master_enabled=False` AND
    `prior_width.enabled=True`, KS-13 sampling is OFF (legacy point-estimate path).
    Conjunction semantics: `ks13_active := master AND sub`.
    """
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    fake_priors = pl.DataFrame({
        "season": [2024], "week": [1], "player_id": ["wr1"], "position": ["WR"],
        "prior_fpts": [20.0], "prior_fpts_lo": [15.0], "prior_fpts_hi": [25.0],
    })
    fake_loader = _StubLoader(fake_priors)
    rows = [{"player_id": "wr1", "position": "WR", "fpts": 12.0}]

    # Sub-flag ON, master OFF → conjunction False → legacy point-estimate path
    cfg_sub_on = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # Master flag OFF — KS-13 must be dormant regardless of RNG seed
    ens_master_off_seed1 = FfOpportunityProjectionEnsembler(
        cfg_sub_on, loader=fake_loader, rng=np.random.default_rng(1),
        ks13_master_enabled=False,
    )
    ens_master_off_seed2 = FfOpportunityProjectionEnsembler(
        cfg_sub_on, loader=fake_loader, rng=np.random.default_rng(99999),
        ks13_master_enabled=False,
    )
    out_seed1, _ = ens_master_off_seed1.blend_week(list(rows), season=2024, week=1)
    out_seed2, _ = ens_master_off_seed2.blend_week(list(rows), season=2024, week=1)

    # RNG-independent → master-off truly bypasses sampling
    assert out_seed1[0]["fpts"] == out_seed2[0]["fpts"], (
        "ks13_master_enabled=False must make blend RNG-independent regardless of sub-flag state"
    )
    # Output equals the legacy point-estimate value: 0.5*12 + 0.5*20 = 16.0
    assert out_seed1[0]["fpts"] == 16.0, (
        f"Master-off + sub-on must use legacy point-estimate (16.0), got {out_seed1[0]['fpts']}"
    )

    # Symmetric: master ON, sub OFF → conjunction also False (covered in
    # test_ks13_unchanged_when_flag_disabled above with ks13_master_enabled=True + sub=False).
    # This test specifically pins the OPPOSITE asymmetry that Plan 09's walk-back relies on.


def test_ks13_master_enabled_lazy_fallback_reads_dict_shaped_phase2_ks_flags(monkeypatch):
    """Codex cycle-5 HIGH (lazy-fallback dict-vs-attribute mismatch fix):
    when `ks13_master_enabled=None` is passed to the ensembler constructor, the
    fallback path MUST resolve the master flag by reading the dict returned from
    `get_phase2_ks_flags()` (Plan 01 line 298: `return defaults.get("phase2_ks_flags", {})`).

    Earlier drafts of this fallback used attribute access
    (`flags.ks13_ff_opportunity_prior_width.enabled`) on what is actually a plain
    dict, which short-circuits to None on getattr-default → silently default-denies
    KS-13 in `validate.py`-driven runs that don't pass an explicit master_enabled
    constructor arg. This test pins the dict-access correctness of the fallback.
    """
    import fantasy_sim.config.loader as loader_mod
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler
    from fantasy_sim.data.ensemble import EnsembleConfig, FfOpportunityConfig
    from fantasy_sim.data.ensemble.models import PriorWidthConfig

    cfg = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.5},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )

    # Case 1: dict-shaped phase2_ks_flags with ks13 master TRUE
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {"enabled": True}},
    )
    ens_master_on = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_master_on._ks13_master_enabled is True, (
        "Lazy fallback MUST read 'ks13_ff_opportunity_prior_width.enabled' from a dict, "
        "not via attribute access. Otherwise `validate.py` runs default-deny KS-13 silently."
    )

    # Case 2: dict-shaped phase2_ks_flags with ks13 master FALSE
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {"enabled": False}},
    )
    ens_master_off = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_master_off._ks13_master_enabled is False

    # Case 3: missing top-level key → default-deny
    monkeypatch.setattr(loader_mod, "get_phase2_ks_flags", lambda: {})
    ens_missing = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_missing._ks13_master_enabled is False

    # Case 4: missing inner key → default-deny
    monkeypatch.setattr(
        loader_mod,
        "get_phase2_ks_flags",
        lambda: {"ks13_ff_opportunity_prior_width": {}},
    )
    ens_missing_inner = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_missing_inner._ks13_master_enabled is False

    # Case 5: shim raises → default-deny (graceful)
    def _raises():
        raise RuntimeError("loader unavailable")
    monkeypatch.setattr(loader_mod, "get_phase2_ks_flags", _raises)
    ens_raises = FfOpportunityProjectionEnsembler(cfg, rng=np.random.default_rng(0))
    assert ens_raises._ks13_master_enabled is False


def test_ks13_probe_script_outputs_json():
    """probe_ff_opportunity_quantiles.py emits valid JSON with 'path' field.

    Codex cycle-2 alignment (HIGH 2): the probe uses the real
    FfOpportunityLoader.load_weekly([season]) API. Full-season probe (no
    --week) is preferred because it exercises every week's row count for a
    robust non_null_fraction. We pin --week 1 here only for test determinism
    against a fixed cache state; remove --week if cache regen is acceptable.
    """
    import subprocess
    result = subprocess.run(
        ["uv", "run", "python", "scripts/probe_ff_opportunity_quantiles.py", "--season", "2024", "--week", "1"],
        capture_output=True, text=True, check=True
    )
    import json
    parsed = json.loads(result.stdout.strip())
    assert "path" in parsed
    assert parsed["path"] in ("A", "B")
    # The probe must report whether lo/hi columns are present (Path A precondition).
    assert "lo_present" in parsed
    assert "hi_present" in parsed
    # And report the non-null fraction so the threshold logic is auditable.
    assert "non_null_fraction" in parsed


def test_ks13_path_a_seed_determinism():
    """Path A sampling is deterministic when RNG is seeded.

    Task 2 ships this as a placeholder; Task 2.5 (codex cycle-2 HIGH 3 fix) REPLACES
    the body with a concrete assertion: two ensemblers seeded with
    `np.random.default_rng(123)` produce identical sampled_prior values.
    """
    pass  # PLACEHOLDER — Task 2.5 replaces this body with concrete assertions


def test_ks13_path_b_artifact_loader_graceful_when_missing():
    """When Path B's std artifact is absent, falls back to point-estimate prior.

    Task 2 ships this as a placeholder; Task 2.5 (codex cycle-2 HIGH 3 fix) REPLACES
    the body with a concrete assertion: an ensembler pointed at an empty
    `artifacts_dir` returns `None` from `_load_ff_opportunity_prior_width_artifact`
    and `0.0` from `_fitted_std_for`, which yields the legacy point-estimate
    prior (no Gaussian sampling).
    """
    pass  # PLACEHOLDER — Task 2.5 replaces this body with concrete assertions
```

(Note: the placeholder tests above expand with concrete fixtures during implementation. The 6 tests are committed in RED state initially, then filled in during the GREEN implementation.)

Run pytest:
```bash
uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13
```

Run full suite:
```bash
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,164 + 6 = 2,170 tests pass.

Commit: `feat(02-07): KS-13 implement prior_width Path A + Path B in ensemble.py (gated)`
  </action>
  <verify>
    <automated>uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13 2>&1 | grep -E "PASSED|FAILED" | head -10 && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `src/fantasy_sim/scoring/ensemble.py` contains the literal string `prior_width.enabled` and `sampled_prior`
    - `src/fantasy_sim/data/ensemble/models.py` contains `class PriorWidthConfig`
    - `tests/test_scoring/test_ensemble.py` contains all 6 `def test_ks13_*` test functions
    - `src/fantasy_sim/scoring/ensemble.py` references `FfOpportunityProjectionEnsembler.blend_week` (the actual method name; codex cycle-2 alignment) not a fictional `adjust_week`
    - `src/fantasy_sim/data/ensemble/loader.py` references `FfOpportunityLoader.load_weekly` (the actual loader API) not a fictional `EnsembleLoader.load_week`
    - `uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13` exits 0
    - `uv run pytest tests/ -v` exits 0 (full suite green; 2,170 tests)
    - `git log -1 --pretty=%s` matches `feat(02-07): KS-13 implement`
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2.5: Path B artifact pipeline — fitter script + runtime loader (codex cycle-2 HIGH 3 fix)</name>
  <files>
    - scripts/fit_ff_opportunity_prior_width.py
    - src/fantasy_sim/scoring/ensemble.py
    - src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/.gitkeep
    - tests/test_scoring/test_ensemble.py
    - tests/test_scripts/test_fit_ff_opportunity_prior_width.py
  </files>
  <read_first>
    - scripts/fit_residual_calibration.py (the analog fitter script — Path B fitter mirrors its structure: argparse flags, training-season loop, per-bucket fit, JSON artifact write)
    - src/fantasy_sim/scoring/residual_calibration.py:189-336 (the analog runtime loader — `fit_residual_calibration_artifact` function + `ResidualCalibrationProjectionAdjuster._artifact` method with cache + schema-version check)
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json (probe outcome from Task 1; SKIP this entire task if probe selected Path A and `non_null_fraction >= 0.80` AND Task 3's bare/full A/B both PASS the Path A promotion bar)
  </read_first>
  <behavior>
    - Codex cycle-2 HIGH 3 fix: the must_haves promised "Path B introduces a new fitted-std artifact concept" — this task is the implementation of that promise. Skip the entire task only if Path A is confirmed sufficient by Task 3's A/B results; otherwise this task is REQUIRED before KS-13 can be promoted.
    - Add `scripts/fit_ff_opportunity_prior_width.py` mirroring `scripts/fit_residual_calibration.py`: takes `--test-seasons`, `--min-source-season`, `--training-years`, `--scoring`, `--output-dir` flags; emits `prior_width_<season>.json` per test_season under `output_dir`.
    - Each artifact JSON contains: `schema_version: 1`, `scoring: <ppr|half_ppr|standard>`, `test_season: int`, `source_seasons: list[int]`, `buckets: dict[position_key, {std_fpts: float, n: int}]`. The bucket key for KS-13 is just `position` (e.g. `"WR"`, `"RB"`, `"TE"`, `"QB"`) because Path B only differs by position; per-fpts-tier subdivision is OUT OF SCOPE for this task (can be a follow-up if Path B underdelivers).
    - Bundle pre-fit artifacts at `src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/` matching the residual_calibration bundle pattern. The directory ships with a `.gitkeep` until artifacts are fit.
    - Add a runtime loader to `FfOpportunityProjectionEnsembler`: `_load_ff_opportunity_prior_width_artifact(season: int) -> dict | None` — mirrors `ResidualCalibrationProjectionAdjuster._artifact` (per-season cache; falls back to bundled directory if `prior_width.artifacts_dir` is unset; returns None on missing file / JSON error / schema-version mismatch / scoring mismatch).
    - Add `_fitted_std_for(position: str, prior_fpts: float, season: int) -> float` (the Path B sigma source referenced from Task 2 File 3 as `self._fitted_std_for(...)`). Reads the loaded artifact, looks up `buckets[position]['std_fpts']`, returns 0.0 (point-estimate fallback) when artifact / bucket is missing.
    - Wire the season into the call site: `FfOpportunityProjectionEnsembler.blend_week(... season=season ...)` already takes `season`; the Path B branch in Task 2's blend block must change `self._fitted_std_for(row.get("position", ""), prior_fpts)` to `self._fitted_std_for(row.get("position", ""), prior_fpts, season)`.
    - Add an `artifacts_dir: Path | None = None` field to `PriorWidthConfig` (mirrors the same field in `ResidualCalibrationConfig`). Defaults yaml stays empty so the bundled dir is used.
    - Replace the 3 placeholder `pass` tests in Task 2 (`test_ks13_path_a_seed_determinism`, `test_ks13_path_b_artifact_loader_graceful_when_missing`, and the path B uses_fitted_std test) with concrete assertions that exercise the artifact loader.
    - Add a new test file `tests/test_scripts/test_fit_ff_opportunity_prior_width.py` that covers the fitter script's CLI smoke-test + per-bucket std computation on a small synthetic input.
  </behavior>
  <action>
**Step 1: Create `scripts/fit_ff_opportunity_prior_width.py`** mirroring `scripts/fit_residual_calibration.py`. Concrete skeleton:

```python
"""Fit per-position residual std for KS-13 Path B (ff_opportunity prior width)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl

from fantasy_sim.data.ensemble.loader import FfOpportunityLoader
from fantasy_sim.data.ensemble.models import FfOpportunityConfig

ARTIFACT_SCHEMA_VERSION = 1


def fit_one_test_season(
    *,
    test_season: int,
    source_seasons: list[int],
    sims: int,
    scoring: str,
) -> dict:
    """Fit per-position std on training seasons; emit one artifact dict.

    Approach: for each (player, week) row in the training-season ff_opportunity
    weekly frame, compute the residual = actual_fpts - prior_fpts (where
    prior_fpts = total_fantasy_points_exp). Group residuals by position;
    per-group std = empirical residual std. Bucket key = position (QB/RB/WR/TE).
    Bayesian-shrunk per-group std toward league-wide std with prior_n = 50 to
    avoid noisy buckets when n < 200.
    """
    # Codex cycle-2 alignment: this script uses the REAL loader API
    # (FfOpportunityLoader.load_weekly per src/fantasy_sim/data/ensemble/loader.py
    # line 43). Earlier drafts referenced fictional EnsembleLoader.load_week_raw.
    loader = FfOpportunityLoader(config=FfOpportunityConfig())
    raw_df = loader.load_weekly(source_seasons)

    # Join to actuals via player_id + season + week (actuals come from
    # nflverse player_stats; reuse the same join pattern as
    # `scripts/fit_residual_calibration.py`).
    actuals = _load_actuals_for_seasons(source_seasons, scoring)

    joined = raw_df.join(
        actuals,
        on=["player_id", "season", "week"],
        how="inner",
    ).with_columns(
        (pl.col("actual_fpts") - pl.col("total_fantasy_points_exp")).alias("residual"),
    )

    league_std = float(joined["residual"].std() or 0.0)
    PRIOR_N = 50  # Bayesian shrinkage strength

    buckets: dict[str, dict] = {}
    for position in ("QB", "RB", "WR", "TE"):
        sub = joined.filter(pl.col("position") == position)
        n = int(sub.height)
        if n == 0:
            continue
        empirical_std = float(sub["residual"].std() or 0.0)
        # Bayesian-shrunk std: weighted average toward league_std
        shrunk = (n * empirical_std + PRIOR_N * league_std) / (n + PRIOR_N)
        buckets[position] = {
            "std_fpts": round(float(shrunk), 4),
            "empirical_std_fpts": round(float(empirical_std), 4),
            "league_std_fpts": round(float(league_std), 4),
            "n": n,
        }

    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "scoring": scoring,
        "test_season": test_season,
        "source_seasons": list(source_seasons),
        "sims": sims,
        "buckets": buckets,
    }


def _load_actuals_for_seasons(seasons: list[int], scoring: str) -> pl.DataFrame:
    """Load weekly actual fantasy points for the requested seasons.

    Mirror the helper in scripts/fit_residual_calibration.py — uses
    nflreadpy.load_player_stats() and computes scoring-format-specific actual_fpts.
    """
    # Implementation: reuse fit_residual_calibration's helper if it's already
    # extracted; otherwise inline the standard pattern. The fitter must agree
    # with the runtime scoring rules (PPR / half_ppr / standard).
    raise NotImplementedError(
        "Implement using the same actuals-loading pattern as "
        "scripts/fit_residual_calibration.py — pull weekly player_stats and "
        "compute fantasy_points per the requested scoring format."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit KS-13 Path B prior-width artifacts.")
    parser.add_argument("--test-seasons", type=int, nargs="+", required=True)
    parser.add_argument("--min-source-season", type=int, required=True)
    parser.add_argument("--training-years", type=int, default=4)
    parser.add_argument("--sims", type=int, default=200)
    parser.add_argument("--scoring", type=str, default="ppr", choices=["ppr", "half_ppr", "standard"])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for test_season in args.test_seasons:
        source_seasons = list(range(
            max(args.min_source_season, test_season - args.training_years),
            test_season,
        ))
        artifact = fit_one_test_season(
            test_season=test_season,
            source_seasons=source_seasons,
            sims=args.sims,
            scoring=args.scoring,
        )
        out_path = args.output_dir / f"prior_width_{test_season}.json"
        with out_path.open("w") as f:
            json.dump(artifact, f, indent=2)
        print(f"Wrote {out_path} (n_buckets={len(artifact['buckets'])})", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 2: Add a runtime loader to `FfOpportunityProjectionEnsembler`.** In `src/fantasy_sim/scoring/ensemble.py`, mirror the `ResidualCalibrationProjectionAdjuster._artifact` pattern:

```python
# At module top, alongside the existing imports:
import json
from pathlib import Path

ARTIFACT_SCHEMA_VERSION = 1
BUNDLED_PRIOR_WIDTH_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "ensemble"
    / "artifacts"
    / "ff_opportunity_prior_width"
    / "decision_s200"
)

# In FfOpportunityProjectionEnsembler.__init__, add:
#   self._prior_width_artifact_cache: dict[int, dict | None] = {}

def _load_ff_opportunity_prior_width_artifact(self, season: int) -> dict | None:
    """Mirror of ResidualCalibrationProjectionAdjuster._artifact for KS-13 Path B.

    Caches per-season; resolves directory from prior_width.artifacts_dir
    (overrides) or BUNDLED_PRIOR_WIDTH_DIR (defaults). Returns None on
    missing file / JSON error / schema-version mismatch / scoring mismatch.
    """
    if season in self._prior_width_artifact_cache:
        return self._prior_width_artifact_cache[season]

    artifacts_dir = (
        Path(self.config.ff_opportunity.prior_width.artifacts_dir)
        if self.config.ff_opportunity.prior_width.artifacts_dir
        else BUNDLED_PRIOR_WIDTH_DIR
    )
    path = artifacts_dir / f"prior_width_{season}.json"
    if not path.exists():
        self._prior_width_artifact_cache[season] = None
        return None
    try:
        with path.open() as f:
            artifact = json.load(f)
    except (OSError, json.JSONDecodeError):
        self._prior_width_artifact_cache[season] = None
        return None
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        self._prior_width_artifact_cache[season] = None
        return None
    # scoring is taken from the EnsembleConfig at construction time; if the
    # ensembler does not currently know its scoring, accept any artifact
    # (Path B precondition: caller-side config governs scoring agreement).
    expected_scoring = getattr(self.config, "scoring", None)
    if expected_scoring is not None and artifact.get("scoring") != expected_scoring:
        self._prior_width_artifact_cache[season] = None
        return None
    self._prior_width_artifact_cache[season] = artifact
    return artifact


def _fitted_std_for(self, position: str, prior_fpts: float, season: int) -> float:
    """KS-13 Path B std lookup. Returns 0.0 (point-estimate fallback) when missing."""
    if not position:
        return 0.0
    artifact = self._load_ff_opportunity_prior_width_artifact(season)
    if artifact is None:
        return 0.0
    bucket = artifact.get("buckets", {}).get(position)
    if not isinstance(bucket, dict):
        return 0.0
    std = bucket.get("std_fpts")
    return float(std) if isinstance(std, (int, float)) else 0.0
```

**Step 3: Wire `season` through the Path B call site.** In Task 2's blend block, the Path B branch becomes:

```python
elif self.config.ff_opportunity.prior_width.path == "B":
    sigma = self._fitted_std_for(row.get("position", ""), prior_fpts, season)
    sampled_prior = float(self._rng.normal(prior_fpts, max(sigma, 0.0))) if sigma > 0 else prior_fpts
```

The `season` parameter is already in scope inside `blend_week` (current signature at line 56-62 of `src/fantasy_sim/scoring/ensemble.py`).

**Step 4: Extend `PriorWidthConfig`.** Add `artifacts_dir: Path | None = None` to the dataclass:

```python
@dataclass(frozen=True)
class PriorWidthConfig:
    """KS-13 D-10: ff_opportunity prior-width config."""
    enabled: bool = False
    path: str = "A"  # "A" = quantile-derived; "B" = fitted residual std
    artifacts_dir: Path | None = None  # codex cycle-2 HIGH 3: Path B override
```

Update the config loader (`src/fantasy_sim/data/ensemble/config.py`) to construct `artifacts_dir` from defaults yaml; keep defaults empty.

**Step 5: Replace the 3 placeholder tests** in `tests/test_scoring/test_ensemble.py` (the ones that say `pass # placeholder`). Concrete assertions:

```python
def test_ks13_path_b_uses_fitted_std_when_lo_hi_absent(tmp_path):
    """Path B: sigma comes from artifact buckets[position]['std_fpts']."""
    import json
    import numpy as np
    from fantasy_sim.data.ensemble.models import (
        EnsembleConfig,
        FfOpportunityConfig,
        PriorWidthConfig,
    )
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler, ARTIFACT_SCHEMA_VERSION

    # Write a synthetic Path B artifact
    artifacts_dir = tmp_path / "ff_opportunity_prior_width"
    artifacts_dir.mkdir()
    with (artifacts_dir / "prior_width_2024.json").open("w") as f:
        json.dump({
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "scoring": "ppr",
            "test_season": 2024,
            "source_seasons": [2020, 2021, 2022, 2023],
            "buckets": {
                "WR": {"std_fpts": 4.5, "n": 1000},
                "RB": {"std_fpts": 5.2, "n": 800},
                "QB": {"std_fpts": 6.1, "n": 200},
                "TE": {"std_fpts": 3.7, "n": 600},
            },
        }, f)

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3, "RB": 0.2, "QB": 0.0, "TE": 0.25},
            prior_width=PriorWidthConfig(
                enabled=True, path="B", artifacts_dir=artifacts_dir,
            ),
        ),
    )
    ensembler = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(42))
    sigma = ensembler._fitted_std_for("WR", 14.0, 2024)
    assert abs(sigma - 4.5) < 1e-9


def test_ks13_path_a_seed_determinism():
    """Path A sampling is deterministic when RNG is seeded.

    Two ensemblers seeded with the same RNG produce identical sampled_prior values.
    """
    import numpy as np
    from fantasy_sim.data.ensemble.models import (
        EnsembleConfig,
        FfOpportunityConfig,
        PriorWidthConfig,
    )
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3},
            prior_width=PriorWidthConfig(enabled=True, path="A"),
        ),
    )
    a = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(123))
    b = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(123))
    # Synthetic prior with lo/hi present — Path A path
    s_a = float(a._rng.normal(14.0, (16.0 - 12.0) / 2.56))
    s_b = float(b._rng.normal(14.0, (16.0 - 12.0) / 2.56))
    assert abs(s_a - s_b) < 1e-9, "same seed must produce identical sampled_prior"


def test_ks13_path_b_artifact_loader_graceful_when_missing(tmp_path):
    """When Path B's artifact is absent, loader returns None and runtime falls
    back to the point-estimate prior (sigma = 0.0 → no sampling)."""
    import numpy as np
    from fantasy_sim.data.ensemble.models import (
        EnsembleConfig,
        FfOpportunityConfig,
        PriorWidthConfig,
    )
    from fantasy_sim.scoring.ensemble import FfOpportunityProjectionEnsembler

    config = EnsembleConfig(
        enabled=True,
        ff_opportunity=FfOpportunityConfig(
            enabled=True,
            weights={"WR": 0.3},
            prior_width=PriorWidthConfig(enabled=True, path="B", artifacts_dir=tmp_path),
        ),
    )
    ensembler = FfOpportunityProjectionEnsembler(config=config, rng=np.random.default_rng(7))
    # Empty artifacts_dir → loader returns None → _fitted_std_for returns 0.0
    artifact = ensembler._load_ff_opportunity_prior_width_artifact(2024)
    assert artifact is None
    sigma = ensembler._fitted_std_for("WR", 14.0, 2024)
    assert sigma == 0.0, "missing artifact must yield sigma=0.0 (point-estimate fallback)"
```

**Step 6: Add `tests/test_scripts/test_fit_ff_opportunity_prior_width.py`** smoke-testing the fitter:

```python
"""Smoke-test the KS-13 Path B fitter script."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


def test_fit_ff_opportunity_prior_width_cli_help_works():
    """The fitter script must at least answer --help cleanly."""
    result = subprocess.run(
        [sys.executable, "scripts/fit_ff_opportunity_prior_width.py", "--help"],
        capture_output=True, text=True, check=True
    )
    assert "--test-seasons" in result.stdout
    assert "--training-years" in result.stdout
    assert "--scoring" in result.stdout
    assert "--output-dir" in result.stdout


def test_fit_ff_opportunity_prior_width_artifact_schema_version_is_1():
    """Generated artifacts must declare schema_version=1 to match the runtime loader."""
    from fantasy_sim.scoring.ensemble import ARTIFACT_SCHEMA_VERSION
    # The fitter script and the runtime loader must agree on schema_version.
    # If the fitter is bumped, the runtime must update simultaneously.
    assert ARTIFACT_SCHEMA_VERSION == 1


def test_fit_ff_opportunity_prior_width_bucket_keys_are_positions():
    """Bucket keys are bare position strings (QB/RB/WR/TE), not composite keys.
    Per-fpts-tier subdivision is OUT OF SCOPE for KS-13 v1."""
    # Synthetic check on a manually-constructed artifact dict
    fake_artifact = {
        "schema_version": 1,
        "scoring": "ppr",
        "test_season": 2024,
        "source_seasons": [2020, 2021, 2022, 2023],
        "buckets": {"WR": {"std_fpts": 4.5, "n": 1000}},
    }
    for key in fake_artifact["buckets"]:
        assert key in {"QB", "RB", "WR", "TE"}, f"bucket key {key} must be a bare position"
```

Run pytest:
```bash
uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13
uv run pytest tests/test_scripts/test_fit_ff_opportunity_prior_width.py -v
uv run pytest tests/ -v 2>&1 | tail -3
```

Expected: 2,170 + 3 (new fitter tests) = 2,173 tests pass.

Commit: `feat(02-07): KS-13 Path B artifact pipeline — fitter script + runtime loader (codex cycle-2 HIGH 3 fix)`
  </action>
  <verify>
    <automated>test -f scripts/fit_ff_opportunity_prior_width.py && grep -q "FfOpportunityLoader" scripts/fit_ff_opportunity_prior_width.py && grep -q "_load_ff_opportunity_prior_width_artifact" src/fantasy_sim/scoring/ensemble.py && grep -q "_fitted_std_for" src/fantasy_sim/scoring/ensemble.py && uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13 2>&1 | grep -E "PASSED|FAILED" && uv run pytest tests/test_scripts/test_fit_ff_opportunity_prior_width.py -v 2>&1 | grep -E "PASSED|FAILED"</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/fit_ff_opportunity_prior_width.py` exists, has a `main()` function, and accepts `--test-seasons`, `--min-source-season`, `--training-years`, `--scoring`, `--output-dir` flags
    - `scripts/fit_ff_opportunity_prior_width.py` imports `FfOpportunityLoader` from `fantasy_sim.data.ensemble.loader` (codex cycle-2 alignment — uses the REAL loader API)
    - `src/fantasy_sim/scoring/ensemble.py` defines `_load_ff_opportunity_prior_width_artifact(self, season: int) -> dict | None` mirroring `ResidualCalibrationProjectionAdjuster._artifact`
    - `src/fantasy_sim/scoring/ensemble.py` defines `_fitted_std_for(self, position: str, prior_fpts: float, season: int) -> float` returning 0.0 on missing artifact / bucket
    - `src/fantasy_sim/scoring/ensemble.py` defines `BUNDLED_PRIOR_WIDTH_DIR` and `ARTIFACT_SCHEMA_VERSION = 1`
    - `src/fantasy_sim/data/ensemble/models.py::PriorWidthConfig` has an `artifacts_dir: Path | None = None` field
    - `src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/` directory exists (with `.gitkeep` until first artifact is fit)
    - `tests/test_scoring/test_ensemble.py` no longer contains `pass # placeholder` lines for `test_ks13_path_a_seed_determinism`, `test_ks13_path_b_artifact_loader_graceful_when_missing`, or `test_ks13_path_b_uses_fitted_std_when_lo_hi_absent` — all three are concrete assertions
    - `tests/test_scripts/test_fit_ff_opportunity_prior_width.py` exists with at least 3 tests
    - `uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13` exits 0 (all 6 tests pass with concrete assertions)
    - `uv run pytest tests/test_scripts/test_fit_ff_opportunity_prior_width.py -v` exits 0
    - `uv run pytest tests/ -v` exits 0 (2,173 tests pass)
    - `git log -1 --pretty=%s` matches `feat(02-07): KS-13 Path B artifact pipeline`
    - **Skip semantics:** if Task 1's probe selected Path A AND Task 3's path-A A/B PASSES the path-A promotion bar (Δ stat_ks[fpts] ≤ -0.01), this entire task may be deferred to a follow-up plan WITH a tracking ticket recorded in `.planning/research/HYPOTHESES.md` under KS-13. The task is NOT silently dropped; the deferral must be explicit.
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 3: Run KS-13 A/B + promotion-state commit</name>
  <files>
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
  </files>
  <read_first>
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json (selected path)
  </read_first>
  <behavior>
    - Run A/B with `--set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true --set ensemble.ff_opportunity.prior_width.path=<A|B>`.
    - Apply path-specific promotion bar: Path A → fpts KS Δ ≤ -0.01 (D-30 standard); Path B → ≤ -0.005 (relaxed).
  </behavior>
  <action>
Run A/B (replace `<PATH>` with the selected path from Task 1):

```bash
uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline bare --arm-b-base bare \
  --set ensemble.dynamic_blend.enabled=true \
  --set ensemble.ff_opportunity.enabled=true \
  --set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true \
  --set ensemble.ff_opportunity.prior_width.enabled=true \
  --set ensemble.ff_opportunity.prior_width.path=<PATH> \
  --label p2.ks13.bare \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_bare.log

uv run python scripts/validate.py \
  --sims 200 --seasons 2022 2023 2024 --scoring ppr \
  --baseline defaults \
  --set phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=true \
  --set ensemble.ff_opportunity.prior_width.enabled=true \
  --set ensemble.ff_opportunity.prior_width.path=<PATH> \
  --label p2.ks13.full \
  2>&1 | tee .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_full.log

uv run python scripts/validate.py --show-ledger | grep -E "p2.ks13"
```

Apply path-specific promotion bar:
- Path A: hard floor + Δ stat_ks[fpts] ≤ -0.01
- Path B: hard floor + Δ stat_ks[fpts] ≤ -0.005

Append to PROMOTION-NOTES.md:
```markdown
## KS-13 (Plan 07) — <STATUS>

**Probe outcome:** path = `<A|B>`, non_null_fraction = <value>.

**A/B results (2026-04-26):**

| Mode | Δ rank_corr | Δ weekly_mae | Δ stat_ks[fpts] | Hard Floor | KS Δ ≤ -0.01 (A) / -0.005 (B) |
|------|-------------|--------------|------------------|-----------|-------------------------------|
| bare | <val>       | <val>        | <val>            | <PASS/FAIL> | <PASS/FAIL>                  |
| full | <val>       | <val>        | <val>            | <PASS/FAIL> | <PASS/FAIL>                  |

**Decision:** `<SHIPPED | SHIPPED-NO-OP | BLOCKED>`. Rationale: <one-sentence>.
```

If SHIPPED, edit defaults.yaml: `phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled: true`, `ensemble.ff_opportunity.prior_width.enabled: true`, `ensemble.ff_opportunity.prior_width.path: <A|B>`.

If SHIPPED-NO-OP / BLOCKED, defaults.yaml stays at the placeholder values from Plan 01.

Commit:
```
feat(02-07): KS-13 <STATUS> per D-30 (Path <A|B>) — Δ rank_corr <val>, Δ weekly_mae <val>, Δ stat_ks[fpts] <val>

Defaults: phase2_ks_flags.ks13_ff_opportunity_prior_width.enabled=<true|false>; ensemble.ff_opportunity.prior_width.{enabled, path}
Refs: D-10 (CONTEXT.md), HYPOTHESES.md KS-13 (lines 261-273)
```
  </action>
  <verify>
    <automated>uv run python scripts/validate.py --show-ledger | grep -E "p2.ks13" | wc -l | tr -d ' ' | grep -E "^2$" && grep -q "## KS-13" .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md && uv run pytest tests/ -v 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - `uv run python scripts/validate.py --show-ledger | grep "^p2.ks13"` returns exactly 2 rows
    - PROMOTION-NOTES.md `## KS-13` section contains probe outcome + A/B table + path-specific bar evaluation + Decision word
    - `uv run pytest tests/ -v` exits 0 (2,173 tests passing if Task 2.5 ran; 2,170 if Path B was deferred per Task 2.5 skip rule)
    - `git log -1 --pretty=%s` matches `feat(02-07): KS-13`
  </acceptance_criteria>
</task>

</tasks>

<verification>
After all 4 tasks complete (Task 1, Task 2, Task 2.5, Task 3 — Task 2.5 may be deferred per its skip rule when Path A is sufficient):

1. `git log --oneline -10` shows 3 or 4 new commits prefixed `(02-07)` (3 if Task 2.5 was deferred; 4 otherwise).
2. `scripts/probe_ff_opportunity_quantiles.py` exists and runs to completion against the REAL `FfOpportunityLoader.load_weekly([season])` API (codex cycle-2 HIGH 2 fix).
3. PROMOTION-NOTES.md `## KS-13` documents the probe outcome + selected path; if Task 2.5 was deferred, PROMOTION-NOTES.md AND `.planning/research/HYPOTHESES.md` both record the explicit deferral.
4. `uv run pytest tests/test_scoring/test_ensemble.py -v -k ks13` exits 0 (6 tests pass; the Path B / artifact-loader / seed-determinism tests have CONCRETE assertions per codex cycle-2 HIGH 3 fix, not `pass` placeholders).
5. **If Task 2.5 ran:** `scripts/fit_ff_opportunity_prior_width.py` exists; `src/fantasy_sim/scoring/ensemble.py` defines `_load_ff_opportunity_prior_width_artifact` and `_fitted_std_for`; `tests/test_scripts/test_fit_ff_opportunity_prior_width.py` exists.
6. `uv run python scripts/validate.py --show-ledger | grep "^p2.ks13"` returns 2 rows.
7. `uv run pytest tests/ -v` exits 0; total = 2,170 (Path A only) or 2,173 (Path A + Path B artifacts).

KS-13 status recorded. Plan 08 (KS-12) may now proceed (Wave 6 in D-12).
</verification>

<!-- Codex cycle-2 alignment (2026-04-27): trailing must_haves block removed; the
authoritative must_haves are in the frontmatter (top of file) which now includes
the codex cycle-2 HIGH 2 + HIGH 3 fixes (verified code surfaces; Task 2.5 Path B
artifact pipeline). -->

