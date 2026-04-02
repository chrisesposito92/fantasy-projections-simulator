"""Tests for PFF config loading."""

import pytest

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.data.pff.models import (
    MatchupConfig,
    MatchupContext,
    PffConfig,
    TalentConfig,
)


class TestMatchupContext:
    def test_defaults_are_neutral(self):
        ctx = MatchupContext()
        assert ctx.catch_rate_factor == 1.0
        assert ctx.pass_yards_factor == 1.0
        assert ctx.sack_rate_factor == 1.0
        assert ctx.int_rate_factor == 1.0
        assert ctx.rush_yards_factor == 1.0
        assert ctx.ol_pass_block_factor == 1.0
        assert ctx.ol_run_block_factor == 1.0


class TestPffConfig:
    def test_defaults_when_no_pff_section(self):
        cfg = load_pff_config({})
        assert cfg.enabled is False
        assert cfg.matchup.enabled is True
        assert cfg.talent.enabled is True

    def test_loads_enabled_flag(self):
        cfg = load_pff_config({"pff": {"enabled": True}})
        assert cfg.enabled is True

    def test_loads_matchup_sensitivity(self):
        cfg = load_pff_config({
            "pff": {
                "enabled": True,
                "matchup": {"pass_defense_sensitivity": 0.12},
            }
        })
        assert cfg.matchup.pass_defense_sensitivity == 0.12
        assert cfg.matchup.pass_rush_sensitivity == 0.10

    def test_loads_talent_prior_strength(self):
        cfg = load_pff_config({
            "pff": {
                "enabled": True,
                "talent": {"prior_strength": 60.0},
            }
        })
        assert cfg.talent.prior_strength == 60.0

    def test_loads_factor_clamp_as_tuple(self):
        cfg = load_pff_config({
            "pff": {
                "matchup": {"factor_clamp": [0.75, 1.25]},
            }
        })
        assert cfg.matchup.factor_clamp == (0.75, 1.25)

    def test_loads_custom_coefficients(self):
        cfg = load_pff_config({
            "pff": {
                "talent": {
                    "catch_rate_coefficients": {"drop_rate": -0.20},
                }
            }
        })
        assert cfg.talent.catch_rate_coefficients["drop_rate"] == -0.20

    def test_data_dir_default_none(self):
        cfg = load_pff_config({"pff": {"enabled": True}})
        assert cfg.data_dir is None

    def test_data_dir_custom(self):
        cfg = load_pff_config({"pff": {"data_dir": "/tmp/pff"}})
        assert cfg.data_dir == "/tmp/pff"

    def test_min_games_default(self):
        cfg = load_pff_config({"pff": {}})
        assert cfg.matchup.min_games == 4
