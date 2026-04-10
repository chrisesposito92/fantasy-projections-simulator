"""Tests for validation config resolution."""
import pytest
from fantasy_sim.validation.config import (
    _parse_value,
    apply_overrides,
    build_engine_configs,
    build_bare_engine_configs,
)
from fantasy_sim.config.loader import load_defaults


class TestParseValue:
    def test_true(self):
        assert _parse_value("true") is True

    def test_false(self):
        assert _parse_value("false") is False

    def test_true_case_insensitive(self):
        assert _parse_value("True") is True
        assert _parse_value("FALSE") is False

    def test_int(self):
        assert _parse_value("42") == 42
        assert isinstance(_parse_value("42"), int)

    def test_negative_int(self):
        assert _parse_value("-3") == -3

    def test_float(self):
        assert _parse_value("0.06") == 0.06
        assert isinstance(_parse_value("0.06"), float)

    def test_negative_float(self):
        assert _parse_value("-0.03") == -0.03

    def test_string(self):
        assert _parse_value("hello") == "hello"
        assert isinstance(_parse_value("hello"), str)

    def test_empty_string(self):
        assert _parse_value("") == ""

    def test_list_of_floats(self):
        result = _parse_value("[0.85,1.15]")
        assert result == [0.85, 1.15]

    def test_list_of_ints(self):
        result = _parse_value("[1,2,3]")
        assert result == [1, 2, 3]

    def test_empty_list(self):
        assert _parse_value("[]") == []

    def test_list_with_spaces(self):
        result = _parse_value("[0.60, 1.40]")
        assert result == [0.60, 1.40]


class TestApplyOverrides:
    def test_set_nested_bool(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        result = apply_overrides(config, ["pff.matchup.enabled=false"])
        assert result["pff"]["matchup"]["enabled"] is False

    def test_set_nested_float(self):
        config = {"pff": {"matchup": {"pass_defense_sensitivity": 0.08}}}
        result = apply_overrides(config, ["pff.matchup.pass_defense_sensitivity=0.12"])
        assert result["pff"]["matchup"]["pass_defense_sensitivity"] == 0.12

    def test_multiple_overrides(self):
        config = {"pff": {"enabled": True, "matchup": {"enabled": True}}}
        result = apply_overrides(config, [
            "pff.enabled=false",
            "pff.matchup.enabled=false",
        ])
        assert result["pff"]["enabled"] is False
        assert result["pff"]["matchup"]["enabled"] is False

    def test_does_not_mutate_original(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        apply_overrides(config, ["pff.matchup.enabled=false"])
        assert config["pff"]["matchup"]["enabled"] is True

    def test_top_level_key(self):
        config = {"scoring_format": "ppr"}
        result = apply_overrides(config, ["scoring_format=half_ppr"])
        assert result["scoring_format"] == "half_ppr"

    def test_invalid_key_raises(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        with pytest.raises(KeyError):
            apply_overrides(config, ["pff.nonexistent.enabled=false"])

    def test_set_int(self):
        config = {"pff": {"kicker": {"prior_strength": 20}}}
        result = apply_overrides(config, ["pff.kicker.prior_strength=30"])
        assert result["pff"]["kicker"]["prior_strength"] == 30

    def test_set_list(self):
        config = {"usage": {"snap": {"factor_clamp": [0.70, 1.30]}}}
        result = apply_overrides(config, ["usage.snap.factor_clamp=[0.85,1.15]"])
        assert result["usage"]["snap"]["factor_clamp"] == [0.85, 1.15]

    def test_invalid_leaf_key_raises(self):
        config = {"pff": {"matchup": {"enabled": True}}}
        with pytest.raises(KeyError, match="enabledd"):
            apply_overrides(config, ["pff.matchup.enabledd=false"])


class TestBuildEngineConfigs:
    def test_defaults_produces_enabled_configs(self):
        defaults = load_defaults()
        configs = build_engine_configs(defaults)
        assert configs["pff_config"] is not None
        assert configs["pff_config"].enabled is True
        assert configs["weather_config"] is not None
        assert configs["weather_config"].enabled is True
        assert configs["vegas_config"] is not None
        assert configs["props_config"] is not None
        assert configs["usage_config"] is not None

    def test_defaults_include_enabled_game_script_config(self):
        defaults = load_defaults()

        configs = build_engine_configs(defaults)

        assert "game_script_config" in configs
        assert configs["game_script_config"] is not None
        assert configs["game_script_config"].enabled is True

    def test_disabled_engine_returns_none(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is None

    def test_sub_engine_override_propagates(self):
        defaults = load_defaults()
        overridden = apply_overrides(defaults, ["pff.matchup.enabled=false"])
        configs = build_engine_configs(overridden)
        assert configs["pff_config"] is not None
        assert configs["pff_config"].matchup.enabled is False


class TestBuildBareEngineConfigs:
    def test_all_none(self):
        configs = build_bare_engine_configs()
        assert configs["pff_config"] is None
        assert configs["weather_config"] is None
        assert configs["vegas_config"] is None
        assert configs["props_config"] is None
        assert configs["usage_config"] is None
        assert configs["game_script_config"] is None
