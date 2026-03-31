"""Tests for pace_factor on TeamDistributions and pace_plays_per_game override."""
import numpy as np
import pytest

from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.engine.play_resolver import (
    _scale_clock_runoff,
    CLOCK_RUN,
    CLOCK_PASS_COMPLETE,
    CLOCK_PASS_INCOMPLETE,
    CLOCK_SACK,
)
from fantasy_sim.engine.game_sim import simulate_game
from fantasy_sim.overrides.engine import (
    TEAM_OVERRIDE_FIELDS,
    BASELINE_PLAYS_PER_GAME,
    apply_team_override,
)
from fantasy_sim.models.distributions import (
    PlayCallingDist,
    PlayOutcomeDist,
    TurnoverRates,
    KickingModel,
    DriveStartModel,
)


def make_dists(team: str, pace_factor: float = 1.0) -> TeamDistributions:
    """Construct a minimal TeamDistributions for testing."""
    play_calling = PlayCallingDist(
        team=team,
        distributions={},
        default={"pass": 0.57, "run": 0.43},
    )
    play_outcomes = PlayOutcomeDist(
        distributions={},
        defaults={
            "pass": np.array([5, 8, 10, -2, 0, 15, 3, 7, 6, 4]),
            "run": np.array([3, 4, 5, 2, 1, -1, 6, 3, 4, 2]),
        },
    )
    turnover_rates = TurnoverRates(
        team=team, int_rate=0.03, fumble_rate=0.02,
        sack_rate=0.06, sack_fumble_rate=0.10,
    )
    kicking = KickingModel(
        fg_make_rate={"0_39": 0.90, "40_49": 0.80, "50_plus": 0.60},
        xp_rate=0.95,
    )
    drive_start = DriveStartModel(
        touchback_rate=0.55,
        touchback_yardline=75,
        return_yardlines=np.array([70, 72, 75, 78, 80]),
    )
    return TeamDistributions(
        play_calling=play_calling,
        play_outcomes=play_outcomes,
        turnover_rates=turnover_rates,
        kicking=kicking,
        drive_start=drive_start,
        pace_factor=pace_factor,
    )


class TestPaceFactorField:
    """Verify pace_factor field exists on TeamDistributions and defaults to 1.0."""

    def test_default_pace_factor(self):
        dists = make_dists("KC")
        assert dists.pace_factor == 1.0

    def test_custom_pace_factor(self):
        dists = make_dists("KC", pace_factor=1.3)
        assert dists.pace_factor == 1.3


class TestScaleClockRunoff:
    """Test _scale_clock_runoff helper function."""

    def test_neutral_no_change(self):
        """pace_factor=1.0 returns base_runoff unchanged."""
        assert _scale_clock_runoff(CLOCK_RUN, 1.0) == CLOCK_RUN
        assert _scale_clock_runoff(CLOCK_PASS_COMPLETE, 1.0) == CLOCK_PASS_COMPLETE
        assert _scale_clock_runoff(CLOCK_PASS_INCOMPLETE, 1.0) == CLOCK_PASS_INCOMPLETE
        assert _scale_clock_runoff(CLOCK_SACK, 1.0) == CLOCK_SACK

    def test_fast_pace_reduces_runoff(self):
        """pace_factor > 1.0 means faster pace, less clock per play."""
        assert _scale_clock_runoff(CLOCK_RUN, 1.3) == round(CLOCK_RUN / 1.3)
        assert _scale_clock_runoff(CLOCK_PASS_COMPLETE, 1.3) == round(CLOCK_PASS_COMPLETE / 1.3)
        assert _scale_clock_runoff(CLOCK_PASS_INCOMPLETE, 1.3) == round(CLOCK_PASS_INCOMPLETE / 1.3)

    def test_slow_pace_increases_runoff(self):
        """pace_factor < 1.0 means slower pace, more clock per play."""
        assert _scale_clock_runoff(CLOCK_RUN, 0.8) == round(CLOCK_RUN / 0.8)
        assert _scale_clock_runoff(CLOCK_PASS_INCOMPLETE, 0.8) == round(CLOCK_PASS_INCOMPLETE / 0.8)

    def test_minimum_is_one(self):
        """Clock runoff never goes below 1 second."""
        assert _scale_clock_runoff(1, 100.0) == 1
        assert _scale_clock_runoff(2, 100.0) == 1


class TestPaceOverrideField:
    """Verify pace_plays_per_game is in TEAM_OVERRIDE_FIELDS and works via apply_team_override."""

    def test_field_in_team_override_fields(self):
        assert "pace_plays_per_game" in TEAM_OVERRIDE_FIELDS

    def test_apply_pace_66_plays(self):
        dists = make_dists("KC")
        apply_team_override(dists, {"pace_plays_per_game": 66})
        expected = 66 / BASELINE_PLAYS_PER_GAME
        assert abs(dists.pace_factor - expected) < 1e-9

    def test_apply_pace_72_plays(self):
        dists = make_dists("KC")
        apply_team_override(dists, {"pace_plays_per_game": 72})
        expected = 72 / BASELINE_PLAYS_PER_GAME
        assert abs(dists.pace_factor - expected) < 1e-9

    def test_apply_pace_58_plays(self):
        dists = make_dists("KC")
        apply_team_override(dists, {"pace_plays_per_game": 58})
        expected = 58 / BASELINE_PLAYS_PER_GAME
        assert abs(dists.pace_factor - expected) < 1e-9

    def test_pace_zero_raises(self):
        dists = make_dists("KC")
        with pytest.raises(ValueError, match="must be positive"):
            apply_team_override(dists, {"pace_plays_per_game": 0})

    def test_pace_negative_raises(self):
        dists = make_dists("KC")
        with pytest.raises(ValueError, match="must be positive"):
            apply_team_override(dists, {"pace_plays_per_game": -10})


class TestPaceAffectsPlayCount:
    """Integration test: fast pace should produce more plays than normal pace."""

    def test_fast_pace_more_plays(self):
        """Run 20 games each at pace_factor 1.0 and 1.3; fast should average more plays."""
        rng = np.random.default_rng(42)
        n_games = 20

        normal_plays = []
        for _ in range(n_games):
            home = make_dists("HOME", pace_factor=1.0)
            away = make_dists("AWAY", pace_factor=1.0)
            result = simulate_game(home, away, rng)
            normal_plays.append(result.total_plays)

        fast_plays = []
        for _ in range(n_games):
            home = make_dists("HOME", pace_factor=1.3)
            away = make_dists("AWAY", pace_factor=1.3)
            result = simulate_game(home, away, rng)
            fast_plays.append(result.total_plays)

        avg_normal = sum(normal_plays) / n_games
        avg_fast = sum(fast_plays) / n_games
        assert avg_fast > avg_normal, (
            f"Fast pace ({avg_fast:.1f} plays) should exceed normal ({avg_normal:.1f} plays)"
        )
