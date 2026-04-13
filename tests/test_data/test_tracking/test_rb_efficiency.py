from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.tracking.models import RbEfficiencyConfig
from fantasy_sim.data.tracking.rb_efficiency import RbEfficiencyEngine, _bounded_factor
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_rb(
    player_id: str,
    carry_share: float,
    rushing_yards_dist: Sequence[float] | None = None,
) -> PlayerModel:
    return PlayerModel(
        player_id=player_id,
        name=player_id,
        position="RB",
        team="BUF",
        usage=PlayerUsage(carry_share=carry_share),
        outcomes=PlayerOutcomes(
            rushing_yards_dist=None
            if rushing_yards_dist is None
            else np.array(rushing_yards_dist, dtype=float),
        ),
    )


def _sample_int_yards(values: np.ndarray) -> int:
    return int(np.random.default_rng(0).choice(values))


def test_rb_efficiency_treats_rush_yoe_as_zero_centered_signal():
    roster = TeamRoster(
        team="BUF",
        players=[
            _make_rb("rb-positive", carry_share=0.20, rushing_yards_dist=[5.0, 10.0]),
            _make_rb("rb-negative", carry_share=0.18, rushing_yards_dist=[3.0, 8.0]),
        ],
    )
    features = pl.DataFrame(
        {
            "team": ["BUF", "BUF"],
            "player_id": ["rb-positive", "rb-negative"],
            "attempts": [18, 18],
            "no_huddle_rate": [0.12, 0.18],
            "play_action_rate": [0.24, 0.20],
            "rush_yoe_per_att": [1.6, -1.0],
        }
    )
    engine = RbEfficiencyEngine(RbEfficiencyConfig())

    engine.apply(roster, features)

    positive_factor = _bounded_factor(
        1.6,
        0.0,
        engine.config.carry_share_sensitivity,
        engine.config.factor_clamp,
    )
    negative_factor = _bounded_factor(
        -1.0,
        0.0,
        engine.config.carry_share_sensitivity,
        engine.config.factor_clamp,
    )

    positive = roster.players[0]
    negative = roster.players[1]
    assert positive.usage.carry_share == pytest.approx(0.20 * positive_factor)
    assert negative.usage.carry_share == pytest.approx(0.18 * negative_factor)
    assert positive.usage.carry_share > 0.20
    assert negative.usage.carry_share < 0.18


def test_rb_efficiency_rounds_rushing_yards_for_integer_sampling():
    roster = TeamRoster(
        team="BUF",
        players=[_make_rb("rb-1", carry_share=0.20, rushing_yards_dist=[10.0])],
    )
    features = pl.DataFrame(
        {
            "team": ["BUF"],
            "player_id": ["rb-1"],
            "attempts": [18],
            "no_huddle_rate": [0.12],
            "play_action_rate": [0.24],
            "rush_yoe_per_att": [2.0],
        }
    )
    engine = RbEfficiencyEngine(RbEfficiencyConfig())

    engine.apply(roster, features)

    adjusted_dist = roster.players[0].outcomes.rushing_yards_dist
    assert adjusted_dist is not None
    assert np.issubdtype(adjusted_dist.dtype, np.integer)
    assert _sample_int_yards(adjusted_dist) == 11
    assert _sample_int_yards(adjusted_dist) != _sample_int_yards(np.array([10.0]))


def test_rb_efficiency_skips_rb_below_min_attempts():
    roster = TeamRoster(
        team="BUF",
        players=[
            _make_rb("rb-1", carry_share=0.20, rushing_yards_dist=[5.0, 10.0]),
            _make_rb("rb-2", carry_share=0.18, rushing_yards_dist=[3.0, 8.0]),
        ],
    )
    features = pl.DataFrame(
        {
            "team": ["BUF", "BUF"],
            "player_id": ["rb-1", "rb-2"],
            "attempts": [10, 18],
            "no_huddle_rate": [0.12, 0.18],
            "play_action_rate": [0.24, 0.20],
            "rush_yoe_per_att": [1.9, 0.4],
        }
    )
    engine = RbEfficiencyEngine(RbEfficiencyConfig())

    engine.apply(roster, features)

    rb = roster.players[0]
    assert rb.usage.carry_share == 0.20
    np.testing.assert_allclose(rb.outcomes.rushing_yards_dist, np.array([5.0, 10.0]))
