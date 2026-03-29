import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations, SimulationSummary
from fantasy_sim.engine.types import TeamDistributions, GameResult
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_team_dists() -> TeamDistributions:
    return TeamDistributions(
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


class TestRunSimulations:
    def test_returns_correct_number_of_results(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=42)
        assert len(results.games) == 10

    def test_all_results_are_game_results(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        for game in results.games:
            assert isinstance(game, GameResult)

    def test_summary_stats_computed(self):
        results = run_simulations(make_team_dists(), make_team_dists(), n_sims=20, seed=42)
        summary = results.summary()
        assert "home_score_mean" in summary
        assert "away_score_mean" in summary
        assert "home_win_pct" in summary
        assert "total_score_mean" in summary
        assert "overtime_pct" in summary

    def test_deterministic_with_same_seed(self):
        r1 = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        r2 = run_simulations(make_team_dists(), make_team_dists(), n_sims=5, seed=42)
        for g1, g2 in zip(r1.games, r2.games):
            assert g1.home_score == g2.home_score
            assert g1.away_score == g2.away_score

    def test_different_seeds_produce_variation(self):
        r1 = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=1)
        r2 = run_simulations(make_team_dists(), make_team_dists(), n_sims=10, seed=2)
        scores1 = [g.home_score for g in r1.games]
        scores2 = [g.home_score for g in r2.games]
        assert scores1 != scores2
