import pytest
from fantasy_sim.scoring.engine import score_player, score_dst, score_kicker
from fantasy_sim.engine.types import PlayerBoxScore, TeamBoxScore


@pytest.fixture
def ppr_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 1, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2, "two_point": 2,
    }


@pytest.fixture
def standard_config():
    return {
        "passing_yard": 0.04, "passing_td": 4, "interception": -2,
        "rushing_yard": 0.1, "rushing_td": 6,
        "reception": 0, "receiving_yard": 0.1, "receiving_td": 6,
        "fumble_lost": -2,
    }


@pytest.fixture
def dst_config():
    return {
        "dst_sack": 1, "dst_interception": 2, "dst_fumble_recovery": 2,
        "dst_td": 6, "dst_safety": 2,
        "dst_points_allowed_0": 10, "dst_points_allowed_1_6": 7,
        "dst_points_allowed_7_13": 4, "dst_points_allowed_14_20": 1,
        "dst_points_allowed_21_27": 0, "dst_points_allowed_28_34": -1,
        "dst_points_allowed_35_plus": -4,
    }


@pytest.fixture
def kicker_config():
    return {
        "fg_0_39": 3, "fg_40_49": 4, "fg_50_plus": 5,
        "xp_made": 1, "fg_miss": -1,
    }


class TestScorePlayerPPR:
    def test_wr_5rec_100yds_1td(self, ppr_config):
        """Spec test: 5 receptions + 100 receiving yards + 1 TD = 21 PPR points."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, ppr_config)
        assert points == pytest.approx(5*1 + 100*0.1 + 1*6)  # 5 + 10 + 6 = 21
        assert points == pytest.approx(21.0)

    def test_qb_stats(self, ppr_config):
        box = PlayerBoxScore("QB1", "QB", "QB", "KC",
                            pass_yards=300, pass_tds=3, interceptions=1,
                            rush_yards=25, rush_tds=0)
        points = score_player(box, ppr_config)
        expected = 300*0.04 + 3*4 + 1*(-2) + 25*0.1  # 12 + 12 - 2 + 2.5 = 24.5
        assert points == pytest.approx(expected)

    def test_rb_with_receptions(self, ppr_config):
        box = PlayerBoxScore("RB1", "RB", "RB", "KC",
                            rush_yards=80, rush_tds=1,
                            receptions=4, targets=5, receiving_yards=30, receiving_tds=0)
        points = score_player(box, ppr_config)
        expected = 80*0.1 + 1*6 + 4*1 + 30*0.1  # 8 + 6 + 4 + 3 = 21
        assert points == pytest.approx(expected)

    def test_fumble_penalty(self, ppr_config):
        box = PlayerBoxScore("RB1", "RB", "RB", "KC",
                            rush_yards=50, fumbles_lost=1)
        points = score_player(box, ppr_config)
        expected = 50*0.1 + 1*(-2)  # 5 - 2 = 3
        assert points == pytest.approx(expected)


class TestScorePlayerStandard:
    def test_wr_5rec_100yds_1td_standard(self, standard_config):
        """Spec test: same stat line in standard = 16 points."""
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, standard_config)
        assert points == pytest.approx(5*0 + 100*0.1 + 1*6)  # 0 + 10 + 6 = 16
        assert points == pytest.approx(16.0)


class TestScoreDST:
    def test_shutout(self, dst_config):
        box = TeamBoxScore(sacks_made=4, interceptions_caught=2, fumbles_recovered=1, safeties=0)
        points = score_dst(box, opponent_score=0, config=dst_config)
        expected = 4*1 + 2*2 + 1*2 + 10  # 4 + 4 + 2 + 10 = 20
        assert points == pytest.approx(expected)

    def test_moderate_points_allowed(self, dst_config):
        box = TeamBoxScore(sacks_made=2, interceptions_caught=1, fumbles_recovered=0, safeties=0)
        points = score_dst(box, opponent_score=17, config=dst_config)
        expected = 2*1 + 1*2 + 1  # 2 + 2 + 1 (14-20 bracket) = 5
        assert points == pytest.approx(expected)

    def test_high_points_allowed_negative(self, dst_config):
        box = TeamBoxScore(sacks_made=1, interceptions_caught=0, fumbles_recovered=0, safeties=0)
        points = score_dst(box, opponent_score=38, config=dst_config)
        expected = 1*1 + (-4)  # 1 - 4 = -3
        assert points == pytest.approx(expected)

    def test_safety_scored(self, dst_config):
        box = TeamBoxScore(sacks_made=0, interceptions_caught=0, fumbles_recovered=0, safeties=1)
        points = score_dst(box, opponent_score=10, config=dst_config)
        expected = 1*2 + 4  # 2 + 4 (7-13 bracket) = 6
        assert points == pytest.approx(expected)


class TestScoreKicker:
    def test_kicker_fg_and_xp(self, kicker_config):

        box = TeamBoxScore(
            fg_made=2, fg_made_0_39=1, fg_made_40_49=1, fg_made_50_plus=0,
            fg_missed=0, xp_made=3, xp_attempts=3,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*3 + 1*4 + 3*1  # 3 + 4 + 3 = 10
        assert points == pytest.approx(expected)

    def test_kicker_with_miss(self, kicker_config):

        box = TeamBoxScore(
            fg_made=1, fg_made_0_39=1, fg_made_40_49=0, fg_made_50_plus=0,
            fg_missed=1, xp_made=2, xp_attempts=2,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*3 + 1*(-1) + 2*1  # 3 - 1 + 2 = 4
        assert points == pytest.approx(expected)

    def test_kicker_long_fg(self, kicker_config):

        box = TeamBoxScore(
            fg_made=1, fg_made_0_39=0, fg_made_40_49=0, fg_made_50_plus=1,
            fg_missed=0, xp_made=1, xp_attempts=1,
        )
        points = score_kicker(box, kicker_config)
        expected = 1*5 + 1*1  # 5 + 1 = 6
        assert points == pytest.approx(expected)


class TestScorePlayerTwoPoint:
    def test_two_point_conversions_score(self, ppr_config):
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receiving_yards=50, receiving_tds=1,
                            two_point_conversions=1)
        points = score_player(box, ppr_config)
        expected = 50 * 0.1 + 1 * 6 + 1 * 2  # 5 + 6 + 2 = 13
        assert points == pytest.approx(expected)

    def test_zero_two_point_no_effect(self, ppr_config):
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receiving_yards=50, receiving_tds=1,
                            two_point_conversions=0)
        points = score_player(box, ppr_config)
        expected = 50 * 0.1 + 1 * 6  # 5 + 6 = 11
        assert points == pytest.approx(expected)


class TestPositionSpecificReception:
    def test_wr_uses_position_specific_key(self):
        config = {
            "receiving_yard": 0.1, "receiving_td": 6,
            "reception": 1.0, "reception_wr": 1.5,
        }
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, config)
        expected = 5 * 1.5 + 100 * 0.1 + 1 * 6  # 7.5 + 10 + 6 = 23.5
        assert points == pytest.approx(expected)

    def test_te_uses_position_specific_key(self):
        config = {
            "receiving_yard": 0.1, "receiving_td": 6,
            "reception": 1.0, "reception_te": 1.5,
        }
        box = PlayerBoxScore("TE1", "TE1", "TE", "KC",
                            receptions=4, receiving_yards=60, receiving_tds=1)
        points = score_player(box, config)
        expected = 4 * 1.5 + 60 * 0.1 + 1 * 6  # 6 + 6 + 6 = 18
        assert points == pytest.approx(expected)

    def test_rb_falls_back_to_generic_reception(self):
        config = {
            "receiving_yard": 0.1, "receiving_td": 6,
            "reception": 1.0, "reception_wr": 1.5,
        }
        box = PlayerBoxScore("RB1", "RB1", "RB", "KC",
                            receptions=3, receiving_yards=30, receiving_tds=0)
        points = score_player(box, config)
        expected = 3 * 1.0 + 30 * 0.1  # 3 + 3 = 6
        assert points == pytest.approx(expected)

    def test_no_position_key_uses_generic(self):
        config = {
            "receiving_yard": 0.1, "receiving_td": 6,
            "reception": 1.0,
        }
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC",
                            receptions=5, receiving_yards=100, receiving_tds=1)
        points = score_player(box, config)
        expected = 5 * 1.0 + 100 * 0.1 + 1 * 6  # 5 + 10 + 6 = 21
        assert points == pytest.approx(expected)

    def test_qb_uses_position_specific_reception(self):
        config = {
            "passing_yard": 0.04, "passing_td": 4,
            "reception": 1.0, "reception_qb": 0,
        }
        box = PlayerBoxScore("QB1", "QB1", "QB", "KC",
                            pass_yards=300, pass_tds=2, receptions=1)
        points = score_player(box, config)
        expected = 300 * 0.04 + 2 * 4 + 1 * 0  # 12 + 8 + 0 = 20
        assert points == pytest.approx(expected)


class TestYardageBonuses:
    def test_rushing_bonus_100(self):
        config = {"rushing_yard": 0.1, "rushing_bonus_100": 3}
        box = PlayerBoxScore("RB1", "RB1", "RB", "KC", rush_yards=120)
        points = score_player(box, config)
        expected = 120 * 0.1 + 3  # 12 + 3 = 15
        assert points == pytest.approx(expected)

    def test_rushing_no_bonus_under_100(self):
        config = {"rushing_yard": 0.1, "rushing_bonus_100": 3}
        box = PlayerBoxScore("RB1", "RB1", "RB", "KC", rush_yards=99)
        points = score_player(box, config)
        expected = 99 * 0.1  # 9.9, no bonus
        assert points == pytest.approx(expected)

    def test_receiving_bonus_100(self):
        config = {"receiving_yard": 0.1, "receiving_bonus_100": 3}
        box = PlayerBoxScore("WR1", "WR1", "WR", "KC", receiving_yards=105)
        points = score_player(box, config)
        expected = 105 * 0.1 + 3  # 10.5 + 3 = 13.5
        assert points == pytest.approx(expected)

    def test_passing_bonus_300(self):
        config = {"passing_yard": 0.04, "passing_bonus_300": 3}
        box = PlayerBoxScore("QB1", "QB1", "QB", "KC", pass_yards=320)
        points = score_player(box, config)
        expected = 320 * 0.04 + 3  # 12.8 + 3 = 15.8
        assert points == pytest.approx(expected)

    def test_passing_no_bonus_under_300(self):
        config = {"passing_yard": 0.04, "passing_bonus_300": 3}
        box = PlayerBoxScore("QB1", "QB1", "QB", "KC", pass_yards=299)
        points = score_player(box, config)
        expected = 299 * 0.04  # 11.96, no bonus
        assert points == pytest.approx(expected)

    def test_rushing_bonus_200_stacks(self):
        config = {"rushing_yard": 0.1, "rushing_bonus_100": 3, "rushing_bonus_200": 5}
        box = PlayerBoxScore("RB1", "RB1", "RB", "KC", rush_yards=210)
        points = score_player(box, config)
        expected = 210 * 0.1 + 3 + 5  # 21 + 3 + 5 = 29
        assert points == pytest.approx(expected)

    def test_passing_bonus_400_stacks(self):
        config = {"passing_yard": 0.04, "passing_bonus_300": 3, "passing_bonus_400": 5}
        box = PlayerBoxScore("QB1", "QB1", "QB", "KC", pass_yards=420)
        points = score_player(box, config)
        expected = 420 * 0.04 + 3 + 5  # 16.8 + 3 + 5 = 24.8
        assert points == pytest.approx(expected)

    def test_no_bonus_keys_no_effect(self):
        config = {"rushing_yard": 0.1, "passing_yard": 0.04, "receiving_yard": 0.1}
        box = PlayerBoxScore("RB1", "RB1", "RB", "KC",
                            rush_yards=150, pass_yards=350, receiving_yards=120)
        points = score_player(box, config)
        expected = 150 * 0.1 + 350 * 0.04 + 120 * 0.1  # 15 + 14 + 12 = 41
        assert points == pytest.approx(expected)
