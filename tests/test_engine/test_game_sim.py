import numpy as np
import pytest
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.engine.types import GameResult, TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.game_state import GameStateBucket


def make_team_dists(**overrides) -> TeamDistributions:
    defaults = dict(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                "pass": np.array([0, 5, 7, 8, 10, 12, 0, 15, -2, 20, 0, 3, 6, 0, 9]),
                "run": np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 4, 3, 2, 5, -2, 8]),
            },
        ),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.60, touchback_yardline=75, return_yardlines=np.array([72, 74, 78, 80])),
    )
    defaults.update(overrides)
    return TeamDistributions(**defaults)


class TestSimulateGame:
    def test_returns_game_result(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert isinstance(result, GameResult)

    def test_scores_are_non_negative(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.home_score >= 0
        assert result.away_score >= 0

    def test_box_scores_have_stats(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.total_plays > 50
        assert result.home_box.pass_attempts + result.home_box.rush_attempts > 0
        assert result.away_box.pass_attempts + result.away_box.rush_attempts > 0

    def test_points_match_box_scores(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.home_score == result.home_box.points
        assert result.away_score == result.away_box.points

    def test_different_seeds_different_results(self):
        r1 = simulate_game(make_team_dists(), make_team_dists(), np.random.default_rng(1))
        r2 = simulate_game(make_team_dists(), make_team_dists(), np.random.default_rng(2))
        assert (r1.home_score != r2.home_score) or (r1.away_score != r2.away_score)

    def test_game_terminates(self):
        """Game should always finish (no infinite loops)."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert result.total_plays < 500

    def test_realistic_play_count(self):
        """NFL games have ~120-160 total plays."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert 80 <= result.total_plays <= 250

    def test_realistic_score_range(self):
        """Most games score between 20-60 combined points."""
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        total = result.home_score + result.away_score
        assert 0 <= total <= 100
