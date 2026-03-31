import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_league_avg_dists() -> TeamDistributions:
    """Team distributions using league-average values."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team="AVG", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(
            distributions={},
            defaults={
                # Realistic NFL pass yards distribution (includes incompletions as 0)
                "pass": np.array([
                    0, 0, 0, 0, 0, 0,        # ~40% incompletion
                    3, 4, 5, 6, 7, 8, 9, 10,  # Short completions
                    12, 15, 18, 20, 25,        # Medium
                    30, 40, 50,                # Deep
                ]),
                # Realistic NFL rush yards distribution
                "run": np.array([
                    -3, -2, -1, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5,
                    6, 7, 8, 10, 12, 15, 20,
                ]),
            },
        ),
        turnover_rates=TurnoverRates(team="AVG", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80, 82])),
    )


@pytest.mark.statistical
class TestStatisticalValidation:
    """Run 2000 simulated games and verify NFL-realistic averages.

    These tests use wide tolerances since we're comparing against league averages
    with simplified distributions. The goal is plausibility, not precision.
    """

    @pytest.fixture(scope="class")
    def sim_results(self):
        dists = make_league_avg_dists()
        return run_simulations(dists, dists, n_sims=2000, seed=42)

    def test_average_total_points(self, sim_results):
        """NFL average is ~45-48 points per game."""
        s = sim_results.summary()
        assert 30 <= s["total_score_mean"] <= 65, f"Total score {s['total_score_mean']:.1f} out of range"

    def test_home_win_rate(self, sim_results):
        """With identical teams, should be ~50% (no home advantage modeled yet)."""
        s = sim_results.summary()
        assert 0.40 <= s["home_win_pct"] <= 0.60, f"Home win rate {s['home_win_pct']:.1%} out of range"

    def test_overtime_rate(self, sim_results):
        """NFL OT rate is ~5%. With identical teams, could be slightly higher."""
        s = sim_results.summary()
        assert 0.01 <= s["overtime_pct"] <= 0.15, f"OT rate {s['overtime_pct']:.1%} out of range"

    def test_average_plays_per_game(self, sim_results):
        """NFL average is ~120-140 total plays per game."""
        s = sim_results.summary()
        assert 80 <= s["plays_mean"] <= 200, f"Plays per game {s['plays_mean']:.0f} out of range"

    def test_scores_have_variance(self, sim_results):
        """Games shouldn't all produce the same score."""
        s = sim_results.summary()
        assert s["total_score_std"] > 5, f"Score std {s['total_score_std']:.1f} too low"

    def test_no_absurd_scores(self, sim_results):
        """No game should have a team scoring >80 points."""
        for game in sim_results.games:
            assert game.home_score <= 80, f"Absurd home score: {game.home_score}"
            assert game.away_score <= 80, f"Absurd away score: {game.away_score}"

    def test_box_scores_consistent(self, sim_results):
        """Points in box score should match game score."""
        for game in sim_results.games:
            assert game.home_score == game.home_box.points
            assert game.away_score == game.away_box.points

    def test_turnovers_reasonable(self, sim_results):
        """Average turnovers per game should be between 1 and 8."""
        total_games = len(sim_results.games)
        total_ints = sum(g.home_box.interceptions_thrown + g.away_box.interceptions_thrown for g in sim_results.games)
        total_fumbles = sum(g.home_box.fumbles_lost + g.away_box.fumbles_lost for g in sim_results.games)
        avg_turnovers = (total_ints + total_fumbles) / total_games
        assert 1.0 <= avg_turnovers <= 8.0, f"Avg turnovers {avg_turnovers:.1f} out of range"

    def test_completion_rate_reasonable(self, sim_results):
        """Team-level completion rate (yards > 0 from distribution).

        Without per-player rosters, completion is determined by the
        team pass distribution having ~27% zeros, yielding ~73% rate
        before sack/INT dilution.  Wide range to accommodate both
        team-level and player-level sims.
        """
        total_comp = sum(g.home_box.completions + g.away_box.completions for g in sim_results.games)
        total_att = sum(g.home_box.pass_attempts + g.away_box.pass_attempts for g in sim_results.games)
        total_sacks = sum(g.home_box.sacks_taken + g.away_box.sacks_taken for g in sim_results.games)
        nfl_att = total_att - total_sacks
        rate = total_comp / nfl_att if nfl_att > 0 else 0
        assert 0.50 <= rate <= 0.85, f"Completion rate {rate:.1%} out of range"

    def test_yards_per_completion_reasonable(self, sim_results):
        """Team-level yd/comp is higher (~14-17) than player-level (~10-12)
        because the distribution includes only non-zero values for completions.
        """
        total_yards = sum(g.home_box.pass_yards + g.away_box.pass_yards for g in sim_results.games)
        total_comp = sum(g.home_box.completions + g.away_box.completions for g in sim_results.games)
        ypc = total_yards / total_comp if total_comp > 0 else 0
        assert 8.0 <= ypc <= 20.0, f"Yards/completion {ypc:.1f} out of range"

    def test_pass_yards_per_team_reasonable(self, sim_results):
        """Team-level pass yards can be higher than player-level due to
        distribution shape (non-zero values average ~16 yards).
        """
        per_team = []
        for g in sim_results.games:
            per_team.append(g.home_box.pass_yards)
            per_team.append(g.away_box.pass_yards)
        mean = np.mean(per_team)
        assert 150 <= mean <= 450, f"Pass yards/team {mean:.0f} out of range"
