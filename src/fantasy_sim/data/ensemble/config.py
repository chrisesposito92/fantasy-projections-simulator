"""Load ensemble configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.ensemble.models import (
    DynamicBlendConfig,
    EnsembleConfig,
    FfOpportunityConfig,
    FfRankingsConfig,
    ResidualCalibrationConfig,
)


def load_ensemble_config(defaults: dict) -> EnsembleConfig:
    """Extract ensemble config from the full defaults config dict."""
    raw = defaults.get("ensemble", {})
    if not raw:
        return EnsembleConfig()

    default_ff_opportunity = FfOpportunityConfig()
    default_dynamic_blend = DynamicBlendConfig()
    default_residual_calibration = ResidualCalibrationConfig()
    ff_opportunity_raw = raw.get("ff_opportunity", {})
    ff_rankings_raw = raw.get("ff_rankings", {})
    dynamic_blend_raw = raw.get("dynamic_blend", {})
    residual_calibration_raw = raw.get("residual_calibration", {})

    ff_opportunity = FfOpportunityConfig(
        enabled=ff_opportunity_raw.get("enabled", False),
        cache_dir=ff_opportunity_raw.get("cache_dir"),
        positions=tuple(ff_opportunity_raw.get("positions", default_ff_opportunity.positions)),
        feature=ff_opportunity_raw.get("feature", default_ff_opportunity.feature),
        weights=dict(ff_opportunity_raw.get("weights", default_ff_opportunity.weights)),
        min_coverage_weeks=ff_opportunity_raw.get(
            "min_coverage_weeks",
            default_ff_opportunity.min_coverage_weeks,
        ),
    )
    ff_rankings = FfRankingsConfig(
        enabled=ff_rankings_raw.get("enabled", False),
    )
    # KS-08 D-06: the simulator_weight_floor is sourced from phase2_ks_flags.ks08 when
    # enabled; falls back to ensemble.dynamic_blend.simulator_weight_floor (default 0.0).
    phase2_flags = defaults.get("phase2_ks_flags", {})
    ks08_block = phase2_flags.get("ks08_dynamic_blend_simulator_floor", {})
    if ks08_block.get("enabled"):
        simulator_weight_floor = float(ks08_block.get("floor", 0.0))
    else:
        simulator_weight_floor = float(
            dynamic_blend_raw.get("simulator_weight_floor", default_dynamic_blend.simulator_weight_floor)
        )

    dynamic_blend = DynamicBlendConfig(
        enabled=dynamic_blend_raw.get("enabled", default_dynamic_blend.enabled),
        weights_dir=dynamic_blend_raw.get("weights_dir", default_dynamic_blend.weights_dir),
        week_buckets=tuple(
            dynamic_blend_raw.get("week_buckets", default_dynamic_blend.week_buckets)
        ),
        min_bucket_rows=int(
            dynamic_blend_raw.get(
                "min_bucket_rows",
                default_dynamic_blend.min_bucket_rows,
            )
        ),
        min_bucket_weeks=int(
            dynamic_blend_raw.get(
                "min_bucket_weeks",
                default_dynamic_blend.min_bucket_weeks,
            )
        ),
        grid_step=float(
            dynamic_blend_raw.get("grid_step", default_dynamic_blend.grid_step)
        ),
        fallback=dynamic_blend_raw.get("fallback", default_dynamic_blend.fallback),
        simulator_weight_floor=simulator_weight_floor,
    )
    residual_calibration = ResidualCalibrationConfig(
        enabled=residual_calibration_raw.get(
            "enabled",
            default_residual_calibration.enabled,
        ),
        artifacts_dir=residual_calibration_raw.get(
            "artifacts_dir",
            default_residual_calibration.artifacts_dir,
        ),
        positions=tuple(
            residual_calibration_raw.get(
                "positions",
                default_residual_calibration.positions,
            )
        ),
        min_bucket_rows=int(
            residual_calibration_raw.get(
                "min_bucket_rows",
                default_residual_calibration.min_bucket_rows,
            )
        ),
        min_bucket_weeks=int(
            residual_calibration_raw.get(
                "min_bucket_weeks",
                default_residual_calibration.min_bucket_weeks,
            )
        ),
        shrinkage_prior_rows=int(
            residual_calibration_raw.get(
                "shrinkage_prior_rows",
                default_residual_calibration.shrinkage_prior_rows,
            )
        ),
        max_abs_adjustment=float(
            residual_calibration_raw.get(
                "max_abs_adjustment",
                default_residual_calibration.max_abs_adjustment,
            )
        ),
        min_training_mae_delta=float(
            residual_calibration_raw.get(
                "min_training_mae_delta",
                default_residual_calibration.min_training_mae_delta,
            )
        ),
        fallback=residual_calibration_raw.get(
            "fallback",
            default_residual_calibration.fallback,
        ),
    )

    return EnsembleConfig(
        enabled=raw.get("enabled", False),
        ff_opportunity=ff_opportunity,
        ff_rankings=ff_rankings,
        dynamic_blend=dynamic_blend,
        residual_calibration=residual_calibration,
    )
