"""Tests for game script config loading."""

from fantasy_sim.data.game_script import GameScriptConfig, load_game_script_config


def test_load_game_script_config_missing_key_returns_disabled_defaults():
    config = load_game_script_config({})

    assert config == GameScriptConfig(enabled=False)
    assert config.trailing_late.deficit_threshold == 8
    assert config.leading_late_rb.lead_threshold == 14


def test_load_game_script_config_reads_nested_values():
    raw = {
        "game_script": {
            "enabled": True,
            "trailing_late": {
                "enabled": True,
                "deficit_threshold": 10,
                "final_five_minutes": 240,
                "final_five_deficit_threshold": 5,
                "pass_rate_prior_strength": 180.0,
                "pace_prior_strength": 210.0,
                "target_prior_strength": 70.0,
                "pass_rate_clamp": [1.02, 1.28],
                "pace_factor_clamp": [1.01, 1.18],
                "target_rank_factor_clamp": [0.9, 1.2],
            },
            "leading_late_rb": {
                "enabled": True,
                "lead_threshold": 17,
                "late_minutes": 540,
                "rb_carry_prior_strength": 120.0,
                "rb_rank_factor_clamp": [0.82, 1.16],
            },
        }
    }

    config = load_game_script_config(raw)

    assert config.enabled is True
    assert config.trailing_late.enabled is True
    assert config.trailing_late.deficit_threshold == 10
    assert config.trailing_late.final_five_minutes == 240
    assert config.trailing_late.final_five_deficit_threshold == 5
    assert config.trailing_late.pass_rate_prior_strength == 180.0
    assert config.trailing_late.pace_prior_strength == 210.0
    assert config.trailing_late.target_prior_strength == 70.0
    assert config.trailing_late.pass_rate_clamp == (1.02, 1.28)
    assert config.trailing_late.pace_factor_clamp == (1.01, 1.18)
    assert config.trailing_late.target_rank_factor_clamp == (0.9, 1.2)
    assert config.leading_late_rb.enabled is True
    assert config.leading_late_rb.lead_threshold == 17
    assert config.leading_late_rb.late_minutes == 540
    assert config.leading_late_rb.rb_carry_prior_strength == 120.0
    assert config.leading_late_rb.rb_rank_factor_clamp == (0.82, 1.16)
