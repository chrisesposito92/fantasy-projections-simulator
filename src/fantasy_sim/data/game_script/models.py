"""Data models for game-script configuration and learned profiles."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TargetRankFactors:
    """Target-share adjustments by target-rank bucket."""

    rank1: float = 1.0
    rank2: float = 1.0
    rank3_plus: float = 1.0


@dataclass(frozen=True)
class RbRankFactors:
    """Carry-share adjustments by running-back rank bucket."""

    rb1: float = 1.0
    rb2: float = 1.0
    rb3_plus: float = 1.0


@dataclass
class TrailingLateConfig:
    """Configuration for trailing-late game script adjustments."""

    enabled: bool = True
    deficit_threshold: int = 8
    final_five_minutes: int = 300
    final_five_deficit_threshold: int = 4
    pass_rate_prior_strength: float = 250.0
    pace_prior_strength: float = 250.0
    target_prior_strength: float = 80.0
    pass_rate_clamp: tuple[float, float] = (1.00, 1.35)
    pace_factor_clamp: tuple[float, float] = (1.00, 1.20)
    target_rank_factor_clamp: tuple[float, float] = (0.85, 1.25)


@dataclass
class LeadingLateRbConfig:
    """Configuration for leading-late RB carry-share adjustments."""

    enabled: bool = False
    lead_threshold: int = 14
    late_minutes: int = 600
    rb_carry_prior_strength: float = 100.0
    rb_rank_factor_clamp: tuple[float, float] = (0.80, 1.20)


@dataclass
class GameScriptConfig:
    """Master configuration for game-script learning and runtime plumbing."""

    enabled: bool = False
    trailing_late: TrailingLateConfig = field(default_factory=TrailingLateConfig)
    leading_late_rb: LeadingLateRbConfig = field(default_factory=LeadingLateRbConfig)


@dataclass(frozen=True)
class GameScriptDiagnostics:
    """Learning diagnostics carried with a profile for validation/reporting."""

    trailing_late_pass_rate_sample: int = 0
    trailing_late_pace_sample: int = 0
    trailing_late_target_sample: int = 0
    leading_late_rb_sample: int = 0
    trailing_late_play_count: int = 0
    trailing_late_pass_rate_ratio: float = 1.0
    trailing_late_pace_ratio: float = 1.0
    trailing_late_rank1_ratio: float = 1.0
    trailing_late_rank2_ratio: float = 1.0
    trailing_late_rank3_plus_ratio: float = 1.0
    leading_late_rb_play_count: int = 0
    leading_late_rb1_ratio: float = 1.0
    leading_late_rb2_ratio: float = 1.0
    leading_late_rb3_plus_ratio: float = 1.0


@dataclass(frozen=True)
class GameScriptProfile:
    """Learned game-script profile attached to TeamDistributions."""

    team: str
    trailing_late_pass_rate_factor: float = 1.0
    trailing_late_pace_factor: float = 1.0
    trailing_late_target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    leading_late_rb_factors: RbRankFactors = field(default_factory=RbRankFactors)
    diagnostics: GameScriptDiagnostics = field(default_factory=GameScriptDiagnostics)
