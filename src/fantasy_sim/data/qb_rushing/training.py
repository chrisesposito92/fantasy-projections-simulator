"""Training helpers for learned QB scramble probabilities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
from scipy.optimize import minimize

from fantasy_sim.data.qb_rushing.models import (
    _logit,
    mobility_tier_from_rates,
    qb_designed_run_feature_values,
    qb_designed_run_tail_key,
    qb_scramble_feature_values,
)
from fantasy_sim.engine.types import GameState


@dataclass(frozen=True)
class QbScramblePriors:
    qb: dict[str, float]
    team: dict[str, float]
    opponent_allowed: dict[str, float]
    league: float
    qb_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    team_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    opponent_allowed_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    league_counts: tuple[int, int] = field(default=(0, 0), repr=False, compare=False)


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


@dataclass(frozen=True)
class QbDesignedRunPriors:
    qb: dict[str, float]
    team: dict[str, float]
    opponent_allowed: dict[str, float]
    league: float
    mobility_tiers: dict[str, str]
    qb_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    team_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    opponent_allowed_counts: dict[str, tuple[int, int]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    league_counts: tuple[int, int] = field(default=(0, 0), repr=False, compare=False)


@dataclass(frozen=True)
class QbDesignedRunTrainingExample:
    features: np.ndarray
    label: int
    base_rate: float


@dataclass(frozen=True)
class QbDesignedRunFitResult:
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
        qb_id = _qb_id_for_row(row)
        team = row.get("posteam")
        opponent = row.get("defteam")
        league_scrambles += label
        league_total += 1
        if qb_id is not None:
            qb_counts[qb_id][0] += label
            qb_counts[qb_id][1] += 1
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
        qb_counts={key: (counts[0], counts[1]) for key, counts in qb_counts.items()},
        team_counts={key: (counts[0], counts[1]) for key, counts in team_counts.items()},
        opponent_allowed_counts={
            key: (counts[0], counts[1]) for key, counts in opponent_counts.items()
        },
        league_counts=(league_scrambles, league_total),
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
    label = _scramble_label(row)
    qb_id = _qb_id_for_row(row)
    qb_prior = _leave_one_out_rate(
        priors.qb_counts,
        qb_id,
        label,
        fallback=None,
    )
    team_prior = _leave_one_out_rate(
        priors.team_counts,
        posteam,
        label,
        fallback=None,
    )
    opponent_prior = _leave_one_out_rate(
        priors.opponent_allowed_counts,
        defteam,
        label,
        fallback=None,
    )
    league_prior = _leave_one_out_counts(priors.league_counts, label)
    league_prior = 0.05 if league_prior is None else league_prior
    team_prior = league_prior if team_prior is None else team_prior
    opponent_prior = league_prior if opponent_prior is None else opponent_prior
    qb_prior = team_prior if qb_prior is None else qb_prior
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
        label=label,
        base_rate=float(qb_prior),
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


def annotate_rusher_positions(
    rows: list[Mapping[str, object]],
    positions_by_player_id: Mapping[str, str],
) -> list[dict[str, object]]:
    annotated: list[dict[str, object]] = []
    for row in rows:
        copied = dict(row)
        rusher_id = copied.get("rusher_player_id")
        if copied.get("rusher_position") in (None, "") and rusher_id not in (None, ""):
            copied["rusher_position"] = positions_by_player_id.get(str(rusher_id))
        annotated.append(copied)
    return annotated


def build_designed_run_priors(rows: list[Mapping[str, object]]) -> QbDesignedRunPriors:
    qb_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    team_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    opponent_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    qb_designed_counts: dict[str, int] = defaultdict(int)
    qb_total_counts: dict[str, int] = defaultdict(int)
    league_qb_runs = 0
    league_total = 0

    for row in rows:
        if not _is_designed_run_row(row):
            continue
        label = _designed_qb_run_label(row)
        qb_id = _offense_qb_id_for_designed_run_row(row)
        team = row.get("posteam")
        opponent = row.get("defteam")
        league_qb_runs += label
        league_total += 1
        if qb_id is not None:
            player_key = qb_id
            qb_total_counts[player_key] += 1
            qb_designed_counts[player_key] += label
            qb_counts[player_key][0] += label
            qb_counts[player_key][1] += 1
        if team is not None:
            team_counts[str(team)][0] += label
            team_counts[str(team)][1] += 1
        if opponent is not None:
            opponent_counts[str(opponent)][0] += label
            opponent_counts[str(opponent)][1] += 1

    league = league_qb_runs / league_total if league_total else 0.0
    qb_rates = {
        key: qb_designed_counts[key] / max(total, 1)
        for key, total in qb_total_counts.items()
        if key in qb_designed_counts
    }
    mobility_tiers = {
        key: mobility_tier_from_rates(rate, 0.0)
        for key, rate in qb_rates.items()
    }
    return QbDesignedRunPriors(
        qb=qb_rates,
        team={key: counts[0] / counts[1] for key, counts in team_counts.items()},
        opponent_allowed={key: counts[0] / counts[1] for key, counts in opponent_counts.items()},
        league=league,
        mobility_tiers=mobility_tiers,
        qb_counts={key: (counts[0], counts[1]) for key, counts in qb_counts.items()},
        team_counts={key: (counts[0], counts[1]) for key, counts in team_counts.items()},
        opponent_allowed_counts={
            key: (counts[0], counts[1]) for key, counts in opponent_counts.items()
        },
        league_counts=(league_qb_runs, league_total),
    )


def build_designed_run_example_from_row(
    row: Mapping[str, object],
    feature_names: tuple[str, ...],
    priors: QbDesignedRunPriors,
) -> QbDesignedRunTrainingExample | None:
    if not _is_designed_run_row(row):
        return None
    if row.get("posteam") is None or row.get("defteam") is None:
        return None
    state = _state_from_row(row)
    if state is None:
        return None

    label = _designed_qb_run_label(row)
    qb_key = _offense_qb_id_for_designed_run_row(row)
    if qb_key is None:
        return None
    posteam = str(row["posteam"])
    defteam = str(row["defteam"])
    home_team = str(row["home_team"])
    away_team = str(row["away_team"])
    league_prior = _leave_one_out_counts(priors.league_counts, label)
    league_prior = 0.05 if league_prior is None else league_prior
    qb_prior = _leave_one_out_rate(priors.qb_counts, qb_key, label, fallback=league_prior)
    team_prior = _leave_one_out_rate(priors.team_counts, posteam, label, fallback=league_prior)
    opponent_prior = _leave_one_out_rate(
        priors.opponent_allowed_counts,
        defteam,
        label,
        fallback=league_prior,
    )
    total_line = _float_or_none(row.get("total_line"))
    spread_line = _float_or_none(row.get("spread_line"))
    implied_team_total = None
    team_spread_line = spread_line
    if total_line is not None and spread_line is not None:
        if posteam == home_team:
            implied_team_total = total_line / 2.0 + spread_line / 2.0
        else:
            implied_team_total = total_line / 2.0 - spread_line / 2.0
            team_spread_line = -spread_line
    values = qb_designed_run_feature_values(
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
        qb_prior_designed_run_share=league_prior if qb_prior is None else qb_prior,
        team_prior_designed_qb_run_rate=league_prior if team_prior is None else team_prior,
        opponent_prior_designed_qb_run_allowed=(
            league_prior if opponent_prior is None else opponent_prior
        ),
        mobility_tier=priors.mobility_tiers.get(qb_key, "medium"),
    )
    features = np.array([values.get(name, 0.0) for name in feature_names], dtype=float)
    if not np.all(np.isfinite(features)):
        return None
    return QbDesignedRunTrainingExample(
        features=features,
        label=label,
        base_rate=float(league_prior if team_prior is None else team_prior),
    )


def fit_logistic_qb_designed_run(
    examples: list[QbDesignedRunTrainingExample],
    feature_names: tuple[str, ...],
    *,
    l2: float = 1.0,
    max_iter: int = 200,
) -> QbDesignedRunFitResult:
    if not examples:
        raise ValueError("Cannot fit QB designed-run model with zero examples")
    fit = fit_logistic_qb_scramble(
        [
            QbScrambleTrainingExample(
                features=example.features,
                label=example.label,
                base_rate=example.base_rate,
            )
            for example in examples
        ],
        feature_names,
        l2=l2,
        max_iter=max_iter,
    )
    return QbDesignedRunFitResult(
        coefficients=fit.coefficients,
        objective=fit.objective,
        converged=fit.converged,
        iterations=fit.iterations,
        num_examples=fit.num_examples,
    )


def build_designed_run_tail_buckets(
    rows: list[Mapping[str, object]],
    *,
    mobility_tiers: Mapping[str, str],
) -> dict[str, tuple[int, ...]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if not _is_designed_run_row(row) or _designed_qb_run_label(row) != 1:
            continue
        state = _state_from_row(row)
        if state is None:
            continue
        rusher_id = row.get("rusher_player_id")
        mobility_tier = mobility_tiers.get(str(rusher_id), "medium")
        yards = _int_or_none(row.get("yards_gained"))
        if yards is None:
            continue
        buckets["global"].append(yards)
        buckets[qb_designed_run_tail_key(state, mobility_tier=mobility_tier)].append(yards)
    return {key: tuple(values) for key, values in buckets.items()}


def _is_modeled_row(row: Mapping[str, object]) -> bool:
    return row.get("play_type") == "pass" or _scramble_label(row) == 1


def _is_designed_run_row(row: Mapping[str, object]) -> bool:
    if row.get("play_type") != "run":
        return False
    if row.get("rusher_player_id") in (None, ""):
        return False
    if row.get("qb_scramble") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("qb_kneel") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("qb_spike") in {1, 1.0, True, "1", "true", "True"}:
        return False
    if row.get("no_play") in {1, 1.0, True, "1", "true", "True"}:
        return False
    return True


def _designed_qb_run_label(row: Mapping[str, object]) -> int:
    return 1 if row.get("rusher_position") == "QB" else 0


def _offense_qb_id_for_designed_run_row(row: Mapping[str, object]) -> str | None:
    for key in (
        "qb_player_id",
        "offense_qb_player_id",
        "posteam_qb_player_id",
        "passer_player_id",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    if _designed_qb_run_label(row) == 1:
        rusher_id = row.get("rusher_player_id")
        if rusher_id not in (None, ""):
            return str(rusher_id)
    return None


def _qb_id_for_row(row: Mapping[str, object]) -> str | None:
    passer_id = row.get("passer_player_id")
    if passer_id not in (None, ""):
        return str(passer_id)
    if _scramble_label(row) == 1:
        rusher_id = row.get("rusher_player_id")
        if rusher_id not in (None, ""):
            return str(rusher_id)
    return None


def _leave_one_out_rate(
    counts_by_key: dict[str, tuple[int, int]],
    key: str | None,
    label: int,
    *,
    fallback: float | None,
) -> float | None:
    if key is None or key not in counts_by_key:
        return fallback
    rate = _leave_one_out_counts(counts_by_key[key], label)
    return fallback if rate is None else rate


def _leave_one_out_counts(counts: tuple[int, int], label: int) -> float | None:
    scrambles, total = counts
    scrambles -= label
    total -= 1
    if total <= 0:
        return None
    return scrambles / total


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


def _int_or_none(value: object) -> int | None:
    try:
        value_i = int(value)
    except (TypeError, ValueError):
        return None
    return value_i


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
