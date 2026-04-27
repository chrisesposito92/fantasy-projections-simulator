"""Data models for ensemble config families."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PriorWidthConfig:
    """KS-13 D-10: ff_opportunity prior-width config.

    enabled: bool — master sub-flag (conjunction with phase2_ks_flags.ks13 master).
    path: str — "A" = quantile-derived sigma; "B" = fitted residual std per bucket.
    artifacts_dir: Path | None — Path B override directory; None -> bundled dir.
    """

    enabled: bool = False
    path: str = "A"  # "A" = quantile-derived; "B" = fitted residual std
    artifacts_dir: Path | None = None  # codex cycle-2 HIGH 3: Path B override


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
    prior_width: PriorWidthConfig = field(default_factory=PriorWidthConfig)  # KS-13 D-10


@dataclass
class FfRankingsConfig:
    """Configuration for the Fantasy Football Rankings signal."""

    enabled: bool = False


@dataclass
class DynamicBlendConfig:
    """Configuration for learned post-simulation source blending."""

    enabled: bool = False
    weights_dir: str | None = None
    week_buckets: tuple[str, ...] = ("1-4", "5-12", "13-18")
    min_bucket_rows: int = 200
    min_bucket_weeks: int = 6
    grid_step: float = 0.05
    fallback: str = "fixed_defaults"
    simulator_weight_floor: float = 0.0  # KS-08 D-06 — Plan 02


@dataclass
class StatLevelConfig:
    """Per-stat residual_calibration config block for KS-09 (Plan 03)."""

    enabled: bool = False
    covered_stats: tuple[str, ...] = ()


@dataclass
class ResidualCalibrationConfig:
    """Configuration for post-simulation residual calibration."""

    enabled: bool = False
    artifacts_dir: str | None = None
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    min_bucket_rows: int = 200
    min_bucket_weeks: int = 6
    shrinkage_prior_rows: int = 200
    max_abs_adjustment: float = 1.5
    min_training_mae_delta: float = -0.01
    fallback: str = "zero"
    stat_level: StatLevelConfig = field(default_factory=StatLevelConfig)
    max_abs_adjustment_by_position: dict[str, float] = field(default_factory=dict)  # placeholder for KS-10 — Plan 05


@dataclass
class EnsembleConfig:
    """Top-level ensemble configuration."""

    enabled: bool = False
    ff_opportunity: FfOpportunityConfig = field(default_factory=FfOpportunityConfig)
    ff_rankings: FfRankingsConfig = field(default_factory=FfRankingsConfig)
    dynamic_blend: DynamicBlendConfig = field(default_factory=DynamicBlendConfig)
    residual_calibration: ResidualCalibrationConfig = field(
        default_factory=ResidualCalibrationConfig
    )
