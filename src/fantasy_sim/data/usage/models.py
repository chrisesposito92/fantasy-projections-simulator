"""Data models for the Usage intelligence layer (USG-01)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SnapConfig:
    """Configuration for snap-count-based share blending."""

    prior_strength: float = 8.0         # Bayesian weight vs games_played
    min_games: int = 4                  # rolling window size (D-04)
    factor_clamp: tuple[float, float] = (0.70, 1.30)


@dataclass
class CpoeConfig:
    """Configuration for CPOE (Completion Percentage Over Expected) signal."""

    enabled: bool = True
    sensitivity: float = 0.30           # grade points per 1-sigma CPOE
    min_plays: int = 20                 # minimum pass attempts in window
    cpoe_league_avg: float = 1.0        # config-driven, not hardcoded (review: sweepable)
    cpoe_league_std: float = 4.0        # config-driven, not hardcoded (review: sweepable)


@dataclass
class NgsConfig:
    """Configuration for Next Gen Stats (separation, cushion) signal."""

    enabled: bool = True
    separation_sensitivity: float = 0.04
    cushion_sensitivity: float = -0.03  # NEGATIVE: high cushion = less threatening WR
    # (review concern: cushion directionality — high cushion means CB is giving space,
    # implying WR is not creating real separation and is less threatening)
    factor_clamp: tuple[float, float] = (0.95, 1.05)
    min_targets: int = 10


@dataclass
class RouteRateConfig:
    """Configuration for route participation rate signal."""

    enabled: bool = True
    sensitivity: float = 0.5            # target_share multiplier weight
    min_routes: int = 10


@dataclass
class UsageConfig:
    """Master configuration for the UsageEngine (USG-01).

    Controls snap blend, CPOE, NGS, and route rate adjustments.
    Enabled by default; set enabled=False to bypass all usage adjustments.
    """

    enabled: bool = True
    snap: SnapConfig = field(default_factory=SnapConfig)
    cpoe: CpoeConfig = field(default_factory=CpoeConfig)
    ngs: NgsConfig = field(default_factory=NgsConfig)
    route_rate: RouteRateConfig = field(default_factory=RouteRateConfig)
