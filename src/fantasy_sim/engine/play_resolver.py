from __future__ import annotations

import numpy as np
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates
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


def resolve_play(
    state: GameState,
    play_type: str,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng, roster)
    if play_type == "run":
        return _resolve_run(state, play_outcomes, turnover_rates, rng, roster)
    raise ValueError(f"Unexpected play_type: {play_type!r}")


def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
) -> PlayResult:
    # Lazy import to avoid circular dependencies
    from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher

    passer_id: str | None = None
    receiver_id: str | None = None

    if roster is not None:
        passer = select_passer(roster)
        passer_id = passer.player_id

        # QB scramble check — before sack/int, the QB decides to run
        if passer.usage.scramble_rate > 0 and rng.random() < passer.usage.scramble_rate:
            scramble_yards_dist = passer.outcomes.scramble_yards_dist
            if scramble_yards_dist is not None and len(scramble_yards_dist) > 0:
                yards = int(rng.choice(scramble_yards_dist))
            else:
                # Fall back to team run distribution
                bucket = bucket_play(
                    state.down, state.distance, state.score_differential,
                    state.quarter, state.yard_line,
                )
                yards = play_outcomes.sample_yards("run", bucket, rng)
            yards = _clamp_yards(state.yard_line, yards)
            is_td = (state.yard_line - yards) <= 0
            is_fumble = rng.random() < passer.outcomes.fumble_rate
            return PlayResult(
                play_type="run", yards=yards,
                is_touchdown=is_td and not is_fumble,
                is_fumble=is_fumble,
                rusher_id=passer_id,
                passer_id=passer_id,
                clock_runoff=CLOCK_RUN,
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
            clock_runoff=CLOCK_SACK,
            passer_id=passer_id,
        )

    # Check for interception
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=CLOCK_PASS_INCOMPLETE,
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
        is_complete = rng.random() < receiver.outcomes.catch_rate

        if is_complete:
            # Use player's receiving yards dist if available, otherwise team dist
            if receiver.outcomes.receiving_yards_dist is not None and len(receiver.outcomes.receiving_yards_dist) > 0:
                yards = int(rng.choice(receiver.outcomes.receiving_yards_dist))
            else:
                yards = max(team_yards, 1)  # Complete pass must gain at least 1 yard
            yards = _clamp_yards(state.yard_line, yards)
        else:
            yards = 0

        is_td = is_complete and (state.yard_line - yards) <= 0

        # Fumble check on completions — use player fumble rate
        is_fumble = False
        if is_complete and rng.random() < receiver.outcomes.fumble_rate:
            is_fumble = True

        return PlayResult(
            play_type="pass", yards=yards,
            is_complete=is_complete,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble,
            clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
            passer_id=passer_id,
            receiver_id=receiver_id,
        )

    # Legacy path (no roster) — identical to Phase 2 behavior
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
        clock_runoff=CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE,
    )


def _resolve_run(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
) -> PlayResult:
    from fantasy_sim.engine.player_selector import select_rusher

    rusher_id: str | None = None

    if roster is not None:
        rusher = select_rusher(roster, state, rng)
        rusher_id = rusher.player_id

        # Use player's rushing yards dist if available
        if rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            raw_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            # Fall back to team distribution
            bucket = bucket_play(
                state.down, state.distance, state.score_differential,
                state.quarter, state.yard_line,
            )
            raw_yards = play_outcomes.sample_yards("run", bucket, rng)

        is_safety = (state.yard_line - raw_yards) >= 100
        yards = _clamp_yards(state.yard_line, raw_yards)
        is_td = (state.yard_line - yards) <= 0

        # Use player fumble rate
        is_fumble = rng.random() < rusher.outcomes.fumble_rate

        return PlayResult(
            play_type="run", yards=yards,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble and not is_safety,
            is_safety=is_safety,
            clock_runoff=CLOCK_RUN,
            rusher_id=rusher_id,
        )

    # Legacy path (no roster) — identical to Phase 2 behavior
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    raw_yards = play_outcomes.sample_yards("run", bucket, rng)

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
        clock_runoff=CLOCK_RUN,
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
