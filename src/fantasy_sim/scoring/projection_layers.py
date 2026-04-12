"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations

from typing import Protocol, TypeVar

from fantasy_sim.scoring.ensemble import BlendStats
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


class ProjectionEnsemblerProtocol(Protocol[ProjectionLayerRowT]):
    def blend_week(
        self,
        projections: list[ProjectionLayerRowT],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRowT], BlendStats]: ...


def apply_projection_layers(
    projections: list[ProjectionLayerRowT],
    *,
    season: int,
    week: int,
    role_trend_adjuster: RoleTrendAdjusterProtocol[ProjectionLayerRowT] | None = None,
    ensembler: ProjectionEnsemblerProtocol[ProjectionLayerRowT] | None = None,
) -> list[ProjectionLayerRowT]:
    rows = projections.copy()
    if role_trend_adjuster is not None:
        rows, _trend_stats = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _blend_stats = ensembler.blend_week(rows, season=season, week=week)
    return rows
