"""Stub test file for VegasEngine integration tests.

Wave 0 scaffold -- real test methods are written by Plan 02-02
during TDD.
"""
import pytest


class TestApplyVegas:
    """Tests for GameContextBuilder._apply_vegas() direct calls."""
    pass


class TestVegasIntegration:
    """Tests for build_game() with Vegas enabled vs disabled."""
    pass


class TestABHarnessVegasModes:
    """Tests for A/B harness mode routing (vegas, vegas+spread)."""
    pass


class TestVegasConfigPropagation:
    """Tests for vegas_config threading through Backtester and parallel workers."""
    pass
