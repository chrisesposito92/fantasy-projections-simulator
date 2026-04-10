import numpy as np
from fantasy_sim.engine.game_script import RuntimeGameScript, apply_pass_rate_factor
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import PlayCallingDist, KickingModel
from fantasy_sim.models.game_state import bucket_play


def select_play_type(
    state: GameState,
    play_calling: PlayCallingDist,
    rng: np.random.Generator,
    script: RuntimeGameScript | None = None,
) -> str:
    """Select run or pass based on game state and team tendencies."""
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    probs = play_calling.get_probs(bucket)
    if script is not None and script.pass_rate_factor != 1.0:
        probs = apply_pass_rate_factor(probs, script.pass_rate_factor)
    play_types = list(probs.keys())
    probabilities = list(probs.values())
    return rng.choice(play_types, p=probabilities)


def fourth_down_decision(state: GameState, kicking: KickingModel) -> str:
    """Decide punt, field_goal, or go_for_it on 4th down."""
    fg_distance = state.yard_line + 17  # 7yd snap + 10yd end zone

    # Go for it near the goal line (inside the 5, short yardage) — prioritize over FG
    if state.yard_line <= 5 and state.distance <= 3:
        return "go_for_it"

    # Go for it on short yardage in opponent's half
    if state.distance <= 2 and state.yard_line <= 45:
        return "go_for_it"

    # Attempt FG if distance is reasonable and probability is decent
    if fg_distance <= 55:
        if kicking.fg_prob(fg_distance) >= 0.40:
            return "field_goal"

    return "punt"
