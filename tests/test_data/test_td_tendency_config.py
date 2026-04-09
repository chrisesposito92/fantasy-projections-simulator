"""Tests for TD tendency config loading."""

from fantasy_sim.data.td_tendency import TdTendencyConfig, load_td_tendency_config


class TestTdTendencyConfig:

    def test_default_config(self):
        config = TdTendencyConfig()
        assert config.enabled is False
        assert config.prior_strength == 15.0
        assert config.min_opportunities == 5
        assert config.factor_clamp == (0.70, 1.30)

    def test_load_from_dict(self):
        raw = {
            "td_tendency": {
                "enabled": True,
                "prior_strength": 20.0,
                "min_opportunities": 8,
                "factor_clamp": [0.80, 1.20],
            }
        }
        config = load_td_tendency_config(raw)
        assert config.enabled is True
        assert config.prior_strength == 20.0
        assert config.min_opportunities == 8
        assert config.factor_clamp == (0.80, 1.20)

    def test_load_missing_key_returns_disabled(self):
        config = load_td_tendency_config({})
        assert config.enabled is False

    def test_load_partial_uses_defaults(self):
        raw = {"td_tendency": {"enabled": True}}
        config = load_td_tendency_config(raw)
        assert config.enabled is True
        assert config.prior_strength == 15.0

    def test_default_config_i5_fields(self):
        config = TdTendencyConfig()
        assert config.i5_enabled is False
        assert config.i5_prior_strength == 25.0
        assert config.i5_min_opportunities == 3

    def test_load_i5_fields_from_dict(self):
        raw = {
            "td_tendency": {
                "enabled": True,
                "i5_enabled": True,
                "i5_prior_strength": 30.0,
                "i5_min_opportunities": 4,
            }
        }
        config = load_td_tendency_config(raw)
        assert config.i5_enabled is True
        assert config.i5_prior_strength == 30.0
        assert config.i5_min_opportunities == 4

    def test_load_partial_i5_uses_defaults(self):
        raw = {"td_tendency": {"enabled": True, "i5_enabled": True}}
        config = load_td_tendency_config(raw)
        assert config.i5_prior_strength == 25.0
        assert config.i5_min_opportunities == 3
