# Parallel build_game() Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parallelize Phase 1 (build_game) of the A/B validation harness using ProcessPoolExecutor with worker-local builders, reducing runtime from ~1700s to ~400s.

**Architecture:** Worker processes each own a GameContextBuilder instance created via pool initializer, reused across all games. Single-arm mode for Backtester, dual-arm mode (off+on) for weekly validation. Sequential fallback for --workers 1.

**Tech Stack:** Python ProcessPoolExecutor, existing GameContextBuilder, existing parallel.py infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-07-parallel-build-game-design.md`

---

## File Structure

| File | Role |
|------|------|
| `src/fantasy_sim/data/game_context.py` | KickingModel defensive copy (1-line fix) |
| `src/fantasy_sim/validation/parallel.py` | Worker functions + `build_games_parallel()` |
| `src/fantasy_sim/validation/backtester.py` | Phase 1 replacement to use `build_games_parallel()` |
| `scripts/validate_weekly_signal.py` | Phase 1 replacement to use `build_games_parallel()` |
| `tests/test_validation/test_parallel.py` | New tests for build parallelism |

---

### Task 1: KickingModel Defensive Copy

**Files:**
- Modify: `src/fantasy_sim/data/game_context.py:189-225`
- Test: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validation/test_parallel.py`:

```python
import copy


class TestKickingModelIsolation:
    def test_weather_mutation_does_not_bleed_across_games(self):
        """Two TeamDistributions from the same pipeline must have independent KickingModels."""
        dists_a = _make_dists("KC")
        dists_b = _make_dists("BUF")

        # Simulate what _apply_weather does: mutate kicking in-place
        original_rate = dists_a.kicking.fg_make_rate["50_plus"]
        dists_a.kicking.fg_make_rate["50_plus"] = 0.10  # severe weather

        # dists_b should NOT see this mutation
        assert dists_b.kicking.fg_make_rate["50_plus"] == original_rate

    def test_build_team_distributions_returns_independent_kicking(self):
        """build_team_distributions must deepcopy kicking from pipeline cache."""
        from fantasy_sim.data.game_context import GameContextBuilder
        from unittest.mock import MagicMock, patch

        builder = object.__new__(GameContextBuilder)
        builder._pff_config = MagicMock(enabled=False)
        builder._matchup_engine = None
        builder._talent_stabilizer = None
        builder._tier_engine = None
        builder._team_context_engine = None
        builder._coverage_engine = None
        builder._kicker_engine = None
        builder._dst_baseline_engine = None
        builder._weather_engine = None
        builder._pff_crosswalk = None
        builder._pff_loader = None
        builder._weather_config = None

        kicking = KickingModel(
            fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65},
            xp_rate=0.94,
        )
        pipeline_output = {
            "play_calling": {"KC": PlayCallingDist(team="KC", distributions={}, default={"pass": 0.55, "run": 0.45})},
            "play_outcomes": PlayOutcomeDist(distributions={}, defaults={}),
            "turnover_rates": {"KC": TurnoverRates(team="KC", int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10)},
            "kicking": kicking,
            "drive_start": DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
        }
        builder._pipeline_cache = pipeline_output
        builder._cached_training_seasons = (2022, 2023, 2024)
        builder._pbp_stats_cache = {}
        builder._player_models_cache = {}
        builder._player_cache_key = ((2022, 2023, 2024), None, None)
        builder.cache_dir = "/tmp"
        builder.loader = MagicMock()

        dists = builder.build_team_distributions("KC", training_seasons=[2022, 2023, 2024])

        # Mutate the returned kicking — should NOT affect the pipeline cache
        dists.kicking.fg_make_rate["50_plus"] = 0.10
        assert pipeline_output["kicking"].fg_make_rate["50_plus"] == 0.65
```

- [ ] **Step 2: Run the test to verify failure**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestKickingModelIsolation::test_build_team_distributions_returns_independent_kicking -v`

Expected: FAIL — `assert 0.10 == 0.65` because kicking is a shared reference.

- [ ] **Step 3: Add deepcopy to build_team_distributions**

In `src/fantasy_sim/data/game_context.py`, add `import copy` at the top (after existing imports), then change the return in `build_team_distributions()`:

```python
import copy
```

Replace the `return TeamDistributions(...)` block (lines ~219-225):

```python
        return TeamDistributions(
            play_calling=play_calling,
            play_outcomes=pipeline_output["play_outcomes"],
            turnover_rates=turnover_rates,
            kicking=copy.deepcopy(pipeline_output["kicking"]),
            drive_start=pipeline_output["drive_start"],
        )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestKickingModelIsolation -v`

Expected: PASS (both tests)

- [ ] **Step 5: Run full existing test suite to check for regressions**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`

Expected: All 1122+ tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/data/game_context.py tests/test_validation/test_parallel.py
git commit -m "fix: deepcopy KickingModel in build_team_distributions to prevent cross-game mutation"
```

---

### Task 2: Single-Arm Build Worker Functions + build_games_parallel

**Files:**
- Modify: `src/fantasy_sim/validation/parallel.py`
- Test: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_validation/test_parallel.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestBuildGamesParallel:
    def _mock_builder(self):
        """Create a mock GameContextBuilder that returns valid game contexts."""
        mock = MagicMock()
        mock.build_game.return_value = (
            _make_dists("KC"), _make_dists("BUF"),
            _make_roster("KC"), _make_roster("BUF"),
        )
        mock._pff_config = MagicMock(enabled=False)
        return mock

    def test_empty_input_returns_empty(self):
        from fantasy_sim.validation.parallel import build_games_parallel
        results = build_games_parallel(
            [], cache_dir=Path("/tmp"), max_workers=1,
        )
        assert results == []

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_sequential_single_game(self, mock_builder_cls):
        mock_builder_cls.return_value = self._mock_builder()
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [("KC", "BUF", [2022, 2023], 2024, 1, "2024_01_KC_BUF", 42)]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "ok"
        assert r["game_id"] == "2024_01_KC_BUF"
        assert r["seed"] == 42
        assert r["week"] == 1
        assert r["home_dists"].play_calling.team == "KC"
        assert r["away_roster"].team == "BUF"

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_sequential_multiple_games(self, mock_builder_cls):
        mock_builder_cls.return_value = self._mock_builder()
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [
            ("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 100),
            ("SF", "DAL", [2022, 2023], 2024, 1, "game_2", 200),
            ("KC", "BUF", [2022, 2023], 2024, 2, "game_3", 300),
        ]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )
        assert len(results) == 3
        # Results should be sorted by (week, game_id)
        assert results[0]["game_id"] == "game_1"
        assert results[1]["game_id"] == "game_2"
        assert results[2]["game_id"] == "game_3"

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_error_skips_failed_game(self, mock_builder_cls):
        mock = self._mock_builder()
        call_count = 0

        def side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("bad team")
            return (
                _make_dists("KC"), _make_dists("BUF"),
                _make_roster("KC"), _make_roster("BUF"),
            )

        mock.build_game.side_effect = side_effect
        mock_builder_cls.return_value = mock
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [
            ("KC", "BUF", [2022, 2023], 2024, 1, "good_1", 100),
            ("XX", "YY", [2022, 2023], 2024, 1, "bad_1", 200),
            ("SF", "DAL", [2022, 2023], 2024, 1, "good_2", 300),
        ]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )
        ok_results = [r for r in results if r["status"] == "ok"]
        err_results = [r for r in results if r["status"] == "error"]
        assert len(ok_results) == 2
        assert len(err_results) == 1
        assert err_results[0]["game_id"] == "bad_1"

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_on_complete_callback(self, mock_builder_cls):
        mock_builder_cls.return_value = self._mock_builder()
        from fantasy_sim.validation.parallel import build_games_parallel

        completed = []
        game_args = [
            ("KC", "BUF", [2022, 2023], 2024, 1, "g1", 1),
            ("SF", "DAL", [2022, 2023], 2024, 1, "g2", 2),
        ]
        build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
            on_complete=lambda done, total: completed.append((done, total)),
        )
        assert len(completed) == 2
        assert completed[-1] == (2, 2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBuildGamesParallel -v`

Expected: FAIL — `build_games_parallel` does not exist yet.

- [ ] **Step 3: Implement worker functions and build_games_parallel**

Add to `src/fantasy_sim/validation/parallel.py` (after the existing `simulate_games_parallel` function):

```python
from pathlib import Path

# --- Phase 1: Build game contexts in parallel ---

# Module-level state for build worker processes
_worker_builders: dict | None = None


def _init_build_worker_single(
    cache_dir: Path,
    pff_config,
    weather_config,
) -> None:
    """Initializer for single-builder worker processes (Backtester)."""
    global _worker_builders
    from fantasy_sim.data.game_context import GameContextBuilder

    _worker_builders = {
        "single": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
        ),
    }


def _build_game_worker_single(args: tuple) -> dict:
    """Worker: build game context for one game (single arm)."""
    home, away, training_seasons, target_season, week, game_id, seed = args
    try:
        hd, ad, hr, ar = _worker_builders["single"].build_game(
            home, away,
            training_seasons=training_seasons,
            target_season=target_season,
            week=week,
        )
        return {
            "status": "ok",
            "game_id": game_id,
            "seed": seed,
            "week": week,
            "home": home,
            "away": away,
            "home_dists": hd,
            "away_dists": ad,
            "home_roster": hr,
            "away_roster": ar,
        }
    except Exception as exc:
        logger.warning("Build failed for %s: %s", game_id, exc)
        return {"status": "error", "game_id": game_id, "error": str(exc)}


def _build_games_sequential(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config=None,
    weather_config=None,
    dual_arm: bool = False,
    on_complete: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Sequential fallback: build games in-process with own builder(s)."""
    from fantasy_sim.data.game_context import GameContextBuilder

    if dual_arm:
        builders = {
            "off": GameContextBuilder(cache_dir=cache_dir),
            "on": GameContextBuilder(
                cache_dir=cache_dir,
                pff_config=pff_config,
                weather_config=weather_config,
            ),
        }
        worker_fn = _build_game_worker_dual
    else:
        builders = {
            "single": GameContextBuilder(
                cache_dir=cache_dir,
                pff_config=pff_config,
                weather_config=weather_config,
            ),
        }
        worker_fn = _build_game_worker_single

    global _worker_builders
    _worker_builders = builders

    total = len(game_args)
    results = []
    for i, args in enumerate(game_args):
        results.append(worker_fn(args))
        if on_complete:
            on_complete(i + 1, total)

    _worker_builders = None
    return results


def build_games_parallel(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config=None,
    weather_config=None,
    max_workers: int | None = None,
    dual_arm: bool = False,
    on_complete: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Build game contexts, optionally in parallel using worker-local builders.

    Args:
        game_args: List of (home, away, training_seasons, target_season,
            week, game_id, seed) tuples.
        cache_dir: Path to data cache directory.
        pff_config: PFF configuration (None = no PFF).
        weather_config: Weather configuration (None = no weather).
        max_workers: Worker processes. None/0=auto, 1=sequential.
        dual_arm: If True, each worker builds both off+on contexts.
        on_complete: Optional callback(completed_count, total_count).

    Returns:
        List of result dicts sorted by (week, game_id).
        Each has "status" ("ok" or "error") and game data.
    """
    if not game_args:
        return []

    if max_workers is None or max_workers == 0:
        max_workers = default_max_workers(len(game_args))

    if max_workers <= 1:
        results = _build_games_sequential(
            game_args, cache_dir, pff_config, weather_config,
            dual_arm, on_complete,
        )
        return sorted(results, key=lambda r: (r.get("week", 0), r.get("game_id", "")))

    from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed

    if dual_arm:
        init_fn = _init_build_worker_dual
        worker_fn = _build_game_worker_dual
    else:
        init_fn = _init_build_worker_single
        worker_fn = _build_game_worker_single

    results: list[dict] = []
    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=init_fn,
        initargs=(cache_dir, pff_config, weather_config),
    ) as pool:
        futures = {
            pool.submit(worker_fn, args): args for args in game_args
        }
        completed = 0
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except BrokenExecutor:
                raise RuntimeError(
                    "Build worker crashed. Try --workers 1 for sequential mode."
                )
            except Exception as exc:
                args = futures[future]
                game_id = args[5]
                logger.warning("Build failed for %s: %s", game_id, exc)
                results.append({"status": "error", "game_id": game_id, "error": str(exc)})
            completed += 1
            if on_complete:
                on_complete(completed, len(game_args))

    return sorted(results, key=lambda r: (r.get("week", 0), r.get("game_id", "")))
```

Note: `_build_game_worker_dual` and `_init_build_worker_dual` are referenced but implemented in Task 3. For now, the `dual_arm=False` path is fully functional.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBuildGamesParallel -v`

Expected: All 5 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/fantasy_sim/validation/parallel.py tests/test_validation/test_parallel.py
git commit -m "feat: add build_games_parallel for Phase 1 parallelism (single-arm)"
```

---

### Task 3: Dual-Arm Build Worker Functions

**Files:**
- Modify: `src/fantasy_sim/validation/parallel.py`
- Test: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validation/test_parallel.py`:

```python
class TestBuildGamesParallelDualArm:
    def _mock_builder(self):
        mock = MagicMock()
        mock.build_game.return_value = (
            _make_dists("KC"), _make_dists("BUF"),
            _make_roster("KC"), _make_roster("BUF"),
        )
        mock._matchup_engine = None
        mock._coverage_engine = None
        mock._pff_crosswalk = None
        mock._pff_config = MagicMock(enabled=False)
        return mock

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_dual_arm_returns_both_arms(self, mock_builder_cls):
        mock_builder_cls.return_value = self._mock_builder()
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1, dual_arm=True,
        )
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "ok"
        assert "off" in r["results"]
        assert "on" in r["results"]
        assert len(r["results"]["off"]) == 4  # (hd, ad, hr, ar)
        assert len(r["results"]["on"]) == 4

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_dual_arm_captures_matchup_aux(self, mock_builder_cls):
        from fantasy_sim.data.pff.models import MatchupContext
        mock_on = self._mock_builder()
        mock_matchup = MagicMock()
        mock_matchup.compute.return_value = MatchupContext(catch_rate_factor=1.05)
        mock_on._matchup_engine = mock_matchup
        mock_on._coverage_engine = None

        call_count = 0
        def make_builder(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return self._mock_builder()  # off builder (no engines)
            return mock_on  # on builder (with engines)

        mock_builder_cls.side_effect = make_builder
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1, dual_arm=True,
        )
        r = results[0]
        assert "matchup_aux" in r
        assert r["matchup_aux"]["home_matchup_ctx"].catch_rate_factor == 1.05

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_dual_arm_error_skips_game(self, mock_builder_cls):
        mock = self._mock_builder()
        mock.build_game.side_effect = RuntimeError("fail")
        mock_builder_cls.return_value = mock
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 42)]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1, dual_arm=True,
        )
        assert len(results) == 1
        assert results[0]["status"] == "error"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBuildGamesParallelDualArm -v`

Expected: FAIL — `_init_build_worker_dual` / `_build_game_worker_dual` not defined.

- [ ] **Step 3: Implement dual-arm worker functions**

Add to `src/fantasy_sim/validation/parallel.py` (after the single-arm functions, before `_build_games_sequential`):

```python
def _init_build_worker_dual(
    cache_dir: Path,
    pff_config,
    weather_config,
) -> None:
    """Initializer for dual-builder worker processes (weekly validation)."""
    global _worker_builders
    from fantasy_sim.data.game_context import GameContextBuilder

    _worker_builders = {
        "off": GameContextBuilder(cache_dir=cache_dir),
        "on": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
        ),
    }


def _build_game_worker_dual(args: tuple) -> dict:
    """Worker: build game context for one game, both off+on arms."""
    home, away, training_seasons, target_season, week, game_id, seed = args
    from fantasy_sim.data.pff.models import MatchupContext

    try:
        hd_off, ad_off, hr_off, ar_off = _worker_builders["off"].build_game(
            home, away,
            training_seasons=training_seasons,
            target_season=target_season,
            week=week,
        )
        hd_on, ad_on, hr_on, ar_on = _worker_builders["on"].build_game(
            home, away,
            training_seasons=training_seasons,
            target_season=target_season,
            week=week,
        )

        # Capture matchup/coverage auxiliary data from the "on" builder
        builder_on = _worker_builders["on"]

        home_matchup_ctx = MatchupContext()
        away_matchup_ctx = MatchupContext()
        if builder_on._matchup_engine is not None:
            home_matchup_ctx = builder_on._matchup_engine.compute(
                defense_team=away, offense_team=home,
                target_season=target_season, max_week=week,
            )
            away_matchup_ctx = builder_on._matchup_engine.compute(
                defense_team=home, offense_team=away,
                target_season=target_season, max_week=week,
            )

        home_coverage: dict = {}
        away_coverage: dict = {}
        if builder_on._coverage_engine is not None:
            home_coverage = builder_on._coverage_engine.compute(
                defense_team=away, offense_roster=hr_on,
                target_season=target_season, max_week=week,
                pff_crosswalk=builder_on._pff_crosswalk,
            )
            away_coverage = builder_on._coverage_engine.compute(
                defense_team=home, offense_roster=ar_on,
                target_season=target_season, max_week=week,
                pff_crosswalk=builder_on._pff_crosswalk,
            )

        return {
            "status": "ok",
            "game_id": game_id,
            "seed": seed,
            "week": week,
            "home": home,
            "away": away,
            "results": {
                "off": (hd_off, ad_off, hr_off, ar_off),
                "on": (hd_on, ad_on, hr_on, ar_on),
            },
            "matchup_aux": {
                "home_matchup_ctx": home_matchup_ctx,
                "away_matchup_ctx": away_matchup_ctx,
                "home_coverage": home_coverage,
                "away_coverage": away_coverage,
            },
        }
    except Exception as exc:
        logger.warning("Build failed for %s: %s", game_id, exc)
        return {"status": "error", "game_id": game_id, "error": str(exc)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBuildGamesParallelDualArm -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/fantasy_sim/validation/parallel.py tests/test_validation/test_parallel.py
git commit -m "feat: add dual-arm build worker for weekly validation parallelism"
```

---

### Task 4: Backtester Phase 1 Integration

**Files:**
- Modify: `src/fantasy_sim/validation/backtester.py:49-130`
- Test: `tests/test_validation/test_backtester.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_validation/test_backtester.py`:

```python
class TestBacktesterParallelBuild:
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_uses_build_games_parallel(self, mock_loader_cls, mock_build_parallel):
        """Backtester.run() should delegate Phase 1 to build_games_parallel."""
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, max_workers=4)
        bt.loader = mock_loader
        bt.run(scoring_config)

        mock_build_parallel.assert_called_once()
        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["max_workers"] == 4
        assert call_kwargs["dual_arm"] is False

        # Verify game_args contain correct parameters
        game_args = mock_build_parallel.call_args[0][0]
        assert len(game_args) == 1
        home, away, ts, target, wk, gid, seed = game_args[0]
        assert home == "KC"
        assert away == "BUF"
        assert ts == [2021, 2022, 2023]
        assert target == 2024
        assert wk == 1

    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_passes_pff_and_weather_config(self, mock_loader_cls, mock_build_parallel):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        from fantasy_sim.data.weather.models import WeatherConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32), "week": pl.Series([], dtype=pl.Int32),
             "game_id": pl.Series([], dtype=pl.Utf8), "home_team": pl.Series([], dtype=pl.Utf8),
             "away_team": pl.Series([], dtype=pl.Utf8)}
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )
        mock_build_parallel.return_value = []

        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        weather_cfg = WeatherConfig(enabled=True)

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg, weather_config=weather_cfg)
        bt.loader = mock_loader
        bt.run(scoring_config)

        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["pff_config"] is pff_cfg
        assert call_kwargs["weather_config"] is weather_cfg
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_validation/test_backtester.py::TestBacktesterParallelBuild -v`

Expected: FAIL — Backtester.run() still uses the sequential builder loop, `build_games_parallel` is not called.

- [ ] **Step 3: Replace Phase 1 in Backtester**

Modify `src/fantasy_sim/validation/backtester.py`:

Add import at top:
```python
from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel, build_games_parallel
```

Replace the `__init__` method to store configs instead of building `self.builder`:

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
        self.test_season = test_season
        self.n_sims = n_sims
        self.training_seasons = list(range(
            test_season - num_training_seasons, test_season
        ))
        self.scoring_format = scoring_format
        self.loader = DataLoader(cache_dir=cache_dir) if cache_dir else DataLoader()
        self._pff_config = pff_config
        self._weather_config = weather_config
        self.max_workers = max_workers
```

Replace Phase 1 in `run()`:

```python
    def run(self, scoring_config: dict) -> BacktestResult:
        """Run the full backtest for one season.

        Uses only training_seasons data for model fitting (no leakage).
        Three phases: build contexts -> simulate (optionally parallel) -> aggregate.
        """
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

        # --- Phase 1: Build game contexts (parallel) ---
        game_args = []
        for wk in weeks:
            week_games = schedules.filter(
                (pl.col("week") == wk) & (pl.col("season") == self.test_season)
            )
            for game in week_games.iter_rows(named=True):
                home, away = game["home_team"], game["away_team"]
                seed = zlib.crc32(game["game_id"].encode()) % (2**31)
                game_args.append((
                    home, away, self.training_seasons,
                    self.test_season, wk, game["game_id"], seed,
                ))

        build_results = build_games_parallel(
            game_args,
            cache_dir=self.loader.cache_dir,
            pff_config=self._pff_config,
            weather_config=self._weather_config,
            max_workers=self.max_workers,
            dual_arm=False,
        )

        specs: list[GameSpec] = []
        for r in build_results:
            if r["status"] != "ok":
                continue
            specs.append(GameSpec(
                game_id=r["game_id"],
                home_dists=r["home_dists"],
                away_dists=r["away_dists"],
                home_roster=r["home_roster"],
                away_roster=r["away_roster"],
                seed=r["seed"],
                week=r["week"],
            ))

        # --- Phase 2: Simulate (parallel or sequential) ---
        sim_results = simulate_games_parallel(
            specs, n_sims=self.n_sims, scoring_config=scoring_config,
            max_workers=self.max_workers,
        )

        # --- Phase 3: Aggregate results ---
        # ... (unchanged from current code, starting at line 132)
```

The Phase 3 aggregation code (lines 132-196) remains exactly as-is.

- [ ] **Step 4: Update existing backtester tests that reference self.builder**

In `tests/test_validation/test_backtester.py`, update `TestBacktesterRosterHandling`:

```python
class TestBacktesterRosterHandling:
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_game_receives_target_season_and_week(self, mock_loader_cls, mock_build_parallel):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        config = load_defaults()
        scoring_config = resolve_scoring(config["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = mock_loader
        bt.run(scoring_config)

        game_args = mock_build_parallel.call_args[0][0]
        home, away, ts, target, wk, gid, seed = game_args[0]
        assert ts == [2021, 2022, 2023]
        assert target == 2024
        assert wk == 1
```

Update `TestBacktesterPffConfig`:

```python
class TestBacktesterPffConfig:
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_pff_config_stored(self, mock_loader_cls):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg)
        assert bt._pff_config is pff_cfg

    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_no_pff_config_is_none(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        bt = Backtester(test_season=2024, n_sims=10)
        assert bt._pff_config is None
```

- [ ] **Step 5: Run all backtester tests**

Run: `uv run pytest tests/test_validation/test_backtester.py -v`

Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`

Expected: All tests pass (existing parallel tests unchanged).

- [ ] **Step 7: Commit**

```bash
git add src/fantasy_sim/validation/backtester.py tests/test_validation/test_backtester.py
git commit -m "feat: Backtester Phase 1 uses build_games_parallel for parallel context building"
```

---

### Task 5: Weekly Validation Phase 1 Integration

**Files:**
- Modify: `scripts/validate_weekly_signal.py:259-393`

- [ ] **Step 1: Add import**

In `scripts/validate_weekly_signal.py`, update the import from `parallel`:

```python
from fantasy_sim.validation.parallel import GameSpec, simulate_games_parallel, default_max_workers, build_games_parallel
```

- [ ] **Step 2: Replace Phase 1 in run_weekly_comparison**

Replace the Phase 1 section (lines ~298-381) of `run_weekly_comparison()`:

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
    """Run PFF-on vs PFF-off for every game in a season, collect per-player records."""

    training_seasons = list(range(
        test_season - num_training_seasons, test_season
    ))
    loader = DataLoader()
    schedules = loader.load_schedules([test_season])
    player_stats = loader.load_player_stats([test_season])

    actuals = load_actual_scores(player_stats, scoring_config, test_season)
    actual_by_pw: dict[str, dict[int, float]] = defaultdict(dict)
    actual_pos: dict[str, str] = {}
    actual_team: dict[str, str] = {}
    actual_name: dict[str, str] = {}
    for a in actuals:
        actual_by_pw[a.player_id][a.week] = a.fpts
        actual_pos[a.player_id] = a.position
        actual_team[a.player_id] = a.team
        actual_name[a.player_id] = a.name

    weeks = sorted(
        schedules.filter(pl.col("season") == test_season)["week"]
        .unique().to_list()
    )
    weeks = [w for w in weeks if 1 <= w <= 18]

    # --- Phase 1: Build all game contexts (parallel) ---
    game_args = []
    for wk in weeks:
        week_games = schedules.filter(
            (pl.col("week") == wk) & (pl.col("season") == test_season)
        )
        print(f"  [{test_season}] Collecting games... Week {wk}/{max(weeks)}", flush=True)
        for game in week_games.iter_rows(named=True):
            home, away = game["home_team"], game["away_team"]
            seed = zlib.crc32(game["game_id"].encode()) % (2**31)
            game_args.append((
                home, away, training_seasons,
                test_season, wk, game["game_id"], seed,
            ))

    print(f"  [{test_season}] Building {len(game_args)} game contexts (workers={max_workers})...", flush=True)

    def _on_build_complete(done: int, total: int) -> None:
        if done % 20 == 0 or done == total:
            print(f"    [{test_season}] {done}/{total} games built", flush=True)

    build_results = build_games_parallel(
        game_args,
        cache_dir=loader.cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        max_workers=max_workers,
        dual_arm=True,
        on_complete=_on_build_complete,
    )

    # Assemble specs + game_aux from results
    specs: list[GameSpec] = []
    game_aux: dict[str, dict] = {}

    for r in build_results:
        if r["status"] != "ok":
            continue
        game_id = r["game_id"]
        off = r["results"]["off"]
        on = r["results"]["on"]

        specs.append(GameSpec(
            game_id=game_id,
            home_dists=off[0], away_dists=off[1],
            home_roster=off[2], away_roster=off[3],
            seed=r["seed"], week=r["week"],
            metadata={"arm": "off"},
        ))
        specs.append(GameSpec(
            game_id=game_id,
            home_dists=on[0], away_dists=on[1],
            home_roster=on[2], away_roster=on[3],
            seed=r["seed"], week=r["week"],
            metadata={"arm": "on"},
        ))

        game_aux[game_id] = {
            "home": r["home"], "away": r["away"], "week": r["week"],
            "home_matchup_ctx": r["matchup_aux"]["home_matchup_ctx"],
            "away_matchup_ctx": r["matchup_aux"]["away_matchup_ctx"],
            "home_coverage": r["matchup_aux"]["home_coverage"],
            "away_coverage": r["matchup_aux"]["away_coverage"],
        }

    # --- Phase 2: Simulate all games (parallel) ---
    print(f"  [{test_season}] Simulating {len(specs)} game-arms...", flush=True)

    def _on_complete(done: int, total: int) -> None:
        if done % 50 == 0 or done == total:
            print(f"    [{test_season}] {done}/{total} complete", flush=True)

    sim_results = simulate_games_parallel(
        specs, n_sims=n_sims, scoring_config=scoring_config,
        max_workers=max_workers, on_complete=_on_complete,
    )

    # --- Phase 3: Pair results and build records ---
    # (unchanged from current code, starting at "by_game: dict[str, ...")
```

Phase 3 (lines 395-448 in original) remains exactly as-is.

- [ ] **Step 3: Remove unused builder variables**

Remove the now-unused lines that created `builder_off` and `builder_on`:

```python
# DELETE these lines (were around line 289-290):
# builder_off = GameContextBuilder(cache_dir=loader.cache_dir)
# builder_on = GameContextBuilder(cache_dir=loader.cache_dir, pff_config=pff_config, weather_config=weather_config)
```

- [ ] **Step 4: Run existing validation tests**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`

Expected: All tests pass. (No script-level tests exist for validate_weekly_signal.py — correctness verified by integration run in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_weekly_signal.py
git commit -m "feat: validate_weekly_signal Phase 1 uses build_games_parallel for parallel context building"
```

---

### Task 6: Determinism & Final Verification Tests

**Files:**
- Modify: `tests/test_validation/test_parallel.py`

- [ ] **Step 1: Write determinism test**

Add to `tests/test_validation/test_parallel.py`:

```python
class TestBuildGamesParallelDeterminism:
    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_sequential_determinism_across_runs(self, mock_builder_cls):
        """Same inputs must produce identical outputs across two sequential runs."""
        call_count = 0
        def make_builder(*a, **kw):
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            mock.build_game.return_value = (
                _make_dists("KC"), _make_dists("BUF"),
                _make_roster("KC"), _make_roster("BUF"),
            )
            mock._pff_config = MagicMock(enabled=False)
            mock._matchup_engine = None
            mock._coverage_engine = None
            mock._pff_crosswalk = None
            return mock
        mock_builder_cls.side_effect = make_builder
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [
            ("KC", "BUF", [2022, 2023], 2024, 1, "game_1", 100),
            ("SF", "DAL", [2022, 2023], 2024, 2, "game_2", 200),
            ("MIA", "NYJ", [2022, 2023], 2024, 1, "game_3", 300),
        ]
        run1 = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )
        run2 = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )

        assert len(run1) == len(run2)
        for r1, r2 in zip(run1, run2):
            assert r1["game_id"] == r2["game_id"]
            assert r1["seed"] == r2["seed"]
            assert r1["week"] == r2["week"]

    @patch("fantasy_sim.validation.parallel.GameContextBuilder")
    def test_results_sorted_by_week_then_game_id(self, mock_builder_cls):
        mock_builder_cls.return_value = MagicMock()
        mock_builder_cls.return_value.build_game.return_value = (
            _make_dists("KC"), _make_dists("BUF"),
            _make_roster("KC"), _make_roster("BUF"),
        )
        mock_builder_cls.return_value._pff_config = MagicMock(enabled=False)
        from fantasy_sim.validation.parallel import build_games_parallel

        game_args = [
            ("KC", "BUF", [2022, 2023], 2024, 3, "game_c", 1),
            ("SF", "DAL", [2022, 2023], 2024, 1, "game_a", 2),
            ("MIA", "NYJ", [2022, 2023], 2024, 1, "game_b", 3),
            ("GB", "CHI", [2022, 2023], 2024, 2, "game_d", 4),
        ]
        results = build_games_parallel(
            game_args, cache_dir=Path("/tmp"), max_workers=1,
        )
        ids = [r["game_id"] for r in results]
        assert ids == ["game_a", "game_b", "game_d", "game_c"]
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_validation/test_parallel.py::TestBuildGamesParallelDeterminism -v`

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=60 -x -q`

Expected: All 1122+ tests pass (plus the ~14 new tests added in this plan).

- [ ] **Step 4: Commit**

```bash
git add tests/test_validation/test_parallel.py
git commit -m "test: add determinism and sort-order tests for build_games_parallel"
```

- [ ] **Step 5: Final verification — run a quick validation to confirm metrics unchanged**

Run: `uv run python scripts/validate_pff_signal.py --mode talent --sims 10 --workers 1 --label "parallel-sequential-check"`

Expected: Completes successfully, metrics in the expected range. This confirms the Backtester integration works end-to-end with sequential mode.
