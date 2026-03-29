import numpy as np
import pytest
from fantasy_sim.engine.types import (
    GameState, TeamBoxScore, PlayResult, GameResult, TeamDistributions,
)
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.game_state import GameStateBucket


class TestGameState:
    def test_initial_state(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.quarter == 1
        assert state.clock == 900
        assert not state.game_over

    def test_score_differential_home(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=14, away_score=7,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.score_differential == 7

    def test_score_differential_away(self):
        state = GameState(
            quarter=1, clock=900, possession="away",
            down=1, distance=10, yard_line=75,
            home_score=14, away_score=7,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.score_differential == -7

    def test_offense_defense(self):
        state = GameState(
            quarter=1, clock=900, possession="home",
            down=1, distance=10, yard_line=75,
            home_score=0, away_score=0,
            home_team="KC", away_team="BUF",
            receiving_2nd_half="away",
        )
        assert state.offense == "home"
        assert state.defense == "away"


class TestTeamBoxScore:
    def test_defaults_to_zero(self):
        box = TeamBoxScore()
        assert box.pass_attempts == 0
        assert box.rush_yards == 0
        assert box.points == 0
        assert box.sacks_made == 0

    def test_mutable(self):
        box = TeamBoxScore()
        box.pass_attempts += 1
        box.pass_yards += 250
        box.points += 7
        assert box.pass_attempts == 1
        assert box.pass_yards == 250


class TestPlayResult:
    def test_normal_completion(self):
        result = PlayResult(play_type="pass", yards=12, is_complete=True, clock_runoff=35)
        assert result.yards == 12
        assert result.is_complete
        assert not result.is_sack
        assert not result.is_touchdown

    def test_touchdown_run(self):
        result = PlayResult(play_type="run", yards=5, is_touchdown=True, clock_runoff=38)
        assert result.is_touchdown
        assert result.yards == 5


class TestTeamDistributions:
    def test_bundles_all_distributions(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        td = TeamDistributions(
            play_calling=PlayCallingDist(team="KC", distributions={bucket: {"pass": 0.6, "run": 0.4}}),
            play_outcomes=PlayOutcomeDist(distributions={}, defaults={"pass": np.array([5]), "run": np.array([3])}),
            turnover_rates=TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
            kicking=KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
            drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([72, 78])),
        )
        assert td.play_calling.team == "KC"
        assert td.kicking.xp_rate == pytest.approx(0.94)


class TestGameResult:
    def test_construction(self):
        result = GameResult(
            home_score=24,
            away_score=17,
            home_box=TeamBoxScore(),
            away_box=TeamBoxScore(),
            total_plays=140,
            overtime=False,
        )
        assert result.home_score == 24
        assert result.away_score == 17
        assert result.total_plays == 140
        assert not result.overtime
