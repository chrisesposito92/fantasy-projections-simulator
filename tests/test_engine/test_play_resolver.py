import numpy as np
import pytest
from fantasy_sim.engine.play_resolver import resolve_play
from fantasy_sim.engine.types import GameState, PlayResult
from fantasy_sim.models.distributions import PlayOutcomeDist, TurnoverRates
from fantasy_sim.models.game_state import GameStateBucket


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


def make_outcomes(pass_yards=None, run_yards=None) -> PlayOutcomeDist:
    defaults = {}
    if pass_yards is not None:
        defaults["pass"] = np.array(pass_yards)
    else:
        defaults["pass"] = np.array([5, 8, 10, 12, 0, 15, -2, 20, 7, 3])
    if run_yards is not None:
        defaults["run"] = np.array(run_yards)
    else:
        defaults["run"] = np.array([3, 4, 5, -1, 2, 7, 1, 6, 0, 8])
    return PlayOutcomeDist(distributions={}, defaults=defaults)


def make_turnover_rates(**overrides) -> TurnoverRates:
    defaults = dict(team="KC", int_rate=0.0, fumble_rate=0.0, sack_rate=0.0, sack_fumble_rate=0.0)
    defaults.update(overrides)
    return TurnoverRates(**defaults)


class TestResolvePass:
    def test_normal_completion(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])  # Always 10 yards
        rates = make_turnover_rates()  # No turnovers
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.play_type == "pass"
        assert result.yards == 10
        assert result.is_complete
        assert not result.is_sack

    def test_incomplete_pass(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[0])  # Always 0 yards = incomplete
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.yards == 0
        assert not result.is_complete

    def test_sack(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)  # Always sacked
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.yards < 0

    def test_interception(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(int_rate=1.0)  # Always INT
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_interception
        assert result.yards == 0

    def test_sack_checked_before_int(self):
        """If sack_rate=1.0 and int_rate=1.0, sack should take priority."""
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0, int_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert not result.is_interception

    def test_pass_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=5)  # 5 yards from end zone
        outcomes = make_outcomes(pass_yards=[10])  # Gain 10 = TD
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 5  # Clamped to end zone

    def test_safety_on_sack(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=97)  # Own 3-yard line
        outcomes = make_outcomes()
        rates = make_turnover_rates(sack_rate=1.0)
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.is_sack
        assert result.is_safety


class TestResolveRun:
    def test_normal_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.play_type == "run"
        assert result.yards == 5
        assert not result.is_fumble

    def test_run_fumble(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble

    def test_run_touchdown(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_touchdown
        assert result.yards == 3  # Clamped to end zone

    def test_fumble_cancels_td(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=3)
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates(fumble_rate=1.0)
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_fumble
        assert not result.is_touchdown

    def test_run_safety(self):
        rng = np.random.default_rng(42)
        state = make_state(yard_line=98)  # Own 2
        outcomes = make_outcomes(run_yards=[-5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.is_safety

    def test_clock_runoff_pass_complete(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(pass_yards=[10])
        rates = make_turnover_rates()
        result = resolve_play(state, "pass", outcomes, rates, rng)
        assert result.clock_runoff > 0

    def test_clock_runoff_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        outcomes = make_outcomes(run_yards=[5])
        rates = make_turnover_rates()
        result = resolve_play(state, "run", outcomes, rates, rng)
        assert result.clock_runoff > 0
