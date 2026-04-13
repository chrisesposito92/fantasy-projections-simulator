from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from fantasy_sim.data.tracking.config import load_tracking_config
from fantasy_sim.data.tracking.receiver_participation import ReceiverParticipationEngine
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_player(
    player_id: str,
    position: str,
    target_share: float,
    air_yards_share: float,
    catch_rate: float,
    receiving_yards_dist: list[float] | None = None,
) -> PlayerModel:
    return PlayerModel(
        player_id=player_id,
        name=player_id,
        position=position,
        team="BUF",
        usage=PlayerUsage(
            target_share=target_share,
            air_yards_share=air_yards_share,
        ),
        outcomes=PlayerOutcomes(
            catch_rate=catch_rate,
            receiving_yards_dist=None if receiving_yards_dist is None else np.array(receiving_yards_dist),
        ),
    )


def _bounded_factor(value: float, baseline: float, sensitivity: float, clamp: tuple[float, float]) -> float:
    lower, upper = clamp
    factor = 1.0 + ((value - baseline) / baseline) * sensitivity
    return float(min(max(factor, lower), upper))


def test_receiver_participation_boosts_wr_usage_and_catch_rate():
    roster = TeamRoster(
        team="BUF",
        players=[
            _make_player("wr-1", "WR", target_share=0.20, air_yards_share=0.18, catch_rate=0.62, receiving_yards_dist=[10.0, 20.0]),
            _make_player("te-1", "TE", target_share=0.12, air_yards_share=0.10, catch_rate=0.66),
        ],
    )
    features = pl.DataFrame(
        {
            "team": ["BUF", "BUF", "BUF", "NYJ"],
            "player_id": ["wr-1", "wr-2", "te-1", "nyj-wr"],
            "targets": [16, 14, 7, 20],
            "catchable_rate": [0.82, 0.61, 0.77, 0.98],
            "contested_rate": [0.12, 0.19, 0.24, 0.40],
            "mean_air_yards": [14.5, 9.4, 10.8, 3.5],
        }
    )
    engine = ReceiverParticipationEngine(load_tracking_config({}).receiver_participation)

    engine.apply(roster, features)

    wr = roster.players[0]
    catchable_baseline = features.get_column("catchable_rate").mean()
    contested_baseline = features.get_column("contested_rate").mean()
    air_yards_baseline = features.get_column("mean_air_yards").mean()

    target_factor = _bounded_factor(
        0.82,
        catchable_baseline,
        engine.config.target_share_sensitivity,
        engine.config.factor_clamp,
    )
    air_factor = _bounded_factor(
        14.5,
        air_yards_baseline,
        engine.config.air_yards_sensitivity,
        engine.config.factor_clamp,
    )
    catchable_factor = _bounded_factor(
        0.82,
        catchable_baseline,
        engine.config.catchable_target_sensitivity,
        engine.config.factor_clamp,
    )
    contested_factor = _bounded_factor(
        0.12,
        contested_baseline,
        engine.config.contested_target_sensitivity,
        engine.config.factor_clamp,
    )

    assert wr.usage.target_share == pytest.approx(0.20 * target_factor)
    assert wr.usage.air_yards_share == pytest.approx(0.18 * air_factor)
    assert wr.outcomes.catch_rate == pytest.approx(0.62 * catchable_factor * contested_factor)
    assert wr.outcomes.receiving_yards_dist == pytest.approx(np.array([10.0, 20.0]) * air_factor)


def test_receiver_participation_skips_te_below_min_targets():
    roster = TeamRoster(
        team="BUF",
        players=[
            _make_player("wr-1", "WR", target_share=0.20, air_yards_share=0.18, catch_rate=0.62),
            _make_player("te-1", "TE", target_share=0.12, air_yards_share=0.10, catch_rate=0.66),
        ],
    )
    features = pl.DataFrame(
        {
            "team": ["BUF", "BUF", "BUF"],
            "player_id": ["wr-1", "wr-2", "te-1"],
            "targets": [16, 14, 7],
            "catchable_rate": [0.82, 0.61, 0.91],
            "contested_rate": [0.12, 0.19, 0.22],
            "mean_air_yards": [14.5, 9.4, 11.0],
        }
    )
    engine = ReceiverParticipationEngine(load_tracking_config({}).receiver_participation)

    engine.apply(roster, features)

    te = roster.players[1]
    assert te.usage.target_share == 0.12
    assert te.usage.air_yards_share == 0.10
    assert te.outcomes.catch_rate == 0.66
