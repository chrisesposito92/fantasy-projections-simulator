from __future__ import annotations

import threading

import polars as pl

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
        self._feature_cache: dict[tuple[str, int, int], pl.DataFrame] = {}
        self._feature_lock = threading.Lock()

    def _cached_features(
        self,
        feature_name: str,
        season: int,
        week: int,
        loader_fn,
    ) -> pl.DataFrame:
        cache_key = (feature_name, season, week)
        with self._feature_lock:
            cached = self._feature_cache.get(cache_key)
            if cached is not None:
                return cached
            features = loader_fn(season, week)
            self._feature_cache[cache_key] = features
            return features

    def _receiver_features(self, season: int, week: int) -> pl.DataFrame:
        return self._cached_features(
            "receiver_participation",
            season,
            week,
            self._loader.load_receiver_features,
        )

    def _rb_features(self, season: int, week: int) -> pl.DataFrame:
        return self._cached_features(
            "rb_efficiency",
            season,
            week,
            self._loader.load_rb_features,
        )

    def _qb_features(self, season: int, week: int) -> pl.DataFrame:
        return self._cached_features(
            "qb_context",
            season,
            week,
            self._loader.load_qb_features,
        )

    def warm(self, season: int, weeks: list[int]) -> None:
        for week in sorted(set(weeks)):
            if week <= 1:
                continue
            if self.config.receiver_participation.enabled:
                self._receiver_features(season, week)
            if self.config.rb_efficiency.enabled:
                self._rb_features(season, week)
            if self.config.qb_context.enabled:
                self._qb_features(season, week)

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
            receiver_features = self._receiver_features(season, week)
            self._receiver_participation_engine.apply(roster, receiver_features)

        if self.config.rb_efficiency.enabled:
            rb_features = self._rb_features(season, week)
            self._rb_efficiency_engine.apply(roster, rb_features)

        if self.config.qb_context.enabled:
            qb_features = self._qb_features(season, week)
            self._qb_context_engine.apply(roster, team_dists, qb_features)
