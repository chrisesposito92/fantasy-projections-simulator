# Testing Patterns

**Analysis Date:** 2026-04-26

## Test Framework

**Runner:**
- pytest 8.0+ (defined in `pyproject.toml`)
- pytest-xdist 3.0+ for parallel test execution
- pytest-hypothesis 6.0+ for property-based testing
- Config: `tests/` directory, Python path includes `src`

**pytest Configuration:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["--import-mode=importlib"]
markers = [
    "integration: tests that call nflreadpy (slow, requires network)",
    "statistical: tests that run bulk simulations (slow)",
]
```

**Assertion Library:**
- pytest built-in assertions: `assert`, `assert X == Y`, `pytest.approx()`
- numpy testing: `np.testing.assert_array_almost_equal()` for float arrays

**Run Commands:**
```bash
# All tests (default)
uv run pytest tests/ -v

# Statistical validation tests only (simulation-heavy)
uv run pytest tests/ -v -m statistical

# Unit tests excluding integration + statistical
uv run pytest tests/ -v -m "not integration and not statistical"

# Watch mode with pytest-watch (if installed)
pytest-watch tests/ -- -v

# Coverage report
pytest --cov=src/fantasy_sim tests/
```

## Test File Organization

**Location:**
- Tests co-located with source: `tests/test_data/test_player_builder.py` mirrors `src/fantasy_sim/data/player_builder.py`
- Top-level test files: `tests/test_smoke.py`, `tests/test_cli.py`, `tests/test_edge_cases.py`
- Subdirectories for complex modules: `tests/test_engine/`, `tests/test_data/test_pff/`, `tests/test_data/test_ensemble/`

**Naming:**
- Test files: `test_*.py` prefix (e.g., `test_player_builder.py`, `test_td_tendency_engine.py`)
- Test classes: `Test[ModuleName]` (e.g., `TestBuildPlayerModels`, `TestRedZoneCatchRate`, `TestTdTendencyBayesianBlend`)
- Test methods: `test_[specific_behavior]` (e.g., `test_returns_dict_of_player_models`, `test_wr_has_target_share`, `test_target_shares_per_team_sum_near_one`)

**Directory Structure:**
```
tests/
├── conftest.py                          # Shared fixtures (PBP, rosters, schedules, kickoffs, field goals)
├── test_smoke.py                        # Import smoke tests
├── test_cli.py                          # CLI integration tests
├── test_edge_cases.py                   # Edge cases
├── test_config/
│   └── test_loader.py                   # Config loading and inheritance
├── test_data/
│   ├── test_player_builder.py           # Player model building (1200+ tests across codebase)
│   ├── test_loader.py                   # Data loading
│   ├── test_pipeline.py                 # Data pipeline
│   ├── test_availability/
│   │   ├── test_engine.py
│   │   └── test_loader.py
│   ├── test_ensemble/
│   │   ├── test_config.py
│   │   ├── test_loader.py
│   │   └── test_normalizer.py
│   ├── test_pff/
│   │   ├── test_tier_engine.py
│   │   ├── test_matchup.py
│   │   ├── test_coverage.py
│   │   ├── test_qb_split.py
│   │   ├── test_rb_scheme_fit.py
│   │   └── test_talent.py
│   └── test_market_history/
│       ├── test_loader.py
│       └── test_importer.py
└── test_engine/
    ├── test_statistical_validation.py   # @pytest.mark.statistical
    ├── test_player_validation.py        # Statistical validation of player outputs
    └── test_play_caller.py              # Play calling logic
```

## Test Structure

**Suite Organization:**
```python
# tests/test_data/test_player_builder.py
import numpy as np
import polars as pl
import pytest
from fantasy_sim.data.player_builder import (
    build_player_models, build_team_roster, blend_with_archetype,
    _aggregate_pbp_stats, build_kicker_model, _assemble_models,
    _build_season_weights,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


class TestBuildPlayerModels:
    """Test player model construction from PBP data."""
    
    def test_returns_dict_of_player_models(self, expanded_pbp, sample_rosters):
        models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
        assert isinstance(models, dict)
        assert "PM15" in models
```

**Patterns:**

1. **Setup/Fixtures:**
   - Fixtures in `tests/conftest.py` provide sample data
   - Fixture scope: `function` (default, fresh per test), `class` (shared in class), `scope="class"` for expensive setup
   - Example: `@pytest.fixture` decorated functions returning sample DataFrames

2. **Assertions:**
   - Exact match: `assert pm.name == "P.Mahomes"`
   - Float approx: `assert total_ts == pytest.approx(1.0, abs=0.05)` (within 0.05 absolute tolerance)
   - Range checks: `assert 0.40 <= s["home_win_pct"] <= 0.60`
   - Array checks: `assert len(tk.outcomes.receiving_yards_dist) > 0`

3. **Parametrization:**
   - `@pytest.mark.parametrize("source_seasons", [[], [2024], [2023, 2024], ["2023"]])`
   - `@pytest.mark.parametrize("field", ["min_examples", "min_tail_samples"])`
   - Used for testing multiple scenarios without code duplication

4. **Error Testing:**
   ```python
   def test_raises_error_on_circular_inherit(self):
       with pytest.raises(ConfigError, match="Circular _inherit detected"):
           resolve_scoring(circular_presets, "format_a")
   ```

## Mocking

**Framework:** `unittest.mock.patch` from Python standard library

**Patterns:**
- Mock external data loaders to avoid network calls:
```python
@pytest.fixture
def mock_pbp_loader(monkeypatch):
    """Mock nflreadpy to prevent network calls in unit tests."""
    def mock_load(season, weeks=None):
        return sample_pbp()
    monkeypatch.setattr("fantasy_sim.data.loader.nflreadpy.load_pbp", mock_load)
```

- Patch at module level where import occurs (not at definition):
```python
from unittest.mock import patch

with patch("fantasy_sim.data.nflreadpy.load_pbp") as mock_load:
    mock_load.return_value = sample_pbp
```

**What to Mock:**
- External APIs (nflreadpy, PFF endpoints, weather, odds API)
- File I/O that would require local data
- Network calls in unit tests

**What NOT to Mock:**
- Internal functions (test them directly)
- Numpy/Polars (test actual computation)
- Game simulation (statistical tests run full simulations)
- Config loading (test YAML resolution with real files)

## Fixtures and Factories

**Test Data:**
From `tests/conftest.py`:
```python
@pytest.fixture
def sample_pbp() -> pl.DataFrame:
    """Minimal PBP data mimicking nflreadpy output.
    
    Contains 20 plays: 12 passes, 8 runs across 2 teams (KC, BUF).
    Enough to compute basic distributions but small enough to verify by hand.
    """
    plays = [
        {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF", "play_type": "pass", 
         "posteam": "KC", "defteam": "BUF", "down": 1, "ydstogo": 10, "yardline_100": 75, 
         "score_differential": 0, "qtr": 1, "yards_gained": 12, "complete_pass": 1, ...},
        # ... more plays
    ]
    return pl.DataFrame(plays)

@pytest.fixture
def expanded_pbp() -> pl.DataFrame:
    """Larger PBP sample for player builder tests — 60 plays per team."""
    rng = np.random.RandomState(42)
    plays = []
    # KC: 40 passes, 20 runs
    # BUF: 30 passes, 30 runs
    for i in range(...):
        plays.append({...})
    return pl.DataFrame(plays)

@pytest.fixture
def sample_rosters() -> pl.DataFrame:
    """Minimal weekly roster data for KC and BUF."""
    rows = []
    for week in range(1, 4):
        rows.extend([
            {"season": 2024, "week": week, "player_id": "PM15", "player_name": "P.Mahomes", ...},
            ...
        ])
    return pl.DataFrame(rows)
```

**Location:**
- Shared fixtures in `tests/conftest.py` (pytest auto-discovers)
- Domain-specific fixtures in test files or their conftest subdirectories
- PBP fixture variations: `sample_pbp` (20 plays), `expanded_pbp` (60 plays), `rz_pbp` (red zone), `air_yards_pbp`, `scramble_pbp`, `scramble_qb_pbp`
- Roster fixtures: `sample_rosters`, `traded_player_rosters`, `midseason_trade_rosters`

## Coverage

**Requirements:** 
- No explicit coverage requirement enforced in CI
- Project maintains 1,200+ tests covering all major paths
- Coverage focuses on domain logic (simulation, scoring, data loading)

**View Coverage:**
```bash
pytest --cov=src/fantasy_sim --cov-report=html tests/
# Opens htmlcov/index.html
```

## Test Types

**Unit Tests:**
- Scope: Single function or method in isolation
- Approach: Fixtures provide sample data, test logic with known inputs
- Example: `test_wr_has_target_share()` checks WR usage calculation
- Speed: <1ms per test
- Markers: None (default)

**Integration Tests:**
- Scope: Multiple components working together
- Markers: `@pytest.mark.integration` (slow, requires external data)
- Approach: Call real loaders (nflreadpy mocked in conftest), test data flow
- Example: `test_game_context_builds_with_real_schedule()` loads nflverse data
- Speed: 1-10 seconds per test (network calls mocked but data loading is real)
- Run: `pytest -m integration` only when needed

**Statistical Validation Tests:**
- Scope: Bulk simulations (2000+ games) against NFL ground truth
- Markers: `@pytest.mark.statistical`
- Approach: `run_simulations()` with league-average distributions, verify summary stats
- Example: `TestStatisticalValidation.test_average_total_points()` checks game totals are 30-65 points
- Speed: 30-120 seconds per test (computationally intensive)
- Run: `pytest -m statistical` for accuracy validation before merge
- Fixture scope: `@pytest.fixture(scope="class")` to share 2000-game result across tests

Example from `tests/test_engine/test_statistical_validation.py`:
```python
@pytest.mark.statistical
class TestStatisticalValidation:
    """Run 2000 simulated games and verify NFL-realistic averages."""
    
    @pytest.fixture(scope="class")
    def sim_results(self):
        dists = make_league_avg_dists()
        return run_simulations(dists, dists, n_sims=2000, seed=42)
    
    def test_average_total_points(self, sim_results):
        """NFL average is ~45-48 points per game."""
        s = sim_results.summary()
        assert 30 <= s["total_score_mean"] <= 65
```

## Common Patterns

**Async Testing:**
- Not applicable (no async code in project)
- All functions are synchronous with explicit RNG passing

**Error Testing:**
```python
def test_raises_no_qb_on_roster(self, sample_rosters):
    models = {
        "TK87": PlayerModel(..., position="TE", team="KC", ...),
        "IP01": PlayerModel(..., position="RB", team="KC", ...),
    }
    roster = TeamRoster("KC", list(models.values()))
    
    with pytest.raises(ValueError, match="No QB found on roster"):
        roster.get_starting_qb()
```

**Fixture Usage - Clean Data:**
```python
def test_target_shares_per_team_sum_near_one(self, expanded_pbp, sample_rosters):
    """Regression: target shares must sum to 1.0 per team after normalization."""
    models = build_player_models(expanded_pbp, sample_rosters, training_seasons=[2024])
    kc_players = [m for m in models.values() if m.team == "KC"]
    total_ts = sum(p.usage.target_share for p in kc_players)
    assert total_ts == pytest.approx(1.0, abs=0.05)
```

**Probabilistic Testing (Hypothesis):**
- Uses `@given` decorator for property-based testing (not yet in project)
- Example pattern (can be applied):
```python
from hypothesis import given, strategies as st

@given(st.integers(min_value=1, max_value=99))
def test_yardline_always_in_range(yardline):
    """yardline_100 must always be 1-99."""
    assert 1 <= yardline <= 99
```

**Regression Notes:**
- Tests include comments explaining what they prevent:
```python
def test_roster_normalizes_carry_shares(self):
    """Carry shares must sum to 1.0 after roster construction.
    
    Regression: when former players had carries in training data but
    aren't on the current roster, raw carry_shares summed to <1.0.
    select_rusher normalizes weights, amplifying each player's actual
    selection probability beyond the intended share value.
    """
```

## Validation Harness

**A/B Testing Approach:**
- Not automated in pytest (manual by user with scripts)
- Ledger persistence: `scripts/validate.py --show-ledger` displays A/B results
- Configuration: `--mode all`, `--mode vegas`, `--mode vegas+spread`, `--mode vegas+props`
- Metrics: Spearman rank correlation, MAE, boom-bust differential, KS distribution test
- Runs: 50-200+ simulations per A/B pair depending on accuracy needed

---

*Testing analysis: 2026-04-26*
