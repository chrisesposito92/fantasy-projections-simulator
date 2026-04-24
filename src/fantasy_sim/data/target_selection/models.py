"""Models and feature helpers for learned receiver target selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from fantasy_sim.engine.game_script import RuntimeGameScript
    from fantasy_sim.engine.types import GameState
    from fantasy_sim.models.player import PlayerModel

TARGET_SELECTION_SCHEMA_VERSION = 1
TARGET_SELECTION_MODEL_TYPE = "conditional_softmax_legacy_anchor"
DEFAULT_ARTIFACT_DIR = (
    Path(__file__).resolve().parent / "artifacts" / "decision_v1"
)

DEFAULT_TARGET_SELECTION_FEATURES: tuple[str, ...] = (
    "legacy_weight",
    "legacy_log_weight",
    "target_rank_inv",
    "target_rank_1",
    "target_rank_2",
    "target_share",
    "red_zone_target_share",
    "outer_rz_target_share",
    "goal_line_target_share",
    "air_yards_share",
    "snap_share",
    "catch_rate",
    "red_zone_catch_rate",
    "receiving_yards_mean_norm",
    "games_played_norm",
    "targets_per_route_rate",
    "is_rb",
    "is_wr",
    "is_te",
    "is_fb",
    "is_red_zone",
    "is_outer_rz",
    "is_goal_line",
    "is_third_down",
    "is_long_distance",
    "is_trailing",
    "is_leading",
    "is_two_minute",
    "is_fourth_quarter",
    "week_norm",
    "distance_norm",
    "yard_line_norm",
    "score_diff_norm",
    "target_share_x_red_zone",
    "red_zone_share_x_red_zone",
    "outer_rz_share_x_outer_rz",
    "goal_line_share_x_goal_line",
    "air_yards_share_x_trailing",
    "rank_inv_x_trailing",
    "rb_x_long_distance",
    "te_x_red_zone",
)


@dataclass(frozen=True)
class TargetSelectionConfig:
    """Configuration for the learned receiver target-selection node."""

    enabled: bool = False
    artifacts_dir: str | None = None
    positions: tuple[str, ...] = ("RB", "WR", "TE", "FB")
    probability_floor: float = 0.001
    max_logit_delta: float = 3.0
    fallback: str = "legacy"


@dataclass(frozen=True)
class TargetSelectionContext:
    """Runtime context for one team's learned receiver-selection model."""

    coefficients: dict[str, float]
    feature_names: tuple[str, ...]
    player_features: dict[str, dict[str, float]]
    probability_floor: float = 0.001
    max_logit_delta: float = 3.0
    fallback: str = "legacy"
    candidate_positions: tuple[str, ...] = ("RB", "WR", "TE", "FB")

    def probabilities(
        self,
        players: list["PlayerModel"],
        legacy_weights: np.ndarray,
        state: "GameState",
        script: "RuntimeGameScript | None" = None,
    ) -> np.ndarray | None:
        """Return learned probabilities for the same candidates legacy uses.

        The learned model is anchored by legacy log-probability and only adds a
        clipped feature delta. Invalid outputs return None so callers can use
        the legacy probabilities for that play.
        """
        if len(players) < 2:
            return None
        allowed_positions = set(self.candidate_positions)
        if any(player.position not in allowed_positions for player in players):
            return None

        base = np.asarray(legacy_weights, dtype=float)
        if base.shape != (len(players),):
            return None
        if not np.all(np.isfinite(base)):
            return None
        base_sum = float(base.sum())
        if base_sum <= 0:
            return None
        base = base / base_sum

        order = sorted(range(len(players)), key=lambda idx: base[idx], reverse=True)
        ranks = np.empty(len(players), dtype=int)
        for rank, idx in enumerate(order, start=1):
            ranks[idx] = rank

        logits = np.log(np.maximum(base, 1e-12))
        for idx, player in enumerate(players):
            static = self.player_features.get(player.player_id)
            if static is None:
                static = build_player_static_features(player)
            features = candidate_feature_values(
                player,
                static,
                state,
                legacy_weight=float(base[idx]),
                target_rank=int(ranks[idx]),
                script=script,
            )
            delta = float(self.coefficients.get("intercept", 0.0))
            for name in self.feature_names:
                delta += float(self.coefficients.get(name, 0.0)) * features.get(name, 0.0)
            delta = float(np.clip(delta, -self.max_logit_delta, self.max_logit_delta))
            logits[idx] += delta

        logits -= float(np.max(logits))
        weights = np.exp(logits)
        if not np.all(np.isfinite(weights)):
            return None
        total = float(weights.sum())
        if total <= 0:
            return None

        probs = weights / total
        if self.probability_floor > 0:
            floor = min(float(self.probability_floor), 1.0 / len(probs))
            probs = np.maximum(probs, floor)
            probs = probs / float(probs.sum())
        if not np.all(np.isfinite(probs)) or float(probs.sum()) <= 0:
            return None
        return probs


def build_player_static_features(player: "PlayerModel") -> dict[str, float]:
    """Build player features that do not vary by play state."""
    usage = player.usage
    outcomes = player.outcomes
    receiving_yards_mean = 0.0
    if outcomes.receiving_yards_dist is not None and len(outcomes.receiving_yards_dist) > 0:
        receiving_yards_mean = float(np.mean(outcomes.receiving_yards_dist))

    return {
        "target_share": _finite_float(usage.target_share),
        "red_zone_target_share": _finite_float(usage.red_zone_target_share),
        "outer_rz_target_share": _finite_float(usage.outer_rz_target_share),
        "goal_line_target_share": _finite_float(usage.goal_line_target_share),
        "air_yards_share": _finite_float(usage.air_yards_share),
        "snap_share": _finite_float(usage.snap_share),
        "catch_rate": _finite_float(outcomes.catch_rate),
        "red_zone_catch_rate": _finite_float(outcomes.red_zone_catch_rate),
        "receiving_yards_mean_norm": _clip(receiving_yards_mean / 20.0, 0.0, 3.0),
        "games_played_norm": _clip(float(player.games_played) / 17.0, 0.0, 2.0),
        "targets_per_route_rate": _finite_float(outcomes.targets_per_route_rate),
        "is_rb": 1.0 if player.position == "RB" else 0.0,
        "is_wr": 1.0 if player.position == "WR" else 0.0,
        "is_te": 1.0 if player.position == "TE" else 0.0,
        "is_fb": 1.0 if player.position == "FB" else 0.0,
    }


def candidate_feature_values(
    player: "PlayerModel",
    static: dict[str, float],
    state: "GameState",
    *,
    legacy_weight: float,
    target_rank: int,
    script: "RuntimeGameScript | None" = None,
) -> dict[str, float]:
    """Build complete candidate features for one player at one play state."""
    is_red_zone = 1.0 if state.yard_line <= 20 else 0.0
    is_outer_rz = 1.0 if 6 <= state.yard_line <= 20 else 0.0
    is_goal_line = 1.0 if state.yard_line <= 5 else 0.0
    is_trailing = 1.0 if state.score_differential < 0 else 0.0
    is_leading = 1.0 if state.score_differential > 0 else 0.0
    if script is not None and getattr(script, "regime", None) == "trailing_late":
        is_trailing = 1.0

    values = dict(static)
    rank_inv = 1.0 / max(1, target_rank)
    legacy = max(float(legacy_weight), 1e-12)
    values.update(
        {
            "legacy_weight": legacy,
            "legacy_log_weight": float(np.log(legacy)),
            "target_rank_inv": rank_inv,
            "target_rank_1": 1.0 if target_rank == 1 else 0.0,
            "target_rank_2": 1.0 if target_rank == 2 else 0.0,
            "is_red_zone": is_red_zone,
            "is_outer_rz": is_outer_rz,
            "is_goal_line": is_goal_line,
            "is_third_down": 1.0 if state.down == 3 else 0.0,
            "is_long_distance": 1.0 if state.distance >= 8 else 0.0,
            "is_trailing": is_trailing,
            "is_leading": is_leading,
            "is_two_minute": 1.0 if state.clock <= 120 and state.quarter in (2, 4) else 0.0,
            "is_fourth_quarter": 1.0 if state.quarter >= 4 else 0.0,
            "week_norm": _clip(float(state.week) / 18.0, 0.0, 1.0),
            "distance_norm": _clip(float(state.distance) / 20.0, 0.0, 2.0),
            "yard_line_norm": _clip(float(state.yard_line) / 100.0, 0.0, 1.0),
            "score_diff_norm": _clip(float(state.score_differential) / 21.0, -2.0, 2.0),
        }
    )
    values.update(
        {
            "target_share_x_red_zone": values["target_share"] * is_red_zone,
            "red_zone_share_x_red_zone": values["red_zone_target_share"] * is_red_zone,
            "outer_rz_share_x_outer_rz": values["outer_rz_target_share"] * is_outer_rz,
            "goal_line_share_x_goal_line": values["goal_line_target_share"] * is_goal_line,
            "air_yards_share_x_trailing": values["air_yards_share"] * is_trailing,
            "rank_inv_x_trailing": rank_inv * is_trailing,
            "rb_x_long_distance": values["is_rb"] * values["is_long_distance"],
            "te_x_red_zone": values["is_te"] * is_red_zone,
        }
    )
    return values


def _finite_float(value: float) -> float:
    value = float(value)
    if not np.isfinite(value):
        return 0.0
    return value


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, _finite_float(value)))
