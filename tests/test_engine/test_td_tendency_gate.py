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


class TestI5GateFactorSelection:
    """Verify i5_rushing_td_factor is used at yard_line <= 5."""

    def test_i5_factor_used_at_yard_line_3(self):
        """At yard_line=3, i5 factor should produce different TD rate."""
        n = 5000
        import numpy as np

        td_count_i5 = sum(
            _red_zone_td_gate(3, "run", np.random.default_rng(i), 1.3)
            for i in range(n)
        )
        td_count_general = sum(
            _red_zone_td_gate(3, "run", np.random.default_rng(i), 0.7)
            for i in range(n)
        )
        assert td_count_i5 > td_count_general

    def test_i5_factor_used_at_yard_line_5(self):
        """At yard_line=5, i5 factor should still be used (boundary)."""
        n = 5000
        import numpy as np

        td_count_high = sum(
            _red_zone_td_gate(5, "run", np.random.default_rng(i), 1.3)
            for i in range(n)
        )
        td_count_low = sum(
            _red_zone_td_gate(5, "run", np.random.default_rng(i + n), 0.7)
            for i in range(n)
        )
        assert td_count_high > td_count_low

    def test_general_factor_used_at_yard_line_10(self):
        """At yard_line=10, general rushing_td_factor is always used (outside i5)."""
        n = 5000
        import numpy as np

        td_count = sum(
            _red_zone_td_gate(10, "run", np.random.default_rng(i), 1.0)
            for i in range(n)
        )
        # RUN_TD_GATE for (6,10) is 0.20, so ~1000/5000 expected
        assert 500 < td_count < 1500
