import numpy as np
import pytest
from fantasy_sim.engine.game_flow import (
    apply_yards, change_possession, score_points,
    handle_turnover, perform_kickoff, perform_punt,
    attempt_field_goal, attempt_pat,
)
from fantasy_sim.engine.types import GameState, TeamBoxScore, PlayResult
from fantasy_sim.models.distributions import KickingModel, DriveStartModel


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


def make_drive_start() -> DriveStartModel:
    return DriveStartModel(
        touchback_rate=1.0, touchback_yardline=75,
        return_yardlines=np.array([75]),
    )


def make_kicking(**overrides) -> KickingModel:
    defaults = dict(
        fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
        xp_rate=0.94,
    )
    defaults.update(overrides)
    return KickingModel(**defaults)


class TestApplyYards:
    def test_advances_down(self):
        state = make_state(down=1, distance=10, yard_line=75)
        apply_yards(state, 5)
        assert state.yard_line == 70
        assert state.down == 2
        assert state.distance == 5

    def test_first_down(self):
        state = make_state(down=2, distance=5, yard_line=70)
        apply_yards(state, 8)
        assert state.yard_line == 62
        assert state.down == 1
        assert state.distance == 10

    def test_loss_of_yards(self):
        state = make_state(down=1, distance=10, yard_line=70)
        apply_yards(state, -3)
        assert state.yard_line == 73
        assert state.down == 2
        assert state.distance == 13

    def test_turnover_on_downs(self):
        """4th down failed conversion flips possession."""
        state = make_state(down=4, distance=5, yard_line=50)
        apply_yards(state, 3)  # Not enough for first down
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert state.yard_line == 53  # Flipped: 100 - 47 = 53


class TestChangePossession:
    def test_flips_home_to_away(self):
        state = make_state(possession="home")
        change_possession(state)
        assert state.possession == "away"

    def test_flips_away_to_home(self):
        state = make_state(possession="away")
        change_possession(state)
        assert state.possession == "home"


class TestScorePoints:
    def test_home_scores(self):
        state = make_state(possession="home")
        score_points(state, 7)
        assert state.home_score == 7
        assert state.away_score == 0

    def test_away_scores(self):
        state = make_state(possession="away")
        score_points(state, 3)
        assert state.away_score == 3
        assert state.home_score == 0


class TestHandleTurnover:
    def test_interception_flips_possession(self):
        state = make_state(possession="home", yard_line=50)
        result = PlayResult(play_type="pass", yards=0, is_interception=True)
        handle_turnover(state, result)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert state.yard_line == 50  # 100 - 50 = 50 (midfield)

    def test_fumble_flips_possession(self):
        state = make_state(possession="home", yard_line=30)
        result = PlayResult(play_type="run", yards=5, is_fumble=True)
        handle_turnover(state, result)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        # Fumble at yard_line 30 - 5 = 25. Flip: 100 - 25 = 75
        assert state.yard_line == 75


class TestPerformKickoff:
    def test_sets_receiving_team_position(self):
        state = make_state(possession="home")
        rng = np.random.default_rng(42)
        perform_kickoff(state, make_drive_start(), rng)
        assert state.yard_line == 75
        assert state.down == 1
        assert state.distance == 10


class TestPerformPunt:
    def test_flips_possession(self):
        state = make_state(possession="home", yard_line=75)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        perform_punt(state, rng, off_box)
        assert state.possession == "away"
        assert state.down == 1
        assert state.distance == 10
        assert off_box.punts == 1

    def test_touchback_on_deep_punt(self):
        state = make_state(possession="home", yard_line=30)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        perform_punt(state, rng, off_box)
        assert state.possession == "away"
        assert 70 <= state.yard_line <= 80  # Touchback at own 20-25


class TestAttemptFieldGoal:
    def test_made_fg(self):
        state = make_state(possession="home", yard_line=20)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        kicking = make_kicking(fg_make_rate={"0_39": 1.0, "40_49": 1.0, "50_plus": 1.0})
        drive_start = make_drive_start()
        attempt_field_goal(state, kicking, drive_start, rng, off_box)
        assert state.home_score == 3
        assert off_box.fg_made == 1
        assert off_box.fg_attempts == 1
        assert off_box.points == 3

    def test_missed_fg_gives_opponent_ball(self):
        state = make_state(possession="home", yard_line=40)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore()
        kicking = make_kicking(fg_make_rate={"0_39": 0.0, "40_49": 0.0, "50_plus": 0.0})
        drive_start = make_drive_start()
        attempt_field_goal(state, kicking, drive_start, rng, off_box)
        assert state.home_score == 0
        assert state.possession == "away"
        assert off_box.fg_made == 0
        assert off_box.fg_attempts == 1


class TestAttemptPat:
    def test_xp_made(self):
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        attempt_pat(state, kicking, rng, off_box)
        assert state.home_score >= 7  # Either XP (7) or 2PT (8)
        assert off_box.points >= 7


class TestAttemptPatWithAttribution:
    def test_2pt_success_returns_scorer_id(self):
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        scorer_id = attempt_pat(state, kicking, rng, off_box, td_scorer_id="WR1", force_two_point=True)
        # With force_two_point=True and ~48% success rate, check result
        if state.home_score == 8:  # 6 + 2 = success
            assert scorer_id == "WR1"
        else:
            assert scorer_id is None

    def test_xp_returns_none(self):
        state = make_state(possession="home", home_score=6)
        rng = np.random.default_rng(42)
        off_box = TeamBoxScore(points=6)
        kicking = make_kicking(xp_rate=1.0)
        scorer_id = attempt_pat(state, kicking, rng, off_box, td_scorer_id="WR1", force_two_point=False)
        assert scorer_id is None
