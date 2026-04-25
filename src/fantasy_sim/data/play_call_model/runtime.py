"""Runtime artifact loading for learned pass/run play calling."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from fantasy_sim.data.play_call_model.models import (
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_PLAY_CALL_FEATURES,
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
    PlayCallContext,
    PlayCallModelConfig,
)

logger = logging.getLogger(__name__)


class PlayCallModel:
    """Loads learned play-call artifacts and builds per-team runtime contexts."""

    def __init__(self, config: PlayCallModelConfig) -> None:
        self.config = config
        self.artifacts_dir = Path(config.artifacts_dir or DEFAULT_ARTIFACT_DIR)
        self._artifact_cache: dict[int, dict[str, Any] | None] = {}

    def build_context(
        self,
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
        team_prior_pass_rate: float = 0.57,
        opponent_prior_pass_rate_allowed: float = 0.57,
    ) -> PlayCallContext | None:
        if not self.config.enabled:
            return None

        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None

        if artifact.get("target_season") != target_season:
            logger.warning(
                "Invalid play-call artifact for %s: target season mismatch",
                target_season,
            )
            return None

        feature_names = artifact.get("feature_names")
        coefficients_raw = artifact.get("coefficients")
        if not isinstance(feature_names, list) or not isinstance(coefficients_raw, dict):
            logger.warning(
                "Invalid play-call artifact for %s: missing feature_names/coefficients",
                target_season,
            )
            return None
        if not feature_names or not all(isinstance(name, str) for name in feature_names):
            logger.warning(
                "Invalid play-call artifact for %s: malformed feature_names",
                target_season,
            )
            return None

        try:
            parsed_features = tuple(feature_names)
            coefficients = {
                str(name): float(value) for name, value in coefficients_raw.items()
            }
        except (TypeError, ValueError):
            logger.warning(
                "Invalid play-call artifact for %s: coefficient parsing failed",
                target_season,
            )
            return None

        missing_features = [name for name in parsed_features if name not in coefficients]
        if missing_features:
            logger.warning(
                "Invalid play-call artifact for %s: missing feature coefficients",
                target_season,
            )
            return None
        if any(name not in DEFAULT_PLAY_CALL_FEATURES for name in parsed_features):
            logger.warning(
                "Invalid play-call artifact for %s: unsupported feature name",
                target_season,
            )
            return None
        if set(coefficients) != set(parsed_features):
            logger.warning(
                "Invalid play-call artifact for %s: coefficient/feature mismatch",
                target_season,
            )
            return None
        if not all(math.isfinite(value) for value in coefficients.values()):
            logger.warning(
                "Invalid play-call artifact for %s: non-finite coefficient",
                target_season,
            )
            return None

        return PlayCallContext(
            coefficients=coefficients,
            feature_names=parsed_features,
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
            team_prior_pass_rate=team_prior_pass_rate,
            opponent_prior_pass_rate_allowed=opponent_prior_pass_rate_allowed,
            probability_clamp=self._artifact_clamp(artifact),
        )

    def _load_artifact(self, target_season: int) -> dict[str, Any] | None:
        if target_season in self._artifact_cache:
            return self._artifact_cache[target_season]

        path = self.artifacts_dir / f"play_call_model_{target_season}.json"
        artifact: dict[str, Any] | None = None
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except FileNotFoundError:
            logger.info("Missing play-call artifact: %s", path)
        except OSError:
            logger.warning("Unable to read play-call artifact: %s", path)
        except UnicodeDecodeError:
            logger.warning("Invalid play-call artifact encoding: %s", path)
        except json.JSONDecodeError:
            logger.warning("Invalid play-call artifact JSON: %s", path)
        else:
            if not isinstance(loaded, dict):
                logger.warning("Invalid play-call artifact payload: %s", path)
            elif loaded.get("schema_version") != PLAY_CALL_MODEL_SCHEMA_VERSION:
                logger.warning("Unsupported play-call artifact schema: %s", path)
            elif loaded.get("model_type") != PLAY_CALL_MODEL_TYPE:
                logger.warning("Unsupported play-call artifact model type: %s", path)
            else:
                artifact = loaded

        self._artifact_cache[target_season] = artifact
        return artifact

    def _artifact_clamp(self, artifact: dict[str, Any]) -> tuple[float, float]:
        clamp = artifact.get("probability_clamp")
        if not isinstance(clamp, list | tuple) or len(clamp) != 2:
            return self.config.probability_clamp
        try:
            lo = float(clamp[0])
            hi = float(clamp[1])
        except (TypeError, ValueError):
            return self.config.probability_clamp
        if not math.isfinite(lo) or not math.isfinite(hi) or lo < 0.0 or hi > 1.0 or lo >= hi:
            return self.config.probability_clamp
        return (lo, hi)
