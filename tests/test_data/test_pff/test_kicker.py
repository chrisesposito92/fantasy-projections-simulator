"""Tests for PFF kicker engine — per-kicker accuracy with Bayesian shrinkage."""

import polars as pl
import pytest

from fantasy_sim.data.pff.models import KickerConfig, PffConfig


class TestKickerConfig:
    def test_default_values(self):
        cfg = KickerConfig()
        assert cfg.enabled is True
        assert cfg.prior_strength == 20
        assert cfg.min_attempts == 5

    def test_pff_config_has_kicker(self):
        pff = PffConfig()
        assert hasattr(pff, "kicker")
        assert isinstance(pff.kicker, KickerConfig)
