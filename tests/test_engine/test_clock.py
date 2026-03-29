import numpy as np
import pytest
from fantasy_sim.engine.clock import apply_clock, check_quarter_end
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import DriveStartModel


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


class TestApplyClock:
    def test_reduces_clock(self):
        state = make_state(clock=900)
        apply_clock(state, 38)
        assert state.clock == 862

    def test_clock_does_not_go_negative(self):
        state = make_state(clock=10)
        apply_clock(state, 38)
        assert state.clock == 0


class TestCheckQuarterEnd:
    def test_q1_to_q2(self):
        state = make_state(quarter=1, clock=0, possession="home")
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 2
        assert state.clock == 900

    def test_q2_to_q3_halftime(self):
        """At halftime, the team that deferred receives."""
        state = make_state(quarter=2, clock=0, receiving_2nd_half="away")
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 3
        assert state.clock == 900
        assert state.possession == "away"
        assert state.down == 1

    def test_q3_to_q4(self):
        state = make_state(quarter=3, clock=0)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 4
        assert state.clock == 900

    def test_q4_end_no_tie_game_over(self):
        state = make_state(quarter=4, clock=0, home_score=21, away_score=14)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.game_over

    def test_q4_end_tie_goes_to_ot(self):
        state = make_state(quarter=4, clock=0, home_score=14, away_score=14)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 5
        assert not state.game_over

    def test_no_transition_when_clock_remaining(self):
        state = make_state(quarter=1, clock=100)
        rng = np.random.default_rng(42)
        check_quarter_end(state, make_drive_start(), make_drive_start(), rng)
        assert state.quarter == 1
        assert state.clock == 100
