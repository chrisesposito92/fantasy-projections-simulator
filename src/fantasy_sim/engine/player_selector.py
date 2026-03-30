"""Player selection for play-by-play simulation.

Thin wrappers around TeamRoster selection methods that add
game-state awareness (e.g., red zone detection, week-based availability).
"""

import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, TeamRoster


def _filter_available(roster: TeamRoster, state: GameState) -> TeamRoster:
    """Return a filtered roster excluding players who have the current week
    in their weeks_missed list.

    If week is 0 (unset), no filtering is applied.
    Returns original roster if no players are filtered out.
    """
    if state.week == 0:
        return roster
    available = [
        p for p in roster.players
        if state.week not in p.weeks_missed
    ]
    if not available:
        return roster  # Safety: never return empty roster
    if len(available) == len(roster.players):
        return roster
    return TeamRoster(team=roster.team, players=available)


def select_passer(roster: TeamRoster, state: GameState | None = None) -> PlayerModel:
    """Select the starting QB. If state is provided, filters out QBs missing this week."""
    if state is not None and state.week > 0:
        filtered = _filter_available(roster, state)
        try:
            return filtered.get_starting_qb()
        except ValueError:
            pass  # Fall back to unfiltered
    return roster.get_starting_qb()


def select_receiver(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
) -> PlayerModel:
    """Select a receiver weighted by target share, filtering out missed-week players."""
    filtered = _filter_available(roster, state)
    is_red_zone = state.yard_line <= 20
    return filtered.select_receiver(rng, is_red_zone=is_red_zone)


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
) -> PlayerModel:
    """Select a ball carrier, filtering out missed-week players."""
    if is_scramble:
        if state.week > 0:
            filtered = _filter_available(roster, state)
            try:
                return filtered.get_starting_qb()
            except ValueError:
                pass
        return roster.get_starting_qb()
    filtered = _filter_available(roster, state)
    is_red_zone = state.yard_line <= 20
    return filtered.select_rusher(rng, is_red_zone=is_red_zone)
