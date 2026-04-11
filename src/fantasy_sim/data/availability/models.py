from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class InjurySignalConfig:
    enabled: bool = True
    hard_out_statuses: tuple[str, ...] = (
        "Out",
        "Doubtful",
        "Suspended",
        "Injured Reserve",
    )
    limited_statuses: tuple[str, ...] = ("Questionable",)
    limited_factor: float = 0.75


@dataclass
class DepthChartSignalConfig:
    enabled: bool = True
    starter_slots: dict[str, str] = field(
        default_factory=lambda: {"QB": "QB1", "RB": "RB1", "WR": "WR1", "TE": "TE1"}
    )


@dataclass
class UsageFallbackConfig:
    enabled: bool = True
    lookback_weeks: int = 3
    min_factor: float = 0.85
    qb_low_usage_factor: float = 0.92
    rb_low_usage_factor: float = 0.90
    wr_low_usage_factor: float = 0.92
    te_low_usage_factor: float = 0.92


@dataclass
class AvailabilityConfig:
    enabled: bool = False
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    injuries: InjurySignalConfig = field(default_factory=InjurySignalConfig)
    depth_charts: DepthChartSignalConfig = field(default_factory=DepthChartSignalConfig)
    usage_fallback: UsageFallbackConfig = field(default_factory=UsageFallbackConfig)
