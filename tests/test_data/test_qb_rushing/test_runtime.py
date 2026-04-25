import json

import pytest

from fantasy_sim.data.qb_rushing import (
    QB_DESIGNED_RUN_MODEL_TYPE,
    QB_DESIGNED_RUN_SCHEMA_VERSION,
    QB_SCRAMBLE_MODEL_TYPE,
    QB_SCRAMBLE_SCHEMA_VERSION,
    QbDesignedRunModel,
    QbDesignedRunModelConfig,
    QbScrambleModel,
    QbScrambleModelConfig,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _qb(scramble_rate=0.08):
    return PlayerModel(
        "QB1",
        "Mobile QB",
        "QB",
        "BUF",
        PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
        PlayerOutcomes(),
    )


def _roster():
    return TeamRoster(team="BUF", players=[_qb()])


def _state():
    return GameState(
        quarter=3,
        clock=400,
        possession="away",
        down=3,
        distance=8,
        yard_line=35,
        home_score=17,
        away_score=14,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
        week=9,
    )


def _config(tmp_path, **overrides):
    values = {"enabled": True, "artifacts_dir": str(tmp_path)}
    values.update(overrides)
    return QbScrambleModelConfig(**values)


def _artifact(**overrides):
    values = {
        "schema_version": QB_SCRAMBLE_SCHEMA_VERSION,
        "model_type": QB_SCRAMBLE_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 1.75],
        "probability_clamp": [0.0, 0.25],
        "priors": {
            "qb": {"QB1": 0.08},
            "team": {"BUF": 0.08},
            "opponent_allowed": {"KC": 0.07},
            "league": 0.06,
        },
        "diagnostics": {"num_examples": 500, "scramble_rate": 0.06},
    }
    values.update(overrides)
    return values


def _write_artifact(tmp_path, **overrides):
    path = tmp_path / "qb_scramble_model_2024.json"
    path.write_text(json.dumps(_artifact(**overrides)), encoding="utf-8")
    return path


def _build_context(model):
    return model.build_context(
        roster=_roster(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=9,
        is_home=False,
    )


def _designed_config(tmp_path, **overrides):
    values = {"enabled": True, "artifacts_dir": str(tmp_path)}
    values.update(overrides)
    return QbDesignedRunModelConfig(**values)


def _designed_artifact(**overrides):
    values = {
        "schema_version": QB_DESIGNED_RUN_SCHEMA_VERSION,
        "model_type": QB_DESIGNED_RUN_MODEL_TYPE,
        "target_season": 2024,
        "source_seasons": [2023],
        "feature_names": ["intercept"],
        "coefficients": {"intercept": 0.0},
        "factor_clamp": [0.50, 2.00],
        "priors": {
            "qb": {"QB1": 0.12},
            "team": {"BUF": 0.08},
            "opponent_allowed": {"KC": 0.07},
            "league": 0.06,
            "mobility_tiers": {"QB1": "high"},
        },
        "tail_buckets": {"global": [6, 9, 12]},
        "diagnostics": {"num_examples": 500, "designed_qb_run_rate": 0.06},
    }
    values.update(overrides)
    return values


def _write_designed_artifact(tmp_path, **overrides):
    path = tmp_path / "qb_designed_run_model_2024.json"
    path.write_text(json.dumps(_designed_artifact(**overrides)), encoding="utf-8")
    return path


def _build_designed_context(model):
    return model.build_context(
        roster=_roster(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        target_season=2024,
        week=9,
        is_home=False,
    )


def test_missing_artifact_returns_none_from_build_context(tmp_path):
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_valid_artifact_builds_context(tmp_path):
    _write_artifact(tmp_path)
    model = QbScrambleModel(_config(tmp_path))

    context = _build_context(model)

    assert context is not None
    assert context.scramble_probability(_state(), _qb()) == pytest.approx(0.08)


def test_invalid_schema_returns_none(tmp_path):
    _write_artifact(tmp_path, schema_version=999)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_non_finite_coefficient_returns_none(tmp_path):
    _write_artifact(tmp_path, coefficients={"intercept": "nan"})
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_unsupported_feature_name_returns_none(tmp_path):
    _write_artifact(
        tmp_path,
        feature_names=["intercept", "unsupported_feature"],
        coefficients={"intercept": 0.0, "unsupported_feature": 1.0},
    )
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_duplicate_feature_names_return_none(tmp_path):
    _write_artifact(
        tmp_path,
        feature_names=["intercept", "intercept"],
        coefficients={"intercept": 1.0},
    )
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_artifact_below_min_examples_returns_none(tmp_path):
    _write_artifact(tmp_path, diagnostics={"num_examples": 499, "scramble_rate": 0.06})
    model = QbScrambleModel(_config(tmp_path, min_examples=500))

    assert _build_context(model) is None


def test_artifact_target_season_mismatch_returns_none(tmp_path):
    _write_artifact(tmp_path, target_season=2023)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


@pytest.mark.parametrize("source_seasons", [[], [2024], [2023, 2024], ["2023"]])
def test_artifact_with_invalid_source_seasons_returns_none(tmp_path, source_seasons):
    _write_artifact(tmp_path, source_seasons=source_seasons)
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None



def test_invalid_utf8_artifact_returns_none(tmp_path):
    (tmp_path / "qb_scramble_model_2024.json").write_bytes(b"\xff\xfe\x00")
    model = QbScrambleModel(_config(tmp_path))

    assert _build_context(model) is None


def test_invalid_artifact_clamps_fall_back_to_config_clamps(tmp_path):
    _write_artifact(
        tmp_path,
        factor_clamp=[2.0, 1.0],
        probability_clamp=[-1.0, 2.0],
    )
    model = QbScrambleModel(
        _config(
            tmp_path,
            factor_clamp=(0.75, 1.25),
            probability_clamp=(0.01, 0.20),
        )
    )

    context = _build_context(model)

    assert context is not None
    assert context.factor_clamp == (0.75, 1.25)
    assert context.probability_clamp == (0.01, 0.20)


def test_valid_artifact_clamps_override_config_clamps(tmp_path):
    _write_artifact(
        tmp_path,
        factor_clamp=[0.60, 1.40],
        probability_clamp=[0.02, 0.22],
    )
    model = QbScrambleModel(
        _config(
            tmp_path,
            factor_clamp=(0.75, 1.25),
            probability_clamp=(0.01, 0.20),
        )
    )

    context = _build_context(model)

    assert context is not None
    assert context.factor_clamp == (0.60, 1.40)
    assert context.probability_clamp == (0.02, 0.22)


def test_malformed_priors_fall_back_to_league_and_default(tmp_path):
    _write_artifact(
        tmp_path,
        priors={
            "team": {"BUF": "nan"},
            "opponent_allowed": "bad",
            "league": 0.06,
        },
    )
    model = QbScrambleModel(_config(tmp_path))

    context = _build_context(model)

    assert context is not None
    assert context.team_prior_scramble_rate == pytest.approx(0.06)
    assert context.opponent_prior_scramble_rate_allowed == pytest.approx(0.06)


def test_malformed_priors_without_valid_league_fall_back_to_default(tmp_path):
    _write_artifact(tmp_path, priors={"team": {"BUF": "nan"}, "league": "bad"})
    model = QbScrambleModel(_config(tmp_path))

    context = _build_context(model)

    assert context is not None
    assert context.team_prior_scramble_rate == pytest.approx(0.05)
    assert context.opponent_prior_scramble_rate_allowed == pytest.approx(0.05)


def test_missing_designed_run_artifact_returns_none(tmp_path):
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_valid_designed_run_artifact_builds_context(tmp_path):
    _write_designed_artifact(tmp_path)
    model = QbDesignedRunModel(_designed_config(tmp_path))

    context = _build_designed_context(model)

    assert context is not None
    assert context.team == "BUF"
    assert context.mobility_tiers["QB1"] == "high"
    assert context.global_tail_yards == (6, 9, 12)


def test_invalid_designed_run_schema_returns_none(tmp_path):
    _write_designed_artifact(tmp_path, schema_version=999)
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_designed_run_artifact_below_min_examples_returns_none(tmp_path):
    _write_designed_artifact(tmp_path, diagnostics={"num_examples": 499, "designed_qb_run_rate": 0.06})
    model = QbDesignedRunModel(_designed_config(tmp_path, min_examples=500))

    assert _build_designed_context(model) is None


def test_designed_run_artifact_requires_tail_buckets(tmp_path):
    _write_designed_artifact(tmp_path, tail_buckets={})
    model = QbDesignedRunModel(_designed_config(tmp_path))

    assert _build_designed_context(model) is None


def test_invalid_designed_run_clamp_falls_back_to_config(tmp_path):
    _write_designed_artifact(tmp_path, factor_clamp=[2.0, 1.0])
    model = QbDesignedRunModel(_designed_config(tmp_path, factor_clamp=(0.75, 1.25)))

    context = _build_designed_context(model)

    assert context is not None
    assert context.factor_clamp == (0.75, 1.25)
