# Testing Patterns

**Analysis Date:** 2026-04-24

## Test Framework

**Runner:**
- pytest 9.0.2 in the active dev dependency group in `pyproject.toml`; optional dev metadata also lists pytest >=8.0 in `pyproject.toml`.
- Config: `pyproject.toml`
- Test paths: `tests`
- Python path: `src`
- Import mode: `--import-mode=importlib`
- Markers: `integration` and `statistical` registered in `pyproject.toml`.

**Assertion Library:**
- pytest assertions and `pytest.approx`, as used in `tests/test_validation/test_metrics.py`, `tests/test_engine/test_types.py`, `tests/test_data/test_actuals.py`, and `tests/test_validation/test_weekly.py`.
- `unittest.mock.patch` and `MagicMock` for dependency mocking, as used in `tests/test_data/test_loader.py`, `tests/test_cli.py`, `tests/test_data/test_weather/test_provider.py`, and `tests/test_scripts/test_scrape_pff.py`.

**Run Commands:**
```bash
uv run pytest tests/ -v
uv run pytest tests/ -v -m statistical
uv run pytest tests/ -v -m integration
uv run pytest tests/test_validation/test_metrics.py -v
uv run pytest tests/test_engine/test_player_selector.py -v
```

**Validation Commands:**
```bash
uv run python scripts/validate.py --sims 50 --label "run-name"
uv run python scripts/validate.py --set usage.ngs.enabled=true --sims 50 --label "test-ngs"
uv run python scripts/validate.py --baseline defaults --set usage.ngs.enabled=true --sims 50
uv run python scripts/validate.py --show-ledger
uv run python scripts/validate_sim.py
uv run python scripts/validate_players.py
uv run python scripts/validate_data.py
```

## Test File Organization

**Location:**
- Tests live under `tests/` and mirror the `src/fantasy_sim/` subsystem layout.
- Model tests: `tests/test_models/` maps to `src/fantasy_sim/models/`.
- Engine tests: `tests/test_engine/` maps to `src/fantasy_sim/engine/`.
- Data-layer tests: `tests/test_data/` maps to `src/fantasy_sim/data/`, with nested packages like `tests/test_data/test_pff/`, `tests/test_data/test_weather/`, `tests/test_data/test_vegas/`, `tests/test_data/test_tracking/`, and `tests/test_data/test_market_history/`.
- Scoring tests: `tests/test_scoring/` maps to `src/fantasy_sim/scoring/`.
- Validation tests: `tests/test_validation/` maps to `src/fantasy_sim/validation/` and `scripts/validate.py`.
- Script tests: `tests/test_scripts/` maps to files under `scripts/`.
- CLI tests: `tests/test_cli.py` covers `src/fantasy_sim/cli.py`.

**Naming:**
- Test files use `test_*.py`: examples include `tests/test_engine/test_play_resolver.py`, `tests/test_data/test_pff/test_tier_engine.py`, `tests/test_scoring/test_dynamic_blend.py`, and `tests/test_validation/test_ledger.py`.
- Test classes use `Test...` names grouped by behavior, such as `TestBucketDistance` in `tests/test_models/test_game_state.py`, `TestDataLoaderCaching` in `tests/test_data/test_loader.py`, and `TestWeatherProvider` in `tests/test_data/test_weather/test_provider.py`.
- Test functions use `test_...` names that state expected behavior, such as `test_dynamic_blend_missing_artifact_falls_back_to_fixed_equivalent()` in `tests/test_scoring/test_dynamic_blend.py` and `test_filters_non_finite_triplets()` in `tests/test_validation/test_metrics.py`.

**Structure:**
```text
tests/
├── conftest.py
├── test_cli.py
├── test_config/
├── test_data/
│   ├── test_pff/
│   ├── test_vegas/
│   ├── test_weather/
│   ├── test_tracking/
│   └── test_market_history/
├── test_engine/
├── test_models/
├── test_scoring/
├── test_scripts/
└── test_validation/
```

## Test Structure

**Suite Organization:**
```python
class TestSelectReceiver:
    def test_wr1_most_frequent(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        ids = [select_receiver(roster, state, rng).player_id for _ in range(200)]
        assert ids.count("WR1") > ids.count("TE1")
        assert ids.count("WR1") > ids.count("RB1")
```
Use this class-plus-behavior pattern for domain tests, as in `tests/test_engine/test_player_selector.py`, `tests/test_models/test_game_state.py`, and `tests/test_config/test_loader.py`.

**Patterns:**
- Build small local factories near the tests they serve. Examples: `make_state()` and `make_roster()` in `tests/test_engine/test_player_selector.py`, `_make_test_dists()` and `_make_test_roster()` in `tests/test_cli.py`, and `_make_entry()` in `tests/test_validation/test_ledger.py`.
- Use shared fixtures for broadly reused NFL-like data in `tests/conftest.py`: `sample_pbp`, `sample_schedules`, `sample_rosters`, `expanded_pbp`, `rz_pbp`, `air_yards_pbp`, and trade/roster fixtures.
- Use deterministic seeds for stochastic tests. Examples: `np.random.default_rng(42)` in `tests/test_engine/test_player_selector.py`, `np.random.default_rng(12345)` in `tests/test_engine/test_dst_defensive_tds.py`, and `run_simulations(..., seed=42)` in `tests/test_engine/test_statistical_validation.py`.
- Use `pytest.approx` for floating-point and statistical comparisons in `tests/test_validation/test_metrics.py`, `tests/test_validation/test_weekly.py`, `tests/test_engine/test_types.py`, and `tests/test_data/test_actuals.py`.
- Use `tmp_path` for filesystem cache, parquet, JSON, and artifact tests, as in `tests/test_data/test_loader.py`, `tests/test_data/test_weather/test_provider.py`, `tests/test_validation/test_ledger.py`, `tests/test_scoring/test_dynamic_blend.py`, and `tests/test_scoring/test_residual_calibration.py`.

## Mocking

**Framework:** `unittest.mock`

**Patterns:**
```python
@patch("fantasy_sim.data.loader.nflreadpy")
def test_load_pbp_caches_to_parquet(self, mock_nfl, loader, cache_dir):
    mock_df = pl.DataFrame({"play_type": ["pass", "run"], "yards_gained": [10, 5]})
    mock_nfl.load_pbp.return_value = mock_df
    result = loader.load_pbp(seasons=[2024])
    assert result.shape == mock_df.shape
    assert (cache_dir / "pbp_2024.parquet").exists()
```
- Patch the dependency at the module path where it is used. Examples: `fantasy_sim.data.loader.nflreadpy` in `tests/test_data/test_loader.py`, `fantasy_sim.cli.GameContextBuilder` in `tests/test_cli.py`, and `fantasy_sim.data.weather.provider.httpx` in `tests/test_data/test_weather/test_provider.py`.
- Use `MagicMock` for HTTP response objects and clients in script/provider tests. Examples: `tests/test_scripts/test_scrape_pff.py`, `tests/test_scripts/test_scrape_pff_props.py`, and `tests/test_data/test_weather/test_provider.py`.
- Use `monkeypatch` for module constants and functions when the test needs to override defaults without replacing whole classes, as in `tests/test_data/test_loader.py`, `tests/test_engine/test_game_sim.py`, and `tests/test_validation/test_coverage.py`.
- Use `caplog` for logging assertions, as in `tests/test_data/test_usage/test_usage_engine.py`, `tests/test_data/test_vegas/test_props_engine.py`, and `tests/test_data/test_pff/test_qb_split_integration.py`.

**What to Mock:**
- Network and external SDK calls: nflreadpy in `tests/test_data/test_loader.py`, httpx calls in `tests/test_data/test_weather/test_provider.py`, and PFF scraper HTTP clients in `tests/test_scripts/test_scrape_pff.py` and `tests/test_scripts/test_scrape_pff_props.py`.
- Expensive context building and simulation collaborators in CLI/validation tests: `GameContextBuilder`, `DataLoader`, `build_games_parallel`, `simulate_games_parallel`, and projection layer builders in `tests/test_cli.py`, `tests/test_validation/test_backtester.py`, and `tests/test_validation/test_validate_script.py`.
- Filesystem roots and cache directories through `tmp_path`, `cache_dir`, constructor injection, or monkeypatching module constants in `tests/test_data/test_loader.py`, `tests/test_data/test_weather/test_provider.py`, and `tests/test_validation/test_coverage.py`.

**What NOT to Mock:**
- Core pure domain logic should be exercised directly with small data: bucket helpers in `tests/test_models/test_game_state.py`, scoring functions in `tests/test_scoring/test_engine.py`, metric functions in `tests/test_validation/test_metrics.py`, player selection in `tests/test_engine/test_player_selector.py`, and config parsing in `tests/test_config/test_loader.py`.
- Polars transformations should run against real `pl.DataFrame` fixtures instead of mocked DataFrames, as in `tests/test_data/test_preprocessor.py`, `tests/test_data/test_market_history/test_loader.py`, `tests/test_data/test_tracking/test_inputs_loader.py`, and `tests/test_data/test_pff/test_tier_engine.py`.
- RNG-driven selection should use deterministic `np.random.default_rng(seed)` rather than mocked random calls, as in `tests/test_engine/test_player_selector.py` and `tests/test_engine/test_dst_defensive_tds.py`.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def sample_pbp() -> pl.DataFrame:
    """Minimal PBP data mimicking nflreadpy output."""
    return pl.DataFrame([...])
```
- Put broad, shared fixtures in `tests/conftest.py`, especially PBP, schedules, kickoff/field goal data, rosters, red-zone samples, and traded-player fixtures.
- Keep one-off factories local to the test file, such as `_make_dists()` and `_make_roster()` in `tests/test_validation/test_parallel.py`, `_make_prop()` in `tests/test_scripts/test_scrape_pff_props.py`, and `_config()` in `tests/test_scoring/test_residual_calibration.py`.
- Use real dataclasses and domain objects in factories: `TeamDistributions`, `PlayCallingDist`, `PlayOutcomeDist`, `PlayerModel`, `PlayerUsage`, and `TeamRoster` in `tests/test_engine/test_player_selector.py`, `tests/test_engine/test_player_validation.py`, and `tests/test_validation/test_parallel.py`.

**Location:**
- Shared fixtures: `tests/conftest.py`
- Subsystem-specific fixtures: individual test modules such as `tests/test_data/test_pff/test_matchup.py`, `tests/test_data/test_pff/test_coverage.py`, `tests/test_data/test_weather/test_provider.py`, and `tests/test_scoring/test_dynamic_blend.py`.
- Script-specific fixtures and local imports: `tests/test_scripts/test_scrape_pff.py`, `tests/test_scripts/test_scrape_pff_props.py`, and `tests/test_scripts/test_fit_target_selection.py`.

## Coverage

**Requirements:** None enforced in `pyproject.toml`

**View Coverage:**
```bash
Not configured
```
- No coverage tool configuration is detected in `pyproject.toml`.
- Use targeted pytest commands first for changed modules, then `uv run pytest tests/ -v` for broad verification when the change touches shared engine, data, scoring, or validation behavior.

## Test Types

**Unit Tests:**
- Unit tests dominate the suite and use small deterministic fixtures. Examples: `tests/test_models/test_game_state.py`, `tests/test_config/test_loader.py`, `tests/test_scoring/test_engine.py`, `tests/test_validation/test_metrics.py`, and `tests/test_data/test_loader.py`.
- Unit tests assert exact values for pure helpers and use `pytest.approx` for floats. Examples: scoring and metric assertions in `tests/test_validation/test_metrics.py`, `tests/test_validation/test_weekly.py`, and `tests/test_data/test_actuals.py`.
- Unit tests for loaders should assert cache behavior, schema behavior, and fallback behavior using `tmp_path` and mocked external calls, as in `tests/test_data/test_loader.py`, `tests/test_data/test_weather/test_provider.py`, and `tests/test_data/test_vegas/test_props_engine.py`.

**Integration Tests:**
- Integration-style tests live under both `tests/test_integration/` and subsystem-specific `*_integration.py` files, such as `tests/test_data/test_pff/test_matchup_integration.py`, `tests/test_data/test_pff/test_qb_split_integration.py`, `tests/test_data/test_pff/test_rb_scheme_fit_integration.py`, `tests/test_data/test_weather/test_integration.py`, and `tests/test_data/test_vegas/test_integration.py`.
- Use integration tests to verify pipeline ordering, cross-module wiring, and config-driven engine activation. Examples: PFF integration tests in `tests/test_data/test_pff/`, weather integration tests in `tests/test_data/test_weather/test_integration.py`, and usage integration tests in `tests/test_data/test_usage/test_usage_integration.py`.
- Mark external-network tests with `@pytest.mark.integration` when they call real external services. The marker is registered in `pyproject.toml`; unit tests should mock external calls by default.

**E2E Tests:**
- Lightweight end-to-end coverage exists in `tests/test_integration/test_end_to_end.py`, `tests/test_smoke.py`, and CLI flows in `tests/test_cli.py`.
- Use `click.testing.CliRunner` for CLI entrypoint tests in `tests/test_cli.py`; patch expensive data loading/context building around CLI commands that should not hit network or slow caches.

**Script Tests:**
- Script tests import target scripts by adding `scripts/` to `sys.path`, as in `tests/test_scripts/test_scrape_pff.py` and `tests/test_scripts/test_scrape_pff_props.py`.
- Script tests should mock HTTP, sleep, filesystem roots, and command-side dependencies. Examples: retry/auth tests in `tests/test_scripts/test_scrape_pff.py`, pagination/cache tests in `tests/test_scripts/test_scrape_pff_props.py`, and ledger tests in `tests/test_scripts/test_ab_ledger.py`.

## Property And Statistical Testing

**Property-Based Tests:**
- Hypothesis is listed in optional dev dependencies in `pyproject.toml`, but no `@given`, `from hypothesis`, or `import hypothesis` tests are detected under `tests/`, `src/`, or `scripts/`.
- Use invariant-style pytest tests for properties until Hypothesis tests are added. Examples: hash/equality invariants in `tests/test_models/test_game_state.py`, deterministic parallel-vs-sequential invariants in `tests/test_validation/test_parallel.py`, and no-negative-average invariants in `tests/test_engine/test_player_validation.py`.
- New Hypothesis tests should live with the subsystem they exercise and use existing dataclasses/fixtures. Good candidates are scoring config invariants in `tests/test_config/test_loader.py`, yardline bounds in `tests/test_engine/test_game_flow.py`, and projection row numeric validity in `tests/test_validation/test_validate_script.py`.

**Statistical Tests:**
```python
@pytest.mark.statistical
def test_defensive_td_statistical_rate_on_interceptions():
    rng = np.random.default_rng(12345)
    n_trials = 5000
    ...
    assert 0.15 <= rate <= 0.25
```
- Mark slow stochastic plausibility tests with `@pytest.mark.statistical`. Existing examples: `tests/test_engine/test_dst_defensive_tds.py`, `tests/test_engine/test_player_validation.py`, `tests/test_engine/test_statistical_validation.py`, and `tests/test_data/test_pff/test_tier_engine.py`.
- Use deterministic seeds and wide domain-appropriate ranges for statistical tests. Examples: total points/play-count ranges in `tests/test_engine/test_statistical_validation.py`, player-level plausible ranges in `tests/test_engine/test_player_validation.py`, and defensive touchdown rate ranges in `tests/test_engine/test_dst_defensive_tds.py`.
- Run statistical tests explicitly with `uv run pytest tests/ -v -m statistical` when changing simulation probabilities, RNG flow, calibration gates, player selection, or empirical distributions.

## Common Patterns

**Async Testing:**
```python
Not detected
```
- No async test pattern is detected. Network-facing code such as `src/fantasy_sim/data/weather/provider.py` and scraper scripts uses synchronous `httpx` calls and is tested with synchronous mocks in `tests/test_data/test_weather/test_provider.py`, `tests/test_scripts/test_scrape_pff.py`, and `tests/test_scripts/test_scrape_pff_props.py`.

**Error Testing:**
```python
with pytest.raises(ConfigError):
    resolve_scoring(config["scoring"], "nonexistent")
```
- Use `pytest.raises` for config and validation errors, as in `tests/test_config/test_loader.py`, `tests/test_edge_cases.py`, `tests/test_validation/test_config.py`, and `tests/test_validation/test_validate_script.py`.
- Match exception text where behavior depends on actionable diagnostics, as in `tests/test_edge_cases.py`, `tests/test_validation/test_config.py`, and `tests/test_validation/test_backtester.py`.
- Use return-value assertions for graceful fallbacks instead of exceptions. Examples: `WeatherProvider.get_weather()` returning `None` in `tests/test_data/test_weather/test_provider.py`, `PropsLoader.load_props()` returning an empty DataFrame in `tests/test_data/test_vegas/test_props_engine.py`, and `load_ledger()` returning `[]` for missing files in `tests/test_validation/test_ledger.py`.

**DataFrame Testing:**
```python
result = loader.load_props(season=2024, week=6)
assert result.shape[0] == 1
assert result["player_id"].to_list() == [101]
```
- Use real `pl.DataFrame` fixtures and assert schema, column existence, shape, and exact lists. Examples: `tests/test_data/test_loader.py`, `tests/test_data/test_market_history/test_loader.py`, `tests/test_data/test_tracking/test_inputs_loader.py`, and `tests/test_data/test_pff/test_loader.py`.
- Write parquet files into `tmp_path` for loader/cache tests, as in `tests/test_data/test_loader.py`, `tests/test_data/test_market_history/test_importer.py`, and `tests/test_scripts/test_scrape_pff_props.py`.

**Validation Harness Testing:**
- Use `tests/test_validation/test_metrics.py` for pure metric behavior including Spearman, MAE, boom/bust calibration, and KS distribution summaries.
- Use `tests/test_validation/test_ledger.py` for ledger schema, legacy normalization, JSON round trips, and table formatting.
- Use `tests/test_validation/test_parallel.py` for worker-count behavior, `GameSpec`/`GameSimResult` dataclasses, deterministic parallel/sequential simulation, and failure handling.
- Use `tests/test_validation/test_validate_script.py` for `scripts/validate.py` behavior such as projection row validation, cache paths, config overrides, workers, and ledger integration.

---

*Testing analysis: 2026-04-24*
