from __future__ import annotations

import polars as pl

from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import RoleTrendProjectionAdjuster


class _StubRoleInputs:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        return self.frame


def _config() -> RoleTrendConfig:
    return RoleTrendConfig(enabled=True)


def test_adjust_week_softly_boosts_and_dampens_then_recomputes_rank():
    frame = pl.DataFrame(
        {
            "season": [2024] * 8,
            "week": [1, 2, 3, 4, 1, 2, 3, 4],
            "team": ["KC"] * 4 + ["BUF"] * 4,
            "player_id": ["WR1"] * 4 + ["RB1"] * 4,
            "position": ["WR"] * 4 + ["RB"] * 4,
            "attempts": [0] * 8,
            "carries": [0, 0, 0, 0, 18, 18, 10, 9],
            "targets": [5, 6, 10, 11, 4, 3, 1, 1],
            "offense_pct": [0.68, 0.69, 0.80, 0.82, 0.70, 0.72, 0.50, 0.48],
        }
    )
    adjuster = RoleTrendProjectionAdjuster(_config(), role_inputs_loader=_StubRoleInputs(frame))

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "name": "Wide One",
                "team": "KC",
                "position": "WR",
                "fpts": 10.0,
                "rank": 2,
            },
            {
                "player_id": "RB1",
                "name": "Back One",
                "team": "BUF",
                "position": "RB",
                "fpts": 10.2,
                "rank": 1,
            },
        ],
        season=2024,
        week=5,
    )

    wr = next(row for row in adjusted if row["player_id"] == "WR1")
    rb = next(row for row in adjusted if row["player_id"] == "RB1")

    assert wr["fpts"] > 10.0
    assert wr["role_trend_applied"] is True
    assert wr["role_trend_factor"] > 1.0
    assert wr["rank"] == 1

    assert rb["fpts"] < 10.2
    assert rb["role_trend_applied"] is True
    assert rb["role_trend_factor"] < 1.0
    assert rb["rank"] == 2

    assert stats.adjusted_rows == 2
    assert stats.neutral_rows == 0


def test_apply_projection_layers_runs_role_trend_before_ensemble():
    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, season, week):
            order.append("trend")
            return projections, object()

    class _Ensemble:
        def blend_week(self, projections, season, week):
            order.append("ensemble")
            return projections, object()

    apply_projection_layers(
        [{"player_id": "WR1", "position": "WR", "team": "KC", "fpts": 10.0, "rank": 1}],
        season=2024,
        week=5,
        role_trend_adjuster=_Trend(),
        ensembler=_Ensemble(),
    )

    assert order == ["trend", "ensemble"]
