import json

import numpy as np
import pytest

from fantasy_sim.data.target_selection import (
    TargetSelectionConfig,
    TargetSelectionContext,
    TargetSelectionModel,
)
from fantasy_sim.data.target_selection.models import (
    TARGET_SELECTION_MODEL_TYPE,
    TARGET_SELECTION_SCHEMA_VERSION,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def make_state() -> GameState:
    return GameState(
        quarter=1,
        clock=900,
        possession="home",
        down=1,
        distance=10,
        yard_line=75,
        home_score=0,
        away_score=0,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
        week=3,
    )


def make_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "WR1",
                "WR1",
                "WR",
                "KC",
                PlayerUsage(target_share=0.5),
                PlayerOutcomes(catch_rate=0.6, receiving_yards_dist=np.array([10, 12])),
            ),
            PlayerModel(
                "TE1",
                "TE1",
                "TE",
                "KC",
                PlayerUsage(target_share=0.5),
                PlayerOutcomes(catch_rate=0.7, receiving_yards_dist=np.array([5, 7])),
            ),
        ],
    )


def make_roster_with_rb() -> TeamRoster:
    roster = make_roster()
    return TeamRoster(
        team=roster.team,
        players=[
            *roster.players,
            PlayerModel(
                "RB1",
                "RB1",
                "RB",
                "KC",
                PlayerUsage(target_share=0.4),
                PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([4, 8])),
            ),
        ],
    )


def write_artifact(path, *, schema_version=TARGET_SELECTION_SCHEMA_VERSION):
    path.write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "model_type": TARGET_SELECTION_MODEL_TYPE,
                "target_season": 2024,
                "feature_names": ["is_te"],
                "coefficients": {"is_te": 3.0},
            }
        )
    )


def test_missing_artifact_returns_none(tmp_path):
    model = TargetSelectionModel(
        TargetSelectionConfig(enabled=True, artifacts_dir=str(tmp_path))
    )

    assert model.build_context(make_roster(), 2024, 1) is None


def test_invalid_schema_returns_none(tmp_path):
    write_artifact(tmp_path / "target_selection_2024.json", schema_version=999)
    model = TargetSelectionModel(
        TargetSelectionConfig(enabled=True, artifacts_dir=str(tmp_path))
    )

    assert model.build_context(make_roster(), 2024, 1) is None


def test_malformed_coefficients_return_none(tmp_path):
    path = tmp_path / "target_selection_2024.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": TARGET_SELECTION_SCHEMA_VERSION,
                "model_type": TARGET_SELECTION_MODEL_TYPE,
                "target_season": 2024,
                "feature_names": ["is_te"],
                "coefficients": {"is_te": None},
            }
        )
    )
    model = TargetSelectionModel(
        TargetSelectionConfig(enabled=True, artifacts_dir=str(tmp_path))
    )

    assert model.build_context(make_roster(), 2024, 1) is None


def test_context_loads_artifact_and_tilts_probabilities(tmp_path):
    write_artifact(tmp_path / "target_selection_2024.json")
    model = TargetSelectionModel(
        TargetSelectionConfig(enabled=True, artifacts_dir=str(tmp_path))
    )
    roster = make_roster()

    context = model.build_context(roster, 2024, 1)

    assert context is not None
    probs = context.probabilities(
        roster.players,
        np.array([0.5, 0.5]),
        make_state(),
    )
    assert probs is not None
    assert probs[1] > probs[0]
    assert np.isclose(probs.sum(), 1.0)


def test_subset_positions_leave_other_candidates_on_legacy_delta():
    roster = make_roster_with_rb()
    # Bypass artifact loading: this behavior belongs to the runtime context,
    # not filesystem parsing.
    target_context = TargetSelectionContext(
        coefficients={"is_te": 2.0},
        feature_names=("is_te",),
        player_features={},
        probability_floor=0.0,
        max_logit_delta=2.0,
        candidate_positions=("WR", "TE"),
    )
    legacy = np.array([0.4, 0.2, 0.4])

    probs = target_context.probabilities(roster.players, legacy, make_state())

    assert probs is not None
    assert probs[1] > legacy[1]
    assert probs[2] / probs[0] == pytest.approx(legacy[2] / legacy[0])
