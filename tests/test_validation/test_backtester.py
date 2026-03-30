# tests/test_validation/test_backtester.py
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
