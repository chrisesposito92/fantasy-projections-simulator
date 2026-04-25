from types import SimpleNamespace

import pytest

from fantasy_sim.data.play_call_model import PlayCallContext, play_call_feature_values
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


def _context(**overrides):
    values = {
        "coefficients": {"intercept": 0.0},
        "feature_names": ("intercept",),
        "team": "BUF",
        "opponent": "KC",
        "home_team": "KC",
        "away_team": "BUF",
        "is_home": False,
        "target_season": 2024,
        "week": 9,
    }
    values.update(overrides)
    return PlayCallContext(**values)


@pytest.mark.parametrize(
    ("coefficient", "expected"),
    [
        (10.0, 0.90),
        (-10.0, 0.10),
    ],
)
def test_pass_probability_applies_configured_clamp(coefficient, expected):
    context = _context(
        coefficients={"intercept": coefficient},
        probability_clamp=(0.10, 0.90),
    )

    assert context.pass_probability(_state()) == pytest.approx(expected)


def test_pass_probability_returns_none_for_non_finite_logit():
    context = _context(coefficients={"intercept": float("nan")})

    assert context.pass_probability(_state()) is None


def test_play_call_feature_values_sets_flags_and_normalized_values():
    features = play_call_feature_values(
        _state(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        week=9,
        spread_line=7.0,
        total_line=51.0,
        implied_team_total=28.0,
        team_prior_pass_rate=1.2,
        opponent_prior_pass_rate_allowed=-0.2,
        script=SimpleNamespace(regime="trailing_late"),
    )

    assert features["down_3"] == 1.0
    assert features["is_short"] == 1.0
    assert features["distance_norm"] == 0.10
    assert features["yard_line_norm"] == 0.18
    assert features["is_red_zone"] == 1.0
    assert features["is_two_minute"] == 1.0
    assert features["is_trailing"] == 1.0
    assert features["is_home"] == 0.0
    assert features["spread_norm"] == 0.5
    assert features["total_norm"] == 0.5
    assert features["implied_total_norm"] == 0.6
    assert features["week_norm"] == 0.5
    assert features["team_prior_pass_rate"] == 1.0
    assert features["opponent_prior_pass_rate_allowed"] == 0.0
    assert features["trailing_late"] == 1.0
