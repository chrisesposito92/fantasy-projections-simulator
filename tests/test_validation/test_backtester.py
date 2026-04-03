# tests/test_validation/test_backtester.py
import polars as pl
from unittest.mock import patch, MagicMock
from fantasy_sim.validation.backtester import Backtester, BacktestResult


class TestBacktester:
    def test_training_seasons_exclude_test_season(self):
        bt = Backtester(test_season=2024, n_sims=10)
        assert 2024 not in bt.training_seasons
        assert len(bt.training_seasons) > 0

    def test_training_seasons_use_prior_years(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=3)
        assert bt.training_seasons == [2021, 2022, 2023]

    def test_backtest_result_has_metrics(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.5,
            season_mae=22.0,
            rank_correlations={"QB": 0.85, "RB": 0.80, "WR": 0.82, "TE": 0.81},
            boom_bust_calibration=0.08,
            total_players_evaluated=96,
            total_weeks_evaluated=18,
        )
        assert result.weekly_mae < 6.0
        assert result.rank_correlations["QB"] > 0.80
        assert result.passes_targets()

    def test_backtest_result_fails_when_metrics_bad(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=8.0,
            season_mae=30.0,
            rank_correlations={"QB": 0.70},
            boom_bust_calibration=0.15,
            total_players_evaluated=24,
            total_weeks_evaluated=18,
        )
        assert not result.passes_targets()


class TestBacktesterRosterHandling:
    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_game_receives_target_season_and_week(self, mock_loader_cls, mock_builder_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})

        mock_builder = MagicMock()
        mock_builder_cls.return_value = mock_builder
        mock_builder.build_game.side_effect = Exception("stop")

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        config = load_defaults()
        scoring_config = resolve_scoring(config["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = mock_loader
        bt.builder = mock_builder

        bt.run(scoring_config)

        call_kwargs = mock_builder.build_game.call_args[1]
        assert call_kwargs["training_seasons"] == [2021, 2022, 2023]
        assert call_kwargs["target_season"] == 2024
        assert call_kwargs["week"] == 1


class TestBacktesterPffConfig:
    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_pff_config_passed_to_builder(self, mock_loader_cls, mock_builder_cls):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg)

        mock_builder_cls.assert_called_once_with(
            cache_dir="/tmp/test",
            pff_config=pff_cfg,
        )

    @patch("fantasy_sim.validation.backtester.GameContextBuilder")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_no_pff_config_passes_none(self, mock_loader_cls, mock_builder_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"

        Backtester(test_season=2024, n_sims=10)

        call_kwargs = mock_builder_cls.call_args[1]
        assert call_kwargs.get("pff_config") is None
