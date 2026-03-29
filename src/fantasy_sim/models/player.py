# src/fantasy_sim/models/player.py
from dataclasses import dataclass
import numpy as np


@dataclass
class PlayerUsage:
    """How often a player is involved in plays."""
    carry_share: float = 0.0
    red_zone_carry_share: float = 0.0
    target_share: float = 0.0
    red_zone_target_share: float = 0.0
    snap_share: float = 0.0
    scramble_rate: float = 0.0


@dataclass
class PlayerOutcomes:
    """What happens when a player is involved in a play."""
    catch_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None
    scramble_yards_dist: np.ndarray | None = None
    fumble_rate: float = 0.0


@dataclass
class PlayerModel:
    """Complete model for one player."""
    player_id: str
    name: str
    position: str
    team: str
    usage: PlayerUsage
    outcomes: PlayerOutcomes
    games_played: int = 17


@dataclass
class TeamRoster:
    """Collection of PlayerModels for one team, with selection methods."""
    team: str
    players: list[PlayerModel]

    def get_starting_qb(self) -> PlayerModel:
        qbs = [p for p in self.players if p.position == "QB"]
        return max(qbs, key=lambda p: p.usage.snap_share)

    def select_receiver(self, rng: np.random.Generator, is_red_zone: bool = False) -> PlayerModel:
        eligible = [p for p in self.players if p.usage.target_share > 0]
        if not eligible:
            eligible = [p for p in self.players if p.position != "QB"]
        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_target_share if p.usage.red_zone_target_share > 0
                else p.usage.target_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.target_share for p in eligible])
        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]

    def select_rusher(self, rng: np.random.Generator, is_red_zone: bool = False) -> PlayerModel:
        eligible = [p for p in self.players if p.usage.carry_share > 0]
        if not eligible:
            eligible = [p for p in self.players if p.position == "RB"]
        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_carry_share if p.usage.red_zone_carry_share > 0
                else p.usage.carry_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.carry_share for p in eligible])
        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]
