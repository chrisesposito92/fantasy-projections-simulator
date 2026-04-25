"""Models for learned QB rushing adjustments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fantasy_sim.engine.types import GameState
    from fantasy_sim.models.player import PlayerModel

QB_SCRAMBLE_SCHEMA_VERSION = 1
QB_SCRAMBLE_MODEL_TYPE = "offset_logistic_qb_scramble_v1"
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "decision_v1"

DEFAULT_QB_SCRAMBLE_FEATURES: tuple[str, ...] = (
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
    "qb_prior_scramble_rate",
    "team_prior_scramble_rate",
    "opponent_prior_scramble_rate_allowed",
)


@dataclass(frozen=True)
class QbScrambleModelConfig:
    """Configuration for learned QB scramble probabilities."""

    enabled: bool = False
    artifacts_dir: str | None = None
    factor_clamp: tuple[float, float] = (0.50, 1.75)
    probability_clamp: tuple[float, float] = (0.0, 0.25)
    min_examples: int = 500


@dataclass(frozen=True)
class QbRushingConfig:
    """Configuration for QB rushing model layers."""

    scramble: QbScrambleModelConfig = field(default_factory=QbScrambleModelConfig)


@dataclass(frozen=True)
class QbScrambleContext:
    """Runtime context for a team's learned QB scramble artifact."""

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
    team_prior_scramble_rate: float = 0.05
    opponent_prior_scramble_rate_allowed: float = 0.05
    factor_clamp: tuple[float, float] = (0.50, 1.75)
    probability_clamp: tuple[float, float] = (0.0, 0.25)

    def scramble_probability(self, state: "GameState", passer: "PlayerModel") -> float | None:
        base_rate = float(passer.usage.scramble_rate)
        if not np.isfinite(base_rate):
            return None
        if base_rate <= 0.0:
            return 0.0

        values = qb_scramble_feature_values(
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
            qb_prior_scramble_rate=base_rate,
            team_prior_scramble_rate=self.team_prior_scramble_rate,
            opponent_prior_scramble_rate_allowed=self.opponent_prior_scramble_rate_allowed,
        )
        delta = 0.0
        for name in self.feature_names:
            delta += float(self.coefficients.get(name, 0.0)) * values.get(name, 0.0)
        if not np.isfinite(delta):
            return None

        raw_prob = _sigmoid(_logit(base_rate) + delta)
        if not np.isfinite(raw_prob):
            return None

        factor = raw_prob / base_rate
        if not np.isfinite(factor):
            return None
        factor_lo, factor_hi = self.factor_clamp
        probability_lo, probability_hi = self.probability_clamp
        prob = float(np.clip(base_rate * np.clip(factor, factor_lo, factor_hi), probability_lo, probability_hi))
        if not np.isfinite(prob):
            return None
        return prob


def _logit(probability: float) -> float:
    prob = float(np.clip(probability, 1e-6, 1.0 - 1e-6))
    return float(np.log(prob / (1.0 - prob)))


def _sigmoid(value: float) -> float:
    return float(1.0 / (1.0 + np.exp(-np.clip(value, -35.0, 35.0))))


def qb_scramble_feature_values(
    state: "GameState",
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
    qb_prior_scramble_rate: float,
    team_prior_scramble_rate: float,
    opponent_prior_scramble_rate_allowed: float,
) -> dict[str, float]:
    del team, opponent, home_team, away_team
    distance = max(0, int(state.distance))
    yard_line = max(1, min(99, int(state.yard_line)))
    score_diff = float(state.score_differential)
    clock = max(0, min(900, int(state.clock)))
    quarter = max(1, min(5, int(state.quarter)))
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
        "qb_prior_scramble_rate": float(np.clip(qb_prior_scramble_rate, 0.0, 1.0)),
        "team_prior_scramble_rate": float(np.clip(team_prior_scramble_rate, 0.0, 1.0)),
        "opponent_prior_scramble_rate_allowed": float(
            np.clip(opponent_prior_scramble_rate_allowed, 0.0, 1.0)
        ),
    }
