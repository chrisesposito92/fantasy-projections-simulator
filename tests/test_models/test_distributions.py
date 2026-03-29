import numpy as np
import pytest
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


class TestPlayCallingDist:
    def test_get_play_probs(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        dist = PlayCallingDist(team="KC", distributions={bucket: {"pass": 0.6, "run": 0.4}})
        probs = dist.get_probs(bucket)
        assert probs["pass"] == pytest.approx(0.6)
        assert probs["run"] == pytest.approx(0.4)

    def test_missing_bucket_falls_back_to_default(self):
        known = GameStateBucket(1, "long", "tied", 1, "own_territory")
        unknown = GameStateBucket(3, "very_long", "down_big", 4, "backed_up")
        dist = PlayCallingDist(team="KC", distributions={known: {"pass": 0.6, "run": 0.4}}, default={"pass": 0.55, "run": 0.45})
        probs = dist.get_probs(unknown)
        assert probs["pass"] == pytest.approx(0.55)

    def test_probs_sum_to_one(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        dist = PlayCallingDist(team="KC", distributions={bucket: {"pass": 0.6, "run": 0.4}})
        probs = dist.get_probs(bucket)
        assert sum(probs.values()) == pytest.approx(1.0)


class TestPlayOutcomeDist:
    def test_sample_yards(self):
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        yards_history = np.array([5, 8, -2, 12, 3, 7, 0, 15, 4, 6])
        dist = PlayOutcomeDist(distributions={("pass", bucket): yards_history})
        rng = np.random.default_rng(42)
        sampled = dist.sample_yards("pass", bucket, rng)
        assert sampled in yards_history

    def test_missing_bucket_falls_back_to_play_type_default(self):
        known = GameStateBucket(1, "long", "tied", 1, "own_territory")
        unknown = GameStateBucket(3, "short", "up_big", 4, "red_zone")
        dist = PlayOutcomeDist(distributions={("pass", known): np.array([5, 8, 3])}, defaults={"pass": np.array([4, 6, 2])})
        rng = np.random.default_rng(42)
        sampled = dist.sample_yards("pass", unknown, rng)
        assert sampled in [4, 6, 2]


class TestTurnoverRates:
    def test_rates(self):
        rates = TurnoverRates(team="KC", int_rate=0.025, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10)
        assert rates.int_rate == pytest.approx(0.025)
        assert rates.fumble_rate == pytest.approx(0.01)


class TestKickingModel:
    def test_fg_probability(self):
        model = KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94)
        assert model.fg_prob(32) == pytest.approx(0.95)
        assert model.fg_prob(45) == pytest.approx(0.82)
        assert model.fg_prob(55) == pytest.approx(0.65)

    def test_xp_rate(self):
        model = KickingModel(fg_make_rate={"0_39": 0.95, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94)
        assert model.xp_rate == pytest.approx(0.94)


class TestDriveStartModel:
    def test_sample_start_yardline(self):
        model = DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([78, 72, 68, 80, 74]))
        rng = np.random.default_rng(42)
        yardline = model.sample_start_yardline(rng)
        assert 1 <= yardline <= 99
