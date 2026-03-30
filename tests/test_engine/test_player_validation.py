import numpy as np
import pytest
from fantasy_sim.engine.monte_carlo import run_simulations
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_realistic_roster(team: str) -> TeamRoster:
    """Build a roster with realistic usage splits."""
    qb = PlayerModel(f"{team}_QB", "QB1", "QB", team,
                     PlayerUsage(snap_share=1.0, scramble_rate=0.06),
                     PlayerOutcomes(scramble_yards_dist=np.array([2, 4, 6, 8, 12, -2, 3, 5])))
    wr1 = PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                      PlayerUsage(target_share=0.24, red_zone_target_share=0.22),
                      PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([5, 7, 8, 10, 12, 14, 16, 20, 25, 35])))
    wr2 = PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                      PlayerUsage(target_share=0.18, red_zone_target_share=0.15),
                      PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([5, 7, 9, 11, 13, 17, 22])))
    wr3 = PlayerModel(f"{team}_WR3", "WR3", "WR", team,
                      PlayerUsage(target_share=0.10),
                      PlayerOutcomes(catch_rate=0.58, receiving_yards_dist=np.array([4, 6, 8, 10, 14])))
    te = PlayerModel(f"{team}_TE", "TE1", "TE", team,
                     PlayerUsage(target_share=0.16, red_zone_target_share=0.20),
                     PlayerOutcomes(catch_rate=0.67, receiving_yards_dist=np.array([4, 6, 8, 10, 12, 15])))
    rb1 = PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                      PlayerUsage(carry_share=0.60, target_share=0.08, red_zone_carry_share=0.65),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 10, 15, 20]),
                          catch_rate=0.72, receiving_yards_dist=np.array([3, 5, 7, 4]),
                          fumble_rate=0.008,
                      ))
    rb2 = PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                      PlayerUsage(carry_share=0.30, target_share=0.05),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([0, 1, 2, 3, 4, 5, 6, 7]),
                          catch_rate=0.65, receiving_yards_dist=np.array([3, 5]),
                          fumble_rate=0.010,
                      ))
    return TeamRoster(team=team, players=[qb, wr1, wr2, wr3, te, rb1, rb2])


def make_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="T", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 0, 0, 0, 5, 7, 8, 10, 12, 15, 20, 25, 30]),
            "run": np.array([-2, 0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 8, 12]),
        }),
        turnover_rates=TurnoverRates(team="T", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 74, 76, 78, 80])),
    )


@pytest.mark.statistical
class TestPlayerStatisticalValidation:
    """Run 500 sims and verify player-level stats are plausible."""

    @pytest.fixture(scope="class")
    def sim_results(self):
        dists = make_dists()
        home_roster = make_realistic_roster("H")
        away_roster = make_realistic_roster("A")
        return run_simulations(dists, dists, n_sims=500, seed=42,
                              home_roster=home_roster, away_roster=away_roster)

    def test_qb_pass_yards_plausible(self, sim_results):
        ps = sim_results.player_summary()
        qb = ps.get("H_QB", {})
        if "pass_yards" in qb:
            mean = qb["pass_yards"]["mean"]
            assert 150 <= mean <= 400, f"QB pass yards {mean:.0f} out of range"

    def test_wr1_targets_plausible(self, sim_results):
        ps = sim_results.player_summary()
        wr = ps.get("H_WR1", {})
        if "targets" in wr:
            mean = wr["targets"]["mean"]
            assert 3 <= mean <= 15, f"WR1 targets {mean:.1f} out of range"

    def test_rb1_rush_yards_plausible(self, sim_results):
        ps = sim_results.player_summary()
        rb = ps.get("H_RB1", {})
        if "rush_yards" in rb:
            mean = rb["rush_yards"]["mean"]
            assert 30 <= mean <= 120, f"RB1 rush yards {mean:.0f} out of range"

    def test_no_negative_averages(self, sim_results):
        ps = sim_results.player_summary()
        for pid, stats in ps.items():
            for stat, values in stats.items():
                if stat in ("rush_yards",):
                    continue  # Rush yards can be negative on individual games
                assert values["mean"] >= 0, f"{pid} {stat} mean is negative"

    def test_target_shares_consistent(self, sim_results):
        """WR1 should have more targets than WR3."""
        ps = sim_results.player_summary()
        wr1_targets = ps.get("H_WR1", {}).get("targets", {}).get("mean", 0)
        wr3_targets = ps.get("H_WR3", {}).get("targets", {}).get("mean", 0)
        if wr1_targets > 0 and wr3_targets > 0:
            assert wr1_targets > wr3_targets
