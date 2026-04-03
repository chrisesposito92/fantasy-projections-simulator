"""Tests for A/B ledger data model and I/O in validate_pff_signal.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest
from validate_pff_signal import (
    SeasonResult,
    LedgerEntry,
    load_ledger,
    save_ledger,
    format_progression_table,
    POSITIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_season_result(test_season: int = 2023, delta: float = 0.05) -> SeasonResult:
    """Create a SeasonResult with controllable rank_corr delta."""
    off_rc = {pos: 0.70 for pos in POSITIONS}
    on_rc = {pos: 0.70 + delta for pos in POSITIONS}
    return SeasonResult(
        test_season=test_season,
        off_weekly_mae=5.0,
        off_season_mae=20.0,
        off_rank_corr=off_rc,
        off_calibration=0.08,
        on_weekly_mae=4.8,
        on_season_mae=19.5,
        on_rank_corr=on_rc,
        on_calibration=0.07,
    )


def _make_ledger_entry(label: str = "test-run", verdict: str = "PASS") -> LedgerEntry:
    return LedgerEntry(
        label=label,
        timestamp="2026-04-02T12:00:00",
        mode="all",
        sims=50,
        test_seasons=[2023, 2024],
        training_years=2,
        pff_config={"enabled": True},
        season_results=[_make_season_result(2023), _make_season_result(2024)],
        verdict=verdict,
    )


# ---------------------------------------------------------------------------
# TestSeasonResult
# ---------------------------------------------------------------------------

class TestSeasonResult:
    def test_rank_corr_delta_computed_correctly(self):
        sr = _make_season_result(delta=0.05)
        assert abs(sr.rank_corr_delta - 0.05) < 1e-9

    def test_rank_corr_delta_zero_when_no_change(self):
        sr = _make_season_result(delta=0.0)
        assert sr.rank_corr_delta == 0.0

    def test_rank_corr_delta_negative_regression(self):
        sr = _make_season_result(delta=-0.02)
        assert abs(sr.rank_corr_delta - (-0.02)) < 1e-9

    def test_rank_corr_delta_averages_all_positions(self):
        """Each position contributes equally to the average."""
        off_rc = {"QB": 0.70, "RB": 0.72, "WR": 0.68, "TE": 0.65}
        on_rc = {"QB": 0.75, "RB": 0.72, "WR": 0.70, "TE": 0.67}
        sr = SeasonResult(
            test_season=2023,
            off_weekly_mae=5.0,
            off_season_mae=20.0,
            off_rank_corr=off_rc,
            off_calibration=0.08,
            on_weekly_mae=4.8,
            on_season_mae=19.5,
            on_rank_corr=on_rc,
            on_calibration=0.07,
        )
        expected = ((0.75 - 0.70) + (0.72 - 0.72) + (0.70 - 0.68) + (0.67 - 0.65)) / 4
        assert abs(sr.rank_corr_delta - expected) < 1e-9

    def test_weekly_mae_delta(self):
        sr = _make_season_result()
        # on=4.8, off=5.0 -> delta = -0.2 (improvement)
        assert abs(sr.weekly_mae_delta - (4.8 - 5.0)) < 1e-9

    def test_season_mae_delta(self):
        sr = _make_season_result()
        assert abs(sr.season_mae_delta - (19.5 - 20.0)) < 1e-9

    def test_calibration_delta(self):
        sr = _make_season_result()
        assert abs(sr.calibration_delta - (0.07 - 0.08)) < 1e-9


# ---------------------------------------------------------------------------
# TestLedgerIO
# ---------------------------------------------------------------------------

class TestLedgerIO:
    def test_load_returns_empty_list_when_no_file(self, tmp_path):
        path = tmp_path / "no_such_file.json"
        result = load_ledger(path)
        assert result == []

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "ledger.json"
        entry = _make_ledger_entry(label="roundtrip-test", verdict="SOFT_PASS")
        save_ledger(path, [entry])

        loaded = load_ledger(path)
        assert len(loaded) == 1
        e = loaded[0]
        assert e.label == "roundtrip-test"
        assert e.verdict == "SOFT_PASS"
        assert e.mode == "all"
        assert e.sims == 50
        assert e.test_seasons == [2023, 2024]
        assert e.training_years == 2
        assert len(e.season_results) == 2

    def test_save_and_load_season_result_fields(self, tmp_path):
        path = tmp_path / "ledger.json"
        entry = _make_ledger_entry()
        save_ledger(path, [entry])

        loaded = load_ledger(path)
        sr = loaded[0].season_results[0]
        assert sr.test_season == 2023
        assert abs(sr.off_weekly_mae - 5.0) < 1e-9
        assert abs(sr.on_weekly_mae - 4.8) < 1e-9
        assert sr.off_rank_corr == {pos: 0.70 for pos in POSITIONS}

    def test_save_creates_parent_dirs(self, tmp_path):
        nested_path = tmp_path / "deep" / "nested" / "ledger.json"
        entry = _make_ledger_entry()
        save_ledger(nested_path, [entry])
        assert nested_path.exists()

    def test_save_multiple_entries(self, tmp_path):
        path = tmp_path / "ledger.json"
        entries = [
            _make_ledger_entry(label="run-1", verdict="PASS"),
            _make_ledger_entry(label="run-2", verdict="FAIL"),
            _make_ledger_entry(label="run-3", verdict="SOFT_PASS"),
        ]
        save_ledger(path, entries)
        loaded = load_ledger(path)
        assert len(loaded) == 3
        assert [e.label for e in loaded] == ["run-1", "run-2", "run-3"]
        assert [e.verdict for e in loaded] == ["PASS", "FAIL", "SOFT_PASS"]

    def test_load_preserves_pff_config(self, tmp_path):
        path = tmp_path / "ledger.json"
        cfg = {"enabled": True, "matchup": {"factor_clamp": 0.3}}
        entry = _make_ledger_entry()
        entry.pff_config = cfg
        save_ledger(path, [entry])
        loaded = load_ledger(path)
        assert loaded[0].pff_config == cfg


# ---------------------------------------------------------------------------
# TestLedgerEntryProperties
# ---------------------------------------------------------------------------

class TestLedgerEntryProperties:
    def test_avg_rank_corr_delta_single_season(self):
        entry = LedgerEntry(
            label="x",
            timestamp="2026-04-02T12:00:00",
            mode="all",
            sims=50,
            test_seasons=[2023],
            training_years=2,
            pff_config={},
            season_results=[_make_season_result(2023, delta=0.05)],
            verdict="PASS",
        )
        assert abs(entry.avg_rank_corr_delta - 0.05) < 1e-9

    def test_avg_rank_corr_delta_multiple_seasons(self):
        entry = LedgerEntry(
            label="x",
            timestamp="2026-04-02T12:00:00",
            mode="all",
            sims=50,
            test_seasons=[2023, 2024],
            training_years=2,
            pff_config={},
            season_results=[
                _make_season_result(2023, delta=0.04),
                _make_season_result(2024, delta=0.06),
            ],
            verdict="PASS",
        )
        assert abs(entry.avg_rank_corr_delta - 0.05) < 1e-9

    def test_avg_weekly_mae_delta(self):
        entry = _make_ledger_entry()
        # Both seasons: on=4.8, off=5.0 -> delta=-0.2 each
        assert abs(entry.avg_weekly_mae_delta - (-0.2)) < 1e-9

    def test_avg_season_mae_delta(self):
        entry = _make_ledger_entry()
        assert abs(entry.avg_season_mae_delta - (-0.5)) < 1e-9

    def test_avg_calibration_delta(self):
        entry = _make_ledger_entry()
        assert abs(entry.avg_calibration_delta - (-0.01)) < 1e-9

    def test_empty_season_results_returns_zero(self):
        entry = LedgerEntry(
            label="empty",
            timestamp="2026-04-02T12:00:00",
            mode="all",
            sims=50,
            test_seasons=[],
            training_years=2,
            pff_config={},
            season_results=[],
            verdict="FAIL",
        )
        assert entry.avg_rank_corr_delta == 0.0
        assert entry.avg_weekly_mae_delta == 0.0
        assert entry.avg_season_mae_delta == 0.0
        assert entry.avg_calibration_delta == 0.0


# ---------------------------------------------------------------------------
# TestProgressionTable
# ---------------------------------------------------------------------------

class TestProgressionTable:
    def test_format_table_empty(self):
        result = format_progression_table([])
        assert "No entries" in result

    def test_format_table_with_entries_contains_label(self):
        entries = [_make_ledger_entry(label="my-cool-run", verdict="PASS")]
        result = format_progression_table(entries)
        assert "my-cool-run" in result

    def test_format_table_with_entries_contains_verdict(self):
        entries = [_make_ledger_entry(label="run-a", verdict="SOFT_PASS")]
        result = format_progression_table(entries)
        assert "SOFT_PASS" in result

    def test_format_table_multiple_entries(self):
        entries = [
            _make_ledger_entry(label="run-1", verdict="PASS"),
            _make_ledger_entry(label="run-2", verdict="FAIL"),
        ]
        result = format_progression_table(entries)
        assert "run-1" in result
        assert "run-2" in result
        assert "PASS" in result
        assert "FAIL" in result

    def test_format_table_row_numbering(self):
        entries = [
            _make_ledger_entry(label="first"),
            _make_ledger_entry(label="second"),
        ]
        result = format_progression_table(entries)
        assert "1" in result
        assert "2" in result

    def test_format_table_has_header_columns(self):
        entries = [_make_ledger_entry()]
        result = format_progression_table(entries)
        # Check key column headers appear
        assert "Label" in result
        assert "Verdict" in result

    def test_format_table_returns_string(self):
        result = format_progression_table([])
        assert isinstance(result, str)
