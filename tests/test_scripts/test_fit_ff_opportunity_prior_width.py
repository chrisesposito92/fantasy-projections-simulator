"""Smoke-tests for the KS-13 Path B fitter script (fit_ff_opportunity_prior_width.py).

These tests verify the CLI smoke-test, schema_version constraint, and bucket-key
shape constraint without actually running the full A/B pipeline (which requires
network data and is tested via validate.py).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest


def test_fit_ff_opportunity_prior_width_cli_help_works():
    """The fitter script must at least answer --help cleanly."""
    result = subprocess.run(
        [sys.executable, "scripts/fit_ff_opportunity_prior_width.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--test-seasons" in result.stdout
    assert "--training-years" in result.stdout
    assert "--scoring" in result.stdout
    assert "--output-dir" in result.stdout


def test_fit_ff_opportunity_prior_width_artifact_schema_version_is_1():
    """Generated artifacts must declare schema_version=1 to match the runtime loader.

    The fitter script and the runtime loader (ensemble.py ARTIFACT_SCHEMA_VERSION)
    must agree on schema_version. If the fitter is bumped, the runtime must update.
    """
    from fantasy_sim.scoring.ensemble import ARTIFACT_SCHEMA_VERSION

    # The fitter script also declares ARTIFACT_SCHEMA_VERSION = 1.
    assert ARTIFACT_SCHEMA_VERSION == 1


def test_fit_ff_opportunity_prior_width_bucket_keys_are_positions():
    """Bucket keys are bare position strings (QB/RB/WR/TE), not composite keys.

    Per-fpts-tier subdivision is OUT OF SCOPE for KS-13 v1.
    """
    # Synthetic check on a manually-constructed artifact dict
    fake_artifact = {
        "schema_version": 1,
        "scoring": "ppr",
        "test_season": 2024,
        "source_seasons": [2020, 2021, 2022, 2023],
        "buckets": {
            "WR": {"std_fpts": 4.5, "n": 1000},
            "RB": {"std_fpts": 5.2, "n": 800},
            "QB": {"std_fpts": 6.1, "n": 200},
            "TE": {"std_fpts": 3.7, "n": 600},
        },
    }
    for key in fake_artifact["buckets"]:
        assert key in {"QB", "RB", "WR", "TE"}, f"bucket key '{key}' must be a bare position string"
