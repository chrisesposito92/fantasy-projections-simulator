"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations

from typing import Protocol

from fantasy_sim.scoring.ensemble import BlendStats
from fantasy_sim.scoring.role_trend import ProjectionRow, TrendStats


class RoleTrendAdjusterProtocol(Protocol):
    def adjust_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], TrendStats]: ...


class ProjectionEnsemblerProtocol(Protocol):
    def blend_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], BlendStats]: ...


def apply_projection_layers(
    projections: list[ProjectionRow],
    *,
    season: int,
    week: int,
    role_trend_adjuster: RoleTrendAdjusterProtocol | None = None,
    ensembler: ProjectionEnsemblerProtocol | None = None,
) -> list[ProjectionRow]:
    rows = [dict(projection) for projection in projections]
    if role_trend_adjuster is not None:
        rows, _trend_stats = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _blend_stats = ensembler.blend_week(rows, season=season, week=week)
    return rows
