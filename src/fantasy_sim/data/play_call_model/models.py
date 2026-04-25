"""Models and feature helpers for learned pass/run play calling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fantasy_sim.engine.game_script import RuntimeGameScript
    from fantasy_sim.engine.types import GameState

PLAY_CALL_MODEL_SCHEMA_VERSION = 1
PLAY_CALL_MODEL_TYPE = "logistic_play_call_v1"
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "decision_v1"

DEFAULT_PLAY_CALL_FEATURES: tuple[str, ...] = (
    "intercept",
    "down_1",
    "down_2",
    "down_3",
    "down_4",
    "distance_norm",
    "is_short",
    "is_long",
    "is_very_long",
    "yard_line_norm",
    "is_red_zone",
    "is_goal_to_go",
    "quarter_1",
    "quarter_2",
    "quarter_3",
    "quarter_4",
    "clock_norm",
    "is_two_minute",
    "score_diff_norm",
    "is_trailing",
    "is_leading",
    "is_home",
    "spread_norm",
    "total_norm",
    "implied_total_norm",
    "week_norm",
    "team_prior_pass_rate",
    "opponent_prior_pass_rate_allowed",
    "trailing_late",
)


@dataclass(frozen=True)
class PlayCallModelConfig:
    """Configuration for the learned pass/run play-call node."""

    enabled: bool = False
    artifacts_dir: str | None = None
    probability_clamp: tuple[float, float] = (0.05, 0.95)


@dataclass(frozen=True)
class PlayCallContext:
    """Runtime context for a team's learned play-call artifact."""

    coefficients: dict[str, float]
    feature_names: tuple[str, ...]
    team: str
    opponent: str
    home_team: str
    away_team: str
    is_home: bool
    target_season: int
    week: int
    spread_line: float | None = None
    total_line: float | None = None
    implied_team_total: float | None = None
    team_prior_pass_rate: float = 0.57
    opponent_prior_pass_rate_allowed: float = 0.57
    probability_clamp: tuple[float, float] = (0.05, 0.95)

    def pass_probability(
        self,
        state: GameState,
        script: RuntimeGameScript | None = None,
    ) -> float | None:
        values = play_call_feature_values(
            state,
            team=self.team,
            opponent=self.opponent,
            home_team=self.home_team,
            away_team=self.away_team,
            is_home=self.is_home,
            week=self.week,
            spread_line=self.spread_line,
            total_line=self.total_line,
            implied_team_total=self.implied_team_total,
            team_prior_pass_rate=self.team_prior_pass_rate,
            opponent_prior_pass_rate_allowed=self.opponent_prior_pass_rate_allowed,
            script=script,
        )
        logit = 0.0
        for name in self.feature_names:
            logit += float(self.coefficients.get(name, 0.0)) * values.get(name, 0.0)
        if not np.isfinite(logit):
            return None
        prob = float(1.0 / (1.0 + np.exp(-np.clip(logit, -35.0, 35.0))))
        lo, hi = self.probability_clamp
        prob = float(np.clip(prob, lo, hi))
        if not np.isfinite(prob):
            return None
        return prob


def play_call_feature_values(
    state: GameState,
    *,
    team: str,
    opponent: str,
    home_team: str,
    away_team: str,
    is_home: bool,
    week: int,
    spread_line: float | None,
    total_line: float | None,
    implied_team_total: float | None,
    team_prior_pass_rate: float,
    opponent_prior_pass_rate_allowed: float,
    script: RuntimeGameScript | None = None,
) -> dict[str, float]:
    del team, opponent, home_team, away_team
    distance = max(0, int(state.distance))
    yard_line = max(1, min(99, int(state.yard_line)))
    score_diff = float(state.score_differential)
    clock = max(0, min(900, int(state.clock)))
    quarter = max(1, min(5, int(state.quarter)))
    trailing_late = 1.0 if getattr(script, "regime", None) == "trailing_late" else 0.0
    spread = 0.0 if spread_line is None else float(spread_line)
    total = 44.0 if total_line is None else float(total_line)
    implied = total / 2.0 if implied_team_total is None else float(implied_team_total)

    return {
        "intercept": 1.0,
        "down_1": 1.0 if state.down == 1 else 0.0,
        "down_2": 1.0 if state.down == 2 else 0.0,
        "down_3": 1.0 if state.down == 3 else 0.0,
        "down_4": 1.0 if state.down == 4 else 0.0,
        "distance_norm": min(distance, 20) / 20.0,
        "is_short": 1.0 if distance <= 3 else 0.0,
        "is_long": 1.0 if 7 <= distance <= 10 else 0.0,
        "is_very_long": 1.0 if distance > 10 else 0.0,
        "yard_line_norm": yard_line / 100.0,
        "is_red_zone": 1.0 if yard_line <= 20 else 0.0,
        "is_goal_to_go": 1.0 if yard_line <= distance else 0.0,
        "quarter_1": 1.0 if quarter == 1 else 0.0,
        "quarter_2": 1.0 if quarter == 2 else 0.0,
        "quarter_3": 1.0 if quarter == 3 else 0.0,
        "quarter_4": 1.0 if quarter == 4 else 0.0,
        "clock_norm": clock / 900.0,
        "is_two_minute": 1.0 if clock <= 120 and quarter in (2, 4) else 0.0,
        "score_diff_norm": float(np.clip(score_diff / 28.0, -1.0, 1.0)),
        "is_trailing": 1.0 if score_diff < 0 else 0.0,
        "is_leading": 1.0 if score_diff > 0 else 0.0,
        "is_home": 1.0 if is_home else 0.0,
        "spread_norm": float(np.clip(spread / 14.0, -1.5, 1.5)),
        "total_norm": float(np.clip((total - 44.0) / 14.0, -1.5, 1.5)),
        "implied_total_norm": float(np.clip((implied - 22.0) / 10.0, -1.5, 1.5)),
        "week_norm": float(np.clip(week / 18.0, 0.0, 1.0)),
        "team_prior_pass_rate": float(np.clip(team_prior_pass_rate, 0.0, 1.0)),
        "opponent_prior_pass_rate_allowed": float(
            np.clip(opponent_prior_pass_rate_allowed, 0.0, 1.0)
        ),
        "trailing_late": trailing_late,
    }
