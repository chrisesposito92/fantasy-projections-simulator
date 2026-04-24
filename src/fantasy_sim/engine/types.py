from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_sim.data.game_script import GameScriptConfig, GameScriptProfile
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


@dataclass
class DefensiveTdRates:
    """Team-specific defensive TD rates (replaces fixed constants in game_sim)."""
    int_return_td_rate: float = 0.20
    fumble_return_td_rate: float = 0.10


@dataclass
class TeamDistributions:
    """All distributions needed to simulate one team."""
    play_calling: PlayCallingDist
    play_outcomes: PlayOutcomeDist
    turnover_rates: TurnoverRates
    kicking: KickingModel
    drive_start: DriveStartModel
    goal_line_concentration_enabled: bool = False
    pace_factor: float = 1.0
    defensive_td_rates: DefensiveTdRates = field(default_factory=DefensiveTdRates)
    game_script_config: GameScriptConfig | None = None
    game_script_profile: GameScriptProfile | None = None
    target_selection_context: object | None = None


@dataclass
class GameState:
    """Mutable game state updated on every play."""
    quarter: int            # 1-4 regulation, 5 = overtime
    clock: int              # seconds remaining in quarter (900 per quarter)
    possession: str         # "home" | "away"
    down: int               # 1-4
    distance: int           # yards to first down
    yard_line: int          # yardline_100: 99=own 1, 50=midfield, 1=opp 1
    home_score: int
    away_score: int
    home_team: str
    away_team: str
    receiving_2nd_half: str  # "home" | "away"
    game_over: bool = False
    week: int = 0
    two_min_warning_fired: bool = False

    @property
    def score_differential(self) -> int:
        """Score diff from perspective of possessing team (positive = winning)."""
        if self.possession == "home":
            return self.home_score - self.away_score
        return self.away_score - self.home_score

    @property
    def offense(self) -> str:
        return self.possession

    @property
    def defense(self) -> str:
        return "away" if self.possession == "home" else "home"


@dataclass
class PlayerBoxScore:
    """Per-player stats for one game."""
    player_id: str
    name: str
    position: str
    team: str
    # Passing
    pass_attempts: int = 0
    completions: int = 0
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions: int = 0
    sacks: int = 0
    # Rushing
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    # Receiving
    targets: int = 0
    receptions: int = 0
    receiving_yards: int = 0
    receiving_tds: int = 0
    # Misc
    fumbles_lost: int = 0
    two_point_conversions: int = 0


@dataclass
class PlayResult:
    """Outcome of a single play."""
    play_type: str          # "pass" | "run"
    yards: int
    is_complete: bool = False
    is_sack: bool = False
    is_interception: bool = False
    is_fumble: bool = False
    is_touchdown: bool = False
    is_safety: bool = False
    is_penalty: bool = False
    clock_runoff: int = 0
    # Player attribution (Phase 3)
    passer_id: str | None = None
    receiver_id: str | None = None
    rusher_id: str | None = None


@dataclass
class TeamBoxScore:
    """Accumulated team-level stats for one game."""
    # Offensive
    pass_attempts: int = 0
    completions: int = 0
    pass_yards: int = 0
    pass_tds: int = 0
    interceptions_thrown: int = 0
    sacks_taken: int = 0
    sack_yards: int = 0
    rush_attempts: int = 0
    rush_yards: int = 0
    rush_tds: int = 0
    fumbles_lost: int = 0
    fg_attempts: int = 0
    fg_made: int = 0
    # Kicking detail (for scoring)
    fg_made_0_39: int = 0
    fg_made_40_49: int = 0
    fg_made_50_plus: int = 0
    fg_missed: int = 0
    xp_attempts: int = 0
    xp_made: int = 0
    punts: int = 0
    points: int = 0
    # Defensive
    sacks_made: int = 0
    interceptions_caught: int = 0
    fumbles_recovered: int = 0
    safeties: int = 0
    defensive_tds: int = 0


@dataclass
class GameResult:
    """Final result of one simulated game."""
    home_score: int
    away_score: int
    home_box: TeamBoxScore
    away_box: TeamBoxScore
    total_plays: int
    overtime: bool
    player_stats: dict[str, PlayerBoxScore] = field(default_factory=dict)
