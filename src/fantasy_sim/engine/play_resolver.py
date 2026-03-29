import numpy as np
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.game_state import bucket_play

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
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(state, play_outcomes, turnover_rates, rng)
    if play_type == "run":
        return _resolve_run(state, play_outcomes, turnover_rates, rng)
    raise ValueError(f"Unexpected play_type: {play_type!r}")


def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
) -> PlayResult:
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
        )

    # Check for interception
    if rng.random() < turnover_rates.int_rate:
        return PlayResult(
            play_type="pass", yards=0, is_interception=True,
            clock_runoff=CLOCK_PASS_INCOMPLETE,
        )

    # Normal pass
    bucket = bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )
    yards = play_outcomes.sample_yards("pass", bucket, rng)
    yards = _clamp_yards(state.yard_line, yards)

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
) -> PlayResult:
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
