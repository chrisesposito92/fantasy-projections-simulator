"""Runtime artifact loading for learned QB scramble probabilities."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbScrambleContext,
    QbScrambleModelConfig,
)
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)


class QbScrambleModel:
    """Loads learned QB scramble artifacts and builds team runtime contexts."""

    def __init__(self, config: QbScrambleModelConfig) -> None:
        self.config = config
        self.artifacts_dir = Path(config.artifacts_dir or DEFAULT_ARTIFACT_DIR)
        self._artifact_cache: dict[int, dict[str, Any] | None] = {}

    def build_context(
        self,
        roster: TeamRoster,
        team: str,
        opponent: str,
        home_team: str,
        away_team: str,
        target_season: int,
        week: int,
        is_home: bool,
        spread_line: float | None = None,
        total_line: float | None = None,
        implied_team_total: float | None = None,
    ) -> QbScrambleContext | None:
        if not self.config.enabled:
            return None

        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None
        if artifact.get("target_season") != target_season:
            logger.warning(
                "Invalid QB scramble artifact for %s: target season mismatch",
                target_season,
            )
            return None
        if not _source_seasons_are_safe(artifact.get("source_seasons"), target_season):
            logger.warning(
                "Invalid QB scramble artifact for %s: unsafe source seasons",
                target_season,
            )
            return None

        parsed = _parse_features_and_coefficients(artifact, target_season)
        if parsed is None:
            return None
        feature_names, coefficients = parsed
        league_prior = _prior_value(artifact.get("priors"), "league", None, 0.05)
        team_prior = _prior_value(artifact.get("priors"), "team", team, league_prior)
        opponent_prior = _prior_value(
            artifact.get("priors"),
            "opponent_allowed",
            opponent,
            league_prior,
        )

        return QbScrambleContext(
            coefficients=coefficients,
            feature_names=feature_names,
            team=team,
            opponent=opponent,
            home_team=home_team,
            away_team=away_team,
            is_home=is_home,
            target_season=target_season,
            week=week,
            spread_line=spread_line,
            total_line=total_line,
            implied_team_total=implied_team_total,
            team_prior_scramble_rate=team_prior,
            opponent_prior_scramble_rate_allowed=opponent_prior,
            factor_clamp=_artifact_clamp(
                artifact.get("factor_clamp"),
                fallback=self.config.factor_clamp,
                min_value=0.0,
                max_value=math.inf,
            ),
            probability_clamp=_artifact_clamp(
                artifact.get("probability_clamp"),
                fallback=self.config.probability_clamp,
                min_value=0.0,
                max_value=1.0,
            ),
        )

    def _load_artifact(self, target_season: int) -> dict[str, Any] | None:
        if target_season in self._artifact_cache:
            return self._artifact_cache[target_season]

        path = self.artifacts_dir / f"qb_scramble_model_{target_season}.json"
        artifact: dict[str, Any] | None = None
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except FileNotFoundError:
            logger.info("Missing QB scramble artifact: %s", path)
        except OSError:
            logger.warning("Unable to read QB scramble artifact: %s", path)
        except UnicodeDecodeError:
            logger.warning("Invalid QB scramble artifact encoding: %s", path)
        except json.JSONDecodeError:
            logger.warning("Invalid QB scramble artifact JSON: %s", path)
        else:
            if not isinstance(loaded, dict):
                logger.warning("Invalid QB scramble artifact payload: %s", path)
            elif loaded.get("schema_version") != QB_SCRAMBLE_SCHEMA_VERSION:
                logger.warning("Unsupported QB scramble artifact schema: %s", path)
            elif loaded.get("model_type") != QB_SCRAMBLE_MODEL_TYPE:
                logger.warning("Unsupported QB scramble artifact model type: %s", path)
            else:
                artifact = loaded

        self._artifact_cache[target_season] = artifact
        return artifact


def _source_seasons_are_safe(source_seasons: object, target_season: int) -> bool:
    if not isinstance(source_seasons, list) or not source_seasons:
        return False
    return all(
        isinstance(season, int)
        and not isinstance(season, bool)
        and season < target_season
        for season in source_seasons
    )


def _parse_features_and_coefficients(
    artifact: dict[str, Any],
    target_season: int,
) -> tuple[tuple[str, ...], dict[str, float]] | None:
    feature_names = artifact.get("feature_names")
    coefficients_raw = artifact.get("coefficients")
    if not isinstance(feature_names, list) or not isinstance(coefficients_raw, dict):
        logger.warning(
            "Invalid QB scramble artifact for %s: missing feature_names/coefficients",
            target_season,
        )
        return None
    if not feature_names or not all(isinstance(name, str) for name in feature_names):
        logger.warning(
            "Invalid QB scramble artifact for %s: malformed feature_names",
            target_season,
        )
        return None
    if any(name not in DEFAULT_QB_SCRAMBLE_FEATURES for name in feature_names):
        logger.warning(
            "Invalid QB scramble artifact for %s: unsupported feature name",
            target_season,
        )
        return None

    parsed_features = tuple(feature_names)
    try:
        coefficients = {str(name): float(value) for name, value in coefficients_raw.items()}
    except (TypeError, ValueError):
        logger.warning(
            "Invalid QB scramble artifact for %s: coefficient parsing failed",
            target_season,
        )
        return None

    if set(coefficients) != set(parsed_features):
        logger.warning(
            "Invalid QB scramble artifact for %s: coefficient/feature mismatch",
            target_season,
        )
        return None
    if not all(math.isfinite(value) for value in coefficients.values()):
        logger.warning(
            "Invalid QB scramble artifact for %s: non-finite coefficient",
            target_season,
        )
        return None
    return parsed_features, coefficients


def _artifact_clamp(
    raw: object,
    *,
    fallback: tuple[float, float],
    min_value: float,
    max_value: float,
) -> tuple[float, float]:
    if not isinstance(raw, list | tuple) or len(raw) != 2:
        return fallback
    try:
        lo = float(raw[0])
        hi = float(raw[1])
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(lo) or not math.isfinite(hi) or lo < min_value or hi > max_value or lo >= hi:
        return fallback
    return (lo, hi)


def _prior_value(priors: object, group: str, key: str | None, fallback: float) -> float:
    if not isinstance(priors, dict):
        return fallback
    raw: object
    if key is None:
        raw = priors.get(group)
    else:
        group_values = priors.get(group)
        if not isinstance(group_values, dict):
            return fallback
        raw = group_values.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        return fallback
    return value
