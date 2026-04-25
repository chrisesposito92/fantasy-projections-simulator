import json

import pytest

from fantasy_sim.data.play_call_model import (
    PLAY_CALL_MODEL_SCHEMA_VERSION,
    PLAY_CALL_MODEL_TYPE,
    PlayCallModel,
    PlayCallModelConfig,
)
from fantasy_sim.engine.types import GameState


def _state(**overrides):
    values = {
        "quarter": 2,
        "clock": 90,
        "possession": "away",
        "down": 3,
        "distance": 2,
        "yard_line": 18,
        "home_score": 21,
        "away_score": 14,
        "home_team": "KC",
        "away_team": "BUF",
        "receiving_2nd_half": "away",
    }
    values.update(overrides)
    return GameState(**values)


def _config(tmp_path, **overrides):
    values = {
        "enabled": True,
        "artifacts_dir": str(tmp_path),
    }
    values.update(overrides)
    return PlayCallModelConfig(**values)


def _artifact(**overrides):
    values = {
        "schema_version": PLAY_CALL_MODEL_SCHEMA_VERSION,
        "model_type": PLAY_CALL_MODEL_TYPE,
        "target_season": 2024,
        "feature_names": ["intercept", "down_3"],
        "coefficients": {"intercept": 0.0, "down_3": 0.0},
    }
    values.update(overrides)
    return values


def _write_artifact(tmp_path, **overrides):
    path = tmp_path / "play_call_model_2024.json"
    path.write_text(json.dumps(_artifact(**overrides)), encoding="utf-8")
    return path


def _build_context(model):
    return model.build_context(
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=9,
        is_home=False,
    )


def test_missing_artifact_returns_none_from_build_context(tmp_path):
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_invalid_schema_returns_none(tmp_path):
    _write_artifact(tmp_path, schema_version=999)
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_valid_artifact_loads_and_clamps_high_probability(tmp_path):
    _write_artifact(
        tmp_path,
        coefficients={"intercept": 0.0, "down_3": 10.0},
        probability_clamp=[0.05, 0.95],
    )
    model = PlayCallModel(_config(tmp_path))

    context = _build_context(model)

    assert context is not None
    assert context.pass_probability(_state()) == pytest.approx(0.95)


def test_non_finite_coefficient_returns_none(tmp_path):
    _write_artifact(tmp_path, coefficients={"intercept": 0.0, "down_3": "nan"})
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_non_finite_extra_coefficient_returns_none(tmp_path):
    _write_artifact(
        tmp_path,
        coefficients={"intercept": 0.0, "down_3": 0.0, "unused": "inf"},
    )
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_missing_feature_coefficient_returns_none(tmp_path):
    _write_artifact(tmp_path, coefficients={"intercept": 0.0})
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_unsupported_feature_name_returns_none(tmp_path):
    _write_artifact(
        tmp_path,
        feature_names=["intercept", "unsupported_feature"],
        coefficients={"intercept": 0.0, "unsupported_feature": 1.0},
    )
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_malformed_feature_names_return_none(tmp_path):
    _write_artifact(tmp_path, feature_names=["intercept", None])
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_artifact_target_season_mismatch_returns_none(tmp_path):
    _write_artifact(tmp_path, target_season=2023)
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None


def test_artifact_read_error_returns_none(tmp_path):
    (tmp_path / "play_call_model_2024.json").mkdir()
    model = PlayCallModel(_config(tmp_path))

    assert _build_context(model) is None
