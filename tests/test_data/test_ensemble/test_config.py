"""Tests for ensemble config loading."""

from fantasy_sim.data.ensemble.config import load_ensemble_config


def test_load_ensemble_config_defaults_when_missing():
    cfg = load_ensemble_config({})

    assert cfg.enabled is False
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_rankings.enabled is False
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.positions == ("QB", "RB", "WR", "TE")
    assert cfg.ff_opportunity.weights == {
        "QB": 0.35,
        "RB": 0.15,
        "WR": 0.25,
        "TE": 0.15,
    }
    assert cfg.dynamic_blend.enabled is False
    assert cfg.dynamic_blend.weights_dir is None
    assert cfg.dynamic_blend.week_buckets == ("1-4", "5-12", "13-18")
    assert cfg.dynamic_blend.min_bucket_rows == 200
    assert cfg.dynamic_blend.min_bucket_weeks == 6
    assert cfg.dynamic_blend.grid_step == 0.05
    assert cfg.dynamic_blend.fallback == "fixed_defaults"


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
                "dynamic_blend": {
                    "enabled": True,
                    "weights_dir": "results/dynamic_blend/test",
                    "week_buckets": ["1-3", "4-10", "11-18"],
                    "min_bucket_rows": 100,
                    "min_bucket_weeks": 4,
                    "grid_step": 0.1,
                    "fallback": "simulator_only",
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
    assert cfg.dynamic_blend.enabled is True
    assert cfg.dynamic_blend.weights_dir == "results/dynamic_blend/test"
    assert cfg.dynamic_blend.week_buckets == ("1-3", "4-10", "11-18")
    assert cfg.dynamic_blend.min_bucket_rows == 100
    assert cfg.dynamic_blend.min_bucket_weeks == 4
    assert cfg.dynamic_blend.grid_step == 0.1
    assert cfg.dynamic_blend.fallback == "simulator_only"


def test_load_ensemble_config_top_level_enabled_with_nested_sections_omitted():
    cfg = load_ensemble_config({"ensemble": {"enabled": True}})

    assert cfg.enabled is True
    assert cfg.ff_opportunity.enabled is False
    assert cfg.ff_opportunity.cache_dir is None
    assert cfg.ff_opportunity.positions == ("QB", "RB", "WR", "TE")
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.weights == {
        "QB": 0.35,
        "RB": 0.15,
        "WR": 0.25,
        "TE": 0.15,
    }
    assert cfg.ff_opportunity.min_coverage_weeks == 1
    assert cfg.ff_rankings.enabled is False
    assert cfg.dynamic_blend.enabled is False
    assert cfg.dynamic_blend.weights_dir is None


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
    assert cfg.ff_opportunity.positions == ("QB", "RB", "WR", "TE")
    assert cfg.ff_opportunity.feature == "total_fantasy_points_exp"
    assert cfg.ff_opportunity.weights == {
        "QB": 0.35,
        "RB": 0.15,
        "WR": 0.25,
        "TE": 0.15,
    }
    assert cfg.ff_opportunity.min_coverage_weeks == 4


def test_default_active_positions_all_have_default_weights():
    cfg = load_ensemble_config({})

    assert all(position in cfg.ff_opportunity.weights for position in cfg.ff_opportunity.positions)
