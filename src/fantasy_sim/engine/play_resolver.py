from __future__ import annotations

import numpy as np
from fantasy_sim.config.loader import get_phase1_ks_flags
from fantasy_sim.engine.types import (
    GameState,
    PlayResult,
    QbDesignedRunContextProtocol,
    QbScrambleContextProtocol,
    TargetSelectionContextProtocol,
)
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates, PenaltyRates
from fantasy_sim.models.game_state import GameStateBucket, bucket_play

# Avoid circular imports — TYPE_CHECKING is compile-time only
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from fantasy_sim.engine.game_script import RuntimeGameScript
    from fantasy_sim.models.player import TeamRoster

# Phase 1 KS-01 feature flag (Cycle 3 D-45). Read once at module import; the
# flag picks between the legacy `_tackled_short` rewrite (default) and the new
# `_tackled_short_preserve_distribution` variant per D-09. validate.py runs both
# A/B arms in a single Python process, so flag flips during a process require
# a process restart — the bare-isolation A/B harness already does this between
# arms via fresh GameContextBuilder construction.
_KS01_PRESERVE_DIST = (
    get_phase1_ks_flags()
    .get("ks01_preserve_distribution", {})
    .get("enabled", False)
)

# Phase 1 KS-04 feature flag (Cycle 3 D-45). When enabled, switches the
# CATCH_YARDS_BOOST policy from "unconditional +1 outside the RZ" to
# "conditional +`_KS04_BOOST_VALUE` only when the un-clamped sample would
# have been clipped by `_clamp_yards`" per D-11/D-12. The new path is the
# Arm B genuine code-path flip; the legacy path (flag off) keeps the
# pre-Phase-1 unconditional `+1` behavior so Arm A is preserved.
_KS04_CONDITIONAL_BOOST = (
    get_phase1_ks_flags()
    .get("ks04_conditional_catch_boost", {})
    .get("enabled", False)
)
_KS04_BOOST_VALUE = float(
    get_phase1_ks_flags()
    .get("ks04_conditional_catch_boost", {})
    .get("boost_value", 1.5)
)

# Average clock runoff in seconds — calibrated for ~65 plays/team/game
CLOCK_RUN = 35
CLOCK_PASS_COMPLETE = 30
CLOCK_PASS_INCOMPLETE = 5
CLOCK_SACK = 35

# Calibration: per-player yards distributions are field-position-independent,
# but the sim samples them at specific field positions where _clamp_yards()
# truncates long catches (e.g., a 30-yard catch at the 20 is clamped to 20).
# This systematically reduces yards/completion vs the distribution mean.
# A conditional additive boost compensates without changing the distribution
# shape or game physics — when KS-04 is enabled (D-11), the boost is applied
# only when the un-clamped sample would have been clipped by _clamp_yards
# (i.e., raw_sample > yard_line). KS-15 (planned) will obviate this entirely.
# The constant value reflects D-12 (`+1.5`); the legacy unconditional code
# path (flag off) hardcodes `+1` to preserve pre-Phase-1 Arm A behavior.
CATCH_YARDS_BOOST = 1.5

# Sack yardage loss distribution
SACK_YARDS = np.array([-3, -4, -5, -5, -6, -7, -7, -8, -8, -10])

# Home-field advantage: 50% chance of +1 yard per play
HOME_FIELD_YARDS_BONUS = 0.5

# Red zone TD gate probabilities — per-play probability that a would-be TD
# actually scores. Calibrated so that drive-level TD rates match NFL averages
# (~55% of RZ drives end in TD) given realistic RZ drive progression.
PASS_TD_GATE = {
    (1, 3): 0.55,
    (4, 5): 0.50,
    (6, 10): 0.45,
    (11, 15): 0.25,
    (16, 20): 0.15,
}

RUN_TD_GATE = {
    (1, 3): 0.35,
    (4, 5): 0.30,
    (6, 10): 0.20,
    (11, 15): 0.12,
    (16, 20): 0.08,
}

# League-average red zone catch rate modifier (RZ completion % / overall %)
RZ_CATCH_RATE_MODIFIER = 0.92


def _red_zone_td_gate(yard_line: int, play_type: str, rng: np.random.Generator, td_factor: float = 1.0) -> bool:
    """Check if a would-be TD actually scores, based on field position.

    Returns True if the TD stands, False if the player is tackled short.
    Outside the red zone (yard_line > 20), always returns True.

    Args:
        td_factor: Player-level multiplier on the base gate probability.
            Centered on 1.0 (neutral). Values > 1.0 increase TD rate,
            < 1.0 decrease it. Clamped so effective probability never exceeds 1.0.
    """
    if yard_line > 20:
        return True
    gate_table = PASS_TD_GATE if play_type == "pass" else RUN_TD_GATE
    for (lo, hi), prob in gate_table.items():
        if lo <= yard_line <= hi:
            return rng.random() < min(1.0, prob * td_factor)
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
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
    target_selection_context: TargetSelectionContextProtocol | None = None,
    qb_scramble_context: QbScrambleContextProtocol | None = None,
    qb_designed_run_context: QbDesignedRunContextProtocol | None = None,
) -> PlayResult:
    if play_type == "pass":
        return _resolve_pass(
            state,
            play_outcomes,
            turnover_rates,
            rng,
            roster,
            is_home,
            pace_factor,
            goal_line_concentration_enabled,
            script,
            target_selection_context,
            qb_scramble_context,
        )
    if play_type == "run":
        return _resolve_run(
            state,
            play_outcomes,
            turnover_rates,
            rng,
            roster,
            is_home,
            pace_factor,
            goal_line_concentration_enabled,
            script,
            qb_designed_run_context,
        )
    raise ValueError(f"Unexpected play_type: {play_type!r}")


def _resolve_pass(
    state: GameState,
    play_outcomes: PlayOutcomeDist,
    turnover_rates: TurnoverRates,
    rng: np.random.Generator,
    roster: TeamRoster | None = None,
    is_home: bool = False,
    pace_factor: float = 1.0,
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
    target_selection_context: TargetSelectionContextProtocol | None = None,
    qb_scramble_context: QbScrambleContextProtocol | None = None,
) -> PlayResult:
    # Lazy import to avoid circular dependencies
    from fantasy_sim.engine.player_selector import select_passer, select_receiver

    passer_id: str | None = None
    receiver_id: str | None = None

    if roster is not None:
        passer = select_passer(roster, state)
        passer_id = passer.player_id

        scramble_rate = passer.usage.scramble_rate
        if qb_scramble_context is not None:
            context_rate = qb_scramble_context.scramble_probability(state, passer)
            if context_rate is not None and np.isfinite(context_rate):
                scramble_rate = float(np.clip(context_rate, 0.0, 1.0))

        # QB scramble check: before sack/int, the QB decides to run.
        if scramble_rate > 0 and rng.random() < scramble_rate:
            scramble_yards_dist = passer.outcomes.scramble_yards_dist
            if scramble_yards_dist is not None and len(scramble_yards_dist) > 0:
                raw_yards = int(rng.choice(scramble_yards_dist))
            else:
                # Fall back to team run distribution
                raw_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)
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
        receiver = select_receiver(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
            script=script,
            target_selection_context=target_selection_context,
        )
        receiver_id = receiver.player_id

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
            full_dist = receiver.outcomes.receiving_yards_dist
            # Sample raw yards first so the KS-04 conditional branch (D-11)
            # can inspect the un-clamped value before deciding whether to add
            # the boost. The legacy code added the boost unconditionally
            # outside the RZ; KS-04 conditions on the clamp actually firing.
            if full_dist is not None and len(full_dist) > 0:
                raw_sample = int(rng.choice(full_dist))
            else:
                # Fallback: sample from team distribution (only when player lacks personal dist)
                team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
                raw_sample = team_yards if team_yards > 0 else int(rng.integers(3, 12))

            # KS-04 D-11 (Cycle 3 D-45): when the flag is on, apply boost
            # ONLY when _clamp_yards would actually fire (raw_sample >
            # yard_line) AND we are outside the red zone. Inside the RZ the
            # TD gate controls scoring and the boost would inflate TDs.
            # When the flag is off, fall back to the legacy unconditional
            # `+1` outside-RZ boost so Arm A is bit-for-bit identical to
            # pre-Phase-1 behavior (preserves the genuine two-arm A/B).
            if _KS04_CONDITIONAL_BOOST:
                if state.yard_line > 20 and raw_sample > state.yard_line:
                    player_yards = raw_sample + _KS04_BOOST_VALUE
                else:
                    player_yards = raw_sample
                # `_apply_home_field` and `_clamp_yards` expect ints; round
                # at the boundary because _KS04_BOOST_VALUE is a float (1.5).
                if isinstance(player_yards, float):
                    player_yards = int(round(player_yards))
            else:
                # Legacy unconditional boost (`+1` outside RZ, 0 inside).
                legacy_boost = 1 if state.yard_line > 20 else 0
                player_yards = raw_sample + legacy_boost

            yards = _apply_home_field(player_yards, is_home, rng)
            yards = _clamp_yards(state.yard_line, yards)
        else:
            yards = 0

        # TD determination with red zone gate
        if is_complete and state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            if _red_zone_td_gate(state.yard_line, "pass", rng, receiver.outcomes.receiving_td_factor):
                is_td = True
            else:
                # KS-01 (D-09 / Cycle 3 D-45): when the flag is on, preserve the
                # sampled distribution by capping at yard_line - 1 instead of
                # overwriting with the legacy strictly-shorter rewrite.
                # `player_yards` is the pre-`_clamp_yards`, pre-`_apply_home_field`
                # value sampled from the receiver's distribution (line 267 / 271).
                if _KS01_PRESERVE_DIST:
                    yards = _tackled_short_preserve_distribution(state.yard_line, player_yards)
                else:
                    yards = _tackled_short(state.yard_line, rng)
                is_td = False
        else:
            is_td = is_complete and (state.yard_line - yards) <= 0

        is_fumble = False
        if is_complete:
            is_fumble = _check_fumble(receiver.outcomes.fumble_rate, turnover_rates.fumble_rate, rng)

        return PlayResult(
            play_type="pass", yards=yards,
            is_complete=is_complete,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble,
            clock_runoff=_scale_clock_runoff(CLOCK_PASS_COMPLETE if is_complete else CLOCK_PASS_INCOMPLETE, pace_factor),
            passer_id=passer_id,
            receiver_id=receiver_id,
        )

    # Legacy path (no roster) — sample from team distribution
    team_yards = play_outcomes.sample_yards("pass", _bucket_from_state(state), rng)
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
    goal_line_concentration_enabled: bool = False,
    script: RuntimeGameScript | None = None,
    qb_designed_run_context: QbDesignedRunContextProtocol | None = None,
) -> PlayResult:
    from fantasy_sim.engine.player_selector import select_rusher

    rusher_id: str | None = None

    if roster is not None:
        rusher = select_rusher(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
            script=script,
            qb_designed_run_context=qb_designed_run_context,
        )
        rusher_id = rusher.player_id

        context_yards = None
        if qb_designed_run_context is not None and rusher.position == "QB":
            context_yards = qb_designed_run_context.designed_run_yards(state, rusher, rng, script=script)

        if context_yards is not None:
            player_yards = int(context_yards)
        elif rusher.outcomes.rushing_yards_dist is not None and len(rusher.outcomes.rushing_yards_dist) > 0:
            player_yards = int(rng.choice(rusher.outcomes.rushing_yards_dist))
        else:
            player_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)

        raw_yards = _apply_home_field(player_yards, is_home, rng)
        is_safety = (state.yard_line - raw_yards) >= 100
        yards = _clamp_yards(state.yard_line, raw_yards)

        # TD determination with red zone gate
        if state.yard_line <= 20 and (state.yard_line - yards) <= 0:
            # Use inside-5 factor at goal line when available
            if state.yard_line <= 5 and rusher.outcomes.i5_rushing_td_factor != 1.0:
                td_factor = rusher.outcomes.i5_rushing_td_factor
            else:
                td_factor = rusher.outcomes.rushing_td_factor
            if _red_zone_td_gate(state.yard_line, "run", rng, td_factor):
                is_td = True
            else:
                # KS-01 (D-09 / Cycle 3 D-45): preserve the sampled distribution
                # when the flag is on. `raw_yards` is the post-`_apply_home_field`,
                # pre-`_clamp_yards` rushing value (line 362).
                if _KS01_PRESERVE_DIST:
                    yards = _tackled_short_preserve_distribution(state.yard_line, raw_yards)
                else:
                    yards = _tackled_short(state.yard_line, rng)
                is_td = False
        else:
            is_td = (state.yard_line - yards) <= 0

        is_fumble = _check_fumble(rusher.outcomes.fumble_rate, turnover_rates.fumble_rate, rng)

        return PlayResult(
            play_type="run", yards=yards,
            is_touchdown=is_td and not is_fumble,
            is_fumble=is_fumble and not is_safety,
            is_safety=is_safety,
            clock_runoff=_scale_clock_runoff(CLOCK_RUN, pace_factor),
            rusher_id=rusher_id,
        )

    # Legacy path (no roster)
    raw_yards = play_outcomes.sample_yards("run", _bucket_from_state(state), rng)
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


def _bucket_from_state(state: GameState) -> GameStateBucket:
    """Build a GameStateBucket from the current game state."""
    return bucket_play(
        state.down, state.distance, state.score_differential,
        state.quarter, state.yard_line,
    )


def _tackled_short_preserve_distribution(yard_line: int, sampled_yards_pre_clamp: int) -> int:
    """KS-01: when the RZ TD gate fails, preserve the sampled distribution.

    Returns ``yards = max(1, min(yard_line - 1, sampled_yards_pre_clamp))``
    per D-09. Reserves 1 yard short of the goal so the play does not score;
    preserves the rest of the catch / run distribution rather than overwriting
    it with a strictly-shorter integer (the legacy ``_tackled_short`` behavior).

    Gated behind ``phase1_ks_flags.ks01_preserve_distribution.enabled`` (default
    ``false``) per Cycle 3 D-45 — so the per-KS A/B genuinely measures the
    marginal effect of this code path vs. the legacy ``_tackled_short`` rewrite.
    """
    return max(1, min(yard_line - 1, sampled_yards_pre_clamp))


def _tackled_short(yard_line: int, rng: np.random.Generator) -> int:
    """Determine yards gained when a player is tackled short of the goal line."""
    short_amount = int(rng.integers(1, max(2, yard_line // 3)))
    return max(0, yard_line - short_amount)


def _check_fumble(
    player_fumble_rate: float,
    team_fumble_rate: float,
    rng: np.random.Generator,
) -> bool:
    """Roll for fumble using player rate, falling back to team rate."""
    rate = player_fumble_rate if player_fumble_rate > 0 else team_fumble_rate
    return rng.random() < rate


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
