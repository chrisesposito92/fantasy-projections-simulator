"""Shared data types for the PFF intelligence layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MatchupContext:
    """Per-game adjustment factors derived from PFF defensive + OL data.

    All factors are centered on 1.0 (neutral). Values < 1.0 mean the
    defense/OL is worse than average (easier matchup for the offense),
    values > 1.0 mean tougher matchup.

    For catch_rate_factor and pass_yards_factor, LOWER values mean tougher
    secondary (reduces opposing offense).
    For sack_rate_factor and int_rate_factor, HIGHER values mean tougher
    pass rush / better secondary (increases sacks/INTs for opposing offense).
    For rush_yards_factor, LOWER values mean tougher run defense.
    """
    catch_rate_factor: float = 1.0
    pass_yards_factor: float = 1.0
    sack_rate_factor: float = 1.0
    int_rate_factor: float = 1.0
    rush_yards_factor: float = 1.0
    ol_pass_block_factor: float = 1.0
    ol_run_block_factor: float = 1.0


@dataclass
class TalentAdjustment:
    """Record of a talent stabilizer adjustment for one player parameter."""
    player_id: str
    parameter: str
    pbp_value: float
    pff_prior: float
    adjusted_value: float
    n_observations: int
    divergence: float


@dataclass
class MatchupConfig:
    """Configuration for the matchup engine."""
    enabled: bool = True
    pass_defense_sensitivity: float = 0.08
    pass_rush_sensitivity: float = 0.10
    run_defense_sensitivity: float = 0.08
    int_rate_sensitivity: float = 0.06
    ol_pass_sensitivity: float = 0.08
    ol_run_sensitivity: float = 0.06
    factor_clamp: tuple[float, float] = (0.80, 1.20)
    min_games: int = 4


@dataclass
class TalentConfig:
    """Configuration for the talent stabilizer."""
    enabled: bool = True
    prior_strength: float = 40.0
    min_divergence: float = 0.03
    catch_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "drop_rate": -0.15,
        "contested_catch_rate": 0.10,
        "qb_accuracy": 0.08,
    })
    rushing_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yco_attempt": 0.6,
        "elusive_rating": 0.008,
    })
    receiving_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yprr": 0.5,
        "avg_depth_of_target": 0.03,
    })


@dataclass
class PffConfig:
    """Top-level PFF configuration."""
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
