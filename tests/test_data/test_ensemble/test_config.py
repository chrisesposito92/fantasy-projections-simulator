"""Tests for ensemble config loading."""

from fantasy_sim.data.ensemble.config import load_ensemble_config


def test_load_ensemble_config_defaults_when_missing():
    cfg = load_ensemble_config({})

    assert cfg.enabled is False
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_rankings.enabled is False
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.positions == ("QB", "WR")
    assert cfg.ff_opportunity.weights == {"QB": 0.35, "WR": 0.25}


def test_load_ensemble_config_reads_nested_values():
    cfg = load_ensemble_config(
        {
            "ensemble": {
                "enabled": True,
                "ff_opportunity": {
                    "enabled": True,
                    "cache_dir": "/tmp/ff-opportunity",
                    "positions": ["QB", "WR", "TE"],
                    "feature": "fantasy_points_exp",
                    "weights": {
                        "QB": 0.4,
                        "WR": 0.3,
                        "RB": 0.2,
                        "TE": 0.1,
                    },
                    "min_coverage_weeks": 3,
                },
                "ff_rankings": {
                    "enabled": True,
                },
            }
        }
    )

    assert cfg.enabled is True
    assert cfg.ff_opportunity.enabled is True
    assert cfg.ff_opportunity.cache_dir == "/tmp/ff-opportunity"
    assert cfg.ff_opportunity.positions == ("QB", "WR", "TE")
    assert cfg.ff_opportunity.feature == "fantasy_points_exp"
    assert cfg.ff_opportunity.weights == {
        "QB": 0.4,
        "WR": 0.3,
        "RB": 0.2,
        "TE": 0.1,
    }
    assert cfg.ff_opportunity.min_coverage_weeks == 3
    assert cfg.ff_rankings.enabled is True


def test_load_ensemble_config_top_level_enabled_with_nested_sections_omitted():
    cfg = load_ensemble_config({"ensemble": {"enabled": True}})

    assert cfg.enabled is True
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_opportunity.cache_dir is None
    assert cfg.ff_opportunity.positions == ("QB", "WR")
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.weights == {"QB": 0.35, "WR": 0.25}
    assert cfg.ff_opportunity.min_coverage_weeks == 1
    assert cfg.ff_rankings.enabled is False


def test_load_ensemble_config_partial_ff_opportunity_override_uses_fallbacks():
    cfg = load_ensemble_config(
        {
            "ensemble": {
                "ff_opportunity": {
                    "min_coverage_weeks": 4,
                }
            }
        }
    )

    assert cfg.enabled is False
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_opportunity.cache_dir is None
    assert cfg.ff_opportunity.positions == ("QB", "WR")
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.weights == {"QB": 0.35, "WR": 0.25}
    assert cfg.ff_opportunity.min_coverage_weeks == 4


def test_default_active_positions_all_have_default_weights():
    cfg = load_ensemble_config({})

    assert all(position in cfg.ff_opportunity.weights for position in cfg.ff_opportunity.positions)
