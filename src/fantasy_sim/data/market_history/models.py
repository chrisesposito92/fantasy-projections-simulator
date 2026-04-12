from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketHistoryFeatureFlags:
    close_fpts: bool = True
    open_fpts: bool = True
    movement: bool = True
    dispersion: bool = True
    anytime_td: bool = True


@dataclass
class MarketHistoryConfig:
    enabled: bool = False
    data_dir: str | None = None
    positions: tuple[str, ...] = ("QB", "RB", "WR", "TE")
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "QB": 0.20,
            "RB": 0.15,
            "WR": 0.20,
            "TE": 0.15,
        }
    )
    min_coverage_weeks: int = 1
    min_books: int = 2
    dispersion_scale: float = 3.0
    features: MarketHistoryFeatureFlags = field(
        default_factory=MarketHistoryFeatureFlags
    )
