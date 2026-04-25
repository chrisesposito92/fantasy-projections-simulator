import numpy as np
import pytest

from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_DESIGNED_RUN_FEATURES,
    DEFAULT_QB_SCRAMBLE_FEATURES,
)
from fantasy_sim.data.qb_rushing.training import (
    QbDesignedRunTrainingExample,
    QbScrambleTrainingExample,
    annotate_rusher_positions,
    build_designed_run_example_from_row,
    build_designed_run_priors,
    build_designed_run_tail_buckets,
    build_example_from_row,
    build_scramble_priors,
    fit_logistic_qb_designed_run,
    fit_logistic_qb_scramble,
    source_seasons_for_artifact,
)


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "BUF",
        "defteam": "KC",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "pass",
        "passer_player_id": "QB1",
        "passer_player_name": "Mobile QB",
        "qb_scramble": 0,
        "down": 3,
        "ydstogo": 8,
        "yardline_100": 35,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
    }
    row.update(overrides)
    return row


def _designed_run_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "season": 2023,
        "week": 5,
        "posteam": "BUF",
        "defteam": "KC",
        "home_team": "KC",
        "away_team": "BUF",
        "play_type": "run",
        "rusher_player_id": "QB1",
        "rusher_position": "QB",
        "qb_scramble": 0,
        "qb_kneel": 0,
        "qb_spike": 0,
        "no_play": 0,
        "yards_gained": 12,
        "down": 3,
        "ydstogo": 2,
        "yardline_100": 18,
        "qtr": 4,
        "quarter_seconds_remaining": 118,
        "score_differential": -6,
        "spread_line": 2.5,
        "total_line": 48.5,
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


def test_build_scramble_priors_counts_dropbacks_and_scrambles():
    priors = build_scramble_priors(
        [
            _row(passer_player_id="QB1", posteam="BUF", defteam="KC", qb_scramble=1),
            _row(passer_player_id="QB1", posteam="BUF", defteam="KC", qb_scramble=0),
            _row(passer_player_id="QB2", posteam="KC", defteam="BUF", qb_scramble=0),
        ]
    )

    assert priors.qb["QB1"] == pytest.approx(0.5)
    assert priors.team["BUF"] == pytest.approx(0.5)
    assert priors.opponent_allowed["KC"] == pytest.approx(0.5)
    assert priors.league == pytest.approx(1 / 3)


def test_build_example_from_row_returns_scramble_label_and_base_rate():
    priors = build_scramble_priors(
        [_row(qb_scramble=1), _row(qb_scramble=1, week=6), _row(qb_scramble=0)]
    )

    example = build_example_from_row(_row(qb_scramble=1), DEFAULT_QB_SCRAMBLE_FEATURES, priors)

    assert example is not None
    assert example.label == 1
    assert example.base_rate == pytest.approx(0.5)
    assert example.features.shape == (len(DEFAULT_QB_SCRAMBLE_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_example_from_row_keeps_scramble_run_rows():
    priors = build_scramble_priors([_row(play_type="run", qb_scramble=1)])

    example = build_example_from_row(
        _row(play_type="run", qb_scramble=1),
        DEFAULT_QB_SCRAMBLE_FEATURES,
        priors,
    )

    assert example is not None
    assert example.label == 1


def test_scramble_run_rows_use_rusher_id_when_passer_id_missing():
    row = _row(
        play_type="run",
        qb_scramble=1,
        passer_player_id=None,
        rusher_player_id="QB1",
    )
    priors = build_scramble_priors([row, _row(passer_player_id="QB2", qb_scramble=0)])

    example = build_example_from_row(row, DEFAULT_QB_SCRAMBLE_FEATURES, priors)

    assert priors.qb["QB1"] == pytest.approx(1.0)
    assert example is not None
    assert example.label == 1
    assert example.base_rate == pytest.approx(0.0)


def test_build_example_from_row_uses_leave_one_out_base_rate():
    row = _row(qb_scramble=1)
    priors = build_scramble_priors([row])

    example = build_example_from_row(row, DEFAULT_QB_SCRAMBLE_FEATURES, priors)

    assert priors.qb["QB1"] == pytest.approx(1.0)
    assert priors.league == pytest.approx(1.0)
    assert example is not None
    assert example.base_rate == pytest.approx(0.05)


def test_build_example_from_row_skips_non_pass_non_scramble_rows():
    priors = build_scramble_priors([_row()])

    assert build_example_from_row(
        _row(play_type="run", qb_scramble=0),
        DEFAULT_QB_SCRAMBLE_FEATURES,
        priors,
    ) is None


def test_fit_logistic_qb_scramble_rejects_empty_examples():
    with pytest.raises(ValueError, match="zero examples"):
        fit_logistic_qb_scramble([], ("intercept",))


def test_fit_logistic_qb_scramble_learns_positive_feature_for_scramble():
    examples = [
        QbScrambleTrainingExample(
            features=np.array([1.0, 1.0]),
            label=1,
            base_rate=0.10,
        )
        for _ in range(30)
    ] + [
        QbScrambleTrainingExample(
            features=np.array([1.0, 0.0]),
            label=0,
            base_rate=0.10,
        )
        for _ in range(30)
    ]

    result = fit_logistic_qb_scramble(
        examples,
        ("intercept", "pressure_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["pressure_feature"] > 0
    assert result.converged is True


def test_annotate_rusher_positions_uses_roster_position():
    rows = [_designed_run_row(rusher_position=None)]
    positions = {"QB1": "QB"}

    annotated = annotate_rusher_positions(rows, positions)

    assert annotated[0]["rusher_position"] == "QB"


def test_build_designed_run_priors_excludes_scrambles_and_kneels():
    priors = build_designed_run_priors(
        [
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=0),
            _designed_run_row(rusher_player_id="RB1", rusher_position="RB", qb_scramble=0),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=1),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_kneel=1),
        ]
    )

    assert priors.league == pytest.approx(0.5)
    assert priors.team["BUF"] == pytest.approx(0.5)
    assert priors.opponent_allowed["KC"] == pytest.approx(0.5)
    assert priors.qb["QB1"] == pytest.approx(1.0)


def test_build_designed_run_example_from_row_uses_qb_label_and_features():
    rows = [
        _designed_run_row(rusher_player_id="QB1", rusher_position="QB"),
        _designed_run_row(rusher_player_id="RB1", rusher_position="RB"),
    ]
    priors = build_designed_run_priors(rows)

    example = build_designed_run_example_from_row(
        rows[0],
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    )

    assert example is not None
    assert example.label == 1
    assert example.base_rate == pytest.approx(0.5)
    assert example.features.shape == (len(DEFAULT_QB_DESIGNED_RUN_FEATURES),)
    assert np.isfinite(example.features).all()


def test_build_designed_run_example_skips_scrambles_and_non_run_rows():
    priors = build_designed_run_priors([_designed_run_row()])

    assert build_designed_run_example_from_row(
        _designed_run_row(qb_scramble=1),
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    ) is None
    assert build_designed_run_example_from_row(
        _designed_run_row(play_type="pass"),
        DEFAULT_QB_DESIGNED_RUN_FEATURES,
        priors,
    ) is None


def test_fit_logistic_qb_designed_run_learns_positive_feature():
    examples = [
        QbDesignedRunTrainingExample(
            features=np.array([1.0, 1.0]),
            label=1,
            base_rate=0.10,
        )
        for _ in range(30)
    ] + [
        QbDesignedRunTrainingExample(
            features=np.array([1.0, 0.0]),
            label=0,
            base_rate=0.10,
        )
        for _ in range(30)
    ]

    result = fit_logistic_qb_designed_run(
        examples,
        ("intercept", "mobile_feature"),
        l2=0.1,
        max_iter=100,
    )

    assert result.num_examples == 60
    assert result.coefficients["mobile_feature"] > 0
    assert result.converged is True


def test_build_designed_run_tail_buckets_uses_only_qb_designed_rows():
    buckets = build_designed_run_tail_buckets(
        [
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", yards_gained=12),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", yards_gained=7),
            _designed_run_row(rusher_player_id="QB1", rusher_position="QB", qb_scramble=1, yards_gained=40),
            _designed_run_row(rusher_player_id="RB1", rusher_position="RB", yards_gained=99),
        ],
        mobility_tiers={"QB1": "high"},
    )

    assert buckets["global"] == (12, 7)
    assert 40 not in buckets["global"]
    assert 99 not in buckets["global"]
