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
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_build_game_receives_target_season_and_week(self, mock_loader_cls, mock_build_parallel):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        config = load_defaults()
        scoring_config = resolve_scoring(config["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10)
        bt.loader = mock_loader
        bt.run(scoring_config)

        game_args = mock_build_parallel.call_args[0][0]
        home, away, ts, target, wk, gid, seed = game_args[0]
        assert ts == [2021, 2022, 2023]
        assert target == 2024
        assert wk == 1


class TestBacktesterPffConfig:
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_pff_config_stored(self, mock_loader_cls):
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg)
        assert bt._pff_config is pff_cfg

    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_no_pff_config_is_none(self, mock_loader_cls):
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = "/tmp/test"
        bt = Backtester(test_season=2024, n_sims=10)
        assert bt._pff_config is None


class TestBacktesterParallelBuild:
    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_uses_build_games_parallel(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "2024_01_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, max_workers=4)
        bt.loader = mock_loader
        bt.run(scoring_config)

        mock_build_parallel.assert_called_once()
        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["max_workers"] == 4
        assert call_kwargs["dual_arm"] is False

    @patch("fantasy_sim.validation.backtester.build_games_parallel")
    @patch("fantasy_sim.validation.backtester.DataLoader")
    def test_phase1_passes_pff_and_weather_config(self, mock_loader_cls, mock_build_parallel):
        from pathlib import Path
        from fantasy_sim.data.pff.models import PffConfig, TalentConfig
        from fantasy_sim.data.weather.models import WeatherConfig

        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        mock_loader.cache_dir = Path("/tmp/test")
        mock_loader.load_schedules.return_value = pl.DataFrame(
            {"season": pl.Series([], dtype=pl.Int32), "week": pl.Series([], dtype=pl.Int32),
             "game_id": pl.Series([], dtype=pl.Utf8), "home_team": pl.Series([], dtype=pl.Utf8),
             "away_team": pl.Series([], dtype=pl.Utf8)}
        )
        mock_loader.load_player_stats.return_value = pl.DataFrame({"season": pl.Series([], dtype=pl.Int32)})
        mock_build_parallel.return_value = []

        pff_cfg = PffConfig(enabled=True, talent=TalentConfig(enabled=True))
        weather_cfg = WeatherConfig(enabled=True)

        from fantasy_sim.config.loader import load_defaults, resolve_scoring
        scoring_config = resolve_scoring(load_defaults()["scoring"], "ppr")

        bt = Backtester(test_season=2024, n_sims=10, pff_config=pff_cfg, weather_config=weather_cfg)
        bt.loader = mock_loader
        bt.run(scoring_config)

        call_kwargs = mock_build_parallel.call_args[1]
        assert call_kwargs["pff_config"] is pff_cfg
        assert call_kwargs["weather_config"] is weather_cfg
