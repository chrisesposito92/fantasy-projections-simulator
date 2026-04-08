# src/fantasy_sim/models/player.py
from dataclasses import dataclass, field
import numpy as np

# Minimum carry_share for a QB to be included in the designed-run rusher pool.
# Distinguishes dual-threat QBs (Allen ~0.22, Hurts ~0.18) from pocket passers
# (Herbert ~0.05, Mahomes ~0.07) who get rushing yards only via scrambles.
MIN_QB_CARRY_SHARE = 0.10


@dataclass
class PlayerUsage:
    """How often a player is involved in plays."""
    carry_share: float = 0.0
    red_zone_carry_share: float = 0.0
    target_share: float = 0.0
    red_zone_target_share: float = 0.0
    air_yards_share: float = 0.0
    snap_share: float = 0.0
    scramble_rate: float = 0.0


@dataclass
class PlayerOutcomes:
    """What happens when a player is involved in a play."""
    catch_rate: float = 0.0
    red_zone_catch_rate: float = 0.0
    receiving_yards_dist: np.ndarray | None = None
    rz_receiving_yards_dist: np.ndarray | None = None
    rushing_yards_dist: np.ndarray | None = None
    scramble_yards_dist: np.ndarray | None = None
    fumble_rate: float = 0.0
    pass_fumble_rate: float = 0.0
    targets_per_route_rate: float = 0.0  # USG-04: targets/routes from PFF receiving_summary


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
    weeks_missed: list[int] = field(default_factory=list)


@dataclass
class TeamRoster:
    """Collection of PlayerModels for one team, with selection methods."""
    team: str
    players: list[PlayerModel]

    def get_starting_qb(self) -> PlayerModel:
        """Return the QB with the highest snap share on this roster.

        Raises ValueError if no QB is present on the roster.
        """
        qbs = [p for p in self.players if p.position == "QB"]
        if not qbs:
            raise ValueError(f"No QB found on roster for {self.team}")
        return max(qbs, key=lambda p: p.usage.snap_share)

    def select_receiver(
        self, rng: np.random.Generator, is_red_zone: bool = False
    ) -> PlayerModel:
        """Randomly select a pass target, weighted by target share.

        Players with target_share > 0 are preferred.  When none exist,
        all non-QB players are eligible with uniform probability.
        Raises ValueError if no eligible receivers exist.
        """
        eligible = [p for p in self.players if p.usage.target_share > 0]
        if not eligible:
            # Fallback: any non-QB with uniform weights
            eligible = [p for p in self.players if p.position != "QB"]
        if not eligible:
            raise ValueError(f"No eligible receivers on roster for {self.team}")

        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_target_share if p.usage.red_zone_target_share > 0
                else p.usage.target_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.target_share for p in eligible])

        # Use uniform weights if all weights are zero (fallback path)
        if weights.sum() == 0:
            weights = np.ones(len(eligible))
        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]

    def select_rusher(
        self, rng: np.random.Generator, is_red_zone: bool = False
    ) -> PlayerModel:
        """Randomly select a ball carrier, weighted by carry share.

        Players with carry_share > 0 are preferred.  When none exist,
        all RBs are eligible with uniform probability.
        Raises ValueError if no eligible rushers exist.
        """
        eligible = [
            p for p in self.players
            if p.usage.carry_share > 0
            and (p.position != "QB" or p.usage.carry_share >= MIN_QB_CARRY_SHARE)
        ]
        if not eligible:
            # Fallback: any RB with uniform weights
            eligible = [p for p in self.players if p.position == "RB"]
        if not eligible:
            raise ValueError(f"No eligible rushers on roster for {self.team}")

        if is_red_zone:
            weights = np.array([
                p.usage.red_zone_carry_share if p.usage.red_zone_carry_share > 0
                else p.usage.carry_share
                for p in eligible
            ])
        else:
            weights = np.array([p.usage.carry_share for p in eligible])

        # Use uniform weights if all weights are zero (fallback path)
        if weights.sum() == 0:
            weights = np.ones(len(eligible))
        weights = weights / weights.sum()
        idx = rng.choice(len(eligible), p=weights)
        return eligible[idx]
