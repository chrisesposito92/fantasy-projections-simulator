from fantasy_sim.data.role_trend.config import load_role_trend_config


def test_load_role_trend_config_defaults_disabled():
    cfg = load_role_trend_config({})

    assert cfg.enabled is False
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.window_weeks == 3
    assert cfg.factor_clamp == (0.90, 1.10)
    assert cfg.qb.sensitivity == 0.12
    assert cfg.wr.sensitivity == 0.10


def test_load_role_trend_config_reads_yaml_values():
    cfg = load_role_trend_config(
        {
            "role_trend": {
                "enabled": True,
                "positions": ["RB", "WR", "TE"],
                "window_weeks": 4,
                "factor_clamp": [0.92, 1.08],
                "rb": {"sensitivity": 0.08},
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.positions == ("RB", "WR", "TE")
    assert cfg.window_weeks == 4
    assert cfg.factor_clamp == (0.92, 1.08)
    assert cfg.rb.sensitivity == 0.08
