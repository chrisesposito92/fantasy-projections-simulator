from fantasy_sim.data.availability.config import load_availability_config


def test_load_availability_config_defaults_disabled():
    cfg = load_availability_config({})

    assert cfg.enabled is False
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.injuries.enabled is True
    assert cfg.depth_charts.enabled is True
    assert cfg.usage_fallback.enabled is True
    assert cfg.usage_fallback.min_factor == 0.85
    assert cfg.usage_fallback.qb_low_usage_factor == 0.92


def test_load_availability_config_reads_yaml_values():
    cfg = load_availability_config(
        {
            "availability": {
                "enabled": True,
                "positions": ["QB", "WR"],
                "injuries": {"enabled": True, "hard_out_statuses": ["Out", "Doubtful"]},
                "depth_charts": {"enabled": True, "starter_slots": {"QB": "QB1"}},
                "usage_fallback": {
                    "enabled": True,
                    "lookback_weeks": 3,
                    "min_factor": 0.90,
                    "qb_low_usage_factor": 0.95,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.positions == ("QB", "WR")
    assert cfg.injuries.hard_out_statuses == ("Out", "Doubtful")
    assert cfg.depth_charts.starter_slots["QB"] == "QB1"
    assert cfg.usage_fallback.lookback_weeks == 3
    assert cfg.usage_fallback.min_factor == 0.90
