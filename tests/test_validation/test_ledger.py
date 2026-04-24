"""Tests for unified A/B validation ledger."""
import json

from fantasy_sim.validation.coverage import SignalCoverage
from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    LedgerEntry,
    SeasonMetrics,
    format_ledger_table,
    load_ledger,
    save_ledger,
)


def _make_entry(label: str = "test-run") -> LedgerEntry:
    """Create a minimal LedgerEntry for testing."""
    return LedgerEntry(
        schema_version=CURRENT_LEDGER_SCHEMA_VERSION,
        label=label,
        timestamp="2026-04-08T12:00:00",
        sims=50,
        test_seasons=[2022, 2023, 2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        comparison_mode="total_lift",
        overrides=[],
        seed_mode="deterministic_game_id_crc32_shared_between_arms",
        coverage_summary={
            "props": SignalCoverage(
                enabled=True,
                status="full",
                covered_seasons=[2022, 2023, 2024],
                missing_seasons=[],
                note=None,
            )
        },
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
                weekly_fpts_ks={
                    "arm_a_ks": 0.22,
                    "arm_b_ks": 0.18,
                    "ks_delta": -0.04,
                    "n": 100,
                },
                stat_ks={
                    "WR": {
                        "receiving_yards": {
                            "arm_a_ks": 0.21,
                            "arm_b_ks": 0.18,
                            "ks_delta": -0.03,
                            "arm_a_mean": 40.0,
                            "arm_b_mean": 38.2,
                            "actual_mean": 47.9,
                            "mean_delta_a": -7.9,
                            "mean_delta_b": -9.7,
                            "n": 25,
                        }
                    }
                },
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
    assert loaded[0].season_results[0].weekly_fpts_ks["ks_delta"] == -0.04
    assert loaded[0].season_results[0].stat_ks["WR"]["receiving_yards"]["n"] == 25


def test_load_ledger_missing_file(tmp_path):
    path = tmp_path / "nonexistent.json"
    assert load_ledger(path) == []


def test_load_legacy_ledger_entry_uses_safe_defaults(tmp_path):
    path = tmp_path / "legacy_ledger.json"
    path.write_text(
        json.dumps(
            [
                {
                    "label": "legacy-run",
                    "timestamp": "2026-04-08T12:00:00",
                    "sims": 10,
                    "test_seasons": [2024],
                    "training_years": 4,
                    "scoring": "ppr",
                    "baseline": "bare",
                    "overrides": [],
                    "config_snapshot": {},
                    "season_results": [
                        {
                            "test_season": 2024,
                            "arm_a_rank_corr": {"QB": 0.40},
                            "arm_b_rank_corr": {"QB": 0.42},
                            "arm_a_weekly_mae": 7.0,
                            "arm_b_weekly_mae": 6.8,
                            "arm_a_season_mae": 2.5,
                            "arm_b_season_mae": 2.3,
                            "arm_a_calibration": 0.12,
                            "arm_b_calibration": 0.10,
                        }
                    ],
                }
            ]
        )
    )

    entry = load_ledger(path)[0]
    assert entry.schema_version is None
    assert entry.comparison_mode is None
    assert entry.seed_mode is None
    assert entry.coverage_summary is None
    assert entry.season_results[0].weekly_fpts_ks == {}
    assert entry.season_results[0].stat_ks == {}


def test_load_ledger_normalizes_old_weekly_fpts_ks_keys(tmp_path):
    path = tmp_path / "legacy_ks_ledger.json"
    path.write_text(
        json.dumps(
            [
                {
                    "label": "legacy-ks-run",
                    "timestamp": "2026-04-08T12:00:00",
                    "sims": 10,
                    "test_seasons": [2024],
                    "training_years": 4,
                    "scoring": "ppr",
                    "baseline": "bare",
                    "overrides": [],
                    "config_snapshot": {},
                    "season_results": [
                        {
                            "test_season": 2024,
                            "arm_a_rank_corr": {},
                            "arm_b_rank_corr": {},
                            "arm_a_weekly_mae": 7.0,
                            "arm_b_weekly_mae": 6.8,
                            "arm_a_season_mae": 2.5,
                            "arm_b_season_mae": 2.3,
                            "arm_a_calibration": 0.12,
                            "arm_b_calibration": 0.10,
                            "weekly_fpts_ks": {
                                "arm_a": 0.22,
                                "arm_b": 0.18,
                                "delta": -0.04,
                                "n": 100,
                            },
                        }
                    ],
                }
            ]
        )
    )

    entry = load_ledger(path)[0]
    assert entry.season_results[0].weekly_fpts_ks == {
        "arm_a_ks": 0.22,
        "arm_b_ks": 0.18,
        "ks_delta": -0.04,
        "n": 100,
    }


def test_format_ledger_table_renders_legacy_for_old_entries(tmp_path):
    path = tmp_path / "legacy_ledger.json"
    path.write_text(
        json.dumps(
            [
                {
                    "label": "legacy-run",
                    "timestamp": "2026-04-08T12:00:00",
                    "sims": 10,
                    "test_seasons": [2024],
                    "training_years": 4,
                    "scoring": "ppr",
                    "baseline": "bare",
                    "overrides": [],
                    "config_snapshot": {},
                    "season_results": [],
                }
            ]
        )
    )

    table = format_ledger_table(load_ledger(path))
    assert "legacy-run" in table
    assert "legacy" in table
    assert "n/a" in table


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
    assert "total_lift" in table
    assert "usage.ngs.enabled=true" in table
    assert "fpts_ks" in table
    assert "-0.040" in table


def test_ledger_roundtrip_preserves_promotion_evidence_scope(tmp_path):
    path = tmp_path / "test_ledger.json"
    entry = _make_entry("phase-3-market-history-v1")
    entry.promotion_evidence_scope = "covered_only"

    save_ledger(path, [entry])
    loaded = load_ledger(path)

    assert loaded[0].promotion_evidence_scope == "covered_only"
