from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.tracking.models import RbEfficiencyConfig
from fantasy_sim.data.tracking.rb_efficiency import RbEfficiencyEngine, _bounded_factor
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_rb(
    player_id: str,
    carry_share: float,
    rushing_yards_dist: list[float] | None = None,
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


def test_rb_efficiency_boosts_carry_share_and_rushing_yards_dist():
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
            "attempts": [18, 18],
            "no_huddle_rate": [0.12, 0.18],
            "play_action_rate": [0.24, 0.20],
            "rush_yoe_per_att": [1.6, 0.4],
        }
    )
    engine = RbEfficiencyEngine(RbEfficiencyConfig())

    engine.apply(roster, features)

    baseline = features.get_column("rush_yoe_per_att").mean()
    carry_factor = _bounded_factor(
        1.6,
        baseline,
        engine.config.carry_share_sensitivity,
        engine.config.factor_clamp,
    )
    yards_factor = _bounded_factor(
        1.6,
        baseline,
        engine.config.rush_yards_sensitivity,
        engine.config.factor_clamp,
    )

    rb = roster.players[0]
    assert rb.usage.carry_share == pytest.approx(0.20 * carry_factor)
    assert rb.outcomes.rushing_yards_dist == pytest.approx(np.array([5.0, 10.0]) * yards_factor)


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
