# tests/test_models/test_player.py
import numpy as np
import pytest
from fantasy_sim.models.player import (
    PlayerUsage, PlayerOutcomes, PlayerModel, TeamRoster,
)


class TestPlayerModel:
    def test_create_wr(self):
        model = PlayerModel(
            player_id="TK87", name="Travis Kelce", position="TE", team="KC",
            usage=PlayerUsage(target_share=0.22, red_zone_target_share=0.25),
            outcomes=PlayerOutcomes(
                catch_rate=0.68,
                receiving_yards_dist=np.array([5, 8, 12, 15, 20, 25, 7, 3]),
                fumble_rate=0.005,
            ),
        )
        assert model.player_id == "TK87"
        assert model.position == "TE"
        assert model.usage.target_share == pytest.approx(0.22)
        assert model.outcomes.catch_rate == pytest.approx(0.68)

    def test_create_rb(self):
        model = PlayerModel(
            player_id="IP01", name="Isiah Pacheco", position="RB", team="KC",
            usage=PlayerUsage(carry_share=0.55, target_share=0.08, red_zone_carry_share=0.60),
            outcomes=PlayerOutcomes(
                rushing_yards_dist=np.array([3, 5, -1, 7, 2, 4, 12, 1]),
                receiving_yards_dist=np.array([4, 6, 8]),
                catch_rate=0.75,
                fumble_rate=0.01,
            ),
        )
        assert model.usage.carry_share == pytest.approx(0.55)
        assert len(model.outcomes.rushing_yards_dist) == 8

    def test_create_qb(self):
        model = PlayerModel(
            player_id="PM15", name="Patrick Mahomes", position="QB", team="KC",
            usage=PlayerUsage(snap_share=1.0, scramble_rate=0.08),
            outcomes=PlayerOutcomes(
                scramble_yards_dist=np.array([5, 8, 12, -2, 3, 15]),
                fumble_rate=0.008,
            ),
        )
        assert model.usage.scramble_rate == pytest.approx(0.08)

    def test_games_played_default(self):
        model = PlayerModel(
            player_id="X", name="X", position="WR", team="T",
            usage=PlayerUsage(), outcomes=PlayerOutcomes(),
        )
        assert model.games_played == 17


class TestTeamRoster:
    @pytest.fixture
    def kc_roster(self):
        qb = PlayerModel("PM15", "Mahomes", "QB", "KC",
                         PlayerUsage(snap_share=1.0, scramble_rate=0.08),
                         PlayerOutcomes(scramble_yards_dist=np.array([5, 8, 12])))
        wr1 = PlayerModel("RE11", "Worthy", "WR", "KC",
                          PlayerUsage(target_share=0.25),
                          PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12, 20])))
        wr2 = PlayerModel("TK87", "Kelce", "TE", "KC",
                          PlayerUsage(target_share=0.22),
                          PlayerOutcomes(catch_rate=0.68, receiving_yards_dist=np.array([5, 10, 15])))
        rb = PlayerModel("IP01", "Pacheco", "RB", "KC",
                         PlayerUsage(carry_share=0.60, target_share=0.10),
                         PlayerOutcomes(
                             rushing_yards_dist=np.array([3, 5, -1, 7]),
                             catch_rate=0.75, receiving_yards_dist=np.array([4, 6]),
                         ))
        rb2 = PlayerModel("CH02", "Clyde", "RB", "KC",
                          PlayerUsage(carry_share=0.30, target_share=0.05),
                          PlayerOutcomes(rushing_yards_dist=np.array([2, 4, 6])))
        return TeamRoster(team="KC", players=[qb, wr1, wr2, rb, rb2])

    def test_get_starting_qb(self, kc_roster):
        qb = kc_roster.get_starting_qb()
        assert qb.position == "QB"
        assert qb.player_id == "PM15"

    def test_select_receiver(self, kc_roster):
        rng = np.random.default_rng(42)
        receivers = [kc_roster.select_receiver(rng) for _ in range(100)]
        ids = [r.player_id for r in receivers]
        assert all(pid in ("RE11", "TK87", "IP01", "CH02") for pid in ids)
        assert ids.count("RE11") > 15
        assert ids.count("TK87") > 10

    def test_select_rusher(self, kc_roster):
        rng = np.random.default_rng(42)
        rushers = [kc_roster.select_rusher(rng) for _ in range(100)]
        ids = [r.player_id for r in rushers]
        assert all(pid in ("IP01", "CH02") for pid in ids)
        assert 40 <= ids.count("IP01") <= 80

    def test_target_shares_normalize(self, kc_roster):
        rng = np.random.default_rng(42)
        receiver = kc_roster.select_receiver(rng)
        assert receiver is not None

    def test_receiver_includes_rbs(self, kc_roster):
        rng = np.random.default_rng(42)
        receivers = [kc_roster.select_receiver(rng) for _ in range(200)]
        ids = set(r.player_id for r in receivers)
        assert "IP01" in ids

    def test_select_receiver_red_zone(self, kc_roster):
        rng = np.random.default_rng(42)
        receiver = kc_roster.select_receiver(rng, is_red_zone=True)
        assert receiver is not None

    # --- Finding 1: division-by-zero on fallback paths ---

    def test_select_receiver_fallback_uniform_when_no_target_shares(self):
        """When no player has target_share > 0, fallback to uniform weights."""
        rb = PlayerModel("RB1", "Back", "RB", "T",
                         PlayerUsage(carry_share=0.60),
                         PlayerOutcomes(rushing_yards_dist=np.array([3, 5])))
        wr = PlayerModel("WR1", "Wide", "WR", "T",
                         PlayerUsage(),
                         PlayerOutcomes(receiving_yards_dist=np.array([8, 12])))
        roster = TeamRoster(team="T", players=[rb, wr])
        rng = np.random.default_rng(42)
        # Should not raise; both non-QBs get equal probability
        receivers = [roster.select_receiver(rng) for _ in range(100)]
        ids = set(r.player_id for r in receivers)
        assert ids == {"RB1", "WR1"}

    def test_select_rusher_fallback_uniform_when_no_carry_shares(self):
        """When no player has carry_share > 0, fallback to uniform weights."""
        rb1 = PlayerModel("RB1", "Back1", "RB", "T",
                          PlayerUsage(), PlayerOutcomes())
        rb2 = PlayerModel("RB2", "Back2", "RB", "T",
                          PlayerUsage(), PlayerOutcomes())
        roster = TeamRoster(team="T", players=[rb1, rb2])
        rng = np.random.default_rng(42)
        # Should not raise; both RBs get equal probability
        rushers = [roster.select_rusher(rng) for _ in range(100)]
        ids = set(r.player_id for r in rushers)
        assert ids == {"RB1", "RB2"}

    # --- Finding 2: error handling for empty roster / missing positions ---

    def test_get_starting_qb_raises_on_no_qb(self):
        """get_starting_qb raises ValueError with a clear message when no QB exists."""
        wr = PlayerModel("WR1", "Wide", "WR", "T",
                         PlayerUsage(target_share=0.50), PlayerOutcomes())
        roster = TeamRoster(team="T", players=[wr])
        with pytest.raises(ValueError, match="No QB found on roster for T"):
            roster.get_starting_qb()

    def test_get_starting_qb_falls_back_to_zero_share_qb_when_needed(self):
        qb = PlayerModel(
            "QB1",
            "Quarterback",
            "QB",
            "T",
            PlayerUsage(snap_share=0.0),
            PlayerOutcomes(),
        )
        roster = TeamRoster(team="T", players=[qb])
        assert roster.get_starting_qb() is qb

    def test_select_receiver_raises_on_empty_roster(self):
        """select_receiver raises ValueError on an empty roster."""
        roster = TeamRoster(team="T", players=[])
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible receivers on roster for T"):
            roster.select_receiver(rng)

    def test_select_rusher_raises_on_empty_roster(self):
        """select_rusher raises ValueError on an empty roster."""
        roster = TeamRoster(team="T", players=[])
        rng = np.random.default_rng(42)
        with pytest.raises(ValueError, match="No eligible rushers on roster for T"):
            roster.select_rusher(rng)
