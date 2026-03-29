import polars as pl
import numpy as np
import pytest
from fantasy_sim.data.preprocessor import Preprocessor
from fantasy_sim.models.game_state import GameStateBucket
from fantasy_sim.models.distributions import (
    PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)


class TestPlayCallingDistributions:
    def test_computes_pass_run_ratio_per_team(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        assert "KC" in dists
        assert "BUF" in dists

    def test_kc_has_correct_overall_ratio(self, sample_pbp):
        """KC has 8 passes and 4 runs = 66.7% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]
        assert kc.default["pass"] == pytest.approx(8 / 12, abs=0.01)
        assert kc.default["run"] == pytest.approx(4 / 12, abs=0.01)

    def test_buf_has_correct_overall_ratio(self, sample_pbp):
        """BUF has 4 passes and 4 runs = 50% pass rate."""
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        buf = dists["BUF"]
        assert buf.default["pass"] == pytest.approx(0.5, abs=0.01)
        assert buf.default["run"] == pytest.approx(0.5, abs=0.01)

    def test_distributions_have_bucketed_entries(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        kc = dists["KC"]
        assert kc.default is not None

    def test_all_probs_sum_to_one(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        for team_dist in dists.values():
            for bucket, probs in team_dist.distributions.items():
                assert sum(probs.values()) == pytest.approx(1.0, abs=0.01)
            assert sum(team_dist.default.values()) == pytest.approx(1.0, abs=0.01)


class TestPlayOutcomeDistributions:
    def test_computes_yards_arrays(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        assert isinstance(dist, PlayOutcomeDist)
        assert len(dist.distributions) > 0 or len(dist.defaults) > 0

    def test_defaults_contain_all_yards(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        assert "pass" in dist.defaults
        assert "run" in dist.defaults

    def test_run_defaults_contain_all_run_yards(self, sample_pbp):
        """All run yards in sample: KC=[5,-2,5,12], BUF=[7,3,1,4]"""
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        all_run_yards = sorted([5, -2, 5, 12, 7, 3, 1, 4])
        default_run = sorted(dist.defaults["run"].tolist())
        assert default_run == all_run_yards

    def test_can_sample_from_distribution(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        rng = np.random.default_rng(42)
        bucket = GameStateBucket(1, "long", "tied", 1, "own_territory")
        yards = dist.sample_yards("pass", bucket, rng)
        assert isinstance(yards, (int, np.integer))


class TestTurnoverRatePreprocessor:
    def test_computes_per_team(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert "KC" in rates
        assert "BUF" in rates

    def test_kc_int_rate(self, sample_pbp):
        """KC has 1 INT on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].int_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_sack_rate(self, sample_pbp):
        """KC has 1 sack on 8 pass attempts = 0.125."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].sack_rate == pytest.approx(1 / 8, abs=0.01)

    def test_kc_fumble_rate(self, sample_pbp):
        """KC has 1 fumble lost on 12 total plays = 0.0833."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["KC"].fumble_rate == pytest.approx(1 / 12, abs=0.01)

    def test_buf_zero_turnovers(self, sample_pbp):
        """BUF has 0 INTs, 0 fumbles, 0 sacks in sample data."""
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        assert rates["BUF"].int_rate == pytest.approx(0.0)
        assert rates["BUF"].fumble_rate == pytest.approx(0.0)
        assert rates["BUF"].sack_rate == pytest.approx(0.0)

    def test_rates_are_probabilities(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        for team_rates in rates.values():
            assert 0.0 <= team_rates.int_rate <= 1.0
            assert 0.0 <= team_rates.fumble_rate <= 1.0
            assert 0.0 <= team_rates.sack_rate <= 1.0
            assert 0.0 <= team_rates.sack_fumble_rate <= 1.0


class TestKickingModelPreprocessor:
    def test_computes_fg_rates_by_distance(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert isinstance(model, KickingModel)
        assert model.fg_make_rate["0_39"] == pytest.approx(1.0)
        assert model.fg_make_rate["40_49"] == pytest.approx(1.0)
        assert model.fg_make_rate["50_plus"] == pytest.approx(0.0)

    def test_fg_prob_returns_correct_bucket(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert model.fg_prob(35) == model.fg_make_rate["0_39"]
        assert model.fg_prob(45) == model.fg_make_rate["40_49"]
        assert model.fg_prob(52) == model.fg_make_rate["50_plus"]

    def test_xp_rate_defaults_when_no_data(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        assert 0.90 <= model.xp_rate <= 0.98


class TestDriveStartModelPreprocessor:
    def test_computes_touchback_rate(self, sample_kickoffs):
        """Sample has 3 touchbacks out of 5 kickoffs = 0.6."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert isinstance(model, DriveStartModel)
        assert model.touchback_rate == pytest.approx(3 / 5, abs=0.01)

    def test_touchback_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert model.touchback_yardline == 75

    def test_return_yardlines_from_non_touchbacks(self, sample_kickoffs):
        """Non-touchback plays have yardline_100 = [78, 72]."""
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert len(model.return_yardlines) == 2
        assert sorted(model.return_yardlines.tolist()) == [72, 78]

    def test_sample_produces_valid_yardline(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        rng = np.random.default_rng(42)
        for _ in range(50):
            yl = model.sample_start_yardline(rng)
            assert 1 <= yl <= 99
