"""Artifact loading for learned receiver target selection."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fantasy_sim.data.target_selection.models import (
    DEFAULT_ARTIFACT_DIR,
    TARGET_SELECTION_MODEL_TYPE,
    TARGET_SELECTION_SCHEMA_VERSION,
    TargetSelectionConfig,
    TargetSelectionContext,
    build_player_static_features,
)
from fantasy_sim.models.player import TeamRoster

logger = logging.getLogger(__name__)


class TargetSelectionModel:
    """Loads per-season conditional-softmax artifacts for runtime use."""

    def __init__(self, config: TargetSelectionConfig) -> None:
        self._config = config
        self._artifacts_dir = (
            Path(config.artifacts_dir)
            if config.artifacts_dir is not None
            else DEFAULT_ARTIFACT_DIR
        )
        self._cache: dict[int, dict | None] = {}

    def build_context(
        self,
        roster: TeamRoster,
        target_season: int,
        week: int,
    ) -> TargetSelectionContext | None:
        """Build a team-game context from the season artifact and roster."""
        if not self._config.enabled:
            return None
        artifact = self._load_artifact(target_season)
        if artifact is None:
            return None

        feature_names = tuple(str(name) for name in artifact.get("feature_names", ()))
        raw_coefficients = artifact.get("coefficients", {})
        try:
            if isinstance(raw_coefficients, list):
                coefficients = {
                    name: float(value)
                    for name, value in zip(feature_names, raw_coefficients, strict=False)
                }
            elif isinstance(raw_coefficients, dict):
                coefficients = {
                    str(name): float(value)
                    for name, value in raw_coefficients.items()
                }
            else:
                logger.warning(
                    "Invalid target-selection coefficients for season %s",
                    target_season,
                )
                return None
        except (TypeError, ValueError) as exc:
            logger.warning(
                "Unable to parse target-selection coefficients for season %s: %s",
                target_season,
                exc,
            )
            return None

        if not feature_names or not coefficients:
            return None

        positions = set(self._config.positions)
        player_features = {
            player.player_id: build_player_static_features(player)
            for player in roster.players
            if player.position in positions
        }
        if not player_features:
            return None

        return TargetSelectionContext(
            coefficients=coefficients,
            feature_names=feature_names,
            player_features=player_features,
            probability_floor=self._config.probability_floor,
            max_logit_delta=self._config.max_logit_delta,
            candidate_positions=self._config.positions,
        )

    def _load_artifact(self, target_season: int) -> dict | None:
        if target_season in self._cache:
            return self._cache[target_season]

        path = self._artifacts_dir / f"target_selection_{target_season}.json"
        if not path.exists():
            logger.info("Target-selection artifact missing: %s", path)
            self._cache[target_season] = None
            return None

        try:
            artifact = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to load target-selection artifact %s: %s", path, exc)
            self._cache[target_season] = None
            return None

        if artifact.get("schema_version") != TARGET_SELECTION_SCHEMA_VERSION:
            logger.warning("Unsupported target-selection artifact schema: %s", path)
            self._cache[target_season] = None
            return None
        if artifact.get("model_type") != TARGET_SELECTION_MODEL_TYPE:
            logger.warning("Unsupported target-selection model type: %s", path)
            self._cache[target_season] = None
            return None

        self._cache[target_season] = artifact
        return artifact
