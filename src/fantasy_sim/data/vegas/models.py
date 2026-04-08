"""Data models for the Vegas intelligence layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VegasContext:
    """Per-team Vegas-derived adjustment factors. All factors centered on 1.0.

    volume_factor (VEG-01): ITT-derived pace scaler. Drives TeamDistributions.pace_factor.
        Higher ITT -> faster pace -> more plays per game.

    pass_rate_factor (VEG-02): Spread-derived pass rate modifier. Drives
        PlayCallingDist.default. Favorites run more (< 1.0), underdogs pass
        more (> 1.0).
    """

    team: str
    volume_factor: float = 1.0
    pass_rate_factor: float = 1.0


@dataclass
class VegasConfig:
    """Configuration for VegasEngine."""

    enabled: bool = False
    itt_sensitivity: float = 0.06
    itt_clamp: tuple[float, float] = (0.88, 1.12)
    spread_sensitivity: float = 0.04
    spread_clamp: tuple[float, float] = (0.92, 1.08)


@dataclass
class PropsConfig:
    """Configuration for player props integration (VEG-03).

    Separate from VegasConfig (following WeatherConfig precedent).
    Passed as its own parameter to GameContextBuilder.__init__().

    Fields:
        enabled: Master switch. False = props disabled (no data reads).
        prior_strength: Bayesian prior weight vs observed games_played.
            Higher = props have less influence. Default 10.0 (10 game-equivalents).
        min_divergence: Minimum |blended_ratio - 1.0| to apply adjustment.
            Prevents noise from near-identical prop/historical values.
        cache_dir: PFF props parquet cache directory.
            None = ~/.fantasy-sim/pff/props/ (default).
    """

    enabled: bool = False
    prior_strength: float = 10.0
    min_divergence: float = 0.005
    cache_dir: str | None = None
