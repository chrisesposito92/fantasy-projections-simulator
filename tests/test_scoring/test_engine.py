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
