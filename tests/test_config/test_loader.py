import pytest
from pathlib import Path
from fantasy_sim.config.loader import load_config, resolve_scoring, ConfigError


@pytest.fixture
def defaults_path():
    return Path(__file__).parent.parent.parent / "config" / "defaults.yaml"


@pytest.fixture
def custom_scoring(tmp_path):
    content = """
inherit: ppr
overrides:
  passing_td: 6
  reception: 1.5
"""
    p = tmp_path / "custom.yaml"
    p.write_text(content)
    return p


class TestLoadConfig:
    def test_loads_defaults(self, defaults_path):
        config = load_config(defaults_path)
        assert "simulation" in config
        assert "scoring" in config
        assert config["simulation"]["num_sims"] == 1000

    def test_scoring_has_presets(self, defaults_path):
        config = load_config(defaults_path)
        assert "ppr" in config["scoring"]
        assert "half_ppr" in config["scoring"]
        assert "standard" in config["scoring"]

    def test_ppr_scoring_values(self, defaults_path):
        config = load_config(defaults_path)
        ppr = config["scoring"]["ppr"]
        assert ppr["passing_yard"] == 0.04
        assert ppr["passing_td"] == 4
        assert ppr["reception"] == 1
        assert ppr["rushing_td"] == 6


class TestResolveScoringInheritance:
    def test_ppr_is_base(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "ppr")
        assert resolved["reception"] == 1
        assert resolved["passing_td"] == 4

    def test_half_ppr_inherits_from_ppr(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "half_ppr")
        assert resolved["reception"] == 0.5
        assert resolved["passing_td"] == 4  # Inherited from PPR

    def test_standard_inherits_from_ppr(self, defaults_path):
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "standard")
        assert resolved["reception"] == 0
        assert resolved["passing_td"] == 4  # Inherited from PPR

    def test_custom_overrides(self, defaults_path, custom_scoring):
        config = load_config(defaults_path)
        custom = load_config(custom_scoring)
        base = resolve_scoring(config["scoring"], custom["inherit"])
        for k, v in custom.get("overrides", {}).items():
            base[k] = v
        assert base["passing_td"] == 6
        assert base["reception"] == 1.5
        assert base["rushing_td"] == 6  # Still from PPR base

    def test_unknown_format_raises(self, defaults_path):
        config = load_config(defaults_path)
        with pytest.raises(ConfigError):
            resolve_scoring(config["scoring"], "nonexistent")

    def test_no_inherit_key_in_base(self, defaults_path):
        """Resolved scoring should not contain _inherit key."""
        config = load_config(defaults_path)
        resolved = resolve_scoring(config["scoring"], "half_ppr")
        assert "_inherit" not in resolved
