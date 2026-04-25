import math

import pytest

from fantasy_sim.data.play_call_model import PlayCallModelConfig
from fantasy_sim.validation.backtester import BacktestResult, Backtester
from fantasy_sim.validation.metrics import boom_bust_calibration


class TestBacktestResultTargets:
    def test_targets_are_defined(self):
        assert BacktestResult.WEEKLY_MAE_TARGET == 6.0
        assert BacktestResult.SEASON_MAE_TARGET == 25.0
        assert BacktestResult.RANK_CORR_TARGET == 0.80
        assert BacktestResult.CALIBRATION_TARGET == 0.10

    def test_passes_targets_when_all_good(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is True

    def test_fails_on_high_weekly_mae(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=7.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_high_season_mae(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=30.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_low_rank_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.75, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_missing_position_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={
                "QB": 0.85,
                "RB": 0.82,
                "WR": 0.81,
            },  # Missing TE
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_nan_rank_correlation(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={
                "QB": float("nan"),
                "RB": 0.82,
                "WR": 0.81,
                "TE": 0.83,
            },
            boom_bust_calibration=0.05,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_fails_on_high_calibration(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=5.0,
            season_mae=20.0,
            rank_correlations={"QB": 0.85, "RB": 0.82, "WR": 0.81, "TE": 0.83},
            boom_bust_calibration=0.15,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is False

    def test_passes_at_exact_boundary(self):
        result = BacktestResult(
            test_season=2024,
            weekly_mae=6.0,
            season_mae=25.0,
            rank_correlations={"QB": 0.80, "RB": 0.80, "WR": 0.80, "TE": 0.80},
            boom_bust_calibration=0.10,
            total_players_evaluated=100,
            total_weeks_evaluated=18,
        )
        assert result.passes_targets() is True


class TestBoomBustCalibration:
    def test_perfect_calibration(self):
        predicted = {"p1": 0.3, "p2": 0.5}
        actual = {"p1": 0.3, "p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)

    def test_imperfect_calibration(self):
        predicted = {"p1": 0.4, "p2": 0.6}
        actual = {"p1": 0.3, "p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.1)

    def test_mismatched_keys_only_uses_common(self):
        predicted = {"p1": 0.3, "p2": 0.5, "p3": 0.9}
        actual = {"p1": 0.3, "p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)

    def test_empty_inputs(self):
        assert boom_bust_calibration({}, {}) == pytest.approx(0.0)

    def test_no_common_keys(self):
        predicted = {"p1": 0.3}
        actual = {"p2": 0.5}
        assert boom_bust_calibration(predicted, actual) == pytest.approx(0.0)


class TestBacktestDataLeakage:
    def test_training_seasons_excludes_test_season(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=3)
        assert bt.test_season == 2024
        assert bt.training_seasons == [2021, 2022, 2023]
        assert 2024 not in bt.training_seasons

    def test_training_seasons_with_different_window(self):
        bt = Backtester(test_season=2023, n_sims=10, num_training_seasons=2)
        assert bt.training_seasons == [2021, 2022]
        assert 2023 not in bt.training_seasons

    def test_single_training_season(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=1)
        assert bt.training_seasons == [2023]
        assert 2024 not in bt.training_seasons

    def test_training_seasons_are_contiguous(self):
        bt = Backtester(test_season=2024, n_sims=10, num_training_seasons=4)
        assert bt.training_seasons == [2020, 2021, 2022, 2023]
        for i in range(1, len(bt.training_seasons)):
            assert bt.training_seasons[i] == bt.training_seasons[i - 1] + 1

    def test_accepts_play_call_model_config(self):
        config = PlayCallModelConfig(enabled=True)

        bt = Backtester(test_season=2024, n_sims=10, play_call_model_config=config)

        assert bt._play_call_model_config is config
