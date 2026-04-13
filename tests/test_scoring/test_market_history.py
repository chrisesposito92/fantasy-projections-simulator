import polars as pl

from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.scoring.ensemble import BlendStats
from fantasy_sim.scoring.market_history import (
    MarketHistoryProjectionAdjuster,
    MarketHistoryStats,
)
from fantasy_sim.scoring.projection_layers import apply_projection_layers
from fantasy_sim.scoring.role_trend import ProjectionRow, TrendStats


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
        snapshot_label="close_core8",
        weights={"QB": 0.50, "RB": 0.15, "WR": 0.25, "TE": 0.15},
    )


def _scoring() -> dict[str, float]:
    return {
        "passing_yard": 0.04,
        "passing_td": 4.0,
        "interception": -2.0,
        "rushing_yard": 0.1,
        "rushing_td": 6.0,
        "receiving_yard": 0.1,
        "receiving_td": 6.0,
        "reception_wr": 1.0,
        "reception_te": 1.0,
        "reception_rb": 1.0,
        "reception_qb": 1.0,
        "fumble_lost": -2.0,
    }


def test_adjust_week_blends_market_native_rows_and_recomputes_rank():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024, 2024, 2024, 2024, 2024],
                "week": [1, 1, 1, 1, 1],
                "player_id": ["QB1", "QB1", "WR1", "WR1", "WR1"],
                "full_name": ["QB One", "QB One", "WR One", "WR One", "WR One"],
                "position": ["QB", "QB", "WR", "WR", "WR"],
                "team": ["KC", "KC", "MIN", "MIN", "MIN"],
                "market_key": [
                    "player_pass_yds",
                    "player_pass_tds",
                    "player_receptions",
                    "player_reception_yds",
                    "player_anytime_td",
                ],
                "bookmaker_count": [2, 2, 2, 2, 2],
                "line": [250.0, 2.5, 6.0, 70.0, None],
                "line_stddev": [0.0, 0.0, 0.0, 0.0, None],
                "implied_prob": [None, None, None, None, 0.50],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(
        _config(),
        loader=loader,
        scoring_config=_scoring(),
    )

    adjusted, stats = adjuster.adjust_week(
        [
            {
                "player_id": "WR1",
                "name": "WR One",
                "position": "WR",
                "team": "MIN",
                "fpts": 11.0,
                "receptions": 4.0,
                "receiving_yards": 50.0,
                "rush_tds": 0.0,
                "receiving_tds": 0.0,
                "rank": 1,
            },
            {
                "player_id": "QB1",
                "name": "QB One",
                "position": "QB",
                "team": "KC",
                "fpts": 10.0,
                "pass_yards": 200.0,
                "pass_tds": 1.0,
                "rush_tds": 0.0,
                "receiving_tds": 0.0,
                "rank": 2,
            },
        ],
        season=2024,
        week=1,
    )

    qb = next(row for row in adjusted if row["player_id"] == "QB1")
    wr = next(row for row in adjusted if row["player_id"] == "WR1")

    assert qb["fpts"] == 14.0
    assert qb["rank"] == 1
    assert qb["market_history_source"] == "market_history"
    assert qb["market_history_weight"] == 0.5
    assert qb["market_history_covered"] is True
    assert qb["market_history_prior_fpts"] == 18.0
    assert qb["market_history_confidence"] == 1.0
    assert qb["market_history_market_count"] == 2
    assert qb["pass_yards"] == 225.0
    assert qb["pass_tds"] == 1.8
    assert wr["fpts"] == 13.0
    assert wr["market_history_weight"] == 0.25
    assert wr["market_history_confidence"] == 1.0
    assert wr["market_history_market_count"] == 3
    assert wr["receptions"] == 4.5
    assert wr["receiving_yards"] == 55.0
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
                "market_key": ["player_receptions"],
                "bookmaker_count": [2],
                "line": [5.0],
                "line_stddev": [0.0],
                "implied_prob": [None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(
        _config(),
        loader=loader,
        scoring_config=_scoring(),
    )

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
    assert "market_history_confidence" not in row
    assert "market_history_market_count" not in row
    assert stats.covered_rows == 0
    assert stats.uncovered_rows == 1


def test_adjust_week_caches_normalized_priors_by_season():
    loader = _StubLoader(
        pl.DataFrame(
            {
                "season": [2024],
                "week": [1],
                "player_id": ["QB1"],
                "full_name": ["QB One"],
                "position": ["QB"],
                "team": ["KC"],
                "market_key": ["player_pass_yds"],
                "bookmaker_count": [2],
                "line": [250.0],
                "line_stddev": [0.0],
                "implied_prob": [None],
            }
        )
    )
    adjuster = MarketHistoryProjectionAdjuster(
        _config(),
        loader=loader,
        scoring_config=_scoring(),
    )
    projections = [
        {
            "player_id": "QB1",
            "name": "QB One",
            "position": "QB",
            "team": "KC",
            "fpts": 10.0,
            "pass_yards": 200.0,
            "rank": 1,
        }
    ]

    adjuster.adjust_week(projections, season=2024, week=1)
    adjuster.adjust_week(projections, season=2024, week=1)

    assert loader.calls == [[2024]]


def test_apply_projection_layers_runs_market_history_between_role_trend_and_ensemble():
    order: list[str] = []

    class _Trend:
        def adjust_week(
            self,
            projections: list[ProjectionRow],
            *,
            season: int,
            week: int,
        ) -> tuple[list[ProjectionRow], TrendStats]:
            order.append("trend")
            return (
                [dict(projections[0], fpts=13.0)],
                TrendStats(total_rows=1, adjusted_rows=1, neutral_rows=0),
            )

    class _Market:
        def adjust_week(
            self,
            projections: list[ProjectionRow],
            *,
            season: int,
            week: int,
        ) -> tuple[list[ProjectionRow], MarketHistoryStats]:
            order.append("market")
            assert projections[0]["fpts"] == 13.0
            return (
                [dict(projections[0], fpts=14.0)],
                MarketHistoryStats(total_rows=1, covered_rows=1, uncovered_rows=0),
            )

    class _Ensemble:
        def blend_week(
            self,
            projections: list[ProjectionRow],
            *,
            season: int,
            week: int,
        ) -> tuple[list[ProjectionRow], BlendStats]:
            order.append("ensemble")
            assert projections[0]["fpts"] == 14.0
            return (
                [dict(projections[0], fpts=15.0)],
                BlendStats(total_rows=1, covered_rows=1, uncovered_rows=0),
            )

    rows: list[ProjectionRow] = [
        {"player_id": "QB1", "position": "QB", "team": "KC", "fpts": 12.0, "rank": 1}
    ]

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
