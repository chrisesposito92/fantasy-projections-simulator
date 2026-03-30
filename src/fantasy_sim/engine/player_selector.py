"""Player selection for play-by-play simulation.

Thin wrappers around TeamRoster selection methods that add
game-state awareness (e.g., red zone detection).
"""

import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, TeamRoster


def select_passer(roster: TeamRoster) -> PlayerModel:
    """Select the starting QB."""
    return roster.get_starting_qb()


def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
) -> PlayerModel:
    """Select a receiver weighted by target share."""
    is_red_zone = state.yard_line <= 20
    return roster.select_receiver(rng, is_red_zone=is_red_zone)


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
) -> PlayerModel:
    """Select a ball carrier. If scramble, returns the QB."""
    if is_scramble:
        return roster.get_starting_qb()
    is_red_zone = state.yard_line <= 20
    return roster.select_rusher(rng, is_red_zone=is_red_zone)
