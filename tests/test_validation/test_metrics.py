# tests/test_validation/test_metrics.py
import numpy as np
import pytest
from fantasy_sim.validation.metrics import (
    spearman_rank_correlation,
    mean_absolute_error,
    season_total_mae,
    boom_bust_calibration,
)


class TestSpearmanRankCorrelation:
    def test_perfect_correlation(self):
        projected = [30.0, 25.0, 20.0, 15.0, 10.0]
        actual = [28.0, 24.0, 19.0, 14.0, 9.0]
        corr = spearman_rank_correlation(projected, actual)
        assert corr == pytest.approx(1.0)

    def test_inverse_correlation(self):
        projected = [30.0, 25.0, 20.0, 15.0, 10.0]
        actual = [9.0, 14.0, 19.0, 24.0, 28.0]
        corr = spearman_rank_correlation(projected, actual)
        assert corr == pytest.approx(-1.0)

    def test_no_correlation(self):
        rng = np.random.default_rng(42)
        projected = rng.random(100).tolist()
        actual = rng.random(100).tolist()
        corr = spearman_rank_correlation(projected, actual)
        assert -0.3 <= corr <= 0.3

    def test_returns_float(self):
        corr = spearman_rank_correlation([1, 2, 3], [1, 2, 3])
        assert isinstance(corr, float)


class TestMeanAbsoluteError:
    def test_zero_error(self):
        mae = mean_absolute_error([10.0, 20.0], [10.0, 20.0])
        assert mae == pytest.approx(0.0)

    def test_known_error(self):
        mae = mean_absolute_error([10.0, 20.0], [12.0, 18.0])
        assert mae == pytest.approx(2.0)

    def test_one_sided_error(self):
        mae = mean_absolute_error([10.0], [15.0])
        assert mae == pytest.approx(5.0)


class TestSeasonTotalMAE:
    def test_aggregates_across_weeks(self):
        projected_weekly = {"P1": [11.0, 11.0, 11.0]}
        actual_weekly = {"P1": [10.0, 12.0, 8.0]}
        mae = season_total_mae(projected_weekly, actual_weekly)
        assert mae == pytest.approx(3.0)

    def test_multiple_players(self):
        projected = {"P1": [10.0, 10.0], "P2": [20.0, 20.0]}
        actual = {"P1": [8.0, 12.0], "P2": [18.0, 22.0]}
        mae = season_total_mae(projected, actual)
        assert mae == pytest.approx(0.0)


class TestBoomBustCalibration:
    def test_perfect_calibration(self):
        predicted_boom_pcts = {"P1": 0.50}
        actual_boom_pcts = {"P1": 0.50}
        cal = boom_bust_calibration(predicted_boom_pcts, actual_boom_pcts)
        assert cal == pytest.approx(0.0, abs=0.01)

    def test_off_by_ten_percent(self):
        predicted_boom_pcts = {"P1": 0.30}
        actual_boom_pcts = {"P1": 0.20}
        cal = boom_bust_calibration(predicted_boom_pcts, actual_boom_pcts)
        assert cal == pytest.approx(0.10, abs=0.01)

    def test_multiple_players(self):
        predicted = {"P1": 0.30, "P2": 0.50}
        actual = {"P1": 0.20, "P2": 0.40}
        cal = boom_bust_calibration(predicted, actual)
        assert cal == pytest.approx(0.10, abs=0.01)
