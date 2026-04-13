from __future__ import annotations

from fantasy_sim.data.tracking.loader import TrackingInputLoader
from fantasy_sim.data.tracking.models import TrackingConfig
from fantasy_sim.data.tracking.qb_context import QbContextEngine
from fantasy_sim.data.tracking.rb_efficiency import RbEfficiencyEngine
from fantasy_sim.data.tracking.receiver_participation import (
    ReceiverParticipationEngine,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.player import TeamRoster


class TrackingEngine:
    def __init__(
        self,
        config: TrackingConfig,
        loader: TrackingInputLoader | None = None,
    ):
        self.config = config
        self._loader = loader or TrackingInputLoader(window_weeks=config.window_weeks)
        self._receiver_participation_engine = ReceiverParticipationEngine(
            config.receiver_participation
        )
        self._rb_efficiency_engine = RbEfficiencyEngine(config.rb_efficiency)
        self._qb_context_engine = QbContextEngine(config.qb_context)

    def apply(
        self,
        roster: TeamRoster,
        team_dists: TeamDistributions,
        season: int,
        week: int,
    ) -> None:
        if not self.config.enabled or week <= 1:
            return

        if self.config.receiver_participation.enabled:
            receiver_features = self._loader.load_receiver_features(season, week)
            self._receiver_participation_engine.apply(roster, receiver_features)

        if self.config.rb_efficiency.enabled:
            rb_features = self._loader.load_rb_features(season, week)
            self._rb_efficiency_engine.apply(roster, rb_features)

        if self.config.qb_context.enabled:
            qb_features = self._loader.load_qb_features(season, week)
            self._qb_context_engine.apply(roster, team_dists, qb_features)
