import json

import numpy as np

from fantasy_sim.data.target_selection import TargetSelectionConfig, TargetSelectionModel
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
