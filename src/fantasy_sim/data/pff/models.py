"""Shared data types for the PFF intelligence layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MatchupContext:
    """Per-game adjustment factors derived from PFF defensive + OL data.

    All factors are centered on 1.0 (neutral), but the direction of a
    tougher/easier matchup depends on the specific factor.

    Lower values mean tougher defense for the offense for:
    - catch_rate_factor
    - pass_yards_factor
    - rush_yards_factor

    Higher values mean tougher defense for the offense for:
    - sack_rate_factor
    - int_rate_factor

    Offensive line factors represent blocking quality for the offense:
    - Higher ol_pass_block_factor / ol_run_block_factor = better blocking
    - Lower ol_pass_block_factor / ol_run_block_factor = worse blocking
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
class ScheduleAdjustmentConfig:
    """Configuration for schedule-adjusted talent evaluation."""
    enabled: bool = True
    weight: float = 0.3
    catch_rate_sensitivity: float = 0.005
    rush_yards_sensitivity: float = 0.3


@dataclass
class NcaaPriorsConfig:
    """Configuration for NCAA-based rookie priors."""
    enabled: bool = True
    draft_weight: float = 0.6
    ncaa_data_dir: str | None = None


@dataclass
class TalentConfig:
    """Configuration for the talent stabilizer."""
    enabled: bool = True
    prior_strength: float | dict[str, float] = 30.0
    min_divergence: float = 0.01
    team_change_factor: float = 1.0
    catch_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "drop_rate": 0.21,
        "contested_catch_rate": -0.25,
        "qb_accuracy": 0.03,
    })
    rushing_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yco_attempt": 0.02,
        "elusive_rating": 0.0005,
    })
    receiving_yards_coefficients: dict[str, float] = field(default_factory=lambda: {
        "yprr": 0.43,
        "avg_depth_of_target": 0.41,
    })
    target_share_coefficients: dict[str, float] = field(default_factory=lambda: {
        "route_grade": 0.5,
        "yprr": 0.3,
    })
    fumble_rate_coefficients: dict[str, float] = field(default_factory=lambda: {
        "grades_hands_fumble": -0.002,
    })
    scramble_rate_enabled: bool = True
    schedule_adjustment: ScheduleAdjustmentConfig = field(
        default_factory=ScheduleAdjustmentConfig
    )
    ncaa_priors: NcaaPriorsConfig = field(
        default_factory=NcaaPriorsConfig
    )


@dataclass
class ArchetypeConfig:
    """Configuration for WR depth-of-target archetypes within tiers."""
    enabled: bool = True
    n_archetypes: int = 3
    adot_grade_key: str = "avg_depth_of_target"
    min_archetype_pool_size: int = 20


@dataclass
class PositionGradeConfig:
    """Primary and secondary PFF grade columns for one position."""
    primary: str
    secondary: str


@dataclass
class NcaaRookieConfig:
    """Configuration for NCAA-based rookie tier assignment."""
    enabled: bool = True
    draft_confidence: dict[int, float] = field(default_factory=lambda: {
        1: 1.0, 2: 0.95, 3: 0.85, 4: 0.75, 5: 0.65, 6: 0.55, 7: 0.50,
    })
    undrafted_confidence: float = 0.40
    ncaa_lookback_seasons: int = 4


@dataclass
class TierConfig:
    """Configuration for the PFF Talent-Tier Distribution Engine."""
    enabled: bool = False
    cutoffs: list[float] = field(default_factory=lambda: [0.85, 0.65, 0.40, 0.20])
    position_grades: dict[str, PositionGradeConfig] = field(
        default_factory=lambda: {
            "QB": PositionGradeConfig(primary="grades_pass", secondary="accuracy_percent"),
            "RB": PositionGradeConfig(primary="grades_run", secondary="elusive_rating"),
            "WR": PositionGradeConfig(primary="grades_pass_route", secondary="yprr"),
            "TE": PositionGradeConfig(primary="grades_pass_route", secondary="recv_grade"),
        }
    )
    reliability_max_games: int = 32
    reliability_team_change_penalty: float = 0.5
    reliability_variance_weight: float = 0.3
    reliability_floor: float = 0.15
    reliability_cap: float = 0.85
    blend_pool_size: int = 500
    ncaa_rookie: NcaaRookieConfig = field(default_factory=NcaaRookieConfig)
    archetypes: ArchetypeConfig = field(default_factory=ArchetypeConfig)


@dataclass
class TeamContext:
    """Season-level team environment factors for tier distribution adjustment.

    All factors centered on 1.0 (neutral).
    """
    pass_rate_factor: float = 1.0
    ol_run_block_factor: float = 1.0
    qb_quality_factor: float = 1.0
    ol_run_yards_scale: float = 10.0


@dataclass
class TeamContextConfig:
    """Configuration for the team context engine."""
    enabled: bool = True
    pass_rate_sensitivity: float = 0.08
    ol_run_sensitivity: float = 0.06
    qb_quality_sensitivity: float = 0.05
    factor_clamp: tuple[float, float] = (0.90, 1.10)
    min_games: int = 4
    ol_run_yards_scale: float = 10.0


@dataclass
class PffConfig:
    """Top-level PFF configuration."""
    enabled: bool = False
    data_dir: str | None = None
    matchup: MatchupConfig = field(default_factory=MatchupConfig)
    talent: TalentConfig = field(default_factory=TalentConfig)
    tier_engine: TierConfig = field(default_factory=TierConfig)
    team_context: TeamContextConfig = field(default_factory=TeamContextConfig)
