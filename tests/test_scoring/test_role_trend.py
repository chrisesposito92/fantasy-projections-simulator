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

    assert wr["fpts"] == 11.0
    assert wr["role_trend_applied"] is True
    assert wr["role_trend_factor"] == 1.1
    assert wr["rank"] == 1

    assert rb["fpts"] == 9.7
    assert rb["role_trend_applied"] is True
    assert rb["role_trend_factor"] == 0.95
    assert rb["rank"] == 2

    assert stats.adjusted_rows == 2
    assert stats.neutral_rows == 0


def test_adjust_week_uses_snap_share_drift_when_volume_is_flat():
    frame = pl.DataFrame(
        {
            "season": [2024] * 4,
            "week": [1, 2, 3, 4],
            "team": ["KC"] * 4,
            "player_id": ["WR1"] * 4,
            "position": ["WR"] * 4,
            "attempts": [0] * 4,
            "carries": [0] * 4,
            "targets": [8] * 4,
            "offense_pct": [0.50, 0.50, 0.90, 0.90],
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
                "fpts": 12.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=5,
    )

    row = adjusted[0]

    assert row["role_trend_factor"] == 1.0533
    assert row["fpts"] == 12.6
    assert row["role_trend_applied"] is True
    assert stats.adjusted_rows == 1
    assert stats.neutral_rows == 0


def test_adjust_week_disabled_config_is_neutral():
    adjuster = RoleTrendProjectionAdjuster(
        RoleTrendConfig(enabled=False),
        role_inputs_loader=_StubRoleInputs(pl.DataFrame()),
    )

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "team": "KC",
                "position": "WR",
                "fpts": 10.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=5,
    )

    assert adjusted[0]["fpts"] == 10.0
    assert adjusted[0]["role_trend_factor"] == 1.0
    assert adjusted[0]["role_trend_applied"] is False
    assert stats.adjusted_rows == 0
    assert stats.neutral_rows == 1


def test_adjust_week_week_one_is_neutral():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [1],
            "team": ["KC"],
            "player_id": ["WR1"],
            "position": ["WR"],
            "attempts": [0],
            "carries": [0],
            "targets": [8],
            "offense_pct": [0.70],
        }
    )
    adjuster = RoleTrendProjectionAdjuster(_config(), role_inputs_loader=_StubRoleInputs(frame))

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "team": "KC",
                "position": "WR",
                "fpts": 10.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    assert adjusted[0]["fpts"] == 10.0
    assert adjusted[0]["role_trend_factor"] == 1.0
    assert adjusted[0]["role_trend_applied"] is False
    assert stats.adjusted_rows == 0
    assert stats.neutral_rows == 1


def test_adjust_week_no_history_is_neutral():
    adjuster = RoleTrendProjectionAdjuster(
        _config(),
        role_inputs_loader=_StubRoleInputs(pl.DataFrame(schema={"season": pl.Int64, "week": pl.Int64, "team": pl.Utf8, "player_id": pl.Utf8, "position": pl.Utf8, "attempts": pl.Int64, "carries": pl.Int64, "targets": pl.Int64, "offense_pct": pl.Float64})),
    )

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "team": "KC",
                "position": "WR",
                "fpts": 10.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=5,
    )

    assert adjusted[0]["fpts"] == 10.0
    assert adjusted[0]["role_trend_factor"] == 1.0
    assert adjusted[0]["role_trend_applied"] is False
    assert stats.adjusted_rows == 0
    assert stats.neutral_rows == 1


def test_adjust_week_position_gated_out_is_neutral():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 2],
            "team": ["KC", "KC"],
            "player_id": ["QB1", "QB1"],
            "position": ["QB", "QB"],
            "attempts": [28, 30],
            "carries": [3, 4],
            "targets": [0, 0],
            "offense_pct": [0.95, 0.96],
        }
    )
    config = RoleTrendConfig(enabled=True, positions=("RB", "WR", "TE"))
    adjuster = RoleTrendProjectionAdjuster(config, role_inputs_loader=_StubRoleInputs(frame))

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "QB1",
                "team": "KC",
                "position": "QB",
                "fpts": 20.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=3,
    )

    assert adjusted[0]["fpts"] == 20.0
    assert adjusted[0]["role_trend_factor"] == 1.0
    assert adjusted[0]["role_trend_applied"] is False
    assert stats.adjusted_rows == 0
    assert stats.neutral_rows == 1


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
