"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations

from typing import Protocol, TypeVar

from fantasy_sim.scoring.dynamic_blend import DynamicBlendStats
from fantasy_sim.scoring.ensemble import BlendStats
from fantasy_sim.scoring.market_history import MarketHistoryStats
from fantasy_sim.scoring.role_trend import ProjectionRow, TrendStats


ProjectionLayerRowT = TypeVar("ProjectionLayerRowT", bound=ProjectionRow)


class RoleTrendAdjusterProtocol(Protocol[ProjectionLayerRowT]):
    def adjust_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], TrendStats]: ...


class MarketHistoryAdjusterProtocol(Protocol[ProjectionLayerRowT]):
    def adjust_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], MarketHistoryStats]: ...


class ProjectionEnsemblerProtocol(Protocol[ProjectionLayerRowT]):
    def blend_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], BlendStats]: ...


class DynamicBlendProtocol(Protocol[ProjectionLayerRowT]):
    def blend_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], DynamicBlendStats]: ...


def apply_projection_layers(
    projections: list[ProjectionLayerRowT],
    *,
    season: int,
    week: int,
    role_trend_adjuster: RoleTrendAdjusterProtocol[ProjectionLayerRowT] | None = None,
    market_history_adjuster: MarketHistoryAdjusterProtocol[ProjectionLayerRowT] | None = None,
    ensembler: ProjectionEnsemblerProtocol[ProjectionLayerRowT] | None = None,
    dynamic_blender: DynamicBlendProtocol[ProjectionLayerRowT] | None = None,
) -> list[ProjectionLayerRowT]:
    rows = projections.copy()
    if role_trend_adjuster is not None:
        rows, _trend_stats = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if dynamic_blender is not None:
        rows, _dynamic_stats = dynamic_blender.blend_week(rows, season=season, week=week)
        return rows
    if market_history_adjuster is not None:
        rows, _market_stats = market_history_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _blend_stats = ensembler.blend_week(rows, season=season, week=week)
    return rows
