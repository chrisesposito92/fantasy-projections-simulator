"""Tests for DST defensive TD modeling (pick-sixes and fumble return TDs)."""

import numpy as np
import pytest
from fantasy_sim.engine.types import TeamBoxScore, PlayResult
from fantasy_sim.engine.game_sim import (
    _update_box_scores,
    INT_RETURN_TD_RATE,
    FUMBLE_RETURN_TD_RATE,
)


def test_team_box_score_has_defensive_tds_field():
    """TeamBoxScore should have a defensive_tds field defaulting to 0."""
    box = TeamBoxScore()
    assert hasattr(box, "defensive_tds")
    assert box.defensive_tds == 0


def test_interception_can_produce_defensive_td():
    """An interception with rng should produce defensive_tds as int >= 0."""
    rng = np.random.default_rng(42)
    off_box = TeamBoxScore()
    def_box = TeamBoxScore()
    result = PlayResult(
        play_type="pass", yards=0, is_interception=True,
    )
    _update_box_scores(off_box, def_box, result, rng=rng)
    assert isinstance(def_box.defensive_tds, int)
    assert def_box.defensive_tds >= 0


def test_fumble_recovery_can_produce_defensive_td():
    """A fumble with rng should produce defensive_tds as int >= 0."""
    rng = np.random.default_rng(42)
    off_box = TeamBoxScore()
    def_box = TeamBoxScore()
    result = PlayResult(
        play_type="run", yards=3, is_fumble=True,
    )
    _update_box_scores(off_box, def_box, result, rng=rng)
    assert isinstance(def_box.defensive_tds, int)
    assert def_box.defensive_tds >= 0


@pytest.mark.statistical
def test_defensive_td_statistical_rate_on_interceptions():
    """Over 5000 interceptions, defensive TD rate should be ~20% (0.15-0.25)."""
    rng = np.random.default_rng(12345)
    total_def_tds = 0
    n_trials = 5000

    for _ in range(n_trials):
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(
            play_type="pass", yards=0, is_interception=True,
        )
        _update_box_scores(off_box, def_box, result, rng=rng)
        total_def_tds += def_box.defensive_tds

    rate = total_def_tds / n_trials
    assert 0.15 <= rate <= 0.25, f"INT return TD rate {rate:.3f} outside [0.15, 0.25]"


@pytest.mark.statistical
def test_defensive_td_statistical_rate_on_fumbles():
    """Over 5000 fumbles, defensive TD rate should be ~10% (0.06-0.14)."""
    rng = np.random.default_rng(12345)
    total_def_tds = 0
    n_trials = 5000

    for _ in range(n_trials):
        off_box = TeamBoxScore()
        def_box = TeamBoxScore()
        result = PlayResult(
            play_type="run", yards=3, is_fumble=True,
        )
        _update_box_scores(off_box, def_box, result, rng=rng)
        total_def_tds += def_box.defensive_tds

    rate = total_def_tds / n_trials
    assert 0.06 <= rate <= 0.14, f"Fumble return TD rate {rate:.3f} outside [0.06, 0.14]"


def test_no_defensive_td_on_normal_play():
    """A normal completion should produce defensive_tds == 0."""
    rng = np.random.default_rng(42)
    off_box = TeamBoxScore()
    def_box = TeamBoxScore()
    result = PlayResult(
        play_type="pass", yards=12, is_complete=True,
    )
    _update_box_scores(off_box, def_box, result, rng=rng)
    assert def_box.defensive_tds == 0


def test_update_box_scores_backward_compatible_without_rng():
    """Calling _update_box_scores without rng should not crash and defensive_tds == 0."""
    off_box = TeamBoxScore()
    def_box = TeamBoxScore()
    result = PlayResult(
        play_type="pass", yards=0, is_interception=True,
    )
    # No rng argument — backward compatibility
    _update_box_scores(off_box, def_box, result)
    assert def_box.defensive_tds == 0
    assert def_box.interceptions_caught == 1
