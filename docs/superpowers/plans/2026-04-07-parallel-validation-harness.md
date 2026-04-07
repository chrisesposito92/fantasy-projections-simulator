# Parallel Validation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallelize A/B validation game simulations across CPU cores for ~3-5x speedup.

**Architecture:** Pre-build game contexts sequentially (preserving GameContextBuilder cache benefits), then fan out CPU-bound `run_simulations()` + `build_player_projections()` calls to a ProcessPoolExecutor worker pool. A new shared `validation/parallel.py` module provides the parallel runner used by both Backtester and the validation scripts.

**Tech Stack:** Python `concurrent.futures.ProcessPoolExecutor`, `os.cpu_count()`, existing `numpy`/`dataclass` types.

**Spec:** `docs/superpowers/specs/2026-04-07-parallel-validation-harness-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/fantasy_sim/validation/parallel.py` | **New.** GameSpec, GameSimResult dataclasses. `simulate_games_parallel()` entry point. `default_max_workers()` adaptive sizing. Module-level `_simulate_worker()` for multiprocessing. |
| `src/fantasy_sim/validation/backtester.py` | **Modify.** Add `max_workers` param. Restructure `run()` into 3 phases: build contexts, simulate parallel, aggregate. |
| `scripts/validate_pff_signal.py` | **Modify.** Add `--workers` CLI arg. Pass `max_workers` to `run_backtest_pair()` and down to Backtester. |
| `scripts/validate_weekly_signal.py` | **Modify.** Add `--workers` CLI arg. Restructure `run_weekly_comparison()` into 3 phases using `simulate_games_parallel()`. |
| `tests/test_validation/test_parallel.py` | **New.** Tests for parallel runner: determinism, sequential fallback, adaptive workers, error isolation, metadata passthrough. |

---

## Task 1: Core Parallel Runner Module

**Files:**
- Create: `src/fantasy_sim/validation/parallel.py`
- Test: `tests/test_validation/test_parallel.py`

### Step 1.1: Write test for default_max_workers

- [ ] **Write the test**

```python
# tests/test_validation/test_parallel.py
"""Tests for parallel game simulation runner."""

import os
from unittest.mock import patch

from fantasy_sim.validation.parallel import default_max_workers


class TestDefaultMaxWorkers:
    def test_basic_computation(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 10  # (12 - 2) // 1 = 10, min(10, 288) = 10

    def test_scales_by_concurrent_seasons(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=2)
            assert result == 5  # (12 - 2) // 2 = 5

    def test_capped_by_batch_size(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=3, num_concurrent=1)
            assert result == 3  # min(10, 3) = 3

    def test_minimum_one_worker(self):
        with patch.object(os, "cpu_count", return_value=2):
            result = default_max_workers(batch_size=100, num_concurrent=4)
            assert result == 1  # max(1, (2-2)//4) = 1

    def test_zero_batch_size(self):
        result = default_max_workers(batch_size=0, num_concurrent=1)
        assert result == 0

    def test_cpu_count_none_fallback(self):
        with patch.object(os, "cpu_count", return_value=None):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 6  # (8 - 2) // 1 = 6 (fallback to 8)
```

- [ ] **Run test to verify it fails**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestDefaultMaxWorkers -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

### Step 1.2: Implement default_max_workers

- [ ] **Write the implementation**

```python
# src/fantasy_sim/validation/parallel.py
"""Parallel game simulation runner for validation harnesses."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def default_max_workers(batch_size: int, num_concurrent: int = 1) -> int:
    """Compute adaptive worker count based on CPU cores and batch size.

    Args:
        batch_size: Number of game specs to simulate.
        num_concurrent: Number of concurrent season-level processes sharing CPUs.

    Returns:
        Worker count: max(1, min((cpu_count - 2) // num_concurrent, batch_size)).
        Returns 0 if batch_size is 0.
    """
    if batch_size == 0:
        return 0
    cpus = os.cpu_count() or 8
    per_pool = max(1, (cpus - 2) // max(1, num_concurrent))
    return min(per_pool, batch_size)
```

- [ ] **Run test to verify it passes**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestDefaultMaxWorkers -v`
Expected: All 7 tests PASS

### Step 1.3: Write test for GameSpec and GameSimResult dataclasses

- [ ] **Add dataclass tests to test file**

Append to `tests/test_validation/test_parallel.py`:

```python
import numpy as np

from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.validation.parallel import GameSpec, GameSimResult


def _make_dists(team: str) -> TeamDistributions:
    """Minimal TeamDistributions for tests."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 5, 8, 10, 12, 15]),
            "run": np.array([2, 3, 4, 5, 6]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


def _make_roster(team: str) -> TeamRoster:
    """Minimal TeamRoster for tests."""
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                   PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                   PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                 catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
    ])


class TestGameSpecDataclass:
    def test_creation(self):
        spec = GameSpec(
            game_id="2024_01_KC_BUF",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=_make_roster("KC"),
            away_roster=_make_roster("BUF"),
            seed=12345,
            week=1,
            metadata={"arm": "off"},
        )
        assert spec.game_id == "2024_01_KC_BUF"
        assert spec.seed == 12345
        assert spec.metadata["arm"] == "off"

    def test_metadata_defaults_to_empty(self):
        spec = GameSpec(
            game_id="test",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=None,
            away_roster=None,
            seed=0,
            week=1,
        )
        assert spec.metadata == {}
```

### Step 1.4: Add GameSpec and GameSimResult to implementation

- [ ] **Add dataclasses to parallel.py**

Append to `src/fantasy_sim/validation/parallel.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fantasy_sim.engine.types import TeamDistributions
    from fantasy_sim.models.player import TeamRoster


@dataclass
class GameSpec:
    """Pre-built game context ready for parallel simulation."""
    game_id: str
    home_dists: TeamDistributions
    away_dists: TeamDistributions
    home_roster: TeamRoster | None
    away_roster: TeamRoster | None
    seed: int
    week: int
    metadata: dict = field(default_factory=dict)


@dataclass
class GameSimResult:
    """Result from one parallel simulation."""
    game_id: str
    projections: list[dict]
    metadata: dict = field(default_factory=dict)
```

- [ ] **Run tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_parallel.py -v`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add src/fantasy_sim/validation/parallel.py tests/test_validation/test_parallel.py
git commit -m "feat(parallel): add GameSpec, GameSimResult, and default_max_workers"
```

---

## Task 2: Parallel Simulation Runner

**Files:**
- Modify: `src/fantasy_sim/validation/parallel.py`
- Test: `tests/test_validation/test_parallel.py`

### Step 2.1: Write test for sequential fallback (workers=1)

- [ ] **Add test**

Append to `tests/test_validation/test_parallel.py`:

```python
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.validation.parallel import simulate_games_parallel


def _make_spec(game_id: str, seed: int, metadata: dict | None = None) -> GameSpec:
    """Helper to create a GameSpec with minimal valid context."""
    return GameSpec(
        game_id=game_id,
        home_dists=_make_dists("KC"),
        away_dists=_make_dists("BUF"),
        home_roster=_make_roster("KC"),
        away_roster=_make_roster("BUF"),
        seed=seed,
        week=1,
        metadata=metadata or {},
    )


class TestSimulateGamesParallel:
    def _get_scoring_config(self) -> dict:
        defaults = load_defaults()
        return resolve_scoring(defaults["scoring"], "ppr")

    def test_sequential_returns_results(self):
        specs = [_make_spec("game_a", seed=42), _make_spec("game_b", seed=99)]
        scoring = self._get_scoring_config()
        results = simulate_games_parallel(specs, n_sims=5, scoring_config=scoring, max_workers=1)
        assert len(results) == 2
        game_ids = {r.game_id for r in results}
        assert game_ids == {"game_a", "game_b"}
        for r in results:
            assert isinstance(r.projections, list)
            assert len(r.projections) > 0

    def test_empty_specs_returns_empty(self):
        scoring = self._get_scoring_config()
        results = simulate_games_parallel([], n_sims=5, scoring_config=scoring, max_workers=1)
        assert results == []
```

- [ ] **Run test to verify it fails**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestSimulateGamesParallel -v`
Expected: FAIL with `ImportError` (simulate_games_parallel not yet defined)

### Step 2.2: Write test for determinism (parallel == sequential)

- [ ] **Add determinism test**

Append to `TestSimulateGamesParallel` class:

```python
    def test_determinism_parallel_matches_sequential(self):
        """Same seeds must produce identical projections regardless of worker count."""
        specs = [
            _make_spec("game_1", seed=100),
            _make_spec("game_2", seed=200),
            _make_spec("game_3", seed=300),
        ]
        scoring = self._get_scoring_config()

        sequential = simulate_games_parallel(specs, n_sims=10, scoring_config=scoring, max_workers=1)
        parallel = simulate_games_parallel(specs, n_sims=10, scoring_config=scoring, max_workers=2)

        # Sort both by game_id for stable comparison
        seq_by_id = {r.game_id: r for r in sequential}
        par_by_id = {r.game_id: r for r in parallel}

        assert set(seq_by_id.keys()) == set(par_by_id.keys())
        for game_id in seq_by_id:
            seq_projs = {p["player_id"]: p["fpts"] for p in seq_by_id[game_id].projections}
            par_projs = {p["player_id"]: p["fpts"] for p in par_by_id[game_id].projections}
            assert seq_projs == par_projs, f"Mismatch for {game_id}"
```

### Step 2.3: Write test for metadata passthrough

- [ ] **Add metadata test**

Append to `TestSimulateGamesParallel` class:

```python
    def test_metadata_passthrough(self):
        specs = [
            _make_spec("game_off", seed=42, metadata={"arm": "off"}),
            _make_spec("game_on", seed=42, metadata={"arm": "on"}),
        ]
        scoring = self._get_scoring_config()
        results = simulate_games_parallel(specs, n_sims=5, scoring_config=scoring, max_workers=1)
        meta_by_id = {r.game_id: r.metadata for r in results}
        assert meta_by_id["game_off"]["arm"] == "off"
        assert meta_by_id["game_on"]["arm"] == "on"
```

### Step 2.4: Write test for error isolation

- [ ] **Add error isolation test**

Append to `TestSimulateGamesParallel` class:

```python
    def test_error_isolation_skips_failed_games(self):
        """A broken spec should not prevent other specs from completing."""
        good_spec = _make_spec("good_game", seed=42)
        bad_spec = GameSpec(
            game_id="bad_game",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=None,  # No roster - will still work (rosters optional)
            away_roster=None,
            seed=99,
            week=1,
        )
        # Sabotage: set play_outcomes to None to force an error in simulate_game
        bad_spec.home_dists.play_outcomes = None  # type: ignore[assignment]

        scoring = self._get_scoring_config()
        results = simulate_games_parallel(
            [good_spec, bad_spec], n_sims=5, scoring_config=scoring, max_workers=1
        )
        # Good game should still succeed
        assert len(results) >= 1
        assert any(r.game_id == "good_game" for r in results)
```

### Step 2.5: Write test for on_complete callback

- [ ] **Add callback test**

Append to `TestSimulateGamesParallel` class:

```python
    def test_on_complete_callback_fires(self):
        specs = [_make_spec("g1", seed=1), _make_spec("g2", seed=2)]
        scoring = self._get_scoring_config()
        completed = []
        results = simulate_games_parallel(
            specs, n_sims=5, scoring_config=scoring, max_workers=1,
            on_complete=lambda done, total: completed.append((done, total)),
        )
        assert len(results) == 2
        assert len(completed) == 2
        assert completed[-1] == (2, 2)
```

### Step 2.6: Implement simulate_games_parallel and _simulate_worker

- [ ] **Add implementation to parallel.py**

Append to `src/fantasy_sim/validation/parallel.py`:

```python
from typing import Callable

from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.scoring.projections import build_player_projections


def _simulate_worker(args: tuple) -> GameSimResult:
    """Worker function for parallel simulation.

    Must be module-level (not a closure) for ProcessPoolExecutor.
    Takes a tuple to work with pool.submit().
    """
    spec, n_sims, scoring_config = args
    results = run_simulations(
        spec.home_dists,
        spec.away_dists,
        n_sims=n_sims,
        seed=spec.seed,
        home_roster=spec.home_roster,
        away_roster=spec.away_roster,
        week=spec.week,
    )
    projections = build_player_projections(results.games, scoring_config)
    return GameSimResult(
        game_id=spec.game_id,
        projections=projections,
        metadata=spec.metadata,
    )


def simulate_games_parallel(
    specs: list[GameSpec],
    n_sims: int,
    scoring_config: dict,
    max_workers: int | None = None,
    on_complete: Callable[[int, int], None] | None = None,
) -> list[GameSimResult]:
    """Run simulations for multiple games, optionally in parallel.

    Args:
        specs: Pre-built game contexts to simulate.
        n_sims: Number of Monte Carlo simulations per game.
        scoring_config: Fantasy scoring configuration dict.
        max_workers: Worker processes. None=auto, 1=sequential, 0=auto.
        on_complete: Optional callback(completed_count, total_count).

    Returns:
        List of GameSimResult (one per successfully simulated game).
    """
    if not specs:
        return []

    if max_workers is None or max_workers == 0:
        max_workers = default_max_workers(len(specs))

    total = len(specs)
    results: list[GameSimResult] = []

    if max_workers <= 1:
        # Sequential path — no multiprocessing overhead
        for i, spec in enumerate(specs):
            try:
                result = _simulate_worker((spec, n_sims, scoring_config))
                results.append(result)
            except Exception:
                logger.warning("Game %s failed, skipping", spec.game_id)
            if on_complete:
                on_complete(i + 1, total)
        return results

    # Parallel path
    from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed

    try:
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_simulate_worker, (spec, n_sims, scoring_config)): spec
                for spec in specs
            }
            completed = 0
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception:
                    logger.warning("Game %s failed, skipping", spec.game_id)
                completed += 1
                if on_complete:
                    on_complete(completed, total)
    except BrokenExecutor:
        logger.error(
            "Worker process crashed. Try --workers 1 for sequential mode."
        )

    return results
```

- [ ] **Run all parallel tests**

Run: `uv run pytest tests/test_validation/test_parallel.py -v`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add src/fantasy_sim/validation/parallel.py tests/test_validation/test_parallel.py
git commit -m "feat(parallel): implement simulate_games_parallel with sequential fallback"
```

---

## Task 3: Backtester Integration

**Files:**
- Modify: `src/fantasy_sim/validation/backtester.py` (lines 51-181)
- Test: `tests/test_validation/test_parallel.py`

### Step 3.1: Write test for Backtester max_workers param

- [ ] **Add test**

Append to `tests/test_validation/test_parallel.py`:

```python
from fantasy_sim.validation.backtester import Backtester


class TestBacktesterParallel:
    def test_default_max_workers_is_one(self):
        bt = Backtester(test_season=2024, n_sims=10)
        assert bt.max_workers == 1

    def test_max_workers_param(self):
        bt = Backtester(test_season=2024, n_sims=10, max_workers=4)
        assert bt.max_workers == 4
```

- [ ] **Run test to verify it fails**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBacktesterParallel -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'max_workers'`

### Step 3.2: Add max_workers param to Backtester.__init__

- [ ] **Modify backtester.py**

In `src/fantasy_sim/validation/backtester.py`, change the `__init__` signature (line 54) to add `max_workers`:

Change:
```python
    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
    ):
```

To:
```python
    def __init__(
        self,
        test_season: int,
        n_sims: int = 100,
        num_training_seasons: int = 3,
        scoring_format: str = "ppr",
        cache_dir: Path | None = None,
        pff_config: PffConfig | None = None,
        weather_config: WeatherConfig | None = None,
        max_workers: int = 1,
    ):
```

And add after `self.builder = GameContextBuilder(...)` (after line 73):

```python
        self.max_workers = max_workers
```

- [ ] **Run test to verify it passes**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBacktesterParallel -v`
Expected: PASS

### Step 3.3: Restructure Backtester.run() into 3 phases

- [ ] **Rewrite `run()` method**

Replace the `run()` method in `src/fantasy_sim/validation/backtester.py` (lines 75-181). The new method has 3 phases:

```python
    def run(self, scoring_config: dict) -> BacktestResult:
        """Run the full backtest for one season.

        Uses only training_seasons data for model fitting (no leakage).
        Three phases: build contexts -> simulate (optionally parallel) -> aggregate.
        """
        from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel

        schedules = self.loader.load_schedules([self.test_season])
        player_stats = self.loader.load_player_stats([self.test_season])

        actuals = load_actual_scores(player_stats, scoring_config, self.test_season)
        actual_by_player_week = defaultdict(dict)
        for a in actuals:
            actual_by_player_week[a.player_id][a.week] = a.fpts

        weeks = sorted(
            schedules.filter(pl.col("season") == self.test_season)["week"]
            .unique().to_list()
        )
        weeks = [w for w in weeks if 1 <= w <= 18]

        # --- Phase 1: Build game contexts (sequential, cache-friendly) ---
        specs: list[GameSpec] = []
        for wk in weeks:
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == self.test_season)
            )
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                try:
                    home_dists, away_dists, home_roster, away_roster = self.builder.build_game(
                        home, away,
                        training_seasons=self.training_seasons,
                        target_season=self.test_season,
                        week=wk,
                    )
                    seed = zlib.crc32(game["game_id"].encode()) % (2**31)
                    specs.append(GameSpec(
                        game_id=game["game_id"],
                        home_dists=home_dists,
                        away_dists=away_dists,
                        home_roster=home_roster,
                        away_roster=away_roster,
                        seed=seed,
                        week=wk,
                    ))
                except Exception:
                    continue

        # --- Phase 2: Simulate (parallel or sequential) ---
        sim_results = simulate_games_parallel(
            specs, n_sims=self.n_sims, scoring_config=scoring_config,
            max_workers=self.max_workers,
        )

        # --- Phase 3: Aggregate results ---
        projected_by_player_week = defaultdict(dict)
        all_weekly_errors = []

        spec_by_id = {s.game_id: s for s in specs}

        for result in sim_results:
            spec = spec_by_id[result.game_id]
            wk = spec.week
            for proj in result.projections:
                pid = proj["player_id"]
                projected_by_player_week[pid][wk] = proj["fpts"]
                if pid in actual_by_player_week and wk in actual_by_player_week[pid]:
                    error = abs(proj["fpts"] - actual_by_player_week[pid][wk])
                    all_weekly_errors.append(error)

        weekly_mae = float(np.mean(all_weekly_errors)) if all_weekly_errors else 99.0

        proj_totals = {pid: sum(wks.values()) for pid, wks in projected_by_player_week.items()}
        act_totals = {pid: sum(wks.values()) for pid, wks in actual_by_player_week.items()}
        common = set(proj_totals.keys()) & set(act_totals.keys())
        season_errors = [abs(proj_totals[pid] - act_totals[pid]) for pid in common]
        season_mae_val = float(np.mean(season_errors)) if season_errors else 99.0

        rank_correlations = {}
        for position in ["QB", "RB", "WR", "TE"]:
            pos_actuals = {
                a.player_id: a for a in actuals
                if a.position == position
            }
            pos_proj = []
            pos_act = []
            for pid in common:
                if pid in pos_actuals:
                    pos_proj.append(proj_totals[pid])
                    pos_act.append(act_totals[pid])
            if len(pos_proj) >= 5:
                rank_correlations[position] = spearman_rank_correlation(pos_proj, pos_act)
            else:
                rank_correlations[position] = 0.0

        boom_threshold = 20.0
        predicted_boom = {}
        actual_boom = {}
        for pid in common:
            proj_weeks = projected_by_player_week.get(pid, {})
            act_weeks = actual_by_player_week.get(pid, {})
            if len(act_weeks) >= 5:
                predicted_boom[pid] = sum(
                    1 for v in proj_weeks.values() if v >= boom_threshold
                ) / max(len(proj_weeks), 1)
                actual_boom[pid] = sum(
                    1 for v in act_weeks.values() if v >= boom_threshold
                ) / len(act_weeks)

        cal = boom_bust_calibration(predicted_boom, actual_boom) if predicted_boom else 0.5

        return BacktestResult(
            test_season=self.test_season,
            weekly_mae=weekly_mae,
            season_mae=season_mae_val,
            rank_correlations=rank_correlations,
            boom_bust_calibration=cal,
            total_players_evaluated=len(common),
            total_weeks_evaluated=len(weeks),
        )
```

- [ ] **Run existing backtester tests to verify no regression**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`
Expected: All existing tests PASS (max_workers defaults to 1 = same sequential behavior)

- [ ] **Run new parallel tests**

Run: `uv run pytest tests/test_validation/test_parallel.py -v`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add src/fantasy_sim/validation/backtester.py tests/test_validation/test_parallel.py
git commit -m "feat(backtester): restructure run() into 3 phases with parallel support"
```

---

## Task 4: validate_pff_signal.py Integration

**Files:**
- Modify: `scripts/validate_pff_signal.py` (lines 466-527 `run_backtest_pair`, lines 642-850 `main`)

### Step 4.1: Add max_workers param to run_backtest_pair

- [ ] **Modify function signature**

In `scripts/validate_pff_signal.py`, change `run_backtest_pair` (line 466):

From:
```python
def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    weather_config: WeatherConfig | None = None,
) -> ComparisonResult:
```

To:
```python
def run_backtest_pair(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    weather_config: WeatherConfig | None = None,
    max_workers: int = 1,
) -> ComparisonResult:
```

### Step 4.2: Pass max_workers to Backtester instances

- [ ] **Modify the two Backtester() calls**

Change the PFF-OFF Backtester creation (line 478):

From:
```python
    bt_off = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
    )
```

To:
```python
    bt_off = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        max_workers=max_workers,
    )
```

Change the PFF-ON Backtester creation (line 513):

From:
```python
    bt_on = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=pff_config,
        weather_config=weather_config,
    )
```

To:
```python
    bt_on = Backtester(
        test_season=test_season,
        n_sims=n_sims,
        num_training_seasons=num_training_seasons,
        pff_config=pff_config,
        weather_config=weather_config,
        max_workers=max_workers,
    )
```

### Step 4.3: Add --workers CLI argument to main()

- [ ] **Add argparse argument**

In `main()`, after the `--config-override` argument (after line 731), add:

```python
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Worker processes for game simulation (0=auto, 1=sequential). Default: auto.",
    )
```

### Step 4.4: Compute per_season_workers and pass to run_backtest_pair

- [ ] **Add import and worker computation**

After the existing imports at the top of the file (around line 31), add:

```python
from fantasy_sim.validation.parallel import default_max_workers
```

In `main()`, after config printing (after line 759), add:

```python
    # Compute per-season worker count
    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=288, num_concurrent=num_seasons)
    print(f"  workers       : {per_season_workers} per season")
```

### Step 4.5: Pass max_workers in season submission

- [ ] **Modify the parallel season block**

In the `ProcessPoolExecutor` block (line 774), change `pool.submit`:

From:
```python
                pool.submit(
                    run_backtest_pair,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    weather_config=weather_config,
                ): season
```

To:
```python
                pool.submit(
                    run_backtest_pair,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    weather_config=weather_config,
                    max_workers=per_season_workers,
                ): season
```

And the single-season path (line 797):

From:
```python
            comparison = run_backtest_pair(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                weather_config=weather_config,
            )
```

To:
```python
            comparison = run_backtest_pair(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                weather_config=weather_config,
                max_workers=per_season_workers,
            )
```

- [ ] **Run existing test suite to verify no regression**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add scripts/validate_pff_signal.py
git commit -m "feat(validate): add --workers flag to A/B validation harness"
```

---

## Task 5: validate_weekly_signal.py Integration

**Files:**
- Modify: `scripts/validate_weekly_signal.py` (lines 261-404 `run_weekly_comparison`, lines 407-595 `main`)

This is the most involved change — restructuring `run_weekly_comparison()` from inline per-game simulation into the 3-phase pattern.

### Step 5.1: Add max_workers param and import

- [ ] **Modify run_weekly_comparison signature**

In `scripts/validate_weekly_signal.py`, change the signature (line 261):

From:
```python
def run_weekly_comparison(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    positions: list[str],
    weather_config: WeatherConfig | None = None,
) -> list[WeeklyPlayerRecord]:
```

To:
```python
def run_weekly_comparison(
    test_season: int,
    n_sims: int,
    scoring_config: dict,
    num_training_seasons: int,
    pff_config: PffConfig,
    positions: list[str],
    weather_config: WeatherConfig | None = None,
    max_workers: int = 1,
) -> list[WeeklyPlayerRecord]:
```

Add import at the top of the file (after line 45):

```python
from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel, default_max_workers
```

### Step 5.2: Restructure into 3 phases

- [ ] **Rewrite the body of `run_weekly_comparison()`**

Replace the loop body (lines 299-404) with the 3-phase pattern:

```python
    # --- Phase 1: Build all game contexts (sequential, cache-friendly) ---
    specs: list[GameSpec] = []
    # Store per-game auxiliary data needed for Phase 3
    game_aux: dict[str, dict] = {}  # game_id -> {home, away, seed, week, matchup, coverage}

    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        print(f"  [{test_season}] Building contexts... Week {wk}/{max(weeks)}", flush=True)
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            game_id = game["game_id"]
            try:
                seed = zlib.crc32(game_id.encode()) % (2**31)

                # PFF-off context
                hd_off, ad_off, hr_off, ar_off = builder_off.build_game(
                    home, away,
                    training_seasons=training_seasons,
                    target_season=test_season, week=wk,
                )
                specs.append(GameSpec(
                    game_id=game_id,
                    home_dists=hd_off, away_dists=ad_off,
                    home_roster=hr_off, away_roster=ar_off,
                    seed=seed, week=wk,
                    metadata={"arm": "off"},
                ))

                # PFF-on context
                hd_on, ad_on, hr_on, ar_on = builder_on.build_game(
                    home, away,
                    training_seasons=training_seasons,
                    target_season=test_season, week=wk,
                )
                specs.append(GameSpec(
                    game_id=game_id,
                    home_dists=hd_on, away_dists=ad_on,
                    home_roster=hr_on, away_roster=ar_on,
                    seed=seed, week=wk,
                    metadata={"arm": "on"},
                ))

                # Capture matchup/coverage contexts (cheap, engines cached)
                home_matchup_ctx = MatchupContext()
                away_matchup_ctx = MatchupContext()
                if builder_on._matchup_engine is not None:
                    home_matchup_ctx = builder_on._matchup_engine.compute(
                        defense_team=away, offense_team=home,
                        target_season=test_season, max_week=wk,
                    )
                    away_matchup_ctx = builder_on._matchup_engine.compute(
                        defense_team=home, offense_team=away,
                        target_season=test_season, max_week=wk,
                    )

                home_coverage: dict = {}
                away_coverage: dict = {}
                if builder_on._coverage_engine is not None:
                    home_coverage = builder_on._coverage_engine.compute(
                        defense_team=away, offense_roster=hr_on,
                        target_season=test_season, max_week=wk,
                        pff_crosswalk=builder_on._pff_crosswalk,
                    )
                    away_coverage = builder_on._coverage_engine.compute(
                        defense_team=home, offense_roster=ar_on,
                        target_season=test_season, max_week=wk,
                        pff_crosswalk=builder_on._pff_crosswalk,
                    )

                game_aux[game_id] = {
                    "home": home, "away": away, "week": wk,
                    "home_matchup_ctx": home_matchup_ctx,
                    "away_matchup_ctx": away_matchup_ctx,
                    "home_coverage": home_coverage,
                    "away_coverage": away_coverage,
                }

            except Exception as exc:
                logger.warning(
                    "Skipping game %s vs %s week %d context build: %s", home, away, wk, exc
                )
                continue

    # --- Phase 2: Simulate all games (parallel) ---
    print(f"  [{test_season}] Simulating {len(specs)} game-arms...", flush=True)
    completed_count = [0]

    def _on_complete(done: int, total: int) -> None:
        # Print progress every 50 completions
        if done % 50 == 0 or done == total:
            print(f"    [{test_season}] {done}/{total} complete", flush=True)

    sim_results = simulate_games_parallel(
        specs, n_sims=n_sims, scoring_config=scoring_config,
        max_workers=max_workers, on_complete=_on_complete,
    )

    # --- Phase 3: Pair results and build records ---
    # Group by game_id and arm
    by_game: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for r in sim_results:
        by_game[r.game_id][r.metadata["arm"]] = r.projections

    records: list[WeeklyPlayerRecord] = []

    for game_id, arms in by_game.items():
        if "off" not in arms or "on" not in arms:
            continue  # skip incomplete pairs

        aux = game_aux.get(game_id)
        if aux is None:
            continue

        home = aux["home"]
        wk = aux["week"]
        home_matchup_ctx = aux["home_matchup_ctx"]
        away_matchup_ctx = aux["away_matchup_ctx"]
        home_coverage = aux["home_coverage"]
        away_coverage = aux["away_coverage"]

        # Index projections by player_id
        on_by_pid = {p["player_id"]: p for p in arms["on"]}
        off_by_pid = {p["player_id"]: p["fpts"] for p in arms["off"]}

        common_pids = set(on_by_pid.keys()) & set(off_by_pid.keys())

        for pid in common_pids:
            proj = on_by_pid[pid]
            pos = proj.get("position") or actual_pos.get(pid, "")
            if pos not in positions:
                continue
            if pid not in actual_by_pw or wk not in actual_by_pw[pid]:
                continue

            team = proj.get("team") or actual_team.get(pid, "")
            is_home = team == home

            matchup_ctx = home_matchup_ctx if is_home else away_matchup_ctx
            cov_map = home_coverage if is_home else away_coverage

            records.append(WeeklyPlayerRecord(
                player_id=pid,
                name=proj.get("name") or actual_name.get(pid, ""),
                position=pos,
                team=team,
                week=wk,
                season=test_season,
                projected_fpts_on=proj["fpts"],
                projected_fpts_off=off_by_pid[pid],
                actual_fpts=actual_by_pw[pid][wk],
                matchup_factors=_filter_matchup_factors(pos, matchup_ctx),
                coverage_modifiers=cov_map.get(pid) if pos == "WR" else None,
            ))

    return records
```

### Step 5.3: Add --workers CLI argument and pass through

- [ ] **Add argparse argument to main()**

After the `--config-override` argument (around line 446), add:

```python
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        metavar="N",
        help="Worker processes for game simulation (0=auto, 1=sequential). Default: auto.",
    )
```

### Step 5.4: Compute and pass max_workers in main()

- [ ] **Add worker computation to main()**

After config printing (around line 469), add:

```python
    num_seasons = len(args.seasons)
    if args.workers == 1:
        per_season_workers = 1
    elif args.workers > 1:
        per_season_workers = args.workers
    else:
        per_season_workers = default_max_workers(batch_size=576, num_concurrent=num_seasons)
    print(f"  workers       : {per_season_workers} per season")
```

- [ ] **Pass max_workers to all run_weekly_comparison calls**

Update the `ProcessPoolExecutor` block `pool.submit` call to include `max_workers=per_season_workers`:

```python
                pool.submit(
                    run_weekly_comparison,
                    test_season=season,
                    n_sims=args.sims,
                    scoring_config=scoring_config,
                    num_training_seasons=args.training_years,
                    pff_config=pff_config,
                    positions=args.positions,
                    weather_config=weather_config,
                    max_workers=per_season_workers,
                ): season
```

And the single-season path:

```python
            season_records = run_weekly_comparison(
                test_season=season,
                n_sims=args.sims,
                scoring_config=scoring_config,
                num_training_seasons=args.training_years,
                pff_config=pff_config,
                positions=args.positions,
                weather_config=weather_config,
                max_workers=per_season_workers,
            )
```

- [ ] **Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`
Expected: All tests PASS

- [ ] **Commit**

```bash
git add scripts/validate_weekly_signal.py
git commit -m "feat(weekly): add --workers flag and 3-phase parallel structure"
```

---

## Task 6: Final Verification

**Files:**
- All modified files

### Step 6.1: Run full test suite

- [ ] **Run all tests**

Run: `uv run pytest tests/ -v --timeout=120`
Expected: All 1122+ tests PASS

### Step 6.2: Verify --help on both scripts

- [ ] **Check CLI help**

Run: `uv run python scripts/validate_pff_signal.py --help`
Expected: `--workers` flag visible in output.

Run: `uv run python scripts/validate_weekly_signal.py --help`
Expected: `--workers` flag visible in output.

### Step 6.3: Smoke test sequential mode

- [ ] **Quick sequential sanity check**

Run: `uv run python scripts/validate_pff_signal.py --mode tier --sims 5 --seasons 2024 --workers 1 --label "parallel-test-seq"`
Expected: Completes without error, ledger entry written.

### Step 6.4: Smoke test parallel mode

- [ ] **Quick parallel sanity check**

Run: `uv run python scripts/validate_pff_signal.py --mode tier --sims 5 --seasons 2024 --workers 4 --label "parallel-test-par"`
Expected: Completes without error, results match sequential (same rank_corr/MAE within noise).

- [ ] **Commit any final fixes if needed**

```bash
git add -A
git commit -m "test: verify parallel validation harness end-to-end"
```
