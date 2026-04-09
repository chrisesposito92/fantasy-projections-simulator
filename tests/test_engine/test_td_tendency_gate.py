"""Tests for player-level TD tendency gate modification."""

import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import _red_zone_td_gate


class TestRedZoneTdGateWithFactor:
    """Verify _red_zone_td_gate accepts and applies td_factor."""

    def test_default_factor_preserves_behavior(self):
        """Factor=1.0 (default) should not change gate probability."""
        rng = np.random.default_rng(42)
        results_default = [_red_zone_td_gate(5, "pass", rng) for _ in range(1000)]
        rng2 = np.random.default_rng(42)
        results_explicit = [_red_zone_td_gate(5, "pass", rng2, td_factor=1.0) for _ in range(1000)]
        assert results_default == results_explicit

    def test_high_factor_increases_td_rate(self):
        """Factor > 1.0 should increase TD conversion rate."""
        n = 5000
        rng_a = np.random.default_rng(123)
        rng_b = np.random.default_rng(456)
        base_tds = sum(_red_zone_td_gate(5, "pass", rng_a, td_factor=1.0) for _ in range(n))
        high_tds = sum(_red_zone_td_gate(5, "pass", rng_b, td_factor=1.3) for _ in range(n))
        assert high_tds > base_tds

    def test_low_factor_decreases_td_rate(self):
        """Factor < 1.0 should decrease TD conversion rate."""
        n = 5000
        rng_a = np.random.default_rng(123)
        rng_b = np.random.default_rng(456)
        base_tds = sum(_red_zone_td_gate(5, "pass", rng_a, td_factor=1.0) for _ in range(n))
        low_tds = sum(_red_zone_td_gate(5, "pass", rng_b, td_factor=0.7) for _ in range(n))
        assert low_tds < base_tds

    def test_factor_clamped_to_max_probability_1(self):
        """Even with very high factor, probability never exceeds 1.0."""
        rng = np.random.default_rng(42)
        results = [_red_zone_td_gate(1, "pass", rng, td_factor=3.0) for _ in range(100)]
        assert all(results), "With clamped prob=1.0, all should be True"

    def test_factor_applies_to_run_gate(self):
        """Factor also works for run plays."""
        n = 5000
        rng_a = np.random.default_rng(789)
        rng_b = np.random.default_rng(101)
        base_tds = sum(_red_zone_td_gate(5, "run", rng_a, td_factor=1.0) for _ in range(n))
        high_tds = sum(_red_zone_td_gate(5, "run", rng_b, td_factor=1.3) for _ in range(n))
        assert high_tds > base_tds

    def test_outside_red_zone_ignores_factor(self):
        """Outside the red zone (yard_line > 20), always returns True regardless of factor."""
        rng = np.random.default_rng(42)
        assert _red_zone_td_gate(25, "pass", rng, td_factor=0.01) is True
        assert _red_zone_td_gate(50, "run", rng, td_factor=0.01) is True
