"""Load ensemble configuration from defaults.yaml."""

from __future__ import annotations

from fantasy_sim.data.ensemble.models import (
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
    ff_opportunity_raw = raw.get("ff_opportunity", {})
    ff_rankings_raw = raw.get("ff_rankings", {})

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

    return EnsembleConfig(
        enabled=raw.get("enabled", False),
        ff_opportunity=ff_opportunity,
        ff_rankings=ff_rankings,
    )
