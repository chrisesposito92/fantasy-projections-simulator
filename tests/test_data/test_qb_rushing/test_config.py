import pytest

from fantasy_sim.data.qb_rushing import load_qb_rushing_config


def test_missing_config_is_disabled():
    config = load_qb_rushing_config({})

    assert config.scramble.enabled is False
    assert config.scramble.artifacts_dir is None
    assert config.scramble.factor_clamp == (0.50, 1.75)
    assert config.scramble.probability_clamp == (0.0, 0.25)
    assert config.scramble.min_examples == 500


def test_missing_config_disables_designed_runs():
    config = load_qb_rushing_config({})

    assert config.designed_runs.enabled is False
    assert config.designed_runs.artifacts_dir is None
    assert config.designed_runs.factor_clamp == (0.50, 2.00)
    assert config.designed_runs.min_examples == 500
    assert config.designed_runs.min_tail_samples == 20


def test_loads_enabled_config_values():
    config = load_qb_rushing_config(
        {
            "qb_rushing": {
                "scramble": {
                    "enabled": True,
                    "artifacts_dir": "results/qb_rushing/scramble/test",
                    "factor_clamp": [0.75, 1.40],
                    "probability_clamp": [0.01, 0.20],
                    "min_examples": 250,
                }
            }
        }
    )

    assert config.scramble.enabled is True
    assert config.scramble.artifacts_dir == "results/qb_rushing/scramble/test"
    assert config.scramble.factor_clamp == (0.75, 1.40)
    assert config.scramble.probability_clamp == (0.01, 0.20)
    assert config.scramble.min_examples == 250


def test_loads_designed_run_config_values():
    config = load_qb_rushing_config(
        {
            "qb_rushing": {
                "designed_runs": {
                    "enabled": True,
                    "artifacts_dir": "results/qb_rushing/designed_runs/test",
                    "factor_clamp": [0.75, 1.60],
                    "min_examples": 250,
                    "min_tail_samples": 12,
                }
            }
        }
    )

    assert config.designed_runs.enabled is True
    assert config.designed_runs.artifacts_dir == "results/qb_rushing/designed_runs/test"
    assert config.designed_runs.factor_clamp == (0.75, 1.60)
    assert config.designed_runs.min_examples == 250
    assert config.designed_runs.min_tail_samples == 12


@pytest.mark.parametrize(
    "clamp",
    [[0.50], [1.75, 0.50], [-0.01, 1.75], [0.50, float("inf")]],
)
def test_invalid_factor_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\\.scramble\\.factor_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"factor_clamp": clamp}}}
        )


@pytest.mark.parametrize(
    "clamp",
    [[0.50], [2.00, 0.50], [-0.01, 2.00], [0.50, float("inf")]],
)
def test_invalid_designed_run_factor_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\\.designed_runs\\.factor_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"designed_runs": {"factor_clamp": clamp}}}
        )


@pytest.mark.parametrize(
    "clamp",
    [[0.0], [0.25, 0.0], [-0.01, 0.25], [0.0, 1.01]],
)
def test_invalid_probability_clamp_raises(clamp):
    with pytest.raises(ValueError, match="qb_rushing\\.scramble\\.probability_clamp"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"probability_clamp": clamp}}}
        )


def test_invalid_min_examples_raises():
    with pytest.raises(ValueError, match="qb_rushing\\.scramble\\.min_examples"):
        load_qb_rushing_config(
            {"qb_rushing": {"scramble": {"min_examples": 0}}}
        )


@pytest.mark.parametrize("field", ["min_examples", "min_tail_samples"])
def test_invalid_designed_run_minimums_raise(field):
    with pytest.raises(ValueError, match=f"qb_rushing\\.designed_runs\\.{field}"):
        load_qb_rushing_config(
            {"qb_rushing": {"designed_runs": {field: 0}}}
        )
