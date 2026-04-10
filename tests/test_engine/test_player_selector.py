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


@pytest.fixture
def make_goal_line_roster() -> TeamRoster:
    qb = PlayerModel(
        "QB1",
        "QB1",
        "QB",
        "KC",
        PlayerUsage(snap_share=1.0),
        PlayerOutcomes(),
    )
    wr1 = PlayerModel(
        "WR1",
        "WR1",
        "WR",
        "KC",
        PlayerUsage(
            target_share=0.24,
            red_zone_target_share=0.12,
            outer_rz_target_share=0.08,
            goal_line_target_share=0.72,
        ),
        PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 20])),
    )
    te1 = PlayerModel(
        "TE1",
        "TE1",
        "TE",
        "KC",
        PlayerUsage(
            target_share=0.18,
            red_zone_target_share=0.58,
            outer_rz_target_share=0.66,
            goal_line_target_share=0.04,
        ),
        PlayerOutcomes(catch_rate=0.70, receiving_yards_dist=np.array([5, 10])),
    )
    rb1 = PlayerModel(
        "RB1",
        "RB1",
        "RB",
        "KC",
        PlayerUsage(
            carry_share=0.32,
            red_zone_carry_share=0.14,
            outer_rz_carry_share=0.08,
            goal_line_carry_share=0.78,
            target_share=0.10,
        ),
        PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7])),
    )
    rb2 = PlayerModel(
        "RB2",
        "RB2",
        "RB",
        "KC",
        PlayerUsage(
            carry_share=0.44,
            red_zone_carry_share=0.64,
            outer_rz_carry_share=0.70,
            goal_line_carry_share=0.06,
            target_share=0.06,
        ),
        PlayerOutcomes(rushing_yards_dist=np.array([2, 4, 6])),
    )
    return TeamRoster(team="KC", players=[qb, wr1, te1, rb1, rb2])


def count_receivers(
    roster: TeamRoster,
    state: GameState,
    *,
    seed: int = 7,
    n: int = 4000,
    goal_line_concentration_enabled: bool = False,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    counts = {"WR1": 0, "TE1": 0, "RB1": 0, "RB2": 0}
    for _ in range(n):
        receiver = select_receiver(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
        )
        counts[receiver.player_id] += 1
    return counts


def count_rushers(
    roster: TeamRoster,
    state: GameState,
    *,
    seed: int = 11,
    n: int = 5000,
    goal_line_concentration_enabled: bool = False,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    counts = {"RB1": 0, "RB2": 0}
    for _ in range(n):
        rusher = select_rusher(
            roster,
            state,
            rng,
            goal_line_concentration_enabled=goal_line_concentration_enabled,
        )
        if rusher.player_id in counts:
            counts[rusher.player_id] += 1
    return counts


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


class TestGoalLineConcentrationSelection:
    def test_goal_line_enabled_uses_goal_line_band_shares(self, make_goal_line_roster: TeamRoster):
        state = make_state(yard_line=3)

        receiver_counts = count_receivers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )
        rusher_counts = count_rushers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )

        assert receiver_counts["WR1"] > receiver_counts["TE1"]
        assert rusher_counts["RB1"] > rusher_counts["RB2"]

    def test_outer_red_zone_enabled_uses_outer_band_shares(self, make_goal_line_roster: TeamRoster):
        state = make_state(yard_line=12)

        receiver_counts = count_receivers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )
        rusher_counts = count_rushers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )

        assert receiver_counts["TE1"] > receiver_counts["WR1"]
        assert rusher_counts["RB2"] > rusher_counts["RB1"]

    def test_feature_disabled_keeps_existing_red_zone_shares(self, make_goal_line_roster: TeamRoster):
        state = make_state(yard_line=3)

        receiver_counts = count_receivers(make_goal_line_roster, state)
        rusher_counts = count_rushers(make_goal_line_roster, state)

        assert receiver_counts["TE1"] > receiver_counts["WR1"]
        assert rusher_counts["RB2"] > rusher_counts["RB1"]

    def test_missing_goal_line_mass_falls_back_to_red_zone_shares(
        self,
        make_goal_line_roster: TeamRoster,
    ):
        make_goal_line_roster.players[1].usage.goal_line_target_share = 0.0
        make_goal_line_roster.players[2].usage.goal_line_target_share = 0.0
        make_goal_line_roster.players[3].usage.goal_line_carry_share = 0.0
        make_goal_line_roster.players[4].usage.goal_line_carry_share = 0.0
        state = make_state(yard_line=2)

        receiver_counts = count_receivers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )
        rusher_counts = count_rushers(
            make_goal_line_roster,
            state,
            goal_line_concentration_enabled=True,
        )

        assert receiver_counts["TE1"] > receiver_counts["WR1"]
        assert rusher_counts["RB2"] > rusher_counts["RB1"]

    def test_outside_red_zone_receiver_selection_stays_on_base_target_share(
        self,
        make_goal_line_roster: TeamRoster,
    ):
        state = make_state(yard_line=35)
        baseline_rng = np.random.default_rng(42)
        enabled_rng = np.random.default_rng(42)

        baseline = [
            select_receiver(make_goal_line_roster, state, baseline_rng).player_id
            for _ in range(250)
        ]
        enabled = [
            select_receiver(
                make_goal_line_roster,
                state,
                enabled_rng,
                goal_line_concentration_enabled=True,
            ).player_id
            for _ in range(250)
        ]

        assert enabled == baseline

    def test_outside_red_zone_rusher_selection_stays_on_base_carry_share(
        self,
        make_goal_line_roster: TeamRoster,
    ):
        state = make_state(yard_line=42)
        baseline_rng = np.random.default_rng(42)
        enabled_rng = np.random.default_rng(42)

        baseline = [
            select_rusher(make_goal_line_roster, state, baseline_rng).player_id
            for _ in range(250)
        ]
        enabled = [
            select_rusher(
                make_goal_line_roster,
                state,
                enabled_rng,
                goal_line_concentration_enabled=True,
            ).player_id
            for _ in range(250)
        ]

        assert enabled == baseline
