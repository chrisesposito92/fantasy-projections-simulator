"""Tests for sweep_talent_params.py — grid builder and results table."""

from __future__ import annotations

import sys
from pathlib import Path
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

# Add scripts dir to path so we can import the module directly
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from sweep_talent_params import (
    DEFAULT_MIN_DIVERGENCES,
    DEFAULT_PRIOR_STRENGTHS,
    build_sweep_grid,
    print_results_table,
)


# ---------------------------------------------------------------------------
# TestSweepGrid
# ---------------------------------------------------------------------------

class TestSweepGrid:
    def test_grid_size(self) -> None:
        grid = build_sweep_grid(prior_strengths=[20, 40, 60], min_divergences=[0.02, 0.03])
        assert len(grid) == 6

    def test_grid_entries_are_dicts(self) -> None:
        grid = build_sweep_grid(prior_strengths=[40], min_divergences=[0.03])
        assert len(grid) == 1
        assert grid[0]["prior_strength"] == 40
        assert grid[0]["min_divergence"] == 0.03

    def test_default_grid_size(self) -> None:
        grid = build_sweep_grid()
        assert len(grid) == 20  # 5 * 4

    def test_all_combinations_present(self) -> None:
        """Every (prior_strength, min_divergence) pair must appear exactly once."""
        ps_vals = [20, 60]
        md_vals = [0.01, 0.05]
        grid = build_sweep_grid(prior_strengths=ps_vals, min_divergences=md_vals)
        seen = {(e["prior_strength"], e["min_divergence"]) for e in grid}
        expected = {(ps, md) for ps in ps_vals for md in md_vals}
        assert seen == expected

    def test_grid_entry_keys(self) -> None:
        """Each entry must have exactly prior_strength and min_divergence keys."""
        grid = build_sweep_grid(prior_strengths=[30], min_divergences=[0.02])
        assert set(grid[0].keys()) == {"prior_strength", "min_divergence"}

    def test_single_combination(self) -> None:
        grid = build_sweep_grid(prior_strengths=[50], min_divergences=[0.04])
        assert len(grid) == 1
        assert grid[0]["prior_strength"] == 50
        assert grid[0]["min_divergence"] == pytest.approx(0.04)

    def test_default_prior_strengths(self) -> None:
        assert DEFAULT_PRIOR_STRENGTHS == [20, 30, 40, 60, 80]

    def test_default_min_divergences(self) -> None:
        assert DEFAULT_MIN_DIVERGENCES == [0.01, 0.02, 0.03, 0.05]

    def test_order_prior_strength_outer_divergence_inner(self) -> None:
        """Grid iterates prior_strength in outer loop, min_divergence in inner."""
        grid = build_sweep_grid(prior_strengths=[10, 20], min_divergences=[0.1, 0.2])
        assert grid[0] == {"prior_strength": 10, "min_divergence": 0.1}
        assert grid[1] == {"prior_strength": 10, "min_divergence": 0.2}
        assert grid[2] == {"prior_strength": 20, "min_divergence": 0.1}
        assert grid[3] == {"prior_strength": 20, "min_divergence": 0.2}

    def test_empty_prior_strengths(self) -> None:
        grid = build_sweep_grid(prior_strengths=[], min_divergences=[0.02])
        assert grid == []

    def test_empty_min_divergences(self) -> None:
        grid = build_sweep_grid(prior_strengths=[40], min_divergences=[])
        assert grid == []


# ---------------------------------------------------------------------------
# TestPrintResultsTable
# ---------------------------------------------------------------------------

class TestPrintResultsTable:
    def _make_result(
        self,
        prior_strength: float = 40.0,
        min_divergence: float = 0.03,
        rank_corr: float = 0.82,
        weekly_mae: float = 5.5,
        season_mae: float = 22.0,
        calibration: float = 0.08,
        rank_corr_delta: float = 0.02,
    ) -> dict:
        return {
            "prior_strength": prior_strength,
            "min_divergence": min_divergence,
            "rank_corr": rank_corr,
            "weekly_mae": weekly_mae,
            "season_mae": season_mae,
            "calibration": calibration,
            "rank_corr_delta": rank_corr_delta,
        }

    def test_prints_header(self, capsys) -> None:
        results = [self._make_result()]
        print_results_table(results)
        captured = capsys.readouterr()
        # Should contain column headers
        assert "prior_str" in captured.out or "prior" in captured.out.lower()

    def test_prints_row_per_result(self, capsys) -> None:
        results = [
            self._make_result(prior_strength=20, min_divergence=0.01),
            self._make_result(prior_strength=40, min_divergence=0.03),
        ]
        print_results_table(results)
        captured = capsys.readouterr()
        assert "20" in captured.out
        assert "40" in captured.out

    def test_marks_best(self, capsys) -> None:
        """The first result (highest rank_corr_delta) should be marked BEST."""
        results = [
            self._make_result(rank_corr_delta=0.05, prior_strength=60),
            self._make_result(rank_corr_delta=0.02, prior_strength=40),
        ]
        print_results_table(results)
        captured = capsys.readouterr()
        assert "BEST" in captured.out

    def test_empty_results_no_crash(self, capsys) -> None:
        print_results_table([])
        captured = capsys.readouterr()
        # Should not crash; may print header or empty message
        assert isinstance(captured.out, str)

    def test_rank_corr_in_output(self, capsys) -> None:
        results = [self._make_result(rank_corr=0.87)]
        print_results_table(results)
        captured = capsys.readouterr()
        assert "0.87" in captured.out or "87" in captured.out

    def test_min_div_in_output(self, capsys) -> None:
        results = [self._make_result(min_divergence=0.05)]
        print_results_table(results)
        captured = capsys.readouterr()
        assert "0.05" in captured.out or "05" in captured.out
