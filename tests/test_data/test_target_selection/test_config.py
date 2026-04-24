import pytest

from fantasy_sim.data.target_selection import load_target_selection_config


def test_missing_config_is_disabled():
    config = load_target_selection_config({})

    assert config.enabled is False


def test_loads_enabled_config_values():
    config = load_target_selection_config(
        {
            "target_selection": {
                "enabled": True,
                "artifacts_dir": "results/target_selection/test",
                "positions": ["WR", "TE"],
                "probability_floor": 0.002,
                "max_logit_delta": 2.5,
                "fallback": "legacy",
            }
        }
    )

    assert config.enabled is True
    assert config.artifacts_dir == "results/target_selection/test"
    assert config.positions == ("WR", "TE")
    assert config.probability_floor == 0.002
    assert config.max_logit_delta == 2.5
    assert config.fallback == "legacy"


def test_invalid_position_raises():
    with pytest.raises(ValueError, match="target_selection\\.positions"):
        load_target_selection_config(
            {"target_selection": {"enabled": True, "positions": ["QB"]}}
        )


def test_invalid_fallback_raises():
    with pytest.raises(ValueError, match="target_selection\\.fallback"):
        load_target_selection_config(
            {"target_selection": {"enabled": True, "fallback": "uniform"}}
        )
