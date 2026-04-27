"""Tests for KS-09 corrected_<stat> routing through scripts/validate.py.

Codex review HIGH 1 (2026-04-27): KS-09 writes corrected_<stat> columns but the
ledger metric (stat_ks / stat_mean_bias) is computed by scripts/validate.py
::_compute_distribution_ks, which historically reads raw <stat>. Plan 03 Task 3
adds corrected-routing gated on phase2_ks_flags.ks09_per_stat_residual_calibration.
These tests exercise the routing decision in isolation.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
_SCRIPTS = str(Path(__file__).resolve().parents[2] / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def test_ks09_validate_routes_corrected_stat_when_flag_on(monkeypatch):
    """When phase2_ks_flags.ks09_per_stat_residual_calibration.enabled=true, validate.py reads
    corrected_<stat> instead of raw <stat> for stat_ks / stat_mean_bias.

    THIS IS THE LOAD-BEARING TEST for the codex HIGH 1 finding. Without this test, KS-09 could
    write corrected_<stat> columns without those columns ever flowing into the ledger metric
    Phase 2 promotes against (the observability-only failure mode).
    """
    import validate  # type: ignore[import]

    # Build minimal arm_a / arm_b inputs where corrected_<stat> != <stat>
    arm_a_rows = {"p1": {1: {"fpts": 16.0, "pass_yards": 240.0}}}
    arm_b_rows = {"p1": {1: {"fpts": 15.5, "pass_yards": 240.0, "corrected_pass_yards": 230.0}}}

    class _Actual:
        fpts = 18.0
        pass_yards = 250.0

    actual_pos = {"p1": "QB"}
    actual_by_pw = {"p1": {1: _Actual()}}

    # Flag ON → validate.py should read corrected_pass_yards (= 230.0), not raw (= 240.0)
    monkeypatch.setattr(
        "fantasy_sim.config.loader.get_phase2_ks_flags",
        lambda: {"ks09_per_stat_residual_calibration": {"enabled": True}},
    )
    weekly_fpts_ks, stat_ks, stat_mean_bias = validate._compute_distribution_ks(
        arm_a_rows, arm_b_rows, actual_by_pw, actual_pos, positions=["QB"]
    )
    # arm_b mean = 230.0 (corrected); actual = 250.0; bias = 230 - 250 = -20.0
    assert "QB" in stat_mean_bias
    assert "pass_yards" in stat_mean_bias["QB"]
    assert math.isclose(stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"], -20.0, abs_tol=0.5)


def test_ks09_validate_routes_raw_stat_when_flag_off(monkeypatch):
    """When the KS-09 flag is OFF, validate.py reads raw <stat> exactly as legacy (byte-identical).

    This is the rollback safety net: even if corrected_<stat> columns leak into projection rows
    (e.g. stale cache), validate.py MUST behave as pre-Plan-03 when the flag is false.
    """
    import validate  # type: ignore[import]

    arm_a_rows = {"p1": {1: {"fpts": 16.0, "pass_yards": 240.0}}}
    # Note: corrected_pass_yards is present but should be IGNORED when flag off
    arm_b_rows = {"p1": {1: {"fpts": 15.5, "pass_yards": 240.0, "corrected_pass_yards": 230.0}}}

    class _Actual:
        fpts = 18.0
        pass_yards = 250.0

    actual_pos = {"p1": "QB"}
    actual_by_pw = {"p1": {1: _Actual()}}

    # Flag OFF → validate.py reads raw pass_yards (= 240.0)
    monkeypatch.setattr(
        "fantasy_sim.config.loader.get_phase2_ks_flags",
        lambda: {"ks09_per_stat_residual_calibration": {"enabled": False}},
    )
    weekly_fpts_ks, stat_ks, stat_mean_bias = validate._compute_distribution_ks(
        arm_a_rows, arm_b_rows, actual_by_pw, actual_pos, positions=["QB"]
    )
    # arm_b mean = 240.0 (raw); actual = 250.0; bias = 240 - 250 = -10.0
    assert "QB" in stat_mean_bias
    assert "pass_yards" in stat_mean_bias["QB"]
    assert math.isclose(stat_mean_bias["QB"]["pass_yards"]["arm_b_bias"], -10.0, abs_tol=0.5)
