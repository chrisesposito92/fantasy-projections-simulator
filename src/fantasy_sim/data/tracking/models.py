from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReceiverParticipationConfig:
    enabled: bool = True
    positions: tuple[str, ...] = ("WR", "TE")
    target_share_sensitivity: float = 0.18
    air_yards_sensitivity: float = 0.12
    catchable_target_sensitivity: float = 0.08
    contested_target_sensitivity: float = -0.04
    factor_clamp: tuple[float, float] = (0.92, 1.08)
    min_targets: int = 8


@dataclass
class RbEfficiencyConfig:
    enabled: bool = True
    carry_share_sensitivity: float = 0.10
    rush_yards_sensitivity: float = 0.08
    factor_clamp: tuple[float, float] = (0.93, 1.07)
    min_attempts: int = 12


@dataclass
class QbContextConfig:
    enabled: bool = True
    pass_rate_sensitivity: float = 0.04
    pace_sensitivity: float = 0.03
    scramble_sensitivity: float = 0.06
    sack_rate_sensitivity: float = 0.05
    factor_clamp: tuple[float, float] = (0.94, 1.06)
    min_dropbacks: int = 20


@dataclass
class TrackingConfig:
    enabled: bool = False
    window_weeks: int = 4
    receiver_participation: ReceiverParticipationConfig = field(
        default_factory=ReceiverParticipationConfig
    )
    rb_efficiency: RbEfficiencyConfig = field(default_factory=RbEfficiencyConfig)
    qb_context: QbContextConfig = field(default_factory=QbContextConfig)
