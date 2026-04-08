"""UsageEngine stub -- to be implemented in Task 2."""

from __future__ import annotations

from fantasy_sim.data.usage.models import UsageConfig
from fantasy_sim.data.loader import DataLoader
from fantasy_sim.models.player import TeamRoster


class UsageEngine:
    """Stub -- implementation in Task 2."""

    def __init__(self, config: UsageConfig, loader: DataLoader) -> None:
        self._config = config
        self._loader = loader

    def apply(self, roster: TeamRoster, season: int, week: int, pff_crosswalk: dict | None = None) -> dict:
        raise NotImplementedError("UsageEngine.apply() not yet implemented (Task 2)")
