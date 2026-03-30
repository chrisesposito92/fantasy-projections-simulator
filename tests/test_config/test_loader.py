import pytest
from pathlib import Path
from fantasy_sim.config.loader import load_config, resolve_scoring, load_custom_scoring, load_defaults, ConfigError


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


class TestLoadCustomScoring:
    def test_load_custom_scoring_with_inherit(self, tmp_path):
        """Custom scoring with inherit should start from preset and apply overrides."""
        content = "inherit: ppr\noverrides:\n  passing_td: 6\n  reception_wr: 1.5\n"
        p = tmp_path / "custom.yaml"
        p.write_text(content)
        defaults = load_defaults()
        result = load_custom_scoring(p, defaults["scoring"])
        assert result["passing_td"] == 6
        assert result["reception_wr"] == 1.5
        assert result["rushing_td"] == 6  # inherited from ppr

    def test_load_custom_scoring_without_inherit(self, tmp_path):
        """Custom scoring without inherit should only contain overrides."""
        content = "overrides:\n  passing_td: 6\n  rushing_td: 8\n"
        p = tmp_path / "custom.yaml"
        p.write_text(content)
        defaults = load_defaults()
        result = load_custom_scoring(p, defaults["scoring"])
        assert result["passing_td"] == 6
        assert result["rushing_td"] == 8
        assert "reception" not in result  # no inherit, no base

    def test_load_custom_scoring_inherit_half_ppr(self, tmp_path):
        """Custom scoring can inherit from half_ppr."""
        content = "inherit: half_ppr\noverrides:\n  passing_td: 6\n"
        p = tmp_path / "custom.yaml"
        p.write_text(content)
        defaults = load_defaults()
        result = load_custom_scoring(p, defaults["scoring"])
        assert result["passing_td"] == 6
        assert result["reception"] == 0.5  # from half_ppr

    def test_load_custom_scoring_invalid_inherit(self, tmp_path):
        """Custom scoring with invalid inherit should raise ConfigError."""
        content = "inherit: nonexistent\noverrides:\n  passing_td: 6\n"
        p = tmp_path / "custom.yaml"
        p.write_text(content)
        defaults = load_defaults()
        with pytest.raises(ConfigError):
            load_custom_scoring(p, defaults["scoring"])

    def test_load_custom_scoring_file_not_found(self):
        """Custom scoring with non-existent file should raise ConfigError."""
        defaults = load_defaults()
        with pytest.raises(ConfigError):
            load_custom_scoring(Path("/tmp/does_not_exist.yaml"), defaults["scoring"])
