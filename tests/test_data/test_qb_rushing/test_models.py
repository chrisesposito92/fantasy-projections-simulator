import numpy as np
import pytest

from fantasy_sim.data.qb_rushing.models import (
    DEFAULT_QB_SCRAMBLE_FEATURES,
    QbScrambleContext,
    qb_scramble_feature_values,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage


def _state(**overrides):
    values = {
        "quarter": 4,
        "clock": 95,
        "possession": "away",
        "down": 3,
        "distance": 8,
        "yard_line": 18,
        "home_score": 21,
        "away_score": 14,
        "home_team": "KC",
        "away_team": "BUF",
        "receiving_2nd_half": "away",
        "week": 9,
    }
    values.update(overrides)
    return GameState(**values)


def _qb(scramble_rate=0.08):
    return PlayerModel(
        "QB1",
        "Mobile QB",
        "QB",
        "BUF",
        PlayerUsage(snap_share=1.0, scramble_rate=scramble_rate),
        PlayerOutcomes(),
    )


def test_feature_values_include_state_market_and_priors():
    values = qb_scramble_feature_values(
        _state(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        week=9,
        spread_line=-3.0,
        total_line=48.0,
        implied_team_total=22.5,
        qb_prior_scramble_rate=0.10,
        team_prior_scramble_rate=0.08,
        opponent_prior_scramble_rate_allowed=0.07,
    )

    assert set(DEFAULT_QB_SCRAMBLE_FEATURES).issubset(values)
    assert values["down_3"] == 1.0
    assert values["is_red_zone"] == 1.0
    assert values["is_two_minute"] == 1.0
    assert values["is_trailing"] == 1.0
    assert values["is_home"] == 0.0
    assert values["spread_norm"] == pytest.approx(-3.0 / 14.0)
    assert values["qb_prior_scramble_rate"] == pytest.approx(0.10)


def test_context_returns_probability_anchored_to_player_prior():
    context = QbScrambleContext(
        coefficients={"intercept": 0.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
    )

    assert context.scramble_probability(_state(), _qb(0.08)) == pytest.approx(0.08)


def test_context_clamps_factor_and_probability():
    context = QbScrambleContext(
        coefficients={"intercept": 10.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
        factor_clamp=(0.50, 1.50),
        probability_clamp=(0.0, 0.20),
    )

    assert context.scramble_probability(_state(), _qb(0.10)) == pytest.approx(0.15)


def test_context_keeps_zero_base_rate_at_zero():
    context = QbScrambleContext(
        coefficients={"intercept": 10.0},
        feature_names=("intercept",),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
    )

    assert context.scramble_probability(_state(), _qb(0.0)) == 0.0


def test_context_sanitizes_non_finite_market_inputs():
    context = QbScrambleContext(
        coefficients={"intercept": 0.0, "spread_norm": 1.0, "total_norm": 1.0},
        feature_names=("intercept", "spread_norm", "total_norm"),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        target_season=2024,
        week=9,
        spread_line=float("nan"),
        total_line=float("inf"),
        implied_team_total="bad",
    )

    values = qb_scramble_feature_values(
        _state(),
        team="BUF",
        opponent="KC",
        home_team="KC",
        away_team="BUF",
        is_home=False,
        week=9,
        spread_line=float("nan"),
        total_line=float("inf"),
        implied_team_total="bad",
        qb_prior_scramble_rate=0.10,
        team_prior_scramble_rate=0.08,
        opponent_prior_scramble_rate_allowed=0.07,
    )

    assert np.isfinite(list(values.values())).all()
    assert context.scramble_probability(_state(), _qb(0.08)) == pytest.approx(0.08)
