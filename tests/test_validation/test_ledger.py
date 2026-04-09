"""Tests for unified A/B validation ledger."""
from fantasy_sim.validation.ledger import (
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)


def _make_entry(label: str = "test-run") -> LedgerEntry:
    """Create a minimal LedgerEntry for testing."""
    return LedgerEntry(
        label=label,
        timestamp="2026-04-08T12:00:00",
        sims=50,
        test_seasons=[2022, 2023, 2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        overrides=[],
        config_snapshot={"pff": {"enabled": True}},
        season_results=[
            SeasonMetrics(
                test_season=2024,
                arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
                arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
                arm_a_weekly_mae=7.0,
                arm_b_weekly_mae=6.8,
                arm_a_season_mae=2.5,
                arm_b_season_mae=2.3,
                arm_a_calibration=0.12,
                arm_b_calibration=0.10,
            ),
        ],
        weekly_summaries=None,
        directional_accuracy=None,
    )


def test_ledger_roundtrip(tmp_path):
    path = tmp_path / "test_ledger.json"
    entries = [_make_entry("run-1"), _make_entry("run-2")]
    save_ledger(path, entries)
    loaded = load_ledger(path)
    assert len(loaded) == 2
    assert loaded[0].label == "run-1"
    assert loaded[1].label == "run-2"


def test_load_ledger_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    assert load_ledger(path) == []


def test_season_metrics_rank_corr_delta():
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.40, "RB": 0.35, "WR": 0.30, "TE": 0.28},
        arm_b_rank_corr={"QB": 0.42, "RB": 0.37, "WR": 0.33, "TE": 0.30},
        arm_a_weekly_mae=7.0,
        arm_b_weekly_mae=6.8,
        arm_a_season_mae=2.5,
        arm_b_season_mae=2.3,
        arm_a_calibration=0.12,
        arm_b_calibration=0.10,
    )
    # avg delta = (0.02 + 0.02 + 0.03 + 0.02) / 4 = 0.0225
    assert abs(sm.rank_corr_delta - 0.0225) < 1e-6


def test_format_ledger_table_empty():
    result = format_ledger_table([])
    assert "No entries" in result


def test_format_ledger_table_with_entries():
    entry = _make_entry("baseline-v1")
    entry.overrides = ["usage.ngs.enabled=true"]
    table = format_ledger_table([entry])
    assert "baseline-v1" in table
    assert "bare" in table
    assert "usage.ngs.enabled=true" in table
