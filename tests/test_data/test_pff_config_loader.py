"""Tests for PFF config loader — kicker and DST baseline parsing."""
from fantasy_sim.data.pff.config import load_pff_config


def test_load_pff_config_parses_kicker():
    config = {
        "pff": {
            "enabled": True,
            "kicker": {
                "enabled": True,
                "prior_strength": 25,
                "min_attempts": 8,
            },
        },
    }
    result = load_pff_config(config)
    assert result.kicker.enabled is True
    assert result.kicker.prior_strength == 25
    assert result.kicker.min_attempts == 8


def test_load_pff_config_parses_dst_baseline():
    config = {
        "pff": {
            "enabled": True,
            "dst_baseline": {
                "enabled": True,
                "sensitivities": {"fumble_rate": 0.08},
                "prior_strength": 15,
                "min_games": 5,
                "clamp": [0.80, 1.20],
            },
        },
    }
    result = load_pff_config(config)
    assert result.dst_baseline.enabled is True
    assert result.dst_baseline.sensitivities == {"fumble_rate": 0.08}
    assert result.dst_baseline.prior_strength == 15
    assert result.dst_baseline.min_games == 5
    assert result.dst_baseline.clamp == [0.80, 1.20]


def test_load_pff_config_kicker_dst_defaults_when_missing():
    """When kicker/dst_baseline sections are absent, defaults are used."""
    config = {"pff": {"enabled": True}}
    result = load_pff_config(config)
    assert result.kicker.enabled is True
    assert result.dst_baseline.enabled is True
