# Codebase Concerns

**Analysis Date:** 2026-04-24

## Summary

This project is mature and heavily validated, but its main risks are operational rather than syntactic. Accuracy work depends on local data caches, paid or authenticated external sources, generated validation artifacts, and long-running A/B harnesses. Future work should treat validation evidence, artifact provenance, and cache coverage as first-class inputs before changing runtime defaults.

The most important planning concern is that many changes can appear behavior-neutral in unit tests while still changing projection distributions, weekly rank correlation, or promotion gates. Any feature that touches `src/fantasy_sim/data/game_context.py`, `src/fantasy_sim/validation/parallel.py`, `scripts/validate.py`, or post-simulation scoring layers should be verified through the project validation path, not only through pytest.

## Highest-Risk Areas

### Validation Runtime And Parallelism

- `scripts/validate.py` is the canonical A/B entrypoint and coordinates config resolution, season loops, cache usage, distribution KS diagnostics, weekly summaries, and ledger writes.
- `src/fantasy_sim/validation/parallel.py` has both simulation parallelism and game-context build parallelism. Simulation still uses `ProcessPoolExecutor` with a `forkserver` context, while context building defaults to `ThreadPoolExecutor` with shared pre-warmed `GameContextBuilder` instances.
- `GameContextBuilder` keeps mutable caches in `src/fantasy_sim/data/game_context.py`: `_pipeline_cache`, `_pbp_stats_cache`, `_player_models_cache`, PFF crosswalk state, and per-engine cache state. The core pipeline cache is guarded by `_pipeline_lock`, but future feature caches need the same care if they are used from threaded validation builds.
- `src/fantasy_sim/validation/parallel.py` still exposes the process-build fallback through `FANTASY_SIM_BUILD_MODE=process`. Future changes should keep both the default threaded path and the fallback path in mind, especially for objects that must be pickleable or importable by worker processes.
- Long validation runs are expected, and duplicate reruns are easy to start accidentally. Before expensive validation work, prefer checking `results/ab_ledger.json`, labels, and existing cache files under `results/cache/`.

### Artifact Coverage And Fallback Semantics

- Promoted dynamic-blend artifacts are bundled in `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/`.
- Promoted residual-calibration artifacts are bundled in `src/fantasy_sim/data/ensemble/artifacts/residual_calibration/decision_s200/`.
- `docs/CONFIG.md` documents that current bundled learned artifacts cover 2023 and 2024; 2022 is intentionally fallback-only because the fitting workflow uses prior source seasons.
- `config/defaults.yaml` has `ensemble.dynamic_blend.enabled=true` and `ensemble.residual_calibration.enabled=true`, so missing artifact behavior is production-relevant. Dynamic blend falls back to fixed defaults; residual calibration falls back to zero adjustment.
- Artifact-producing scripts such as `scripts/fit_dynamic_blend_weights.py`, `scripts/fit_residual_calibration.py`, and target-selection training scripts should record enough metadata for later runs to distinguish covered-season evidence from fallback-season evidence.

### Local Cache Dependence

- The runtime relies on local nflverse caches under `~/.fantasy-sim/cache/`, PFF processed data under `~/.fantasy-sim/pff/processed/`, props data under `~/.fantasy-sim/pff/props/`, weather data under `~/.fantasy-sim/weather/`, and market-history data under `~/.fantasy-sim/market-history/processed/`.
- `src/fantasy_sim/validation/coverage.py` contains explicit coverage checks for many optional signals, but cache contents can still differ by machine. Treat validation results as tied to the local cache snapshot unless the run records coverage and artifact context.
- `src/fantasy_sim/data/market_history/loader.py` expects files named like `player_markets_<season>_<snapshot_label>.parquet`. The default `snapshot_label` is `close_core8` in `config/defaults.yaml`, so changing snapshot labels can silently create no-data behavior unless coverage checks catch it.
- `scripts/fetch_market_history_events.py` and `scripts/fetch_market_history_props.py` depend on cached event inventory and The Odds API snapshots. Market-history expansion should preserve the current `close_core8` contract while adding broader coverage.
- `results/` is ignored except for `results/.gitkeep`, so local validation ledgers and caches are intentionally machine-specific. Do not assume a clean checkout includes the same `results/ab_ledger.json` evidence present in this workspace.

### External Credentials And Secret Boundaries

- `docs/pff-setup.md` instructs users to store PFF cookies in `~/.fantasy-sim/pff/.env`.
- `scripts/scrape_pff.py` reads PFF cookie auth from the PFF environment file and writes raw/processed PFF data under `~/.fantasy-sim/pff/`.
- `scripts/scrape_pff_props.py` reads `PFF_API_KEY` from the environment or `~/.fantasy-sim/pff/.env`.
- `scripts/fetch_market_history_events.py` and `scripts/fetch_market_history_props.py` load The Odds API credentials from environment or `~/.fantasy-sim/market-history/.env`.
- Never commit real `.env` files, raw credential values, cookies, API keys, or request headers. The repository `.gitignore` excludes `.env`, `.planning/`, `.bg-shell/`, local venvs, Python caches, and most `results/` output.

### Feature-Flag Surface Area

- `config/defaults.yaml` has many independent enabled flags across PFF, weather, Vegas, usage, tracking, target selection, ensemble, market history, availability, role trend, game script, goal-line concentration, and TD tendency.
- Several subfeatures are intentionally implemented but disabled by default, including `tracking.enabled`, `target_selection.enabled`, `role_trend.enabled`, `goal_line_concentration.enabled`, `pff.depth_role.enabled`, `pff.rb_scheme_fit.enabled`, and `pff.qb_split.enabled`.
- Future changes should avoid bundling multiple feature flips in one promotion run. `docs/hypotheses-list.md` recommends validating each hypothesis against `baseline=defaults` on its own.
- Some comments in `config/defaults.yaml` still say "flip to true after A/B validation" near fields that are now true, such as TD tendency settings. Treat config comments as useful but secondary to docs, ledger evidence, and code reality.

## Known Stale Or Legacy Surfaces

- `scripts/validate_pff_signal.py` and `scripts/validate_weekly_signal.py` are deprecated in favor of `scripts/validate.py`.
- `docs/weekly-validation-notes.md` explicitly says it is historical background for the standalone weekly-validation harness, not the primary source of truth.
- `docs/archive/accuracy-roadmap.md` preserves older phase decisions. It is useful evidence, but current defaults and recent decisions should be confirmed against `config/defaults.yaml`, `docs/hypotheses-list.md`, `docs/CONFIG.md`, and `results/ab_ledger.json` when present.
- Planning docs under `docs/superpowers/` contain implementation history and proposed plans. They may include stale commands or superseded assumptions, so use them as historical context rather than current execution instructions.

## Security And Data Handling Concerns

- Authenticated scrapers use `httpx` and external paid APIs. Avoid logging full request headers, cookies, API keys, or raw auth errors that include credential material.
- Raw PFF and The Odds API caches live outside the repo under `~/.fantasy-sim/`. They may contain paid-source data and should not be copied into committed docs or fixtures.
- `src/fantasy_sim/data/market_history/loader.py` and crosswalk logic join player-market names to nflverse roster IDs. Name-resolution failures can reduce market coverage without raising a hard error because missing crosswalk rows are skipped.
- Fuzzy matching exists in override and market/props crosswalk paths. Future changes should preserve ambiguity handling and should add regression tests for name/team edge cases.

## Performance Concerns

- Validation context building is expensive because it loads nflverse data, builds distributions, builds current rosters, and initializes optional data engines.
- `src/fantasy_sim/data/game_context.py` has warm/cache behavior intended to avoid rebuilding the same pipeline and player models repeatedly. New features should integrate into `warm()` and cache keys where appropriate.
- PFF, tracking, weather, props, market history, and target-selection layers can each add IO or CPU cost. A feature that improves accuracy but invalidates shared caches may make iteration substantially slower.
- `src/fantasy_sim/validation/parallel.py` sorts results after parallel work for determinism. Preserve deterministic ordering and deterministic seed behavior when changing validation execution.

## Accuracy And Statistical Validation Concerns

- Unit tests cannot prove projection improvements. Accuracy claims need the A/B harness and should cite ledger labels, sims, baseline mode, overrides, covered seasons, and promotion scope.
- `scripts/validate.py` now includes fantasy-point KS and stat-level KS distribution diagnostics across major QB/RB/WR/TE stats. Future improvements should watch distribution shape, not just rank correlation and MAE.
- `docs/hypotheses-list.md` notes that recent broad heuristic layers often landed near the noise floor or failed promotion. Prefer narrow, decision-point changes with explicit gates.
- Residual calibration changes final `fpts` only and leaves stat columns unchanged. That is useful for fantasy accuracy but can mask stat-distribution problems if reviewers only inspect fantasy-point metrics.

## Testing And CI Risks

- `pyproject.toml` configures pytest with `--import-mode=importlib`, `pythonpath = ["src"]`, and markers for `integration` and `statistical`.
- `.github/workflows/ci.yml` runs the unit suite across multiple Python versions. Local validation may use a newer `.venv` Python than CI, so compatibility-sensitive changes should use the uv-managed test path.
- Tests mock nflreadpy and external data heavily. When changing loader behavior or cache schema, add tests around schema, empty-frame behavior, and fallback paths instead of relying on live network calls.
- Statistical tests and full validation runs are slower than normal unit tests. Keep small unit tests for parser/config/schema invariants, then reserve validation runs for promotion evidence.

## Recommended Planning Guardrails

- Start from `scripts/validate.py`, `src/fantasy_sim/validation/ledger.py`, `src/fantasy_sim/validation/coverage.py`, `docs/hypotheses-list.md`, and `docs/CONFIG.md` before planning accuracy work.
- For any new data source or cache expansion, first document cache layout, required columns, coverage by season, and fallback behavior.
- For any learned or generated artifact, record the training seasons, test seasons, source coverage, artifact directory, schema/version, and exact validation command.
- Keep current default-on behavior stable unless a new validation run beats `baseline=defaults` with clear covered-season evidence and no meaningful QB/WR regression.
- Do not inspect or copy credential files while mapping, planning, or documenting the codebase.
