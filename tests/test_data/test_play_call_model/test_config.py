import pytest

from fantasy_sim.data.play_call_model import load_play_call_model_config


def test_missing_config_is_disabled():
    config = load_play_call_model_config({})

    assert config.enabled is False
    assert config.artifacts_dir is None
    assert config.probability_clamp == (0.05, 0.95)
    assert config.fallback == "empirical"


def test_loads_enabled_config_values():
    config = load_play_call_model_config(
        {
            "play_call_model": {
                "enabled": True,
                "artifacts_dir": "results/play_call_model/test",
                "probability_clamp": [0.10, 0.90],
                "fallback": "empirical",
            }
        }
    )

    assert config.enabled is True
    assert config.artifacts_dir == "results/play_call_model/test"
    assert config.probability_clamp == (0.10, 0.90)
    assert config.fallback == "empirical"


@pytest.mark.parametrize(
    "clamp",
    [
        [0.10],
        [0.90, 0.10],
        [-0.01, 0.90],
        [0.10, 1.01],
    ],
)
def test_invalid_probability_clamp_raises(clamp):
    with pytest.raises(ValueError, match="play_call_model\\.probability_clamp"):
        load_play_call_model_config(
            {"play_call_model": {"enabled": True, "probability_clamp": clamp}}
        )


def test_invalid_fallback_raises():
    with pytest.raises(ValueError, match="play_call_model\\.fallback"):
        load_play_call_model_config(
            {"play_call_model": {"enabled": True, "fallback": "neutral"}}
        )
