"""Player selection for play-by-play simulation.

Thin wrappers around TeamRoster selection methods that add
game-state awareness (e.g., red zone detection, week-based availability).
"""

import numpy as np
from fantasy_sim.engine.game_script import RuntimeGameScript
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import MIN_QB_CARRY_SHARE, PlayerModel, TeamRoster


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
    script: RuntimeGameScript | None = None,
) -> PlayerModel:
    """Select a receiver weighted by target share, filtering out missed-week players."""
    filtered = _filter_available(roster, state)
    eligible = [player for player in filtered.players if player.usage.target_share > 0]
    if not eligible:
        eligible = [player for player in filtered.players if player.position != "QB"]
    if not eligible:
        raise ValueError(f"No eligible receivers on roster for {filtered.team}")

    is_red_zone = state.yard_line <= 20
    base_weights = np.array(
        [
            (
                player.usage.red_zone_target_share
                if is_red_zone and player.usage.red_zone_target_share > 0
                else player.usage.target_share
            )
            for player in eligible
        ],
        dtype=float,
    )

    rank_order = sorted(
        range(len(eligible)),
        key=lambda idx: base_weights[idx],
        reverse=True,
    )
    rank_factors = np.ones(len(eligible), dtype=float)
    for rank, idx in enumerate(rank_order, start=1):
        rank_factors[idx] = _receiver_rank_factor(rank, script)

    weights = base_weights * rank_factors
    if weights.sum() == 0:
        weights = np.ones(len(eligible), dtype=float)
    weights = weights / weights.sum()
    return eligible[rng.choice(len(eligible), p=weights)]


def _receiver_rank_factor(rank: int, script: RuntimeGameScript | None) -> float:
    """Return transient trailing-late target concentration for a receiver rank."""
    if script is None or script.regime != "trailing_late":
        return 1.0
    if rank == 1:
        return script.target_factors.rank1
    if rank == 2:
        return script.target_factors.rank2
    return script.target_factors.rank3_plus


def _rb_rank_factor(rank: int, script: RuntimeGameScript | None) -> float:
    """Return transient leading-late carry factor for an RB rank."""
    if script is None or script.regime != "leading_late_rb":
        return 1.0
    if rank == 1:
        return script.rb_factors.rb1
    if rank == 2:
        return script.rb_factors.rb2
    return script.rb_factors.rb3_plus


def _apply_rb_rank_factors(
    players: list[PlayerModel],
    weights: np.ndarray,
    script: RuntimeGameScript | None,
) -> np.ndarray:
    """Apply leading-late RB rank adjustments without changing non-RB mass."""
    if script is None or script.regime != "leading_late_rb":
        return weights

    rb_indices = [idx for idx, player in enumerate(players) if player.position == "RB"]
    if len(rb_indices) < 2:
        return weights

    rb_total = float(weights[rb_indices].sum())
    if rb_total == 0:
        return weights

    adjusted = weights.copy()
    rank_order = sorted(rb_indices, key=lambda idx: weights[idx], reverse=True)
    for rank, idx in enumerate(rank_order, start=1):
        adjusted[idx] = weights[idx] * _rb_rank_factor(rank, script)

    adjusted_rb_total = float(adjusted[rb_indices].sum())
    if adjusted_rb_total == 0:
        return weights

    adjusted[rb_indices] *= rb_total / adjusted_rb_total
    return adjusted


def select_rusher(
    roster: TeamRoster,
    state: GameState,
    rng: np.random.Generator,
    is_scramble: bool = False,
    script: RuntimeGameScript | None = None,
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
    eligible = [
        player for player in filtered.players
        if player.usage.carry_share > 0
        and (player.position != "QB" or player.usage.carry_share >= MIN_QB_CARRY_SHARE)
    ]
    if not eligible:
        eligible = [player for player in filtered.players if player.position == "RB"]
    if not eligible:
        raise ValueError(f"No eligible rushers on roster for {filtered.team}")

    base_weights = np.array(
        [
            (
                player.usage.red_zone_carry_share
                if is_red_zone and player.usage.red_zone_carry_share > 0
                else player.usage.carry_share
            )
            for player in eligible
        ],
        dtype=float,
    )
    weights = _apply_rb_rank_factors(eligible, base_weights, script)
    if weights.sum() == 0:
        weights = np.ones(len(eligible), dtype=float)
    weights = weights / weights.sum()
    return eligible[rng.choice(len(eligible), p=weights)]
