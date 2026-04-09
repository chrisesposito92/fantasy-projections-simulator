"""Test that td_tendency config flows through validation pipeline."""

from fantasy_sim.validation.config import build_engine_configs, build_bare_engine_configs


class TestTdTendencyConfigResolution:

    def test_build_engine_configs_includes_td_tendency(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "td_tendency": {"enabled": True, "prior_strength": 20},
        }
        result = build_engine_configs(config)
        assert "td_tendency_config" in result
        assert result["td_tendency_config"] is not None
        assert result["td_tendency_config"].enabled is True
        assert result["td_tendency_config"].prior_strength == 20

    def test_build_bare_includes_td_tendency_none(self):
        result = build_bare_engine_configs()
        assert "td_tendency_config" in result
        assert result["td_tendency_config"] is None

    def test_disabled_td_tendency_returns_none(self):
        config = {
            "pff": {"enabled": False},
            "weather": {"enabled": False},
            "vegas": {"enabled": False},
            "usage": {"enabled": False},
            "td_tendency": {"enabled": False},
        }
        result = build_engine_configs(config)
        assert result["td_tendency_config"] is None
