"""Tests for PFF config loading."""

import pytest

from fantasy_sim.data.pff.config import load_pff_config
from fantasy_sim.config.loader import load_defaults
from fantasy_sim.data.pff.models import (
    DepthRoleConfig,
    DepthRoleEfficiencyConfig,
    DepthRoleEfficiencyPositionConfig,
    DepthRolePositionConfig,
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


class TestPositionSpecificStrength:
    def test_scalar_prior_strength_still_works(self):
        cfg = load_pff_config({"pff": {"talent": {"prior_strength": 50.0}}})
        assert cfg.talent.prior_strength == 50.0

    def test_dict_prior_strength_loaded(self):
        cfg = load_pff_config({"pff": {"talent": {"prior_strength": {
            "QB": 60, "WR": 40, "TE": 35, "RB": 30, "default": 40,
        }}}})
        assert isinstance(cfg.talent.prior_strength, dict)
        assert cfg.talent.prior_strength["QB"] == 60

    def test_team_change_factor_loaded(self):
        cfg = load_pff_config({"pff": {"talent": {"team_change_factor": 0.5}}})
        assert cfg.talent.team_change_factor == 0.5


def test_load_pff_config_coverage():
    """Coverage config is loaded from defaults.yaml."""
    config = {
        "pff": {
            "enabled": True,
            "coverage": {
                "enabled": True,
                "catch_rate_sensitivity": 0.06,
                "ypr_sensitivity": 0.05,
                "min_coverage_targets": 30,
                "min_z_score_targets": 15,
                "min_z_score_population": 10,
                "factor_clamp": [0.93, 1.07],
                "min_games": 3,
            },
        }
    }
    pff = load_pff_config(config)
    assert pff.coverage.enabled is True
    assert pff.coverage.catch_rate_sensitivity == 0.06
    assert pff.coverage.ypr_sensitivity == 0.05
    assert pff.coverage.min_coverage_targets == 30
    assert pff.coverage.min_z_score_targets == 15
    assert pff.coverage.min_z_score_population == 10
    assert pff.coverage.factor_clamp == (0.93, 1.07)
    assert pff.coverage.min_games == 3


def test_load_pff_config_coverage_defaults():
    """Coverage config uses defaults when not specified in yaml."""
    config = {"pff": {"enabled": True}}
    pff = load_pff_config(config)
    assert pff.coverage.enabled is True
    assert pff.coverage.catch_rate_sensitivity == 0.04
    assert pff.coverage.factor_clamp == (0.97, 1.03)


def test_load_pff_config_depth_role_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    assert isinstance(cfg.depth_role, DepthRoleConfig)
    assert cfg.depth_role.enabled is False
    assert cfg.depth_role.positions == ("WR", "TE")
    assert cfg.depth_role.min_routes == 15
    assert cfg.depth_role.min_targets == 6
    assert cfg.depth_role.min_games == 4
    assert cfg.depth_role.early_season_blend is True
    assert cfg.depth_role.wr == DepthRolePositionConfig(
        target_share_sensitivity=0.10,
        air_yards_share_sensitivity=0.12,
        factor_clamp=(0.94, 1.06),
    )
    assert cfg.depth_role.te == DepthRolePositionConfig(
        target_share_sensitivity=0.08,
        air_yards_share_sensitivity=0.06,
        factor_clamp=(0.95, 1.05),
    )


def test_load_pff_config_depth_role_defaults_from_shipped_yaml():
    cfg = load_pff_config(load_defaults())

    assert isinstance(cfg.depth_role, DepthRoleConfig)
    assert cfg.depth_role.enabled is False
    assert cfg.depth_role.positions == ("WR", "TE")
    assert cfg.depth_role.min_routes == 15
    assert cfg.depth_role.min_targets == 6
    assert cfg.depth_role.min_games == 4
    assert cfg.depth_role.early_season_blend is True
    assert cfg.depth_role.wr == DepthRolePositionConfig(
        target_share_sensitivity=0.10,
        air_yards_share_sensitivity=0.12,
        factor_clamp=(0.94, 1.06),
    )
    assert cfg.depth_role.te == DepthRolePositionConfig(
        target_share_sensitivity=0.08,
        air_yards_share_sensitivity=0.06,
        factor_clamp=(0.95, 1.05),
    )


def test_load_pff_config_depth_role_efficiency_defaults_from_shipped_yaml():
    cfg = load_pff_config(load_defaults())

    eff = cfg.depth_role.efficiency
    assert isinstance(eff, DepthRoleEfficiencyConfig)
    assert eff.enabled is False
    assert eff.min_routes == 15
    assert eff.min_receptions == 6
    assert eff.min_games == 4
    assert eff.catch_rate_clamp == (0.94, 1.06)
    assert eff.yards_scale_clamp == (0.92, 1.08)
    assert eff.wr == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.08,
        yards_scale_sensitivity=0.10,
    )
    assert eff.te == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.06,
        yards_scale_sensitivity=0.08,
    )


def test_load_pff_config_depth_role_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "depth_role": {
                    "enabled": True,
                    "positions": ["WR"],
                    "min_routes": 22,
                    "min_targets": 9,
                    "min_games": 5,
                    "early_season_blend": False,
                    "wr": {
                        "target_share_sensitivity": 0.14,
                        "air_yards_share_sensitivity": 0.16,
                        "factor_clamp": [0.92, 1.08],
                    },
                    "te": {
                        "target_share_sensitivity": 0.07,
                        "air_yards_share_sensitivity": 0.05,
                        "factor_clamp": [0.96, 1.04],
                    },
                },
            }
        }
    )

    assert cfg.depth_role.enabled is True
    assert cfg.depth_role.positions == ("WR",)
    assert cfg.depth_role.min_routes == 22
    assert cfg.depth_role.min_targets == 9
    assert cfg.depth_role.min_games == 5
    assert cfg.depth_role.early_season_blend is False
    assert cfg.depth_role.wr.target_share_sensitivity == 0.14
    assert cfg.depth_role.wr.air_yards_share_sensitivity == 0.16
    assert cfg.depth_role.wr.factor_clamp == (0.92, 1.08)
    assert cfg.depth_role.te.target_share_sensitivity == 0.07
    assert cfg.depth_role.te.air_yards_share_sensitivity == 0.05
    assert cfg.depth_role.te.factor_clamp == (0.96, 1.04)


def test_load_pff_config_depth_role_efficiency_defaults():
    cfg = load_pff_config({"pff": {"enabled": True}})

    eff = cfg.depth_role.efficiency
    assert isinstance(eff, DepthRoleEfficiencyConfig)
    assert eff.enabled is False
    assert eff.min_routes == 15
    assert eff.min_receptions == 6
    assert eff.min_games == 4
    assert eff.catch_rate_clamp == (0.94, 1.06)
    assert eff.yards_scale_clamp == (0.92, 1.08)
    assert eff.wr == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.08,
        yards_scale_sensitivity=0.10,
    )
    assert eff.te == DepthRoleEfficiencyPositionConfig(
        catch_rate_sensitivity=0.06,
        yards_scale_sensitivity=0.08,
    )


def test_load_pff_config_depth_role_efficiency_custom_values():
    cfg = load_pff_config(
        {
            "pff": {
                "enabled": True,
                "depth_role": {
                    "efficiency": {
                        "enabled": True,
                        "min_routes": 18,
                        "min_receptions": 8,
                        "min_games": 5,
                        "catch_rate_clamp": [0.95, 1.05],
                        "yards_scale_clamp": [0.93, 1.07],
                        "wr": {
                            "catch_rate_sensitivity": 0.11,
                            "yards_scale_sensitivity": 0.13,
                        },
                        "te": {
                            "catch_rate_sensitivity": 0.09,
                            "yards_scale_sensitivity": 0.07,
                        },
                    }
                },
            }
        }
    )

    eff = cfg.depth_role.efficiency
    assert eff.enabled is True
    assert eff.min_routes == 18
    assert eff.min_receptions == 8
    assert eff.min_games == 5
    assert eff.catch_rate_clamp == (0.95, 1.05)
    assert eff.yards_scale_clamp == (0.93, 1.07)
    assert eff.wr.catch_rate_sensitivity == 0.11
    assert eff.wr.yards_scale_sensitivity == 0.13
    assert eff.te.catch_rate_sensitivity == 0.09
    assert eff.te.yards_scale_sensitivity == 0.07


def test_load_pff_config_depth_role_rejects_invalid_positions():
    with pytest.raises(ValueError, match="Invalid pff\\.depth_role\\.positions config"):
        load_pff_config(
            {
                "pff": {
                    "enabled": True,
                    "depth_role": {
                        "positions": ["WR", "QB"],
                    },
                }
            }
        )
