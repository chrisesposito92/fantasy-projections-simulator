"""Data models for ensemble config families."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FfOpportunityConfig:
    """Configuration for the Fantasy Football Opportunity signal."""

    enabled: bool = False
    cache_dir: str | None = None
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    feature: str = "total_fantasy_points_exp"
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "QB": 0.35,
            "RB": 0.15,
            "WR": 0.25,
            "TE": 0.15,
        }
    )
    min_coverage_weeks: int = 1


@dataclass
class FfRankingsConfig:
    """Configuration for the Fantasy Football Rankings signal."""

    enabled: bool = False


@dataclass
class EnsembleConfig:
    """Top-level ensemble configuration."""

    enabled: bool = False
    ff_opportunity: FfOpportunityConfig = field(default_factory=FfOpportunityConfig)
    ff_rankings: FfRankingsConfig = field(default_factory=FfRankingsConfig)
