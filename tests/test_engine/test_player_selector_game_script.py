import numpy as np
import pytest

from fantasy_sim.data.game_script import RbRankFactors, TargetRankFactors
from fantasy_sim.engine.game_script import RuntimeGameScript
from fantasy_sim.engine.player_selector import (
    _apply_rb_rank_factors,
    select_receiver,
    select_rusher,
)
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def make_state(**overrides) -> GameState:
    defaults = dict(
        quarter=4,
        clock=420,
        possession="home",
        down=1,
        distance=10,
        yard_line=65,
        home_score=17,
        away_score=24,
        home_team="KC",
        away_team="BUF",
        receiving_2nd_half="away",
    )
    defaults.update(overrides)
    return GameState(**defaults)


def make_roster() -> TeamRoster:
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
        PlayerUsage(target_share=0.30, red_zone_target_share=0.18),
        PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 18])),
    )
    wr2 = PlayerModel(
        "WR2",
        "WR2",
        "WR",
        "KC",
        PlayerUsage(target_share=0.22, red_zone_target_share=0.30),
        PlayerOutcomes(catch_rate=0.61, receiving_yards_dist=np.array([7, 10, 15])),
    )
    te1 = PlayerModel(
        "TE1",
        "TE1",
        "TE",
        "KC",
        PlayerUsage(target_share=0.18, red_zone_target_share=0.24),
        PlayerOutcomes(catch_rate=0.70, receiving_yards_dist=np.array([5, 8, 12])),
    )
    rb1 = PlayerModel(
        "RB1",
        "RB1",
        "RB",
        "KC",
        PlayerUsage(target_share=0.10, red_zone_target_share=0.08),
        PlayerOutcomes(catch_rate=0.76, receiving_yards_dist=np.array([3, 5, 7])),
    )
    return TeamRoster(team="KC", players=[qb, wr1, wr2, te1, rb1])


def make_rush_roster() -> TeamRoster:
    qb = PlayerModel(
        "QB1",
        "QB1",
        "QB",
        "KC",
        PlayerUsage(snap_share=1.0, carry_share=0.12),
        PlayerOutcomes(),
    )
    rb1 = PlayerModel(
        "RB1",
        "RB1",
        "RB",
        "KC",
        PlayerUsage(carry_share=0.58),
        PlayerOutcomes(),
    )
    rb2 = PlayerModel(
        "RB2",
        "RB2",
        "RB",
        "KC",
        PlayerUsage(carry_share=0.22),
        PlayerOutcomes(),
    )
    rb3 = PlayerModel(
        "RB3",
        "RB3",
        "RB",
        "KC",
        PlayerUsage(carry_share=0.08),
        PlayerOutcomes(),
    )
    return TeamRoster(team="KC", players=[qb, rb1, rb2, rb3])


def count_receivers(
    roster: TeamRoster,
    state: GameState,
    script: RuntimeGameScript | None,
    *,
    seed: int = 7,
    n: int = 4000,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    counts = {"WR1": 0, "WR2": 0, "TE1": 0, "RB1": 0}
    for _ in range(n):
        receiver = select_receiver(roster, state, rng, script=script)
        counts[receiver.player_id] += 1
    return counts


def count_rushers(
    roster: TeamRoster,
    state: GameState,
    script: RuntimeGameScript | None,
    *,
    seed: int = 11,
    n: int = 5000,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    counts = {"QB1": 0, "RB1": 0, "RB2": 0, "RB3": 0}
    for _ in range(n):
        rusher = select_rusher(roster, state, rng, script=script)
        counts[rusher.player_id] += 1
    return counts


class TestSelectReceiverGameScript:
    def test_trailing_late_increases_wr1_frequency_relative_to_neutral(self):
        roster = make_roster()
        state = make_state(yard_line=65)
        neutral_counts = count_receivers(roster, state, script=None)
        trailing_counts = count_receivers(
            roster,
            state,
            script=RuntimeGameScript(
                regime="trailing_late",
                target_factors=TargetRankFactors(rank1=1.25, rank2=1.0, rank3_plus=0.85),
            ),
        )

        assert trailing_counts["WR1"] > neutral_counts["WR1"]

    def test_red_zone_selection_uses_red_zone_shares_and_concentration(self):
        roster = make_roster()
        state = make_state(yard_line=12)
        neutral_counts = count_receivers(roster, state, script=None)
        trailing_counts = count_receivers(
            roster,
            state,
            script=RuntimeGameScript(
                regime="trailing_late",
                target_factors=TargetRankFactors(rank1=1.25, rank2=1.1, rank3_plus=0.85),
            ),
        )

        assert neutral_counts["WR2"] > neutral_counts["WR1"]
        assert trailing_counts["WR2"] > neutral_counts["WR2"]

    def test_neutral_script_preserves_existing_behavior_with_same_seed(self):
        roster = make_roster()
        state = make_state(yard_line=65)
        baseline_rng = np.random.default_rng(42)
        neutral_rng = np.random.default_rng(42)

        baseline = [select_receiver(roster, state, baseline_rng).player_id for _ in range(250)]
        scripted = [
            select_receiver(roster, state, neutral_rng, script=RuntimeGameScript()).player_id
            for _ in range(250)
        ]

        assert scripted == baseline


class TestSelectRusherGameScript:
    def test_neutral_script_preserves_existing_behavior_with_same_seed(self):
        roster = make_rush_roster()
        state = make_state(yard_line=65, home_score=24, away_score=10, possession="home")
        baseline_rng = np.random.default_rng(42)
        neutral_rng = np.random.default_rng(42)

        baseline = [select_rusher(roster, state, baseline_rng).player_id for _ in range(250)]
        scripted = [
            select_rusher(roster, state, neutral_rng, script=RuntimeGameScript()).player_id
            for _ in range(250)
        ]

        assert scripted == baseline

    def test_leading_late_rb_increases_rb2_frequency_relative_to_neutral(self):
        roster = make_rush_roster()
        state = make_state(yard_line=65, home_score=24, away_score=10, possession="home")
        neutral_counts = count_rushers(roster, state, script=None)
        leading_counts = count_rushers(
            roster,
            state,
            script=RuntimeGameScript(
                regime="leading_late_rb",
                rb_factors=RbRankFactors(rb1=0.8, rb2=1.25, rb3_plus=1.1),
            ),
        )

        assert leading_counts["RB2"] > neutral_counts["RB2"]

    def test_leading_late_rb_preserves_qb_selection_frequency(self):
        roster = make_rush_roster()
        state = make_state(yard_line=65, home_score=24, away_score=10, possession="home")
        neutral_counts = count_rushers(roster, state, script=None)
        leading_counts = count_rushers(
            roster,
            state,
            script=RuntimeGameScript(
                regime="leading_late_rb",
                rb_factors=RbRankFactors(rb1=0.8, rb2=1.25, rb3_plus=1.1),
            ),
        )

        assert leading_counts["QB1"] == neutral_counts["QB1"]

    def test_scramble_ignores_script(self):
        roster = make_rush_roster()
        state = make_state(yard_line=65, home_score=24, away_score=10, possession="home")
        baseline_rng = np.random.default_rng(42)
        scripted_rng = np.random.default_rng(42)

        baseline = [
            select_rusher(roster, state, baseline_rng, is_scramble=True).player_id
            for _ in range(50)
        ]
        scripted = [
            select_rusher(
                roster,
                state,
                scripted_rng,
                is_scramble=True,
                script=RuntimeGameScript(
                    regime="leading_late_rb",
                    rb_factors=RbRankFactors(rb1=0.8, rb2=1.25, rb3_plus=1.1),
                ),
            ).player_id
            for _ in range(50)
        ]

        assert scripted == baseline
        assert all(player_id == "QB1" for player_id in scripted)

    def test_apply_rb_rank_factors_preserves_non_rb_carry_mass(self):
        roster = make_rush_roster()
        weights = np.array([0.12, 0.58, 0.22, 0.08], dtype=float)
        script = RuntimeGameScript(
            regime="leading_late_rb",
            rb_factors=RbRankFactors(rb1=0.8, rb2=1.25, rb3_plus=1.1),
        )

        adjusted = _apply_rb_rank_factors(roster.players, weights, script)

        assert adjusted[0] == pytest.approx(weights[0])
        assert adjusted[1:].sum() == pytest.approx(weights[1:].sum())
