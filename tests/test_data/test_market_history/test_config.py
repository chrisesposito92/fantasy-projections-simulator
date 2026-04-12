"""Tests for market-history config loading."""

from fantasy_sim.data.market_history.config import load_market_history_config


def test_load_market_history_config_defaults_when_missing():
    cfg = load_market_history_config({})

    assert cfg.enabled is False
    assert cfg.data_dir is None
    assert cfg.positions == ("QB", "RB", "WR", "TE")
    assert cfg.weights == {
        "QB": 0.20,
        "RB": 0.15,
        "WR": 0.20,
        "TE": 0.15,
    }
    assert cfg.min_coverage_weeks == 1
    assert cfg.min_books == 2
    assert cfg.dispersion_scale == 3.0
    assert cfg.features.close_fpts is True
    assert cfg.features.open_fpts is True
    assert cfg.features.movement is True
    assert cfg.features.dispersion is True
    assert cfg.features.anytime_td is True


def test_load_market_history_config_reads_nested_values():
    cfg = load_market_history_config(
        {
            "market_history": {
                "enabled": True,
                "data_dir": "/tmp/market-history",
                "positions": ["QB", "WR", "TE"],
                "weights": {
                    "QB": 0.30,
                    "RB": 0.10,
                    "WR": 0.25,
                    "TE": 0.20,
                },
                "min_coverage_weeks": 2,
                "min_books": 3,
                "dispersion_scale": 4.5,
                "features": {
                    "close_fpts": True,
                    "open_fpts": False,
                    "movement": True,
                    "dispersion": False,
                    "anytime_td": True,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.data_dir == "/tmp/market-history"
    assert cfg.positions == ("QB", "WR", "TE")
    assert cfg.weights == {
        "QB": 0.30,
        "RB": 0.10,
        "WR": 0.25,
        "TE": 0.20,
    }
    assert cfg.min_coverage_weeks == 2
    assert cfg.min_books == 3
    assert cfg.dispersion_scale == 4.5
    assert cfg.features.close_fpts is True
    assert cfg.features.open_fpts is False
    assert cfg.features.movement is True
    assert cfg.features.dispersion is False
    assert cfg.features.anytime_td is True


def test_default_positions_all_have_default_weights():
    cfg = load_market_history_config({})
    assert all(position in cfg.weights for position in cfg.positions)
