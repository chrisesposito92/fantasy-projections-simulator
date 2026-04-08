"""Parallel game simulation runner for validation harnesses."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fantasy_sim.data.pff.models import PffConfig
    from fantasy_sim.data.weather.models import WeatherConfig
    from fantasy_sim.data.vegas.models import PropsConfig, VegasConfig
    from fantasy_sim.data.usage.models import UsageConfig
    from fantasy_sim.engine.types import TeamDistributions
    from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)

# Module-level builder registry — populated by _init_build_worker_* initializers
_worker_builders: dict | None = None


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


from typing import Callable

from fantasy_sim.data.game_context import GameContextBuilder
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
                logger.warning("Game %s failed, skipping", spec.game_id, exc_info=True)
            if on_complete:
                on_complete(i + 1, total)
        return results

    # Parallel path
    from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed

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
            except BrokenExecutor:
                raise RuntimeError(
                    "Worker process crashed. Try --workers 1 for sequential mode."
                )
            except Exception:
                logger.warning("Game %s failed, skipping", spec.game_id, exc_info=True)
            completed += 1
            if on_complete:
                on_complete(completed, total)

    return results


# ---------------------------------------------------------------------------
# Phase 1 parallelism: game context building
# ---------------------------------------------------------------------------

# GameContextBuilder is imported at module level (for mock patching in tests)
# and also inside worker init functions (for subprocess workers that don't
# share the parent's module namespace).


def _init_build_worker_single(
    cache_dir: Path,
    pff_config: "PffConfig | None",
    weather_config: "WeatherConfig | None",
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
) -> None:
    """ProcessPoolExecutor initializer: create one GameContextBuilder per worker."""
    global _worker_builders
    from fantasy_sim.data.game_context import GameContextBuilder  # deferred

    builder = GameContextBuilder(
        cache_dir=cache_dir,
        pff_config=pff_config,
        weather_config=weather_config,
        vegas_config=vegas_config,
        props_config=props_config,
        usage_config=usage_config,
    )
    _worker_builders = {"single": builder}


def _build_game_worker_single(args: tuple) -> dict:
    """Worker function for single-arm game context building.

    Must be module-level (not a closure) for ProcessPoolExecutor.

    Args:
        args: (home, away, training_seasons, target_season, week, game_id, seed)

    Returns:
        Result dict with keys: status, game_id, seed, week, home, away,
        home_dists, away_dists, home_roster, away_roster.
        On error: status='error', error=str(exc).
    """
    home, away, training_seasons, target_season, week, game_id, seed = args
    try:
        builder = _worker_builders["single"]
        home_dists, away_dists, home_roster, away_roster = builder.build_game(
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
            "home_dists": home_dists,
            "away_dists": away_dists,
            "home_roster": home_roster,
            "away_roster": away_roster,
        }
    except Exception as exc:
        logger.warning("Build failed for game %s: %s", game_id, exc, exc_info=True)
        return {
            "status": "error",
            "game_id": game_id,
            "seed": seed,
            "week": week,
            "home": home,
            "away": away,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


def _init_build_worker_dual(
    cache_dir: Path,
    pff_config: PffConfig | None,
    weather_config: WeatherConfig | None,
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
) -> None:
    """ProcessPoolExecutor initializer: create off+on builders per worker."""
    global _worker_builders
    from fantasy_sim.data.game_context import GameContextBuilder

    _worker_builders = {
        "off": GameContextBuilder(cache_dir=cache_dir),
        "on": GameContextBuilder(
            cache_dir=cache_dir,
            pff_config=pff_config,
            weather_config=weather_config,
            vegas_config=vegas_config,
            props_config=props_config,
            usage_config=usage_config,
        ),
    }


def _build_game_worker_dual(args: tuple) -> dict:
    """Worker: build game context for one game, both off+on arms."""
    home, away, training_seasons, target_season, week, game_id, seed = args
    from fantasy_sim.data.pff.models import MatchupContext

    try:
        hd_off, ad_off, hr_off, ar_off = _worker_builders["off"].build_game(
            home, away, training_seasons=training_seasons,
            target_season=target_season, week=week,
        )
        hd_on, ad_on, hr_on, ar_on = _worker_builders["on"].build_game(
            home, away, training_seasons=training_seasons,
            target_season=target_season, week=week,
        )

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
        logger.warning("Build failed for %s: %s", game_id, exc, exc_info=True)
        return {
            "status": "error",
            "game_id": game_id,
            "seed": seed,
            "week": week,
            "home": home,
            "away": away,
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


def _build_games_sequential(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config: "PffConfig | None",
    weather_config: "WeatherConfig | None",
    dual_arm: bool,
    on_complete: "Callable[[int, int], None] | None",
    vegas_config: "VegasConfig | None" = None,
    props_config: "PropsConfig | None" = None,
    usage_config: "UsageConfig | None" = None,
) -> list[dict]:
    """Sequential fallback: build game contexts one at a time."""
    global _worker_builders

    if dual_arm:
        _worker_builders = {
            "off": GameContextBuilder(cache_dir=cache_dir),
            "on": GameContextBuilder(
                cache_dir=cache_dir,
                pff_config=pff_config,
                weather_config=weather_config,
                vegas_config=vegas_config,
                props_config=props_config,
                usage_config=usage_config,
            ),
        }
    else:
        _worker_builders = {
            "single": GameContextBuilder(
                cache_dir=cache_dir,
                pff_config=pff_config,
                weather_config=weather_config,
                vegas_config=vegas_config,
                props_config=props_config,
                usage_config=usage_config,
            ),
        }

    total = len(game_args)
    results: list[dict] = []
    for i, args in enumerate(game_args):
        if dual_arm:
            result = _build_game_worker_dual(args)
        else:
            result = _build_game_worker_single(args)
        results.append(result)
        if on_complete:
            on_complete(i + 1, total)
    return results


def build_games_parallel(
    game_args: list[tuple],
    cache_dir: Path,
    pff_config=None,
    weather_config=None,
    vegas_config=None,
    props_config=None,
    usage_config=None,
    max_workers: int | None = None,
    dual_arm: bool = False,
    on_complete: "Callable[[int, int], None] | None" = None,
) -> list[dict]:
    """Build game contexts for multiple games, optionally in parallel.

    Args:
        game_args: List of tuples (home, away, training_seasons, target_season,
                   week, game_id, seed).
        cache_dir: Directory for the GameContextBuilder cache.
        pff_config: PffConfig or None (passed to GameContextBuilder).
        weather_config: WeatherConfig or None (passed to GameContextBuilder).
        max_workers: Worker processes. None/0=auto, 1=sequential.
        dual_arm: If True, use dual-arm workers (off+on).
        on_complete: Optional callback(completed_count, total_count).

    Returns:
        List of result dicts sorted by (week, game_id).
    """
    if not game_args:
        return []

    if max_workers is None or max_workers == 0:
        max_workers = default_max_workers(len(game_args))

    # Cap build workers: each worker independently warms pipeline/PBP/PFF
    # caches, so more workers = more I/O contention and memory pressure.
    _MAX_BUILD_WORKERS = 4
    if max_workers > _MAX_BUILD_WORKERS:
        max_workers = _MAX_BUILD_WORKERS

    total = len(game_args)

    if max_workers <= 1:
        results = _build_games_sequential(
            game_args, cache_dir, pff_config, weather_config, dual_arm, on_complete,
            vegas_config=vegas_config,
            props_config=props_config,
            usage_config=usage_config,
        )
    else:
        from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, as_completed

        if dual_arm:
            init_fn = _init_build_worker_dual
            worker_fn = _build_game_worker_dual
        else:
            init_fn = _init_build_worker_single
            worker_fn = _build_game_worker_single

        with ProcessPoolExecutor(
            max_workers=max_workers,
            initializer=init_fn,
            initargs=(cache_dir, pff_config, weather_config, vegas_config, props_config, usage_config),
        ) as pool:
            futures = {
                pool.submit(worker_fn, args): args for args in game_args
            }
            completed = 0
            raw_results: list[dict] = []
            for future in as_completed(futures):
                args = futures[future]
                try:
                    result = future.result()
                    raw_results.append(result)
                except BrokenExecutor:
                    raise RuntimeError(
                        "Worker process crashed. Try --workers 1 for sequential mode."
                    )
                except Exception as exc:
                    game_id = args[5]
                    logger.warning(
                        "Build failed for game %s: %s", game_id, exc, exc_info=True
                    )
                    raw_results.append({
                        "status": "error",
                        "game_id": game_id,
                        "seed": args[6],
                        "week": args[4],
                        "home": args[0],
                        "away": args[1],
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    })
                completed += 1
                if on_complete:
                    on_complete(completed, total)
        results = raw_results

    # Sort by (week, game_id) for deterministic ordering
    results.sort(key=lambda r: (r.get("week", 0), r.get("game_id", "")))
    return results
