"""Training helpers for learned pass/run play calling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.optimize import minimize

from fantasy_sim.data.play_call_model.models import play_call_feature_values
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class PlayCallTrainingExample:
    features: np.ndarray
    label: int


@dataclass(frozen=True)
class PlayCallFitResult:
    coefficients: dict[str, float]
    objective: float
    converged: bool
    iterations: int
    num_examples: int


def source_seasons_for_artifact(
    *,
    target_season: int,
    min_source_season: int,
    training_years: int,
) -> list[int]:
    start = max(int(min_source_season), int(target_season) - int(training_years))
    return list(range(start, int(target_season)))


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value_f):
        return None
    return value_f


def _state_from_row(row: Mapping[str, object]) -> GameState | None:
    try:
        quarter = int(row.get("qtr") or 1)
        clock = int(row.get("quarter_seconds_remaining") or 0)
        posteam = str(row["posteam"])
        home_team = str(row["home_team"])
        away_team = str(row["away_team"])
        possession = "home" if posteam == home_team else "away"
        posteam_score = int(row.get("posteam_score") or 0)
        defteam_score = int(row.get("defteam_score") or 0)
        if "score_differential" in row and row.get("score_differential") is not None:
            score_differential = int(row["score_differential"])
            if possession == "home":
                home_score = max(0, score_differential)
                away_score = max(0, -score_differential)
            else:
                home_score = max(0, -score_differential)
                away_score = max(0, score_differential)
        else:
            home_score = posteam_score if possession == "home" else defteam_score
            away_score = defteam_score if possession == "home" else posteam_score

        return GameState(
            quarter=quarter,
            clock=clock,
            possession=possession,
            down=int(row["down"]),
            distance=int(row["ydstogo"]),
            yard_line=int(row["yardline_100"]),
            home_score=home_score,
            away_score=away_score,
            home_team=home_team,
            away_team=away_team,
            receiving_2nd_half="away",
            week=int(row.get("week") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return None


def build_example_from_row(
    row: Mapping[str, object],
    feature_names: tuple[str, ...],
) -> PlayCallTrainingExample | None:
    play_type = row.get("play_type")
    if play_type not in {"pass", "run"}:
        return None
    if row.get("posteam") is None or row.get("defteam") is None:
        return None

    state = _state_from_row(row)
    if state is None:
        return None

    posteam = str(row["posteam"])
    defteam = str(row["defteam"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])
    spread_line = _float_or_none(row.get("spread_line"))
    total_line = _float_or_none(row.get("total_line"))
    implied_team_total = None
    team_spread_line = None
    if total_line is None or spread_line is None:
        total_line = None
    else:
        team_spread_line = spread_line
        if posteam == home_team:
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            implied_team_total = total_line / 2.0 - spread_line / 2.0
            team_spread_line = -spread_line

    values = play_call_feature_values(
        state,
        team=posteam,
        opponent=defteam,
        home_team=home_team,
        away_team=away_team,
        is_home=posteam == home_team,
        week=int(row.get("week") or 0),
        spread_line=team_spread_line,
        total_line=total_line,
        implied_team_total=implied_team_total,
        team_prior_pass_rate=0.57,
        opponent_prior_pass_rate_allowed=0.57,
        script=None,
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)):
        return None

    return PlayCallTrainingExample(
        features=features,
        label=1 if play_type == "pass" else 0,
    )


def fit_logistic_play_call(
    examples: list[PlayCallTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> PlayCallFitResult:
    if not examples:
        raise ValueError("Cannot fit play-call model with zero examples")
    if not feature_names:
        raise ValueError("feature_names must not be empty")

    n_features = len(feature_names)
    x = np.vstack([example.features for example in examples]).astype(float)
    y = np.array([example.label for example in examples], dtype=float)
    if x.shape != (len(examples), n_features):
        raise ValueError("Feature matrix shape does not match feature_names")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Training examples must contain finite values")

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = np.clip(x @ beta, -35.0, 35.0)
        loss = float(np.sum(np.logaddexp(0.0, logits) - y * logits))
        loss += 0.5 * l2 * float(np.dot(beta, beta))
        probs = 1.0 / (1.0 + np.exp(-logits))
        grad = x.T @ (probs - y) + l2 * beta
        return loss, grad

    result = minimize(
        objective,
        np.zeros(n_features, dtype=float),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": max_iter},
    )
    return PlayCallFitResult(
        coefficients={
            name: float(value)
            for name, value in zip(feature_names, result.x, strict=True)
        },
        objective=float(result.fun),
        converged=bool(result.success),
        iterations=int(result.nit),
        num_examples=len(examples),
    )
