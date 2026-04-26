"""Tests for the Cycle-3 SeasonMetrics.stat_mean_bias schema bump."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fantasy_sim.validation.ledger import (
    CURRENT_LEDGER_SCHEMA_VERSION,
    LedgerEntry,
    SeasonMetrics,
    load_ledger,
    save_ledger,
)


def test_current_schema_version_is_5():
    assert CURRENT_LEDGER_SCHEMA_VERSION == 5


def test_season_metrics_default_stat_mean_bias_is_empty_dict():
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.5},
        arm_b_rank_corr={"QB": 0.55},
        arm_a_weekly_mae=5.0,
        arm_b_weekly_mae=4.8,
        arm_a_season_mae=20.0,
        arm_b_season_mae=19.5,
        arm_a_calibration=0.95,
        arm_b_calibration=0.96,
    )
    assert sm.stat_mean_bias == {}


def test_season_metrics_stat_mean_bias_round_trip():
    """Round-trip a SeasonMetrics with stat_mean_bias through save_ledger / load_ledger."""
    sm = SeasonMetrics(
        test_season=2024,
        arm_a_rank_corr={"QB": 0.5},
        arm_b_rank_corr={"QB": 0.55},
        arm_a_weekly_mae=5.0,
        arm_b_weekly_mae=4.8,
        arm_a_season_mae=20.0,
        arm_b_season_mae=19.5,
        arm_a_calibration=0.95,
        arm_b_calibration=0.96,
        stat_mean_bias={
            "QB": {
                "pass_yards": {
                    "arm_a_bias": -28.5,
                    "arm_b_bias": -8.2,
                    "bias_delta": 20.3,
                    "n": 540,
                }
            }
        },
    )
    entry = LedgerEntry(
        label="test.cycle3",
        timestamp="2026-04-26T00:00:00Z",
        sims=200,
        test_seasons=[2024],
        training_years=4,
        scoring="ppr",
        baseline="bare",
        overrides=[],
        config_snapshot={},
        season_results=[sm],
        schema_version=5,
    )
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        save_ledger(path, [entry])
        loaded = load_ledger(path)
    assert len(loaded) == 1
    assert (
        loaded[0].season_results[0].stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"]
        == -8.2
    )


def test_load_ledger_backward_compat_old_entry_without_stat_mean_bias():
    """Pre-v5 entries (no stat_mean_bias key) load with stat_mean_bias defaulted to empty dict."""
    old_entry_dict = {
        "label": "phase0.legacy",
        "timestamp": "2026-01-01T00:00:00Z",
        "sims": 200,
        "test_seasons": [2024],
        "training_years": 4,
        "scoring": "ppr",
        "baseline": "bare",
        "overrides": [],
        "config_snapshot": {},
        "season_results": [
            {
                "test_season": 2024,
                "arm_a_rank_corr": {"QB": 0.5},
                "arm_b_rank_corr": {"QB": 0.55},
                "arm_a_weekly_mae": 5.0,
                "arm_b_weekly_mae": 4.8,
                "arm_a_season_mae": 20.0,
                "arm_b_season_mae": 19.5,
                "arm_a_calibration": 0.95,
                "arm_b_calibration": 0.96,
                "weekly_fpts_ks": {},
                "stat_ks": {},
                # NOTE: no stat_mean_bias — pre-v5 entry
            }
        ],
        "schema_version": 4,
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "ledger.json"
        path.write_text(json.dumps([old_entry_dict]))
        loaded = load_ledger(path)
    assert len(loaded) == 1
    assert loaded[0].season_results[0].stat_mean_bias == {}
