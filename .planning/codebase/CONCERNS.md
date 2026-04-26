# Codebase Concerns

**Analysis Date:** 2026-04-26

## Tech Debt

**Deprecated Validation Scripts (Legacy A/B Path):**
- Issue: `scripts/validate_pff_signal.py` and `scripts/validate_weekly_signal.py` marked as deprecated in AGENTS.md but still present and maintained
- Files: `scripts/validate_pff_signal.py`, `scripts/validate_weekly_signal.py`
- Impact: Dual validation paths confuse users about which script to use; legacy scripts may diverge from current defaults/config structure over time
- Fix approach: Archive old scripts into a `legacy/` subdirectory or fully remove once all workflows migrated to `scripts/validate.py`

**QB Rushing Features Off-by-Default (Incomplete Experiments):**
- Issue: Two QB rushing models in development but both disabled by default in `config/defaults.yaml`
- Files: `src/fantasy_sim/data/qb_rushing/` (models.py, runtime.py, training.py, 60+ KB)
- Impact: `qb_rushing.scramble.enabled=false` and `qb_rushing.designed_runs.enabled=false` indicate these features are incomplete; disabled to avoid breaking projections; recent commits (commits 72dbc35, b044fb0, 613d302, 7c76f75, d73243d) show active development with "smoke" validation
- Fix approach: Complete A/B validation for both models independently, then test in full stack; enable only when metrics improve significantly

**PFF Depth-Role Layer Disabled:**
- Issue: Complex depth-role efficiency engine fully implemented but not enabled: `pff.depth_role.enabled=false` and `pff.depth_role.efficiency.enabled=false`
- Files: `src/fantasy_sim/data/pff/depth_role.py` (full implementation), `config/defaults.yaml` lines 133-160
- Impact: 25+ lines of configuration and trained models exist but are not being used; Phase 5 analysis suggests this adds noise without meaningful lift
- Fix approach: Re-validate against current ensemble (dynamic_blend + residual_calibration) in isolation; document findings; either enable with threshold or archive entirely

**PFF RB Scheme-Fit and QB Split Disabled:**
- Issue: Two sophisticated PFF engines implemented but disabled: `pff.rb_scheme_fit.enabled=false` and `pff.qb_split.enabled=false`
- Files: `src/fantasy_sim/data/pff/rb_scheme_fit.py`, `src/fantasy_sim/data/pff/qb_split.py`, recent commits showing QB split design (9017f65)
- Impact: Complex game-level adjustment layers remain in codebase but untested in production; recent "QB designed-run" work (Phase 5 chain) may interact with these layers if re-enabled
- Fix approach: Validate both in isolation and full stack; ensure QB designed-run and QB split do not double-apply similar adjustments

**Tracking Engine Disabled:**
- Issue: Full weekly tracking engine implemented but disabled: `tracking.enabled=false`
- Files: `src/fantasy_sim/data/tracking/` (full subpackage with config, models, engine)
- Impact: 5-layer tracking subsystem (receiver participation, RB efficiency, QB context, etc.) exists but not used; adds maintenance burden
- Fix approach: Re-validate tracking against current ensemble; document if it adds noise or is simply redundant with other layers

**Team Context Engine Disabled:**
- Issue: `pff.team_context.enabled=false` despite being fully implemented
- Files: `src/fantasy_sim/data/pff/team_context.py`, config lines 103-110
- Impact: Season-level OL/pass-rate/QB-quality adjustments are available but not being applied
- Fix approach: A/B test team context in isolation and with full stack; explain why it was disabled

## Known Issues & In-Progress Work

**QB Scramble Model Smoke Validation:**
- Symptoms: Commits indicate "smoke validation" status but not full statistical validation against kill-point thresholds
- Files: `src/fantasy_sim/data/qb_rushing/`, config lines 304-308
- Trigger: Run `uv run python scripts/validate.py --set qb_rushing.scramble.enabled=true --sims 100` to full A/B test
- Workaround: Feature remains off; users cannot enable it
- Note: See ROADMAP.md commit c6fbd00 for detailed status on QB rushing phases

**QB Designed-Run Model Smoke Validation:**
- Symptoms: Recent commits (b075862, dbf676e) show "smoke" validation but not full metric validation
- Files: `src/fantasy_sim/data/qb_rushing/` (designed_runs submodule)
- Trigger: Same A/B validation path as QB scramble
- Workaround: Feature remains off; docs/roadmap.md (commit 32dbcf3) parks priority after smoke
- Note: Covers both probability and yards adjustments; architecture passes through game_context and play_resolver

**Artifact Fallback Gaps:**
- Symptoms: Multiple ensemble engines use fallback behavior when artifacts are missing (dynamic_blend, residual_calibration)
- Files: `src/fantasy_sim/scoring/dynamic_blend.py`, `src/fantasy_sim/scoring/residual_calibration.py`
- Impact: 2022 data may fall back to zero adjustment; missing weeks may cause silent fallback; no explicit logging of fallback usage in user output
- Fix approach: Log fallback usage to stderr or detailed report; add warning when artifact coverage < 80%

## Security Considerations

**PFF Cookie Authentication:**
- Risk: PFF data access requires browser session cookie (manual authentication, stored locally)
- Files: `scripts/scrape_pff.py` (uses httpx with auth), cache at `~/.fantasy-sim/pff/.env` (never read this file)
- Current mitigation: Stored in user home directory with restricted filesystem permissions; no key in repo
- Recommendations: Add documentation on secure credential rotation; consider OAuth or API-key alternative when available

**The Odds API Key Storage:**
- Risk: The Odds API key stored in `~/.fantasy-sim/props/.env` for player props backfill
- Files: `src/fantasy_sim/data/market_history/events_inventory.py`, `props_backfill.py`
- Current mitigation: Stored locally in user home; never committed to repo
- Recommendations: Document .env file protection; add guidance on rotating API keys periodically

**Environment Variable Leakage:**
- Risk: `.env` file in repo root (49 bytes, minimal but present)
- Files: `.env` at project root
- Current mitigation: Listed in `.gitignore`
- Recommendations: Verify no credentials in root `.env`; move to docs/example.env

## Performance Bottlenecks

**DataLoader PBP Network Fetch:**
- Problem: `src/fantasy_sim/data/loader.py` calls nflreadpy to fetch PBP data on first use; network-dependent
- Files: `src/fantasy_sim/data/loader.py` (DataLoader class), `src/fantasy_sim/data/pipeline.py`
- Cause: No pre-downloaded baseline; each new environment must fetch ~500MB of historical data
- Impact: Initial CLI runs block on network; no timeout specified
- Improvement path: Add `--cache-dir` option to override default `~/.fantasy-sim/cache/`, document pre-fetch step for CI/deployment

**Game Context Builder Three-Layer Cache:**
- Problem: Cache invalidation strategy relies on training_seasons tuple as key; config changes don't invalidate
- Files: `src/fantasy_sim/data/game_context.py` (GameContextBuilder, lines 86-91)
- Cause: Mutable config objects (PffConfig, WeatherConfig, etc.) passed to __init__ but not included in cache key
- Impact: Changing config (e.g., enabling a new layer) may not clear pipeline cache; users may see stale results
- Improvement path: Include config hash in cache key or add explicit `--clear-cache` CLI flag

**Monte Carlo Simulation Parallelization:**
- Problem: `src/fantasy_sim/engine/monte_carlo.py` runs 1000+ sims per game sequentially by default
- Files: `src/fantasy_sim/engine/monte_carlo.py` (run_simulations function)
- Impact: Single-threaded execution for large season backtests (2000+ games × 1000 sims = 2M simulations)
- Current: No explicit parallelization; relies on numpy for vectorization
- Improvement path: Add `--workers` flag to CLI; use concurrent.futures or multiprocessing for sim batches

**Play-Outcome Sampling at Field Position:**
- Problem: Empirical yard distributions sampled without position context; clamping creates bias
- Files: `src/fantasy_sim/engine/play_resolver.py` (lines 26-32, CATCH_YARDS_BOOST = 1)
- Cause: `CATCH_YARDS_BOOST` is a band-aid for field-position clamping bias (yards reduced ~1-2 per catch)
- Impact: All receivers get +1 yard/catch as compensation; not player-specific or context-aware
- Improvement path: Build position-aware distributions or use LOESS smoothing to adjust for field position

## Fragile Areas

**Game State Bucketing System:**
- Files: `src/fantasy_sim/models/game_state.py` (GameStateBucket), used throughout engine
- Why fragile: Five-tuple key (down, distance, score_diff, quarter, yard_zone) is brittle; changes to bucketing logic affect all distributions
- Safe modification: Add tests for boundary conditions (e.g., 4th down edge cases); validate bucketing output matches historical PBP
- Test coverage: Unit tests in `tests/test_models/test_game_state.py` exist but limited to happy paths

**Red Zone TD Gate Probability Lookup:**
- Files: `src/fantasy_sim/engine/play_resolver.py` (lines 43-57, PASS_TD_GATE and RUN_TD_GATE dicts)
- Why fragile: Hard-coded gate probabilities calibrated against 2021-2024 NFL data; NFL rules or pace changes may invalidate
- Safe modification: Add regression tests using historical drives; measure drive-level TD rate post-calibration
- Test coverage: `tests/test_engine/test_play_resolver.py` has direct tests; need integration tests on full-season backtests

**Config Inheritance Chain Resolution:**
- Files: `src/fantasy_sim/config/loader.py` (resolve_scoring function)
- Why fragile: `_inherit` chains (ppr → half_ppr → standard) have no cycle detection; circular inheritance crashes silently
- Safe modification: Add cycle detection in `resolve_scoring()`; validate config schema on load
- Test coverage: Tests exist but don't cover circular inheritance or deep chains

**Player Model Normalization (Share Redistribution):**
- Files: `src/fantasy_sim/data/player_builder.py` (build_team_roster), `src/fantasy_sim/overrides/engine.py` (share redistribution)
- Why fragile: Carry/target shares normalized to sum to 1.0 per roster; overrides trigger proportional redistribution which may not preserve total snap usage
- Safe modification: Add invariant checks: sum(carry_share) == 1.0 after redistribution; test with all positions present/missing
- Test coverage: 6+ tests for overrides but limited edge cases (e.g., all players overridden to zero)

**Ensemble Artifact Loading Fallback:**
- Files: `src/fantasy_sim/scoring/dynamic_blend.py` (lines 28-35, BUNDLED_WEIGHTS_DIR), `src/fantasy_sim/scoring/residual_calibration.py` (fallback_zero, fallback_market_history)
- Why fragile: Silent fallback to zero adjustment when artifacts missing; no explicit fallback logging in user output
- Safe modification: Log which artifacts are missing/loaded; add telemetry to track fallback frequency
- Test coverage: Fallback paths tested but not in integration tests

## Scaling Limits

**Player Model Cache Memory:**
- Current: `_player_models_cache: dict[tuple, dict[str, PlayerModel]]` in GameContextBuilder stores per-week, per-props-enabled variant
- Limit: 17 weeks × 2 (props enabled/disabled) = 34 entries per training_seasons config; each entry ~500-1000 PlayerModels
- Impact: Memory grows linearly with number of seasons and weeks accessed; no eviction policy
- Scaling path: Add LRU cache with configurable max entries; profile memory during full-season backtests

**Dynamic Blend Artifacts:**
- Current: Bundled weights stored at `src/fantasy_sim/data/ensemble/artifacts/dynamic_blend/decision_s200/`
- Coverage: 2023-2024 only (2022 artifacts missing per README); per-position, per-week-bucket, per-source-mask, per-confidence-bucket
- Scaling: Adding new seasons requires re-training all position/bucket combinations
- Scaling path: Consider quarterly/monthly re-training pipeline; archive old artifacts; document training schedule

**Validation Ledger Size:**
- Current: `results/pff_ab_ledger.json` and `results/ab_ledger.json` store all historical runs
- Impact: Ledger grows indefinitely; querying becomes slow after 1000+ runs
- Scaling path: Archive old runs by quarter; provide query tool to filter by date/position/metric

## Dependencies at Risk

**nflreadpy (NFL Data):**
- Risk: Single source for PBP, roster, schedule data; no fallback if nflverse.com data changes or API breaks
- Impact: Missing data means CLI cannot run; cached data provides temporary workaround
- Migration plan: Document cache-dir approach; pre-package critical 2022-2024 data as fallback

**httpx (Network Requests):**
- Risk: Used for PFF, Open-Meteo, The Odds API; no retry/backoff logic in calls
- Impact: Transient network errors break validation runs; no explicit timeout defaults
- Migration plan: Add retry decorator with exponential backoff; set explicit timeouts (5s for PFF, 10s for open-meteo)

**polars (DataFrame):**
- Risk: Relatively new library; potential for breaking changes in minor versions
- Impact: Used throughout data layer; no abstraction layer
- Current: Pinned in `pyproject.toml`
- Migration plan: Monitor polars releases; test on new versions before updating; keep pandas import available as fallback

**nflverse Archive Data (2019-2024):**
- Risk: Historical data depends on nflverse.com availability and data retention policy
- Impact: If nflverse deletes old data, backtests on 2019-2021 seasons become impossible
- Migration plan: Download and archive critical seasons locally; document retention policy

## Missing Critical Features

**Config Validation at Load Time:**
- Problem: Invalid config keys or mistyped settings pass silently; errors appear at runtime in engine
- Example: `pff.depth_role.enabled: truee` (typo) would not error until first PFF engine access
- Blocks: Users cannot safely experiment with new configs without dry-run validation
- Recommendation: Add JSON-schema validation in `config/loader.py` with helpful error messages

**Explicit Fallback Logging:**
- Problem: When artifacts are missing, dynamic_blend and residual_calibration fall back silently
- Blocks: Users don't know when their projections are using default vs. learned weights
- Recommendation: Log fallback usage to stderr with position/week/bucket info; add summary to CLI output

**Multi-Model Ensemble:**
- Problem: Current stack (dynamic_blend → residual_calibration) is hard-wired; no way to test alternative ensembles
- Blocks: Extending ensemble architecture requires code changes
- Recommendation: Parametrize ensemble order and weights; allow multiple ensemble files

## Test Coverage Gaps

**QB Rushing (Scramble + Designed-Run):**
- What's not tested: Full A/B validation on scramble_rate and designed_run probability factors; edge cases (QBs with 0% designed runs, mobile vs. pocket passers)
- Files: `src/fantasy_sim/data/qb_rushing/`, `tests/test_data/test_qb_rushing/` (sparse)
- Risk: Features may improve metrics when tested but fail in edge cases (e.g., rookie QBs, backup QBs with sparse data)
- Priority: HIGH (in-progress feature; blocks release)

**Tracking Engine Coverage:**
- What's not tested: Full integration of tracking adjustments with other engines; interaction with dynamic_blend
- Files: `src/fantasy_sim/data/tracking/` (enabled=false in defaults)
- Risk: If re-enabled, may double-apply similar adjustments to other layers
- Priority: MEDIUM (low priority but large codebase)

**PFF Depth-Role + Efficiency Engines:**
- What's not tested: Statistical validation against 2023-2024 data; interaction with team_context when both enabled
- Files: `src/fantasy_sim/data/pff/depth_role.py`
- Risk: Complex layering may cause unexpected interactions or overfitting
- Priority: MEDIUM (disabled but fully implemented)

**Cache Invalidation:**
- What's not tested: Config changes don't invalidate three-layer cache; stale data persists across config tweaks
- Files: `src/fantasy_sim/data/game_context.py` (cache logic)
- Risk: Hard to debug; users may spend hours tuning config while cache serves stale results
- Priority: HIGH (affects all workflows)

**Ensemble Artifact Fallback Paths:**
- What's not tested: All fallback code paths (missing artifact, missing bucket, missing season); user expectations when fallback occurs
- Files: `src/fantasy_sim/scoring/dynamic_blend.py`, `residual_calibration.py`
- Risk: Silent failures lead to untraced accuracy differences
- Priority: MEDIUM (artifact coverage is good but edge cases exist)

---

*Concerns audit: 2026-04-26*
