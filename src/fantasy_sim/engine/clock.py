import numpy as np
from fantasy_sim.engine.types import GameState
from fantasy_sim.engine.game_flow import perform_kickoff
from fantasy_sim.models.distributions import DriveStartModel

QUARTER_SECONDS = 900
OT_SECONDS = 600
TWO_MINUTE_MARK = 120


def apply_clock(state: GameState, runoff: int) -> None:
    """Subtract clock runoff, clamping to zero."""
    state.clock = max(0, state.clock - runoff)


def check_two_minute_warning(state: GameState) -> None:
    """If clock just crossed below 120 in Q2/Q4, snap it back to 120. Fires once per half."""
    if state.quarter not in (2, 4):
        return
    if state.clock < TWO_MINUTE_MARK and not state.two_min_warning_fired:
        state.clock = TWO_MINUTE_MARK
        state.two_min_warning_fired = True


def check_quarter_end(
    state: GameState,
    home_drive_start: DriveStartModel,
    away_drive_start: DriveStartModel,
    rng: np.random.Generator,
) -> None:
    """Check if the quarter has ended and handle transitions."""
    if state.clock > 0:
        return

    if state.quarter == 1:
        # Q1 → Q2: teams switch ends, same possession continues
        state.quarter = 2
        state.clock = QUARTER_SECONDS

    elif state.quarter == 2:
        # Halftime → Q3: second-half receiving team gets kickoff
        state.quarter = 3
        state.clock = QUARTER_SECONDS
        state.two_min_warning_fired = False
        state.possession = state.receiving_2nd_half
        recv_dists = home_drive_start if state.possession == "home" else away_drive_start
        perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 3:
        # Q3 → Q4
        state.quarter = 4
        state.clock = QUARTER_SECONDS

    elif state.quarter == 4:
        # End of regulation
        if state.home_score != state.away_score:
            state.game_over = True
        else:
            # Overtime
            state.quarter = 5
            state.clock = OT_SECONDS
            # Coin toss for OT — random team receives
            ot_receiver = "home" if rng.random() < 0.5 else "away"
            state.possession = ot_receiver
            recv_dists = home_drive_start if ot_receiver == "home" else away_drive_start
            perform_kickoff(state, recv_dists, rng)

    elif state.quarter == 5:
        # OT period ended — in regular season, game ends as tie
        state.game_over = True
