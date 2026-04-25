"""Models for learned QB rushing adjustments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
