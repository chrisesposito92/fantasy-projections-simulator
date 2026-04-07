"""Tests for parallel game simulation runner."""

import os
from unittest.mock import patch

from fantasy_sim.validation.parallel import default_max_workers


class TestDefaultMaxWorkers:
    def test_basic_computation(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 10  # (12 - 2) // 1 = 10, min(10, 288) = 10

    def test_scales_by_concurrent_seasons(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=288, num_concurrent=2)
            assert result == 5  # (12 - 2) // 2 = 5

    def test_capped_by_batch_size(self):
        with patch.object(os, "cpu_count", return_value=12):
            result = default_max_workers(batch_size=3, num_concurrent=1)
            assert result == 3  # min(10, 3) = 3

    def test_minimum_one_worker(self):
        with patch.object(os, "cpu_count", return_value=2):
            result = default_max_workers(batch_size=100, num_concurrent=4)
            assert result == 1  # max(1, (2-2)//4) = 1

    def test_zero_batch_size(self):
        result = default_max_workers(batch_size=0, num_concurrent=1)
        assert result == 0

    def test_cpu_count_none_fallback(self):
        with patch.object(os, "cpu_count", return_value=None):
            result = default_max_workers(batch_size=288, num_concurrent=1)
            assert result == 6  # (8 - 2) // 1 = 6 (fallback to 8)


import numpy as np

from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes
from fantasy_sim.validation.parallel import GameSpec, GameSimResult


def _make_dists(team: str) -> TeamDistributions:
    """Minimal TeamDistributions for tests."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 5, 8, 10, 12, 15]),
            "run": np.array([2, 3, 4, 5, 6]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


def _make_roster(team: str) -> TeamRoster:
    """Minimal TeamRoster for tests."""
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                   PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                   PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                 catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
    ])


class TestGameSpecDataclass:
    def test_creation(self):
        spec = GameSpec(
            game_id="2024_01_KC_BUF",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=_make_roster("KC"),
            away_roster=_make_roster("BUF"),
            seed=12345,
            week=1,
            metadata={"arm": "off"},
        )
        assert spec.game_id == "2024_01_KC_BUF"
        assert spec.seed == 12345
        assert spec.metadata["arm"] == "off"

    def test_metadata_defaults_to_empty(self):
        spec = GameSpec(
            game_id="test",
            home_dists=_make_dists("KC"),
            away_dists=_make_dists("BUF"),
            home_roster=None,
            away_roster=None,
            seed=0,
            week=1,
        )
        assert spec.metadata == {}


class TestGameSimResult:
    def test_creation(self):
        result = GameSimResult(
            game_id="2024_01_KC_BUF",
            projections=[{"player_id": "KC_QB", "fpts": 22.4}],
            metadata={"arm": "baseline"},
        )
        assert result.game_id == "2024_01_KC_BUF"
        assert len(result.projections) == 1
        assert result.projections[0]["fpts"] == 22.4
        assert result.metadata["arm"] == "baseline"

    def test_metadata_defaults_to_empty(self):
        result = GameSimResult(game_id="test", projections=[])
        assert result.metadata == {}

    def test_empty_projections(self):
        result = GameSimResult(game_id="test", projections=[])
        assert result.projections == []
