"""Tests for fit_talent_coefficients.py — PBP extraction, OLS fitting, CV."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl
import pytest

# Add scripts dir to path so we can import the module directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from fit_talent_coefficients import (
    cross_validate_ols,
    extract_pbp_catch_rates,
    extract_pbp_yards_per_carry,
    extract_pbp_yards_per_catch,
    fit_ols,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_pbp() -> pl.DataFrame:
    """Small PBP DataFrame that covers pass, rush, and sack plays."""
    return pl.DataFrame({
        "play_type": ["pass", "pass", "pass", "pass", "pass", "pass", "run", "run", "run"],
        "complete_pass": [1, 0, 1, 1, 0, 1, 0, 0, 0],
        "pass_attempt": [1, 1, 1, 1, 1, 1, 0, 0, 0],
        "rush_attempt": [0, 0, 0, 0, 0, 0, 1, 1, 1],
        "sack": [0, 0, 0, 0, 1, 0, 0, 0, 0],  # play 4 is a sack (pass_attempt=1, sack=1)
        "yards_gained": [12, 0, 8, 15, -7, 20, 5, 3, 10],
        "receiver_player_id": ["WR1", "WR1", "WR2", "WR1", None, "WR2", None, None, None],
        "rusher_player_id": [None, None, None, None, None, None, "RB1", "RB1", "RB1"],
        "season": [2023, 2023, 2023, 2023, 2023, 2023, 2023, 2023, 2023],
    })


# ---------------------------------------------------------------------------
# extract_pbp_catch_rates
# ---------------------------------------------------------------------------

class TestExtractPbpCatchRates:
    def test_basic_catch_rate(self, sample_pbp: pl.DataFrame) -> None:
        """WR1 has 3 targets (incl 1 sack excluded), 2 catches."""
        # pass_attempt=1, sack=0 → WR1 has rows 0,1,3 → targets=3, catches=2
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=2)
        assert "WR1" in rates
        assert abs(rates["WR1"] - 2 / 3) < 0.01

    def test_sack_excluded_from_targets(self, sample_pbp: pl.DataFrame) -> None:
        """Sack plays (sack==1) must not count as a target."""
        # Row 4: pass_attempt=1, sack=1, receiver=None — should be excluded
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=1)
        # WR2 has 2 valid targets (rows 2 and 5), both completions → 1.0
        assert "WR2" in rates
        assert abs(rates["WR2"] - 1.0) < 0.01

    def test_min_targets_filter(self, sample_pbp: pl.DataFrame) -> None:
        """Players below min_targets threshold are excluded."""
        # With min_targets=4, no player qualifies (WR1=3, WR2=2)
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=4)
        assert len(rates) == 0

    def test_null_receiver_excluded(self, sample_pbp: pl.DataFrame) -> None:
        """Plays with null receiver_player_id are excluded."""
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=1)
        assert None not in rates

    def test_returns_dict(self, sample_pbp: pl.DataFrame) -> None:
        rates = extract_pbp_catch_rates(sample_pbp, min_targets=1)
        assert isinstance(rates, dict)
        for k, v in rates.items():
            assert isinstance(k, str)
            assert 0.0 <= v <= 1.0

    def test_from_spec_example(self) -> None:
        """Reproduce the exact example from the task spec."""
        pbp = pl.DataFrame({
            "play_type": ["pass", "pass", "pass", "pass", "run", "run"],
            "complete_pass": [1, 0, 1, 1, 0, 0],
            "pass_attempt": [1, 1, 1, 1, 0, 0],
            "rush_attempt": [0, 0, 0, 0, 1, 1],
            "sack": [0, 0, 0, 0, 0, 0],
            "yards_gained": [12, 0, 8, 15, 5, 3],
            "receiver_player_id": ["WR1", "WR1", "WR2", "WR1", None, None],
            "rusher_player_id": [None, None, None, None, "RB1", "RB1"],
            "season": [2023, 2023, 2023, 2023, 2023, 2023],
        })
        rates = extract_pbp_catch_rates(pbp, min_targets=2)
        assert "WR1" in rates
        assert abs(rates["WR1"] - 2 / 3) < 0.01


# ---------------------------------------------------------------------------
# extract_pbp_yards_per_catch
# ---------------------------------------------------------------------------

class TestExtractPbpYardsPerCatch:
    def test_basic_yards_per_catch(self, sample_pbp: pl.DataFrame) -> None:
        """WR1 has 2 completions: 12 and 15 yards → mean = 13.5."""
        ypc = extract_pbp_yards_per_catch(sample_pbp, min_catches=2)
        assert "WR1" in ypc
        assert abs(ypc["WR1"] - 13.5) < 0.01

    def test_incomplete_excluded(self, sample_pbp: pl.DataFrame) -> None:
        """Incomplete passes (complete_pass==0) must not affect mean."""
        ypc = extract_pbp_yards_per_catch(sample_pbp, min_catches=1)
        # WR2: completions at rows 2 (8 yds) and 5 (20 yds) → mean=14.0
        assert "WR2" in ypc
        assert abs(ypc["WR2"] - 14.0) < 0.01

    def test_min_catches_filter(self, sample_pbp: pl.DataFrame) -> None:
        """Players below min_catches are excluded."""
        ypc = extract_pbp_yards_per_catch(sample_pbp, min_catches=5)
        assert len(ypc) == 0

    def test_returns_dict_of_floats(self, sample_pbp: pl.DataFrame) -> None:
        ypc = extract_pbp_yards_per_catch(sample_pbp, min_catches=1)
        assert isinstance(ypc, dict)
        for k, v in ypc.items():
            assert isinstance(k, str)
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# extract_pbp_yards_per_carry
# ---------------------------------------------------------------------------

class TestExtractPbpYardsPerCarry:
    def test_basic_yards_per_carry(self, sample_pbp: pl.DataFrame) -> None:
        """RB1 has 3 carries: 5, 3, 10 → mean = 6.0."""
        ypc = extract_pbp_yards_per_carry(sample_pbp, min_carries=3)
        assert "RB1" in ypc
        assert abs(ypc["RB1"] - 6.0) < 0.01

    def test_min_carries_filter(self, sample_pbp: pl.DataFrame) -> None:
        """Players below min_carries are excluded."""
        ypc = extract_pbp_yards_per_carry(sample_pbp, min_carries=10)
        assert len(ypc) == 0

    def test_null_rusher_excluded(self, sample_pbp: pl.DataFrame) -> None:
        """Plays with null rusher_player_id are excluded."""
        ypc = extract_pbp_yards_per_carry(sample_pbp, min_carries=1)
        assert None not in ypc

    def test_returns_dict_of_floats(self, sample_pbp: pl.DataFrame) -> None:
        ypc = extract_pbp_yards_per_carry(sample_pbp, min_carries=1)
        assert isinstance(ypc, dict)
        for k, v in ypc.items():
            assert isinstance(k, str)
            assert isinstance(v, float)


# ---------------------------------------------------------------------------
# fit_ols
# ---------------------------------------------------------------------------

class TestFitOls:
    def test_recovers_coefficients(self) -> None:
        """OLS must recover known ground truth coefficients."""
        rng = np.random.default_rng(42)
        n = 100
        X = rng.standard_normal((n, 2))
        y = 0.64 + 0.5 * X[:, 0] - 0.3 * X[:, 1] + rng.normal(0, 0.01, n)
        intercept, coeffs, r_sq = fit_ols(X, y)
        assert abs(intercept - 0.64) < 0.05
        assert abs(coeffs[0] - 0.5) < 0.1
        assert abs(coeffs[1] - (-0.3)) < 0.1
        assert r_sq > 0.9

    def test_perfect_fit_gives_r2_one(self) -> None:
        """Perfect linear data → R² == 1.0."""
        X = np.arange(10, dtype=float).reshape(-1, 1)
        y = 3.0 * X[:, 0] + 7.0
        intercept, coeffs, r_sq = fit_ols(X, y)
        assert abs(intercept - 7.0) < 1e-6
        assert abs(coeffs[0] - 3.0) < 1e-6
        assert abs(r_sq - 1.0) < 1e-6

    def test_single_feature(self) -> None:
        """Works with a single feature column."""
        rng = np.random.default_rng(0)
        X = rng.standard_normal((50, 1))
        y = 2.0 * X[:, 0] + 1.0 + rng.normal(0, 0.05, 50)
        intercept, coeffs, r_sq = fit_ols(X, y)
        assert len(coeffs) == 1
        assert abs(coeffs[0] - 2.0) < 0.2
        assert r_sq > 0.8

    def test_returns_three_element_tuple(self) -> None:
        X = np.random.randn(20, 2)
        y = np.random.randn(20)
        result = fit_ols(X, y)
        assert len(result) == 3
        intercept, coeffs, r_sq = result
        assert isinstance(intercept, float)
        assert isinstance(coeffs, np.ndarray)
        assert isinstance(r_sq, float)

    def test_r_squared_range(self) -> None:
        """R² should be in [0, 1] for non-degenerate inputs."""
        rng = np.random.default_rng(99)
        X = rng.standard_normal((50, 3))
        y = rng.standard_normal(50)  # random noise → low R²
        _, _, r_sq = fit_ols(X, y)
        assert -0.1 <= r_sq <= 1.0  # small tolerance for pure noise case


# ---------------------------------------------------------------------------
# cross_validate_ols
# ---------------------------------------------------------------------------

class TestCrossValidateOls:
    def test_returns_low_mae_for_linear_data(self) -> None:
        """CV MAE should be low when signal is strong."""
        rng = np.random.default_rng(42)
        n = 50
        X = rng.standard_normal((n, 2))
        y = 0.64 + 0.5 * X[:, 0] + rng.normal(0, 0.02, n)
        folds = [np.arange(25), np.arange(25, 50)]
        mae = cross_validate_ols(X, y, folds)
        assert mae < 0.1

    def test_returns_float(self) -> None:
        rng = np.random.default_rng(7)
        X = rng.standard_normal((30, 2))
        y = rng.standard_normal(30)
        folds = [np.arange(15), np.arange(15, 30)]
        mae = cross_validate_ols(X, y, folds)
        assert isinstance(mae, float)
        assert mae >= 0.0

    def test_single_fold_leave_one_out(self) -> None:
        """With one fold, trains on that fold alone and tests the complement."""
        rng = np.random.default_rng(5)
        n = 40
        X = rng.standard_normal((n, 1))
        y = 2.0 * X[:, 0] + 0.5 + rng.normal(0, 0.01, n)
        folds = [np.arange(20), np.arange(20, 40)]
        mae = cross_validate_ols(X, y, folds)
        assert mae < 0.1

    def test_higher_noise_gives_higher_mae(self) -> None:
        """More noise → higher CV MAE."""
        rng = np.random.default_rng(13)
        n = 80
        X = rng.standard_normal((n, 2))
        folds = [np.arange(40), np.arange(40, 80)]

        y_clean = 0.5 * X[:, 0] + rng.normal(0, 0.01, n)
        y_noisy = 0.5 * X[:, 0] + rng.normal(0, 1.0, n)

        mae_clean = cross_validate_ols(X, y_clean, folds)
        mae_noisy = cross_validate_ols(X, y_noisy, folds)
        assert mae_noisy > mae_clean

    def test_three_folds(self) -> None:
        """Works correctly with 3 folds."""
        rng = np.random.default_rng(21)
        n = 60
        X = rng.standard_normal((n, 2))
        y = 1.0 * X[:, 0] - 0.5 * X[:, 1] + rng.normal(0, 0.05, n)
        folds = [np.arange(20), np.arange(20, 40), np.arange(40, 60)]
        mae = cross_validate_ols(X, y, folds)
        assert isinstance(mae, float)
        assert mae >= 0.0
