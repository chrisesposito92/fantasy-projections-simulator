"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations

from typing import Protocol, TypedDict, TypeVar, cast

from fantasy_sim.scoring.ensemble import BlendStats
from fantasy_sim.scoring.role_trend import TrendStats


class ProjectionLayerRow(TypedDict):
    """Core fields shared by post-simulation projection rows."""

    player_id: str
    position: str
    team: str
    fpts: float
    rank: int


ProjectionLayerRowT = TypeVar("ProjectionLayerRowT", bound=ProjectionLayerRow)


class RoleTrendAdjusterProtocol(Protocol):
    def adjust_week(
        self,
        projections: list[ProjectionLayerRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRow], TrendStats]: ...


class ProjectionEnsemblerProtocol(Protocol):
    def blend_week(
        self,
        projections: list[ProjectionLayerRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionLayerRow], BlendStats]: ...


def apply_projection_layers[ProjectionLayerRowT: ProjectionLayerRow](
    projections: list[ProjectionLayerRowT],
    *,
    season: int,
    week: int,
    role_trend_adjuster: RoleTrendAdjusterProtocol | None = None,
    ensembler: ProjectionEnsemblerProtocol | None = None,
) -> list[ProjectionLayerRowT]:
    rows: list[ProjectionLayerRow] = [
        cast(ProjectionLayerRow, cast(object, dict(projection)))
        for projection in projections
    ]
    if role_trend_adjuster is not None:
        rows, _trend_stats = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _blend_stats = ensembler.blend_week(rows, season=season, week=week)
    return cast(list[ProjectionLayerRowT], rows)
