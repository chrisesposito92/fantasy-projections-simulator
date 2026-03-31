from __future__ import annotations

import numpy as np
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates, PenaltyRates
from fantasy_sim.models.game_state import bucket_play

# Avoid circular imports — TYPE_CHECKING is compile-time only
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.models.player import TeamRoster

# Average clock runoff in seconds
CLOCK_RUN = 38
CLOCK_PASS_COMPLETE = 35
CLOCK_PASS_INCOMPLETE = 7
CLOCK_SACK = 38

# Sack yardage loss distribution
SACK_YARDS = np.array([-3, -4, -5, -5, -6, -7, -7, -8, -8, -10])

# Home-field advantage: 50% chance of +1 yard per play
HOME_FIELD_YARDS_BONUS = 0.5

# Red zone TD gate probabilities — calibrated from 2024 NFL data.
# Given a play with enough yards to score, probability it actually results in a TD.
PASS_TD_GATE = {
    (1, 3): 0.90,
    (4, 5): 0.90,
    (6, 10): 0.80,
    (11, 15): 0.50,
    (16, 20): 0.30,
}

RUN_TD_GATE = {
    (1, 3): 0.65,
    (4, 5): 0.55,
    (6, 10): 0.40,
    (11, 15): 0.25,
    (16, 20): 0.15,
}

# League-average red zone catch rate modifier (RZ completion % / overall %)
RZ_CATCH_RATE_MODIFIER = 0.85


def _red_zone_td_gate(yard_line: int, play_type: str, rng: np.random.Generator) -> bool:
    """Check if a would-be TD actually scores, based on field position.

    Returns True if the TD stands, False if the player is tackled short.
    Outside the red zone (yard_line > 20), always returns True.
    """
    if yard_line > 20:
        return True
    gate_table = PASS_TD_GATE if play_type == "pass" else RUN_TD_GATE
    for (lo, hi), prob in gate_table.items():
        if lo <= yard_line <= hi:
            return rng.random() < prob
    return True  # Safety fallback


def _scale_clock_runoff(base_runoff: int, pace_factor: float) -> int:
    """Scale clock runoff by pace factor.
    pace_factor > 1.0: faster pace, less clock per play (more plays per game).
    pace_factor < 1.0: slower pace, more clock per play (fewer plays per game).
    pace_factor == 1.0: no change.
    Returns at least 1 second to prevent infinite games.
    """
    if pace_factor == 1.0:
        return base_runoff
    return max(1, round(base_runoff / pace_factor))


def _apply_home_field(yards: int, is_home: bool, rng: np.random.Generator) -> int:
    """Apply home-field advantage: 50% chance of +1 yard when is_home=True."""
    if is_home and rng.random() < HOME_FIELD_YARDS_BONUS:
        return yards + 1
    return yards


def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
    pace_factor: float = 1.0,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng, roster, is_home, pace_factor)
    if play_type == "run":
        return _resolve_run(state, play_outcomes, turnover_rates, rng, roster, is_home, pace_factor)
    raise ValueError(f"Unexpected play_type: {play_type!r}")


def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
    pace_factor: float = 1.0,
) -> PlayResult:
    # Lazy import to avoid circular dependencies
    from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher

    passer_id: str | None = None
    receiver_id: str | None = None

    if roster is not None:
        passer = select_passer(roster, state)
        passer_id = passer.player_id

        # QB scramble check — before sack/int, the QB decides to run
        if passer.usage.scramble_rate > 0 and rng.random() < passer.usage.scramble_rate:
            scramble_yards_dist = passer.outcomes.scramble_yards_dist
            if scramble_yards_dist is not None and len(scramble_yards_dist) > 0:
                raw_yards = int(rng.choice(scramble_yards_dist))
            else:
                # Fall back to team run distribution
                bucket = bucket_play(
                    state.down, state.distance, state.score_differential,
                    state.quarter, state.yard_line,
                )
                raw_yards = play_outcomes.sample_yards("run", bucket, rng)
            raw_yards = _apply_home_field(raw_yards, is_home, rng)
            is_safety = (state.yard_line - raw_yards) >= 100
            if is_safety:
                yards = -(99 - state.yard_line)
            else:
                yards = _clamp_yards(state.yard_line, raw_yards)
            is_td = (state.yard_line - yards) <= 0
            is_fumble = rng.random() < passer.outcomes.fumble_rate
            return PlayResult(
                play_type="run", yards=yards,
                is_touchdown=is_td and not is_fumble and not is_safety,
                is_fumble=is_fumble and not is_safety,
                is_safety=is_safety,
                rusher_id=passer_id,
                passer_id=passer_id,
                clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor),
            )

    # Check for sack first
    if rng.random() < turnover_rates.sack_rate:
        yards = int(rng.choice(SACK_YARDS))
        is_fumble = rng.random() < turnover_rates.sack_fumble_rate
        new_yl = state.yard_line - yards  # yards is negative, so this increases
        is_safety = new_yl >= 100
        if is_safety:
            yards = -(99 - state.yard_line)  # clamp to own end zone
        return PlayResult(
            play_type="pass", yards=yards, is_sack=True,
            is_fumble=is_fumble and not is_safety, is_safety=is_safety,
            clock_runoff=_scale_clock_runoff(CLOCK_SACK, pace_factor),
            passer_id=passer_id,
        )

    # Check for interception
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=_scale_clock_runoff(CLOCK_PASS_INCOMPLETE, pace_factor),
            passer_id=passer_id,
        )

    # QB pre-throw fumble check (botched snap, strip while throwing)
    if roster is not None and passer_id is not None:
        if passer.outcomes.pass_fumble_rate > 0:
            if rng.random() < passer.outcomes.pass_fumble_rate:
                return PlayResult(
                    play_type="pass", yards=0, is_fumble=True,
                    clock_runoff=_scale_clock_runoff(CLOCK_PASS_INCOMPLETE, pace_factor),
                    passer_id=passer_id,
                )

    # Select receiver when roster is available (after sack/INT checks)
    if roster is not None:
        receiver = select_receiver(roster, state, rng)
        receiver_id = receiver.player_id

    # Normal pass — determine yards from team distribution first
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    team_yards = play_outcomes.sample_yards("pass", bucket, rng)

    if roster is not None and receiver_id is not None:
        # Player-aware pass resolution
        # Use red zone catch rate when inside the 20
        if state.yard_line <= 20:
            effective_catch_rate = receiver.outcomes.red_zone_catch_rate
            if effective_catch_rate <= 0 and receiver.outcomes.catch_rate > 0:
                # Only fallback when RZ rate was never computed (not a valid 0.0 from data)
                effective_catch_rate = receiver.outcomes.catch_rate * RZ_CATCH_RATE_MODIFIER
        else:
            effective_catch_rate = receiver.outcomes.catch_rate

        is_complete = rng.random() < effective_catch_rate

        if is_complete:
            # Use player's receiving yards dist if available, otherwise team dist
            if receiver.outcomes.receiving_yards_dist is not None and len(receiver.outcomes.receiving_yards_dist) > 0:
                player_yards = int(rng.choice(receiver.outcomes.receiving_yards_dist))
            else:
                player_yards = max(team_yards, 1)  # Complete pass must gain at least 1 yard

            yards = _apply_home_field(player_yards, is_home, rng)
            yards = _clamp_yards(state.yard_line, yards)
        else:
            yards = 0

        # TD determination with red zone gate
        if is_complete and state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "pass", rng):
                yards = _clamp_yards(state.yard_line, yards)
                is_td = True
            else:
                # Tackled short of goal line
                short_amount = int(rng.integers(1, max(2, state.yard_line // 3)))
                yards = max(0, state.yard_line - short_amount)
                # Ensure receiver doesn't reach the goal line
                if yards >= state.yard_line:
                    yards = max(0, state.yard_line - 1)
                is_td = False
        else:
            is_td = is_complete and (state.yard_line - yards) <= 0

        # Red zone yards blending: cap non-TD catches by team-level distribution
        if is_complete and not is_td and state.yard_line <= 20:
            yards = min(yards, max(team_yards, 1))

        # Fumble check on completions — use player fumble rate, fall back to team rate
        is_fumble = False
        if is_complete:
            player_fumble = receiver.outcomes.fumble_rate
            effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
            is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="pass", yards=yards,
            is_complete=is_complete,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble,
            clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor),
            passer_id=passer_id,
            receiver_id=receiver_id,
        )

    # Legacy path (no roster) — identical to Phase 2 behavior
    team_yards = _apply_home_field(team_yards, is_home, rng)
    yards = _clamp_yards(state.yard_line, team_yards)

    is_complete = yards > 0
    is_td = (state.yard_line - yards) <= 0

    # Fumble check on completions
    is_fumble = False
    if is_complete and rng.random() < turnover_rates.fumble_rate:
        is_fumble = True

    return PlayResult(
        play_type="pass", yards=yards,
        is_complete=is_complete,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble,
        clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor),
    )


def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
    pace_factor: float = 1.0,
) -> PlayResult:
    from fantasy_sim.engine.player_selector import select_rusher

    rusher_id: str | None = None

    if roster is not None:
        rusher = select_rusher(roster, state, rng)
        rusher_id = rusher.player_id

        # Use player's rushing yards dist if available
        if rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            player_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            # Fall back to team distribution
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            player_yards = play_outcomes.sample_yards("run", bucket, rng)

        raw_yards = _apply_home_field(player_yards, is_home, rng)
        is_safety = (state.yard_line - raw_yards) >= 100
        yards = _clamp_yards(state.yard_line, raw_yards)

        # TD determination with red zone gate
        if state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "run", rng):
                is_td = True
            else:
                # Tackled short of goal line
                short_amount = int(rng.integers(1, max(2, state.yard_line // 3)))
                yards = max(0, state.yard_line - short_amount)
                if yards >= state.yard_line:
                    yards = max(0, state.yard_line - 1)
                is_td = False
        else:
            is_td = (state.yard_line - yards) <= 0

        # Red zone yards blending: cap non-TD runs by team-level distribution
        if not is_td and state.yard_line <= 20 and yards > 0:
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            team_run_yards = play_outcomes.sample_yards("run", bucket, rng)
            yards = min(yards, max(team_run_yards, 1))

        # Use player fumble rate, fall back to team rate if unset
        player_fumble = rusher.outcomes.fumble_rate
        effective_rate = player_fumble if player_fumble > 0 else turnover_rates.fumble_rate
        is_fumble = rng.random() < effective_rate

        return PlayResult(
            play_type="run", yards=yards,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble and not is_safety,
            is_safety=is_safety,
            clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor),
            rusher_id=rusher_id,
        )

    # Legacy path (no roster) — identical to Phase 2 behavior
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    raw_yards = play_outcomes.sample_yards("run", bucket, rng)
    raw_yards = _apply_home_field(raw_yards, is_home, rng)

    # Check safety on raw yards before clamping (ball pushed past own end zone)
    is_safety = (state.yard_line - raw_yards) >= 100

    yards = _clamp_yards(state.yard_line, raw_yards)

    is_td = (state.yard_line - yards) <= 0
    is_fumble = rng.random() < turnover_rates.fumble_rate

    return PlayResult(
        play_type="run", yards=yards,
        is_touchdown=is_td and not is_fumble,
        is_fumble=is_fumble and not is_safety,
        is_safety=is_safety,
        clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor),
    )


def _clamp_yards(yard_line: int, yards: int) -> int:
    """Clamp yards so play doesn't go past either end zone."""
    # Can't gain more than distance to opponent's end zone
    if yards > yard_line:
        yards = yard_line
    # Can't lose past own end zone (safety is handled separately)
    max_loss = -(99 - yard_line)
    if yards < max_loss:
        yards = max_loss
    return yards


def check_penalty(penalty_rates: PenaltyRates, rng: np.random.Generator) -> tuple[str, int] | None:
    """Check if a penalty occurs. Returns (penalty_type, yards) or None."""
    if penalty_rates.penalty_rate <= 0:
        return None
    if rng.random() >= penalty_rates.penalty_rate:
        return None

    types = list(penalty_rates.type_distribution.keys())
    probs = np.array([penalty_rates.type_distribution[t] for t in types])
    if probs.sum() == 0:
        return None
    probs = probs / probs.sum()
    penalty_type = types[rng.choice(len(types), p=probs)]
    yards = int(penalty_rates.avg_yards.get(penalty_type, 5))
    return penalty_type, yards


def apply_penalty(state: GameState, penalty_type: str, penalty_yards: int) -> PlayResult:
    """Create a PlayResult for a penalty. Does NOT mutate state."""
    if penalty_type == "pass_interference":
        return PlayResult(play_type="pass", yards=penalty_yards, is_penalty=True, clock_runoff=0)
    else:
        return PlayResult(play_type="pass", yards=-penalty_yards, is_penalty=True, clock_runoff=0)
