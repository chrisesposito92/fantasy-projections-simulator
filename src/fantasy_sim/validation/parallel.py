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
