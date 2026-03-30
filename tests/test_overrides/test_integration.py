import numpy as np
import pytest
from fantasy_sim.overrides.engine import apply_player_override, apply_team_override
from fantasy_sim.overrides.parser import OverrideSet
from fantasy_sim.data.game_context import apply_overrides
from fantasy_sim.models.player import (
    PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster,
)
from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


def make_roster(team="KC"):
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team,
                    PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR1", "WR1", "WR", team,
                    PlayerUsage(target_share=0.25),
                    PlayerOutcomes(catch_rate=0.63, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_WR2", "WR2", "WR", team,
                    PlayerUsage(target_share=0.20),
                    PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([7, 10]))),
        PlayerModel(f"{team}_RB1", "RB1", "RB", team,
                    PlayerUsage(carry_share=0.60, target_share=0.10),
                    PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]))),
        PlayerModel(f"{team}_RB2", "RB2", "RB", team,
                    PlayerUsage(carry_share=0.30, target_share=0.05),
                    PlayerOutcomes(rushing_yards_dist=np.array([2, 4]))),
    ])


def make_dists(team="KC"):
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.57, "run": 0.43}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([5, 10]), "run": np.array([3, 5])}),
        turnover_rates=TurnoverRates(team=team, int_rate=0.025, fumble_rate=0.012, sack_rate=0.065, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


class TestOverrideIntegration:
    def test_target_share_override_redistributes(self):
        """Spec test: player target share override redistributes to teammates."""
        roster = make_roster()
        original_total = sum(p.usage.target_share for p in roster.players)
        apply_player_override(roster, "KC_WR1", {"target_share": 0.30})
        new_total = sum(p.usage.target_share for p in roster.players)
        assert new_total == pytest.approx(original_total, abs=0.01)

    def test_games_missed_reduces_games_played(self):
        """Spec test: games_missed override reduces games_played."""
        roster = make_roster()
        apply_player_override(roster, "KC_QB", {"games_missed": [4, 5, 6]})
        qb = next(p for p in roster.players if p.player_id == "KC_QB")
        assert qb.games_played == 14

    def test_team_pass_rate_shifts_balance(self):
        """Spec test: team pass rate override shifts run/pass balance."""
        dists = make_dists()
        apply_team_override(dists, {"pass_rate": 0.65})
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)
        assert dists.play_calling.default["run"] == pytest.approx(0.35)

    def test_stacking_player_and_team_no_conflict(self):
        """Spec test: stacking player + team overrides doesn't conflict."""
        roster = make_roster()
        dists = make_dists()
        apply_player_override(roster, "KC_WR1", {"target_share": 0.30})
        apply_team_override(dists, {"pass_rate": 0.65})
        wr1 = next(p for p in roster.players if p.player_id == "KC_WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists.play_calling.default["pass"] == pytest.approx(0.65)

    def test_config_file_matches_cli_override(self):
        """Spec test: override via CLI flag matches override via config file."""
        roster1 = make_roster("T1")
        roster2 = make_roster("T2")
        dists1 = make_dists("T1")
        dists2 = make_dists("T2")

        # Apply via OverrideSet (config file path)
        overrides = OverrideSet(
            players={"T1_WR1": {"target_share": 0.30}},
            teams={"T1": {"pass_rate": 0.62}},
        )
        apply_overrides(overrides, dists1, dists2, roster1, roster2)

        wr1 = next(p for p in roster1.players if p.player_id == "T1_WR1")
        assert wr1.usage.target_share == pytest.approx(0.30)
        assert dists1.play_calling.default["pass"] == pytest.approx(0.62)

    def test_apply_overrides_resolves_to_correct_roster(self):
        """Overrides applied to the right team's roster/dists."""
        home_roster = make_roster("KC")
        away_roster = make_roster("BUF")
        home_dists = make_dists("KC")
        away_dists = make_dists("BUF")

        overrides = OverrideSet(
            players={"KC_WR1": {"target_share": 0.30}},
            teams={"BUF": {"pass_rate": 0.62}},
        )
        apply_overrides(overrides, home_dists, away_dists, home_roster, away_roster)

        kc_wr1 = next(p for p in home_roster.players if p.player_id == "KC_WR1")
        assert kc_wr1.usage.target_share == pytest.approx(0.30)
        assert away_dists.play_calling.default["pass"] == pytest.approx(0.62)
        # KC pass rate should be unchanged
        assert home_dists.play_calling.default["pass"] == pytest.approx(0.57)
