import numpy as np
import pytest
from fantasy_sim.overrides.engine import (
    apply_player_override,
    apply_team_override,
    redistribute_target_shares,
    redistribute_carry_shares,
)
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_roster() -> TeamRoster:
    return TeamRoster(team="KC", players=[
        PlayerModel("QB1", "Mahomes", "QB", "KC",
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel("WR1", "Worthy", "WR", "KC",
                    PlayerUsage(target_share=0.24, red_zone_target_share=0.22),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel("WR2", "Rice", "WR", "KC",
                    PlayerUsage(target_share=0.18),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([7, 10]))),
        PlayerModel("TE1", "Kelce", "TE", "KC",
                    PlayerUsage(target_share=0.22),
                    PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([5, 10]))),
        PlayerModel("RB1", "Pacheco", "RB", "KC",
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                  catch_rate=0.72, receiving_yards_dist=np.array([4, 6]))),
        PlayerModel("RB2", "Clyde", "RB", "KC",
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 4]))),
    ])


def make_dists() -> TeamDistributions:
    return TeamDistributions(
        play_calling=PlayCallingDist(team="KC", distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([5, 10]), "run": np.array([3, 5])}),
        turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


class TestApplyPlayerOverride:
    def test_override_target_share(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"target_share": 0.30})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)

    def test_override_carry_share(self):
        roster = make_roster()
        apply_player_override(roster, "RB1", {"carry_share": 0.75})
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        assert rb1.usage.carry_share == pytest.approx(0.75)

    def test_override_games_played(self):
        roster = make_roster()
        apply_player_override(roster, "WR1", {"games_played": 14})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.games_played == 14

    def test_override_games_missed(self):
        roster = make_roster()
        apply_player_override(roster, "QB1", {"games_missed": [4, 5, 6]})
        qb = next(p for p in roster.players if p.player_id == "QB1")
        assert qb.games_played == 14  # 17 - 3

    def test_unknown_player_raises(self):
        roster = make_roster()
        with pytest.raises(KeyError):
            apply_player_override(roster, "FAKE_ID", {"target_share": 0.30})

    def test_unknown_field_raises(self):
        roster = make_roster()
        with pytest.raises(ValueError):
            apply_player_override(roster, "WR1", {"nonexistent_field": 0.5})


class TestRedistributeTargetShares:
    def test_increase_redistributes_to_teammates(self):
        roster = make_roster()
        # WR1 goes from 0.24 to 0.30 (+0.06)
        # Others: WR2=0.18, TE1=0.22, RB1=0.10, RB2=0.05 (sum=0.55)
        redistribute_target_shares(roster, "WR1", old_share=0.24, new_share=0.30)
        wr2 = next(p for p in roster.players if p.player_id == "WR2")
        te1 = next(p for p in roster.players if p.player_id == "TE1")
        rb1 = next(p for p in roster.players if p.player_id == "RB1")
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        # All others should decrease
        assert wr2.usage.target_share < 0.18
        assert te1.usage.target_share < 0.22
        # Total target shares should still sum to ~0.79 (original sum)
        total = 0.30 + wr2.usage.target_share + te1.usage.target_share + rb1.usage.target_share + rb2.usage.target_share
        assert total == pytest.approx(0.79, abs=0.01)

    def test_decrease_redistributes_to_teammates(self):
        roster = make_roster()
        redistribute_target_shares(roster, "WR1", old_share=0.24, new_share=0.18)
        wr2 = next(p for p in roster.players if p.player_id == "WR2")
        # WR2 should increase (got some of the freed share)
        assert wr2.usage.target_share > 0.18


class TestRedistributeCarryShares:
    def test_increase_redistributes(self):
        roster = make_roster()
        redistribute_carry_shares(roster, "RB1", old_share=0.60, new_share=0.75)
        rb2 = next(p for p in roster.players if p.player_id == "RB2")
        assert rb2.usage.carry_share < 0.30
        # Total should still be ~0.90
        total = 0.75 + rb2.usage.carry_share
        assert total == pytest.approx(0.90, abs=0.01)


class TestApplyTeamOverride:
    def test_override_pass_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"pass_rate": 0.65})
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
        assert dists.play_calling.default["run"] == pytest.approx(0.35)

    def test_override_sack_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"sack_rate": 0.08})
        assert dists.turnover_rates.sack_rate == pytest.approx(0.08)

    def test_override_int_rate(self):
        dists = make_dists()
        apply_team_override(dists, {"int_rate": 0.03})
        assert dists.turnover_rates.int_rate == pytest.approx(0.03)

    def test_stacking_player_and_team_overrides(self):
        """Player + team overrides on same team should not conflict."""
        roster = make_roster()
        dists = make_dists()
        apply_player_override(roster, "WR1", {"target_share": 0.30})
        apply_team_override(dists, {"pass_rate": 0.65})
        wr1 = next(p for p in roster.players if p.player_id == "WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
