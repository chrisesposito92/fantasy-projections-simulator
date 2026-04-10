from __future__ import annotations

from dataclasses import dataclass, field

from fantasy_sim.data.game_script import (
    GameScriptConfig,
    GameScriptProfile,
    RbRankFactors,
    TargetRankFactors,
)
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class RuntimeGameScript:
    regime: str = "neutral"
    pass_rate_factor: float = 1.0
    pace_factor: float = 1.0
    target_factors: TargetRankFactors = field(default_factory=TargetRankFactors)
    rb_factors: RbRankFactors = field(default_factory=RbRankFactors)


def resolve_game_script(
    state: GameState,
    config: GameScriptConfig | None,
    profile: GameScriptProfile | None,
) -> RuntimeGameScript:
    if config is None or profile is None or not config.enabled:
        return RuntimeGameScript()

    if (
        state.quarter == 4
        and config.trailing_late.enabled
        and state.score_differential <= -config.trailing_late.deficit_threshold
    ):
        return RuntimeGameScript(
            regime="trailing_late",
            pass_rate_factor=profile.trailing_late_pass_rate_factor,
            pace_factor=profile.trailing_late_pace_factor,
            target_factors=profile.trailing_late_target_factors,
        )

    if (
        state.quarter == 4
        and config.trailing_late.enabled
        and state.clock <= config.trailing_late.final_five_minutes
        and state.score_differential <= -config.trailing_late.final_five_deficit_threshold
    ):
        return RuntimeGameScript(
            regime="trailing_late",
            pass_rate_factor=profile.trailing_late_pass_rate_factor,
            pace_factor=profile.trailing_late_pace_factor,
            target_factors=profile.trailing_late_target_factors,
        )

    if (
        state.quarter == 4
        and config.leading_late_rb.enabled
        and state.clock <= config.leading_late_rb.late_minutes
        and state.score_differential >= config.leading_late_rb.lead_threshold
    ):
        return RuntimeGameScript(
            regime="leading_late_rb",
            rb_factors=profile.leading_late_rb_factors,
        )

    return RuntimeGameScript()


def apply_pass_rate_factor(probs: dict[str, float], factor: float) -> dict[str, float]:
    pass_prob = min(0.99, max(0.01, probs["pass"] * factor))
    return {"pass": pass_prob, "run": 1.0 - pass_prob}


def effective_pace_factor(base_pace: float, script: RuntimeGameScript | None) -> float:
    if script is None:
        return base_pace
    return base_pace * script.pace_factor
