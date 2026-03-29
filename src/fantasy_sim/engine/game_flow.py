import numpy as np
from fantasy_sim.engine.types import GameState, TeamBoxScore, PlayResult
from fantasy_sim.models.distributions import KickingModel, DriveStartModel

# Punt net yards distribution
PUNT_NET_YARDS = np.array([35, 38, 40, 42, 44, 45, 45, 46, 48, 50, 52, 55])

# PAT/2PT constants
TWO_POINT_ATTEMPT_RATE = 0.06
TWO_POINT_SUCCESS_RATE = 0.48


def apply_yards(state: GameState, yards: int) -> None:
    """Apply yards gained to game state. Handles first downs and turnover on downs.

    Precondition: caller must handle touchdowns (yard_line - yards <= 0) before
    calling this function. Passing a touchdown play here will produce invalid state.
    """
    state.yard_line -= yards

    if yards >= state.distance:
        # First down
        state.down = 1
        state.distance = min(10, state.yard_line)  # Can't need more than yards to goal
    elif state.down == 4:
        # Failed 4th down — turnover on downs
        change_possession(state)
        state.yard_line = 100 - state.yard_line
        state.down = 1
        state.distance = 10
    else:
        state.down += 1
        state.distance -= yards


def change_possession(state: GameState) -> None:
    """Flip possession between home and away."""
    state.possession = "away" if state.possession == "home" else "home"


def score_points(state: GameState, points: int) -> None:
    """Add points to the possessing team's score."""
    if state.possession == "home":
        state.home_score += points
    else:
        state.away_score += points


def handle_turnover(state: GameState, result: PlayResult) -> None:
    """Handle interception or fumble — flip possession at the spot."""
    spot = state.yard_line - result.yards
    change_possession(state)
    state.yard_line = 100 - spot
    state.down = 1
    state.distance = 10


def perform_kickoff(
    state: GameState, drive_start: DriveStartModel, rng: np.random.Generator
) -> None:
    """Set up receiving team's starting field position after a kickoff."""
    state.yard_line = drive_start.sample_start_yardline(rng)
    state.down = 1
    state.distance = 10


def perform_punt(
    state: GameState, rng: np.random.Generator, off_box: TeamBoxScore
) -> None:
    """Execute a punt and give the ball to the other team."""
    off_box.punts += 1
    net_yards = int(rng.choice(PUNT_NET_YARDS))
    landing_yl = state.yard_line - net_yards

    change_possession(state)

    if landing_yl <= 0:
        # Touchback — opponent starts at own 25
        state.yard_line = 75
    else:
        state.yard_line = 100 - landing_yl

    state.down = 1
    state.distance = 10


def attempt_field_goal(
    state: GameState,
    kicking: KickingModel,
    drive_start: DriveStartModel,
    rng: np.random.Generator,
    off_box: TeamBoxScore,
) -> None:
    """Attempt a field goal. Made = 3 points + kickoff. Missed = opponent takes over."""
    fg_distance = state.yard_line + 17
    off_box.fg_attempts += 1

    if rng.random() < kicking.fg_prob(fg_distance):
        # Made
        off_box.fg_made += 1
        score_points(state, 3)
        off_box.points += 3
        change_possession(state)
        perform_kickoff(state, drive_start, rng)
    else:
        # Missed — opponent takes over at spot of kick (or own 20, whichever better)
        spot = state.yard_line + 7  # Snap spot
        change_possession(state)
        state.yard_line = max(100 - spot, 80)  # At least own 20
        state.down = 1
        state.distance = 10


def attempt_pat(
    state: GameState,
    kicking: KickingModel,
    rng: np.random.Generator,
    off_box: TeamBoxScore,
) -> None:
    """Attempt PAT (extra point or 2-point conversion) after a touchdown."""
    if rng.random() < TWO_POINT_ATTEMPT_RATE:
        # 2-point attempt
        if rng.random() < TWO_POINT_SUCCESS_RATE:
            score_points(state, 2)
            off_box.points += 2
    else:
        # Extra point
        off_box.xp_attempts += 1
        if rng.random() < kicking.xp_rate:
            score_points(state, 1)
            off_box.points += 1
            off_box.xp_made += 1
