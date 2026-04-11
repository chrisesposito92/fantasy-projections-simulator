"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations

from typing import Any, Protocol

from fantasy_sim.scoring.role_trend import ProjectionRow


class RoleTrendAdjusterProtocol(Protocol):
    def adjust_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], Any]: ...


class ProjectionEnsemblerProtocol(Protocol):
    def blend_week(
        self,
        projections: list[ProjectionRow],
        *,
        season: int,
        week: int,
    ) -> tuple[list[ProjectionRow], Any]: ...


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
        rows, _ = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _ = ensembler.blend_week(rows, season=season, week=week)
    return rows
