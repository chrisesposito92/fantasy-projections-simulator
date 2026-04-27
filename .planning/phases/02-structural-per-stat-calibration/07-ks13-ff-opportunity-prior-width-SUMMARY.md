---
phase: 02-structural-per-stat-calibration
plan: 07
subsystem: scoring/ensemble, data/ensemble, scripts
tags: [ks-13, ff-opportunity, prior-width, dual-gate, path-b, shipped-no-op]
dependency_graph:
  requires: [02-01-phase2-scaffolding, 02-02-ks08-dynamic-blend-floor]
  provides: [ks13_ff_opportunity_prior_width_arch, bundled_prior_width_artifacts, dual_gate_master_flag]
  affects: [plan-09-aggregate, plan-09-reverse-ablation]
tech_stack:
  added: []
  patterns: [probe-then-decide, dual-gate-conjunction, lazy-fallback-dict-access, bayesian-shrinkage-std]
key_files:
  created:
    - scripts/probe_ff_opportunity_quantiles.py
    - scripts/fit_ff_opportunity_prior_width.py
    - src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_2023.json
    - src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_2024.json
    - src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/.gitkeep
    - tests/test_scripts/test_fit_ff_opportunity_prior_width.py
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_probe.json
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_bare.log
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_full.log
    - .planning/phases/02-structural-per-stat-calibration/logs/p2_ks13_refit.log
  modified:
    - src/fantasy_sim/scoring/ensemble.py
    - src/fantasy_sim/data/ensemble/models.py
    - src/fantasy_sim/data/ensemble/config.py
    - src/fantasy_sim/data/ensemble/normalizer.py
    - tests/test_scoring/test_ensemble.py
    - config/defaults.yaml
    - .planning/phases/02-structural-per-stat-calibration/logs/PROMOTION-NOTES.md
decisions:
  - "Probe selected Path B: nflverse FF Opportunity data has no total_fantasy_points_exp_lo/hi columns"
  - "KS-13 dual-gate: ks13_active = ks13_master_enabled AND prior_width.enabled (conjunction); master flag is sole-sufficient kill switch for Plan 09 reverse-ablation"
  - "Lazy-fallback reads dict from get_phase2_ks_flags() using dict-access (not attribute-access) — codex cycle-5 fix"
  - "SHIPPED-NO-OP: hard floor passes (rank_corr -0.0007, weekly_mae -0.001) but fpts KS Δ≈0.000 does not meet -0.005 Path B bar; symmetric noise does not reduce KS gap from systematic biases"
  - "Path A architecture retained for future data sources that include lo/hi quantiles; normalizer extended to pass through optional columns"
metrics:
  duration: ~120min
  completed_date: "2026-04-27"
  tasks_completed: 4
  files_changed: 17
---

# Phase 2 Plan 07: KS-13 FF Opportunity Prior Width Summary

KS-13 implements probe-then-decide prior-width sampling in `FfOpportunityProjectionEnsembler.blend_week`. Probe confirmed Path B (no lo/hi quantiles in nflverse data). Path B fitted per-position residual std (QB=5.65, WR=4.59, RB=4.19, TE=3.54). Full-stack A/B: hard floor passes (rank_corr -0.0007, weekly_mae -0.001) but fpts KS Δ≈0.000 — SHIPPED-NO-OP.

## What Was Built

### Task 1: Probe Script + Outcome Recording

- Created `scripts/probe_ff_opportunity_quantiles.py` using the real `FfOpportunityLoader.load_weekly([season])` API (codex cycle-2 HIGH 2 alignment)
- Ran probe against 2024 season: `{"path": "B", "lo_present": false, "hi_present": false, "non_null_fraction": 0.0}`
- nflverse FF Opportunity data does NOT include `total_fantasy_points_exp_lo` / `_hi` — Path B selected
- Saved probe JSON to `logs/p2_ks13_probe.json`; recorded outcome in `PROMOTION-NOTES.md ## KS-13`

### Task 2: ensemble.py Implementation + 8 Unit Tests

**`src/fantasy_sim/data/ensemble/models.py`:** Added `PriorWidthConfig` dataclass with `enabled: bool`, `path: str`, `artifacts_dir: Path | None = None`. Extended `FfOpportunityConfig` with `prior_width: PriorWidthConfig` field.

**`src/fantasy_sim/data/ensemble/config.py`:** Updated `load_ensemble_config()` to construct `PriorWidthConfig` from `defaults.yaml` `ensemble.ff_opportunity.prior_width` block.

**`src/fantasy_sim/data/ensemble/normalizer.py`:** Extended `normalize_ff_opportunity` to pass through optional `total_fantasy_points_exp_lo/hi` → `prior_fpts_lo/hi` columns when present (Path A future support).

**`src/fantasy_sim/scoring/ensemble.py`:** Full rewrite of `FfOpportunityProjectionEnsembler`:
- Adds `rng: np.random.Generator | None = None` and `ks13_master_enabled: bool | None = None` constructor params
- **Codex cycle-4 dual-gate:** `ks13_active = self._ks13_master_enabled AND _pw.enabled` — conjunction; master flag is sole-sufficient kill switch
- **Codex cycle-5 lazy fallback:** resolves master flag from `get_phase2_ks_flags()` via dict-access (`flags.get(...)`) not attribute access
- Path A: `sigma = (prior_hi - prior_lo) / 2.56` Gaussian sampling (requires lo/hi in prior dict)
- Path B: `sigma = self._fitted_std_for(position, prior_fpts, season)` from artifact loader
- Adds `_load_ff_opportunity_prior_width_artifact(season)` with per-season cache + bundled dir fallback + lazy None on missing/error/version-mismatch
- Adds `_fitted_std_for(position, prior_fpts, season)` returning 0.0 (point-estimate) on missing artifact/bucket
- Adds `ARTIFACT_SCHEMA_VERSION = 1` and `BUNDLED_PRIOR_WIDTH_DIR` constants
- New `ensemble_sampled_prior_fpts` output field (KS-13 diagnostic)

**8 KS-13 unit tests** added to `tests/test_scoring/test_ensemble.py`:
1. `test_ks13_path_a_uses_quantile_width_when_lo_hi_present` — empirical std matches expected sigma ±20%; determinism
2. `test_ks13_path_b_uses_fitted_std_when_lo_hi_absent` — concrete artifact loader assertion (sigma=4.5 from synthetic artifact)
3. `test_ks13_unchanged_when_flag_disabled` — flag-off → RNG-independent → 16.0 (point-estimate)
4. `test_ks13_dual_gate_master_flag_off_keeps_ks13_dormant` — master=False + sub=True → 16.0 (codex cycle-4)
5. `test_ks13_master_enabled_lazy_fallback_reads_dict_shaped_phase2_ks_flags` — 5 monkeypatched cases (codex cycle-5)
6. `test_ks13_probe_script_outputs_json` — subprocess JSON smoke-test
7. `test_ks13_path_a_seed_determinism` — same seed → same sampled value
8. `test_ks13_path_b_artifact_loader_graceful_when_missing` — empty dir → artifact=None → sigma=0.0

### Task 2.5: Path B Artifact Pipeline

**`scripts/fit_ff_opportunity_prior_width.py`:** Full fitter mirroring `fit_residual_calibration.py`:
- CLI flags: `--test-seasons`, `--min-source-season`, `--training-years`, `--scoring`, `--output-dir`
- Joins FF Opportunity prior (`total_fantasy_points_exp`) to actual weekly fpts via `load_actual_scores`
- Computes per-position residuals; Bayesian shrinkage with `PRIOR_N=50` toward league-wide std
- Emits `prior_width_<season>.json` with `schema_version=1`, per-position `std_fpts, empirical_std_fpts, league_std_fpts, n`

**Bundled artifacts** at `src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/`:
- `prior_width_2023.json`: QB=5.67, RB=4.19, WR=4.59, TE=3.54 (16540 residuals, league_std=4.49)
- `prior_width_2024.json`: QB=5.65, RB=4.19, WR=4.59, TE=3.54 (22150 residuals, league_std=4.46)

**3 fitter tests** at `tests/test_scripts/test_fit_ff_opportunity_prior_width.py`: CLI help, schema_version=1, bare-position bucket keys.

### Task 3: A/B Validation + Promotion-State Commit

**Probe:** Path B selected — nflverse data lacks lo/hi quantile columns.

**A/B results:**

| Mode | Δ rank_corr | Δ weekly_mae | Δ fpts_ks avg | Hard Floor | KS Δ ≤ -0.005 (Path B) |
|------|-------------|--------------|----------------|-----------|------------------------|
| bare (#122) | +0.0012 | +0.072 | -0.000 | FAIL (MAE +0.072) | FAIL |
| full pre-artifacts (#123) | -0.0004 | +0.005 | -0.000 | PASS | FAIL |
| full with artifacts (#124) | -0.0007 | -0.001 | +0.000 | PASS | FAIL |

**Decision: SHIPPED-NO-OP.** Hard floor passes on full-stack; fpts KS bar not met. Symmetric Gaussian noise centered on the ff_opportunity prior doesn't reduce KS because the distribution gap comes from systematic biases (QB pass_yards / WR receiving_yards under-projection), not from lack of width in the prior. Architecture is correct and in place.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Normalizer drops prior_fpts_lo/hi — extended to pass through optional columns**
- **Found during:** Task 2 (writing Path A tests)
- **Issue:** `normalize_ff_opportunity` called `.select(list(NORMALIZED_SCHEMA))` which dropped `total_fantasy_points_exp_lo/hi` before they reached `blend_week`. Path A stub tests would fail.
- **Fix:** Extended normalizer with `_OPTIONAL_QUANTILE_SOURCES` mapping and optional column pass-through in the normalization pipeline.
- **Files modified:** `src/fantasy_sim/data/ensemble/normalizer.py`
- **Commit:** 169004d

**2. [Rule 3 - Blocking] `defaults.yaml` missing `prior_width.path` and `prior_width.artifacts_dir` fields**
- **Found during:** Task 3 when `apply_overrides` raised `KeyError: 'path' not found in ensemble.ff_opportunity.prior_width'`
- **Issue:** `defaults.yaml` only had `prior_width.enabled` — the `path` and `artifacts_dir` fields were not present, blocking validate.py `--set` override.
- **Fix:** Added `path: B` and `artifacts_dir: null` to `config/defaults.yaml` under `ensemble.ff_opportunity.prior_width`.
- **Files modified:** `config/defaults.yaml`
- **Commit:** e5790c7

**3. [Rule 2 - Enhancement] Fit Path B artifacts before final A/B (no prior-width effect without them)**
- **Found during:** Task 3 — first full A/B run (#123) showed Δ fpts_ks=-0.000 because empty artifact dir caused sigma=0.0 fallback
- **Fix:** Ran `scripts/fit_ff_opportunity_prior_width.py` for 2023/2024 test seasons; bundled artifacts to `decision_s200/`; re-ran A/B (#124). Result still Δ≈0 but now reflects actual sampling behavior.
- **Files modified:** Artifact JSON files added
- **Commit:** e5790c7

## Known Stubs

None — all paths implemented with concrete behavior. The `_load_ff_opportunity_prior_width_artifact` returns `None` on missing artifact (lazy fallback to point-estimate), which is the correct specified behavior, not a stub.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundary changes introduced.

## Self-Check: PASSED

Files exist:
- scripts/probe_ff_opportunity_quantiles.py: FOUND
- scripts/fit_ff_opportunity_prior_width.py: FOUND
- src/fantasy_sim/scoring/ensemble.py (sampled_prior): FOUND
- src/fantasy_sim/data/ensemble/models.py (PriorWidthConfig): FOUND
- src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_2023.json: FOUND
- src/fantasy_sim/data/ensemble/artifacts/ff_opportunity_prior_width/decision_s200/prior_width_2024.json: FOUND
- tests/test_scoring/test_ensemble.py (8 KS-13 tests): FOUND
- tests/test_scripts/test_fit_ff_opportunity_prior_width.py: FOUND

Commits exist (4 plan tasks):
- 3c60eac: feat(02-07): KS-13 add probe_ff_opportunity_quantiles.py
- 169004d: feat(02-07): KS-13 implement prior_width Path A + Path B in ensemble.py
- 59d1240: feat(02-07): KS-13 Path B artifact pipeline — fitter script + runtime loader
- e5790c7: feat(02-07): KS-13 SHIPPED-NO-OP per D-30 (Path B)

Test suite: 2184 passed (was 2173; +8 KS-13 ensemble tests, +3 fitter tests).
Ledger: 3 p2.ks13 entries (#122 bare, #123 full pre-artifacts, #124 full with artifacts).
