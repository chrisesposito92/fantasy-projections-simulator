import pytest
from fantasy_sim.data.preprocessor import Preprocessor


class TestSanityChecks:
    def test_play_calling_probs_are_valid(self, sample_pbp):
        pre = Preprocessor()
        dists = pre.compute_play_calling(sample_pbp)
        for team, dist in dists.items():
            assert sum(dist.default.values()) == pytest.approx(1.0, abs=0.01)
            for prob in dist.default.values():
                assert 0.0 <= prob <= 1.0

    def test_play_outcomes_have_data(self, sample_pbp):
        pre = Preprocessor()
        dist = pre.compute_play_outcomes(sample_pbp)
        assert len(dist.defaults) >= 2
        for play_type, arr in dist.defaults.items():
            assert len(arr) > 0

    def test_turnover_rates_are_valid_probabilities(self, sample_pbp):
        pre = Preprocessor()
        rates = pre.compute_turnover_rates(sample_pbp)
        for team, r in rates.items():
            assert 0.0 <= r.int_rate <= 1.0
            assert 0.0 <= r.fumble_rate <= 1.0
            assert 0.0 <= r.sack_rate <= 1.0
            assert 0.0 <= r.sack_fumble_rate <= 1.0

    def test_kicking_model_rates_are_valid(self, sample_field_goals):
        pre = Preprocessor()
        model = pre.compute_kicking_model(sample_field_goals)
        for bucket, rate in model.fg_make_rate.items():
            assert 0.0 <= rate <= 1.0
        assert 0.0 <= model.xp_rate <= 1.0

    def test_drive_start_yardlines_are_valid(self, sample_kickoffs):
        pre = Preprocessor()
        model = pre.compute_drive_start_model(sample_kickoffs)
        assert 0.0 <= model.touchback_rate <= 1.0
        assert 1 <= model.touchback_yardline <= 99
        for yl in model.return_yardlines:
            assert 1 <= yl <= 99
