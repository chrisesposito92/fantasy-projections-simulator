from dataclasses import dataclass
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


@dataclass
class TeamDistributions:
    """All distributions needed to simulate one team."""
    play_calling: PlayCallingDist
    play_outcomes: PlayOutcomeDist
    turnover_rates: TurnoverRates
    kicking: KickingModel
    drive_start: DriveStartModel


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
    clock_runoff: int = 0


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
    xp_attempts: int = 0
    xp_made: int = 0
    punts: int = 0
    points: int = 0
    # Defensive
    sacks_made: int = 0
    interceptions_caught: int = 0
    fumbles_recovered: int = 0
    safeties: int = 0


@dataclass
class GameResult:
    """Final result of one simulated game."""
    home_score: int
    away_score: int
    home_box: TeamBoxScore
    away_box: TeamBoxScore
    total_plays: int
    overtime: bool
