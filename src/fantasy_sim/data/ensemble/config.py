"""Load ensemble configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.ensemble.models import (
    DynamicBlendConfig,
    EnsembleConfig,
    FfOpportunityConfig,
    FfRankingsConfig,
)


def load_ensemble_config(defaults: dict) -> EnsembleConfig:
    """Extract ensemble config from the full defaults config dict."""
    raw = defaults.get("ensemble", {})
    if not raw:
        return EnsembleConfig()

    default_ff_opportunity = FfOpportunityConfig()
    default_dynamic_blend = DynamicBlendConfig()
    ff_opportunity_raw = raw.get("ff_opportunity", {})
    ff_rankings_raw = raw.get("ff_rankings", {})
    dynamic_blend_raw = raw.get("dynamic_blend", {})

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
    )

    return EnsembleConfig(
        enabled=raw.get("enabled", False),
        ff_opportunity=ff_opportunity,
        ff_rankings=ff_rankings,
        dynamic_blend=dynamic_blend,
    )
