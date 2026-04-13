"""Tests for tracking config loading."""

from fantasy_sim.config.loader import load_defaults
from fantasy_sim.data.tracking.config import load_tracking_config


def test_load_tracking_config_defaults_when_missing():
    cfg = load_tracking_config({})

    assert cfg.enabled is False
    assert cfg.window_weeks == 4
    assert cfg.receiver_participation.positions == ("WR", "TE")
    assert cfg.receiver_participation.enabled is True
    assert cfg.rb_efficiency.enabled is True
    assert cfg.qb_context.enabled is True


def test_load_tracking_config_matches_checked_in_defaults():
    cfg = load_tracking_config(load_defaults())

    assert cfg.enabled is False
    assert cfg.window_weeks == 4
    assert cfg.receiver_participation.enabled is True
    assert cfg.receiver_participation.positions == ("WR", "TE")
    assert cfg.receiver_participation.target_share_sensitivity == 0.18
    assert cfg.receiver_participation.air_yards_sensitivity == 0.12
    assert cfg.receiver_participation.catchable_target_sensitivity == 0.08
    assert cfg.receiver_participation.contested_target_sensitivity == -0.04
    assert cfg.receiver_participation.factor_clamp == (0.92, 1.08)
    assert cfg.receiver_participation.min_targets == 8
    assert cfg.rb_efficiency.enabled is True
    assert cfg.rb_efficiency.carry_share_sensitivity == 0.10
    assert cfg.rb_efficiency.rush_yards_sensitivity == 0.08
    assert cfg.rb_efficiency.factor_clamp == (0.93, 1.07)
    assert cfg.rb_efficiency.min_attempts == 12
    assert cfg.qb_context.enabled is True
    assert cfg.qb_context.pass_rate_sensitivity == 0.04
    assert cfg.qb_context.pace_sensitivity == 0.03
    assert cfg.qb_context.scramble_sensitivity == 0.06
    assert cfg.qb_context.sack_rate_sensitivity == 0.05
    assert cfg.qb_context.factor_clamp == (0.94, 1.06)
    assert cfg.qb_context.min_dropbacks == 20


def test_load_tracking_config_reads_nested_values():
    cfg = load_tracking_config(
        {
            "tracking": {
                "enabled": True,
                "window_weeks": 6,
                "receiver_participation": {
                    "enabled": False,
                    "positions": ["WR", "TE", "RB"],
                    "target_share_sensitivity": 0.22,
                    "air_yards_sensitivity": 0.14,
                    "catchable_target_sensitivity": 0.09,
                    "contested_target_sensitivity": -0.06,
                    "factor_clamp": [0.91, 1.09],
                    "min_targets": 10,
                },
                "rb_efficiency": {
                    "enabled": False,
                    "carry_share_sensitivity": 0.12,
                    "rush_yards_sensitivity": 0.09,
                    "factor_clamp": [0.92, 1.08],
                    "min_attempts": 14,
                },
                "qb_context": {
                    "enabled": False,
                    "pass_rate_sensitivity": 0.05,
                    "pace_sensitivity": 0.04,
                    "scramble_sensitivity": 0.07,
                    "sack_rate_sensitivity": 0.06,
                    "factor_clamp": [0.93, 1.07],
                    "min_dropbacks": 24,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.window_weeks == 6
    assert cfg.receiver_participation.enabled is False
    assert cfg.receiver_participation.positions == ("WR", "TE", "RB")
    assert cfg.receiver_participation.target_share_sensitivity == 0.22
    assert cfg.receiver_participation.air_yards_sensitivity == 0.14
    assert cfg.receiver_participation.catchable_target_sensitivity == 0.09
    assert cfg.receiver_participation.contested_target_sensitivity == -0.06
    assert cfg.receiver_participation.factor_clamp == (0.91, 1.09)
    assert cfg.receiver_participation.min_targets == 10
    assert cfg.rb_efficiency.enabled is False
    assert cfg.rb_efficiency.carry_share_sensitivity == 0.12
    assert cfg.rb_efficiency.rush_yards_sensitivity == 0.09
    assert cfg.rb_efficiency.factor_clamp == (0.92, 1.08)
    assert cfg.rb_efficiency.min_attempts == 14
    assert cfg.qb_context.enabled is False
    assert cfg.qb_context.pass_rate_sensitivity == 0.05
    assert cfg.qb_context.pace_sensitivity == 0.04
    assert cfg.qb_context.scramble_sensitivity == 0.07
    assert cfg.qb_context.sack_rate_sensitivity == 0.06
    assert cfg.qb_context.factor_clamp == (0.93, 1.07)
    assert cfg.qb_context.min_dropbacks == 24


def test_load_tracking_config_returns_independent_nested_objects():
    first = load_tracking_config({})
    second = load_tracking_config({})

    first.receiver_participation.enabled = False
    first.receiver_participation.min_targets = 99
    first.rb_efficiency.min_attempts = 42
    first.qb_context.pace_sensitivity = 0.11

    assert second.receiver_participation.enabled is True
    assert second.receiver_participation.min_targets == 8
    assert second.rb_efficiency.min_attempts == 12
    assert second.qb_context.pace_sensitivity == 0.03
