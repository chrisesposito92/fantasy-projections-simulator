"""Tests for market-history config loading."""

from pathlib import Path

import yaml

from fantasy_sim.data.market_history.config import load_market_history_config
from fantasy_sim.data.market_history.models import (
    MarketHistoryConfig,
    MarketHistoryFeatureFlags,
)


def _load_defaults_yaml() -> dict:
    defaults_path = Path(__file__).resolve().parents[3] / "config" / "defaults.yaml"
    return yaml.safe_load(defaults_path.read_text())


def test_load_market_history_config_defaults_when_missing():
    cfg = load_market_history_config({})

    assert cfg.enabled is False
    assert cfg.data_dir is None
    assert cfg.snapshot_label == "close_core8"
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


def test_load_market_history_config_defaults_are_isolated_between_calls():
    first = load_market_history_config({})
    second = load_market_history_config({})

    first.weights["QB"] = 0.99
    first.features.open_fpts = False

    assert second.weights["QB"] == 0.20
    assert second.features.open_fpts is True
    assert first.weights is not second.weights
    assert first.features is not second.features


def test_load_market_history_config_matches_checked_in_defaults():
    cfg = load_market_history_config(_load_defaults_yaml())

    assert cfg == MarketHistoryConfig()
    assert cfg.features == MarketHistoryFeatureFlags()


def test_load_market_history_config_reads_nested_values():
    cfg = load_market_history_config(
        {
            "market_history": {
                "enabled": True,
                "data_dir": "/tmp/market-history",
                "snapshot_label": "close_core8",
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
    assert cfg.snapshot_label == "close_core8"
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


def test_load_market_history_config_uses_default_data_dir_when_missing():
    cfg = load_market_history_config(
        {
            "market_history": {
                "enabled": True,
            }
        }
    )

    assert cfg.data_dir is None


def test_load_market_history_config_partial_feature_override_keeps_other_defaults():
    cfg = load_market_history_config(
        {
            "market_history": {
                "features": {
                    "open_fpts": False,
                }
            }
        }
    )

    assert cfg.features.close_fpts is True
    assert cfg.features.open_fpts is False
    assert cfg.features.movement is True
    assert cfg.features.dispersion is True
    assert cfg.features.anytime_td is True


def test_default_positions_all_have_default_weights():
    cfg = load_market_history_config({})
    assert all(position in cfg.weights for position in cfg.positions)
