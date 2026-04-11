"""Shared ordering for post-simulation projection layers."""

from __future__ import annotations


def apply_projection_layers(
    projections: list[dict],
    *,
    season: int,
    week: int,
    role_trend_adjuster=None,
    ensembler=None,
) -> list[dict]:
    rows = [dict(projection) for projection in projections]
    if role_trend_adjuster is not None:
        rows, _ = role_trend_adjuster.adjust_week(rows, season=season, week=week)
    if ensembler is not None:
        rows, _ = ensembler.blend_week(rows, season=season, week=week)
    return rows
