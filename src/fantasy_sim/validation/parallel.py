"""Parallel game simulation runner for validation harnesses."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fantasy_sim.engine.types import TeamDistributions
    from fantasy_sim.models.player import TeamRoster

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
