from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl

from fantasy_sim.data.ensemble.models import EnsembleConfig, FfOpportunityConfig
from fantasy_sim.data.market_history.models import MarketHistoryConfig
from fantasy_sim.data.role_trend.models import RoleTrendConfig
from fantasy_sim.validation.backtester import Backtester


def _load_validate_module():
    import importlib.util

    validate_path = Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
    spec = importlib.util.spec_from_file_location(
        "validate_script_market_history_test",
        validate_path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backtester_applies_role_trend_then_market_history_then_ensemble():
    mock_loader = MagicMock()
    mock_loader.cache_dir = Path("/tmp/test-cache")
    mock_loader.load_schedules.return_value = pl.DataFrame(
        [
            {
                "season": 2024,
                "week": 1,
                "game_id": "2024_01_KC_BUF",
                "home_team": "KC",
                "away_team": "BUF",
            }
        ]
    )
    mock_loader.load_player_stats.return_value = pl.DataFrame(
        {"season": pl.Series([], dtype=pl.Int32)}
    )

    build_results = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 7,
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "home_dists": object(),
            "away_dists": object(),
            "home_roster": object(),
            "away_roster": object(),
        }
    ]
    sim_results = [
        SimpleNamespace(
            game_id="2024_01_KC_BUF",
            projections=[
                {
                    "player_id": "player-1",
                    "fpts": 12.0,
                    "position": "QB",
                    "team": "KC",
                    "name": "Patrick Example",
                }
            ],
        )
    ]
    actuals = [
        SimpleNamespace(
            player_id="player-1",
            week=1,
            fpts=15.0,
            position="QB",
            team="KC",
            name="Patrick Example",
        )
    ]

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

    with patch(
        "fantasy_sim.validation.backtester.build_games_parallel",
        return_value=build_results,
    ), patch(
        "fantasy_sim.validation.backtester.simulate_games_parallel",
        return_value=sim_results,
    ), patch(
        "fantasy_sim.validation.backtester.load_actual_scores",
        return_value=actuals,
    ), patch(
        "fantasy_sim.validation.backtester.RoleTrendProjectionAdjuster",
        return_value=_Trend(),
    ), patch(
        "fantasy_sim.validation.backtester.MarketHistoryProjectionAdjuster",
        return_value=_Market(),
    ), patch(
        "fantasy_sim.validation.backtester.FfOpportunityProjectionEnsembler",
        return_value=_Ensemble(),
    ):
        bt = Backtester(
            test_season=2024,
            n_sims=10,
            role_trend_config=RoleTrendConfig(enabled=True),
            market_history_config=MarketHistoryConfig(enabled=True),
            ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
        )
        bt.loader = mock_loader

        result = bt.run(scoring_config={})

    assert result.weekly_mae == 0.0
    assert order == ["trend", "market", "ensemble"]


def test_run_season_applies_role_trend_then_market_history_then_ensemble():
    validate = _load_validate_module()

    build_b = [
        {
            "status": "ok",
            "game_id": "2024_01_KC_BUF",
            "seed": 7,
            "week": 1,
            "home": "KC",
            "away": "BUF",
            "home_dists": object(),
            "away_dists": object(),
            "home_roster": object(),
            "away_roster": object(),
        }
    ]
    actual = SimpleNamespace(
        player_id="player-1",
        week=1,
        fpts=15.0,
        position="QB",
        team="KC",
        name="Patrick Example",
    )
    cached_arm_a = {
        "projections": {"player-1": {1: 10.0}},
        "player_meta": {
            "player-1": {
                "position": "QB",
                "team": "KC",
                "name": "Patrick Example",
            }
        },
    }
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

    with patch.object(validate, "build_games_parallel", return_value=build_b), patch.object(
        validate,
        "simulate_games_parallel",
        return_value=[
            SimpleNamespace(
                game_id="2024_01_KC_BUF",
                metadata={},
                projections=[
                    {
                        "player_id": "player-1",
                        "fpts": 12.0,
                        "position": "QB",
                        "team": "KC",
                        "name": "Patrick Example",
                    }
                ],
            )
        ],
    ), patch.object(
        validate,
        "load_actual_scores",
        return_value=[actual],
    ), patch.object(
        validate,
        "DataLoader",
    ) as mock_loader_cls, patch.object(
        validate,
        "RoleTrendProjectionAdjuster",
        return_value=_Trend(),
    ), patch.object(
        validate,
        "MarketHistoryProjectionAdjuster",
        return_value=_Market(),
    ), patch.object(
        validate,
        "FfOpportunityProjectionEnsembler",
        return_value=_Ensemble(),
    ):
        mock_loader = mock_loader_cls.return_value
        mock_loader.cache_dir = Path("/tmp/test-cache")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            [
                {
                    "season": 2024,
                    "week": 1,
                    "game_id": "2024_01_KC_BUF",
                    "home_team": "KC",
                    "away_team": "BUF",
                }
            ]
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32)}
        )

        result = validate.run_season(
            test_season=2024,
            n_sims=10,
            scoring_config={},
            num_training_seasons=3,
            arm_a_configs={
                "pff_config": None,
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": None,
                "market_history_config": None,
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_b_configs={
                "pff_config": object(),
                "weather_config": None,
                "vegas_config": None,
                "props_config": None,
                "usage_config": None,
                "availability_config": None,
                "role_trend_config": RoleTrendConfig(enabled=True),
                "market_history_config": MarketHistoryConfig(enabled=True),
                "game_script_config": None,
                "goal_line_concentration_config": None,
                "td_tendency_config": None,
            },
            arm_a_ensemble_config=None,
            arm_b_ensemble_config=EnsembleConfig(
                enabled=True,
                ff_opportunity=FfOpportunityConfig(enabled=True),
            ),
            positions=["QB"],
            max_workers=1,
            cached_arm_a=cached_arm_a,
        )

    assert result["season_metrics"].arm_b_weekly_mae == 0.0
    assert result["weekly_records"][0].projected_fpts_on == 15.0
    assert order == ["trend", "market", "ensemble"]
