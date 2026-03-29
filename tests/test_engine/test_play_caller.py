import numpy as np
import pytest
from fantasy_sim.engine.play_caller import select_play_type, fourth_down_decision
from fantasy_sim.engine.types import GameState
from fantasy_sim.models.distributions import PlayCallingDist, KickingModel
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


def make_play_calling(pass_rate: float = 0.6) -> PlayCallingDist:
    return PlayCallingDist(
        team="KC", distributions={},
        default={"pass": pass_rate, "run": 1 - pass_rate},
    )


def make_kicking() -> KickingModel:
    return KickingModel(
        fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65},
        xp_rate=0.94,
    )


class TestSelectPlayType:
    def test_returns_pass_or_run(self):
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling()
        result = select_play_type(state, play_calling, rng)
        assert result in ("pass", "run")

    def test_respects_distribution(self):
        """With 100% pass rate, should always return pass."""
        rng = np.random.default_rng(42)
        state = make_state()
        play_calling = make_play_calling(pass_rate=1.0)
        results = [select_play_type(state, play_calling, rng) for _ in range(100)]
        assert all(r == "pass" for r in results)

    def test_uses_game_state_for_bucket(self):
        """Different game states should produce different buckets for lookup."""
        rng = np.random.default_rng(42)
        bucket = GameStateBucket(3, "long", "down_big", 4, "own_territory")
        play_calling = PlayCallingDist(
            team="KC",
            distributions={bucket: {"pass": 0.95, "run": 0.05}},
            default={"pass": 0.5, "run": 0.5},
        )
        state = make_state(down=3, distance=10, yard_line=60, quarter=4,
                          home_score=0, away_score=21)
        results = [select_play_type(state, play_calling, rng) for _ in range(100)]
        pass_rate = sum(1 for r in results if r == "pass") / 100
        assert pass_rate > 0.85


class TestFourthDownDecision:
    def test_punt_from_own_territory(self):
        state = make_state(down=4, distance=5, yard_line=70)
        assert fourth_down_decision(state, make_kicking()) == "punt"

    def test_fg_from_makeable_range(self):
        """yard_line=30 → FG distance = 30 + 17 = 47 yards. Should attempt."""
        state = make_state(down=4, distance=5, yard_line=30)
        assert fourth_down_decision(state, make_kicking()) == "field_goal"

    def test_go_for_it_short_yardage_in_opp_territory(self):
        """4th and 1 at opponent's 40."""
        state = make_state(down=4, distance=1, yard_line=40)
        assert fourth_down_decision(state, make_kicking()) == "go_for_it"

    def test_go_for_it_near_goal_line(self):
        """4th and 2 at the opponent's 3."""
        state = make_state(down=4, distance=2, yard_line=3)
        assert fourth_down_decision(state, make_kicking()) == "go_for_it"

    def test_punt_on_long_yardage(self):
        """4th and 15 at opponent's 40 — too long to go for it, too far for FG."""
        state = make_state(down=4, distance=15, yard_line=40)
        assert fourth_down_decision(state, make_kicking()) == "punt"

    def test_fg_attempt_at_long_range_declined(self):
        """yard_line=45 → FG distance = 62 yards. Too far, should punt."""
        state = make_state(down=4, distance=5, yard_line=45)
        assert fourth_down_decision(state, make_kicking()) == "punt"
