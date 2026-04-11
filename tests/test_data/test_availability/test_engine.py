from __future__ import annotations

import numpy as np
import polars as pl

from fantasy_sim.data.availability.engine import AvailabilityEngine
from fantasy_sim.data.availability.models import AvailabilityConfig
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "QB1",
                "Starter QB",
                "QB",
                "KC",
                PlayerUsage(snap_share=1.0),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "QB2",
                "Backup QB",
                "QB",
                "KC",
                PlayerUsage(snap_share=0.2),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "WR1",
                "Wide One",
                "WR",
                "KC",
                PlayerUsage(target_share=0.30),
                PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8.0, 12.0])),
            ),
        ],
    )


class _StubRoleInputs:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame

    def load_weekly(self, seasons: list[int]) -> pl.DataFrame:
        return self.frame


def _config() -> AvailabilityConfig:
    return AvailabilityConfig(enabled=True)


def test_explicit_out_zeroes_receiver_share():
    frame = pl.DataFrame(
        {
            "season": [2024],
            "week": [5],
            "team": ["KC"],
            "player_id": ["WR1"],
            "position": ["WR"],
            "attempts": [0],
            "carries": [0],
            "targets": [7],
            "offense_pct": [0.75],
            "report_status": ["Out"],
            "practice_status": ["Did Not Participate"],
            "depth_position": ["WR1"],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    decisions = engine.apply(roster, season=2024, week=5)

    wr = next(player for player in roster.players if player.player_id == "WR1")
    assert wr.usage.target_share == 0.0
    assert decisions["WR1"].hard_inactive is True
    assert decisions["WR1"].reason == "injury:Out"


def test_usage_only_low_usage_soft_dampens_but_does_not_bench_qb():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [2, 3, 4],
            "team": ["KC", "KC", "KC"],
            "player_id": ["QB1", "QB1", "QB1"],
            "position": ["QB", "QB", "QB"],
            "attempts": [10, 11, 9],
            "carries": [1, 0, 1],
            "targets": [0, 0, 0],
            "offense_pct": [0.61, 0.59, 0.58],
            "report_status": [None, None, None],
            "practice_status": [None, None, None],
            "depth_position": [None, None, None],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    engine.apply(roster, season=2024, week=5)

    qb = next(player for player in roster.players if player.player_id == "QB1")
    assert 0.0 < qb.usage.snap_share < 1.0


def test_explicit_qb1_depth_chart_demotes_backup():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [5, 5],
            "team": ["KC", "KC"],
            "player_id": ["QB1", "QB2"],
            "position": ["QB", "QB"],
            "attempts": [0, 0],
            "carries": [0, 0],
            "targets": [0, 0],
            "offense_pct": [0.70, 0.20],
            "report_status": [None, None],
            "practice_status": [None, None],
            "depth_position": ["QB1", "QB2"],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    engine.apply(roster, season=2024, week=5)

    qb1 = next(player for player in roster.players if player.player_id == "QB1")
    qb2 = next(player for player in roster.players if player.player_id == "QB2")
    assert qb1.usage.snap_share == 1.0
    assert qb2.usage.snap_share == 0.0


def test_usage_only_stays_neutral_when_participation_data_is_missing():
    frame = pl.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "week": [2, 3, 4],
            "team": ["KC", "KC", "KC"],
            "player_id": ["QB1", "QB1", "QB1"],
            "position": ["QB", "QB", "QB"],
            "attempts": [10, 11, 9],
            "carries": [1, 0, 1],
            "targets": [0, 0, 0],
            "offense_pct": [None, None, None],
            "report_status": [None, None, None],
            "practice_status": [None, None, None],
            "depth_position": [None, None, None],
        }
    )
    roster = _roster()
    engine = AvailabilityEngine(_config(), role_inputs_loader=_StubRoleInputs(frame))

    decisions = engine.apply(roster, season=2024, week=5)

    qb = next(player for player in roster.players if player.player_id == "QB1")
    assert qb.usage.snap_share == 1.0
    assert decisions["QB1"].factor == 1.0
    assert decisions["QB1"].reason is None
