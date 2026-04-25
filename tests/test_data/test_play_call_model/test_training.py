import numpy as np
import pytest

from fantasy_sim.data.play_call_model.models import DEFAULT_PLAY_CALL_FEATURES
from fantasy_sim.data.play_call_model.training import (
    PlayCallTrainingExample,
    build_example_from_row,
    fit_logistic_play_call,
    source_seasons_for_artifact,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "KC",
        "defteam": "BUF",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "pass",
        "down": 3,
        "ydstogo": 8,
        "yardline_100": 35,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
        "goal_to_go": False,
    }
    row.update(overrides)
    return row


def test_source_seasons_for_artifact_uses_prior_seasons_only():
    seasons = source_seasons_for_artifact(
        target_season=2024,
        min_source_season=2018,
        training_years=4,
    )

    assert seasons == [2020, 2021, 2022, 2023]


def test_source_seasons_for_artifact_clamps_to_min_source_season():
    seasons = source_seasons_for_artifact(
        target_season=2022,
        min_source_season=2020,
        training_years=4,
    )

    assert seasons == [2020, 2021]


def test_build_example_from_row_returns_binary_label_and_feature_vector():
    example = build_example_from_row(_row(), DEFAULT_PLAY_CALL_FEATURES)

    assert example is not None
    assert example.label == 1
    assert example.features.shape == (len(DEFAULT_PLAY_CALL_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_example_from_row_labels_run_as_zero():
    example = build_example_from_row(_row(play_type="run"), DEFAULT_PLAY_CALL_FEATURES)

    assert example is not None
    assert example.label == 0


def test_build_example_from_row_skips_non_scrimmage_play():
    assert build_example_from_row(
        _row(play_type="punt"),
        DEFAULT_PLAY_CALL_FEATURES,
    ) is None


def test_fit_logistic_play_call_rejects_empty_examples():
    with pytest.raises(ValueError, match="zero examples"):
        fit_logistic_play_call([], ("intercept",))


def test_fit_logistic_play_call_learns_positive_feature_for_pass():
    examples = [
        PlayCallTrainingExample(features=np.array([1.0, 1.0]), label=1)
        for _ in range(30)
    ] + [
        PlayCallTrainingExample(features=np.array([1.0, 0.0]), label=0)
        for _ in range(30)
    ]

    result = fit_logistic_play_call(
        examples,
        ("intercept", "pass_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["pass_feature"] > 0
    assert result.converged is True
