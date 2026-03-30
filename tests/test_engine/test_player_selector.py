import numpy as np
import pytest
from fantasy_sim.engine.player_selector import select_passer, select_receiver, select_rusher
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerUsage, PlayerOutcomes, TeamRoster


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=1, clock=900, possession="home",
        down=1, distance=10, yard_line=75,
        home_score=0, away_score=0,
        home_team="KC", away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_roster() -> TeamRoster:
    qb = PlayerModel("QB1", "QB", "QB", "KC",
                     PlayerUsage(snap_share=1.0, scramble_rate=0.08),
                     PlayerOutcomes(scramble_yards_dist=np.array([5, 8])))
    wr1 = PlayerModel("WR1", "WR1", "WR", "KC",
                      PlayerUsage(target_share=0.28),
                      PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 20])))
    te1 = PlayerModel("TE1", "TE1", "TE", "KC",
                      PlayerUsage(target_share=0.20),
                      PlayerOutcomes(catch_rate=0.70, receiving_yards_dist=np.array([5, 10])))
    rb1 = PlayerModel("RB1", "RB1", "RB", "KC",
                      PlayerUsage(carry_share=0.65, target_share=0.12),
                      PlayerOutcomes(
                          rushing_yards_dist=np.array([3, 5, 7]),
                          catch_rate=0.75, receiving_yards_dist=np.array([4, 6]),
                      ))
    return TeamRoster(team="KC", players=[qb, wr1, te1, rb1])


class TestSelectPasser:
    def test_returns_qb(self):
        roster = make_roster()
        qb = select_passer(roster)
        assert qb.position == "QB"


class TestSelectReceiver:
    def test_returns_player_with_target_share(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        receiver = select_receiver(roster, state, rng)
        assert receiver.usage.target_share > 0

    def test_wr1_most_frequent(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        ids = [select_receiver(roster, state, rng).player_id for _ in range(200)]
        assert ids.count("WR1") > ids.count("TE1")
        assert ids.count("WR1") > ids.count("RB1")


class TestSelectRusher:
    def test_returns_player_with_carry_share(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        rusher = select_rusher(roster, state, rng)
        assert rusher.usage.carry_share > 0

    def test_handles_qb_scramble(self):
        rng = np.random.default_rng(42)
        roster = make_roster()
        state = make_state()
        rusher = select_rusher(roster, state, rng, is_scramble=True)
        assert rusher.position == "QB"
