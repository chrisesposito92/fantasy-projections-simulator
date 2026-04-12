from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PositionTrendConfig:
    sensitivity: float


@dataclass
class RoleTrendConfig:
    enabled: bool = False
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    window_weeks: int = 3
    factor_clamp: tuple[float, float] = (0.90, 1.10)
    qb: PositionTrendConfig = field(
        default_factory=lambda: PositionTrendConfig(sensitivity=0.12)
    )
    rb: PositionTrendConfig = field(
        default_factory=lambda: PositionTrendConfig(sensitivity=0.10)
    )
    wr: PositionTrendConfig = field(
        default_factory=lambda: PositionTrendConfig(sensitivity=0.10)
    )
    te: PositionTrendConfig = field(
        default_factory=lambda: PositionTrendConfig(sensitivity=0.08)
    )
