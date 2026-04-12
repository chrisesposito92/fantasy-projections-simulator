from types import SimpleNamespace

import polars as pl

from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.scoring.market_history import MarketHistoryProjectionAdjuster
from fantasy_sim.scoring.projection_layers import apply_projection_layers


class _StubLoader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.calls: list[list[int]] = []

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        self.calls.append(list(seasons))
        return self.frame


def _config(*, enabled: bool = True) -> MarketHistoryConfig:
    return MarketHistoryConfig(
        enabled=enabled,
        weights={"QB": 0.50, "RB": 0.15, "WR": 0.25, "TE": 0.15},
    )


def test_adjust_week_blends_covered_rows_and_recomputes_rank():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024, 2024],
                "week": [1, 1],
                "player_id": ["QB1", "WR1"],
                "full_name": ["QB One", "WR One"],
                "position": ["QB", "WR"],
                "team": ["KC", "MIN"],
                "open_fpts": [19.0, 12.0],
                "close_fpts": [20.0, 12.0],
                "books": [2, 2],
                "line_stddev": [0.0, 0.0],
                "anytime_td_prob": [None, None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(_config(), loader=loader)

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "name": "WR One",
                "position": "WR",
                "team": "MIN",
                "fpts": 11.0,
                "rank": 1,
            },
            {
                "player_id": "QB1",
                "name": "QB One",
                "position": "QB",
                "team": "KC",
                "fpts": 10.0,
                "rank": 2,
            },
        ],
        season=2024,
        week=1,
    )

    qb = next(row for row in adjusted if row["player_id"] == "QB1")
    wr = next(row for row in adjusted if row["player_id"] == "WR1")

    assert qb["fpts"] == 15.0
    assert qb["rank"] == 1
    assert qb["market_history_source"] == "market_history"
    assert qb["market_history_weight"] == 0.5
    assert qb["market_history_covered"] is True
    assert qb["market_history_prior_fpts"] == 20.0
    assert wr["fpts"] == 11.2
    assert wr["market_history_weight"] == 0.25
    assert stats.covered_rows == 2
    assert stats.uncovered_rows == 0


def test_adjust_week_marks_uncovered_rows_without_changing_fpts():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["WR1"],
                "full_name": ["WR One"],
                "position": ["WR"],
                "team": ["MIN"],
                "open_fpts": [12.0],
                "close_fpts": [12.0],
                "books": [2],
                "line_stddev": [0.0],
                "anytime_td_prob": [None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(_config(), loader=loader)

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "RB1",
                "name": "RB One",
                "position": "RB",
                "team": "SF",
                "fpts": 13.0,
                "rank": 1,
            }
        ],
        season=2024,
        week=1,
    )

    row = adjusted[0]
    assert row["fpts"] == 13.0
    assert row["market_history_source"] is None
    assert row["market_history_weight"] == 0.0
    assert row["market_history_covered"] is False
    assert stats.covered_rows == 0
    assert stats.uncovered_rows == 1


def test_apply_projection_layers_runs_market_history_between_role_trend_and_ensemble():
    order: list[str] = []

    class _Trend:
        def adjust_week(self, projections, *, season, week):
            order.append("trend")
            return ([dict(projections[0], fpts=13.0)], SimpleNamespace())

    class _Market:
        def adjust_week(self, projections, *, season, week):
            order.append("market")
            assert projections[0]["fpts"] == 13.0
            return ([dict(projections[0], fpts=14.0)], SimpleNamespace())

    class _Ensemble:
        def blend_week(self, projections, *, season, week):
            order.append("ensemble")
            assert projections[0]["fpts"] == 14.0
            return ([dict(projections[0], fpts=15.0)], SimpleNamespace())

    rows = [{"player_id": "QB1", "position": "QB", "team": "KC", "fpts": 12.0, "rank": 1}]

    adjusted = apply_projection_layers(
        rows,
        season=2024,
        week=1,
        role_trend_adjuster=_Trend(),
        market_history_adjuster=_Market(),
        ensembler=_Ensemble(),
    )

    assert adjusted[0]["fpts"] == 15.0
    assert order == ["trend", "market", "ensemble"]
