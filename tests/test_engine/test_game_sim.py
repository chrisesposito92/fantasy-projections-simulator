import numpy as np
import pytest
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.engine.types import GameResult, TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


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


def make_roster_for_sim(team: str = "T") -> TeamRoster:
    qb = PlayerModel(f"{team}_QB", "QB", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.05),
                     PlayerOutcomes(scramble_yards_dist=np.array([3, 5, 8, 12, -1])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.25),
                      PlayerOutcomes(catch_rate=0.62, receiving_yards_dist=np.array([5, 8, 10, 12, 15, 20, 25])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.20),
                      PlayerOutcomes(catch_rate=0.58, receiving_yards_dist=np.array([5, 7, 10, 14, 18])))
    te = PlayerModel(f"{team}_TE", "TE", "TE", team,
                     PlayerUsage(target_share=0.18),
                     PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([4, 6, 8, 12])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.10),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 12]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7]),
                          fumble_rate=0.01,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([1, 2, 3, 4, 5, 6]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 4]),
                          fumble_rate=0.008,
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, te, rb1, rb2])


class TestSimulateGameWithPlayers:
    def test_returns_player_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        assert len(result.player_stats) > 0

    def test_qb_has_passing_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        qb = result.player_stats.get("H_QB")
        assert qb is not None
        assert qb.pass_attempts > 0

    def test_wr_has_receiving_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        wr = result.player_stats.get("H_WR1")
        assert wr is not None
        assert wr.targets > 0

    def test_rb_has_rushing_stats(self):
        rng = np.random.default_rng(42)
        home_roster = make_roster_for_sim("H")
        away_roster = make_roster_for_sim("A")
        result = simulate_game(
            make_team_dists(), make_team_dists(), rng,
            home_roster=home_roster, away_roster=away_roster,
        )
        rb = result.player_stats.get("H_RB1")
        assert rb is not None
        assert rb.rush_attempts > 0

    def test_backward_compatible_without_rosters(self):
        rng = np.random.default_rng(42)
        result = simulate_game(make_team_dists(), make_team_dists(), rng)
        assert len(result.player_stats) == 0
        assert result.total_plays > 50
