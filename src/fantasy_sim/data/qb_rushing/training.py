"""Training helpers for learned QB scramble probabilities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

import numpy as np
from scipy.optimize import minimize

from fantasy_sim.data.qb_rushing.models import _logit, qb_scramble_feature_values
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class QbScramblePriors:
    qb: dict[str, float]
    team: dict[str, float]
    opponent_allowed: dict[str, float]
    league: float


@dataclass(frozen=True)
class QbScrambleTrainingExample:
    features: np.ndarray
    label: int
    base_rate: float


@dataclass(frozen=True)
class QbScrambleFitResult:
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


def build_scramble_priors(rows: list[Mapping[str, object]]) -> QbScramblePriors:
    qb_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    team_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    opponent_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    league_scrambles = 0
    league_total = 0

    for row in rows:
        if not _is_modeled_row(row):
            continue
        label = _scramble_label(row)
        qb_id = row.get("passer_player_id")
        team = row.get("posteam")
        opponent = row.get("defteam")
        league_scrambles += label
        league_total += 1
        if qb_id is not None:
            qb_counts[str(qb_id)][0] += label
            qb_counts[str(qb_id)][1] += 1
        if team is not None:
            team_counts[str(team)][0] += label
            team_counts[str(team)][1] += 1
        if opponent is not None:
            opponent_counts[str(opponent)][0] += label
            opponent_counts[str(opponent)][1] += 1

    league = league_scrambles / league_total if league_total else 0.0
    return QbScramblePriors(
        qb={key: counts[0] / counts[1] for key, counts in qb_counts.items()},
        team={key: counts[0] / counts[1] for key, counts in team_counts.items()},
        opponent_allowed={key: counts[0] / counts[1] for key, counts in opponent_counts.items()},
        league=league,
    )


def build_example_from_row(
    row: Mapping[str, object],
    feature_names: tuple[str, ...],
    priors: QbScramblePriors,
) -> QbScrambleTrainingExample | None:
    if not _is_modeled_row(row):
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
    qb_id = str(row.get("passer_player_id") or "")
    qb_prior = priors.qb.get(qb_id, priors.team.get(posteam, priors.league))
    team_prior = priors.team.get(posteam, priors.league)
    opponent_prior = priors.opponent_allowed.get(defteam, priors.league)
    total_line = _float_or_none(row.get("total_line"))
    spread_line = _float_or_none(row.get("spread_line"))
    implied_team_total = None
    team_spread_line = None
    if total_line is not None and spread_line is not None:
        team_spread_line = spread_line
        if posteam == home_team:
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            implied_team_total = total_line / 2.0 - spread_line / 2.0
            team_spread_line = -spread_line

    values = qb_scramble_feature_values(
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
        qb_prior_scramble_rate=qb_prior,
        team_prior_scramble_rate=team_prior,
        opponent_prior_scramble_rate_allowed=opponent_prior,
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)) or not np.isfinite(qb_prior):
        return None

    return QbScrambleTrainingExample(
        features=features,
        label=_scramble_label(row),
        base_rate=float(np.clip(qb_prior, 1e-6, 1.0 - 1e-6)),
    )


def fit_logistic_qb_scramble(
    examples: list[QbScrambleTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> QbScrambleFitResult:
    if not examples:
        raise ValueError("Cannot fit QB scramble model with zero examples")
    if not feature_names:
        raise ValueError("feature_names must not be empty")

    n_features = len(feature_names)
    x = np.vstack([example.features for example in examples]).astype(float)
    y = np.array([example.label for example in examples], dtype=float)
    offsets = np.array([_logit(example.base_rate) for example in examples], dtype=float)
    if x.shape != (len(examples), n_features):
        raise ValueError("Feature matrix shape does not match feature_names")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(offsets)):
        raise ValueError("Training examples must contain finite values")

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        logits = np.clip(offsets + x @ beta, -35.0, 35.0)
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
    return QbScrambleFitResult(
        coefficients={
            name: float(value)
            for name, value in zip(feature_names, result.x, strict=True)
        },
        objective=float(result.fun),
        converged=bool(result.success),
        iterations=int(result.nit),
        num_examples=len(examples),
    )


def _is_modeled_row(row: Mapping[str, object]) -> bool:
    return row.get("play_type") == "pass" or _scramble_label(row) == 1


def _scramble_label(row: Mapping[str, object]) -> int:
    return 1 if row.get("qb_scramble") in {1, 1.0, True, "1", "true", "True"} else 0


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
        if row.get("score_differential") is not None:
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
