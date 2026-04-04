"""Tests for the PFF team context engine."""

import pytest
import numpy as np

from fantasy_sim.data.pff.models import TeamContext, TeamContextConfig


class TestTeamContextDataModel:
    def test_team_context_defaults(self):
        """All factors default to 1.0 (neutral), scale defaults to 10.0."""
        ctx = TeamContext()
        assert ctx.pass_rate_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0
        assert ctx.qb_quality_factor == 1.0
        assert ctx.ol_run_yards_scale == 10.0

    def test_team_context_custom_values(self):
        """TeamContext can be constructed with custom factor values."""
        ctx = TeamContext(
            pass_rate_factor=1.08,
            ol_run_block_factor=0.94,
            qb_quality_factor=1.05,
            ol_run_yards_scale=12.0,
        )
        assert ctx.pass_rate_factor == 1.08
        assert ctx.ol_run_block_factor == 0.94
        assert ctx.qb_quality_factor == 1.05
        assert ctx.ol_run_yards_scale == 12.0

    def test_team_context_config_defaults(self):
        """TeamContextConfig has correct default values."""
        cfg = TeamContextConfig()
        assert cfg.enabled is True
        assert cfg.pass_rate_sensitivity == 0.08
        assert cfg.ol_run_sensitivity == 0.06
        assert cfg.qb_quality_sensitivity == 0.05
        assert cfg.factor_clamp == (0.90, 1.10)
        assert cfg.min_games == 4
        assert cfg.ol_run_yards_scale == 10.0

    def test_team_context_config_custom(self):
        """TeamContextConfig can be constructed with custom values."""
        cfg = TeamContextConfig(
            enabled=False,
            pass_rate_sensitivity=0.10,
            factor_clamp=(0.85, 1.15),
        )
        assert cfg.enabled is False
        assert cfg.pass_rate_sensitivity == 0.10
        assert cfg.factor_clamp == (0.85, 1.15)
