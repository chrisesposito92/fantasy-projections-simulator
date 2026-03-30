import pytest
from pathlib import Path
from fantasy_sim.overrides.parser import (
    parse_override_config,
    parse_cli_override,
    OverrideSet,
)


class TestParseOverrideConfig:
    def test_parses_player_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
players:
  WR1:
    target_share: 0.28
  RB1:
    carry_share: 0.75
""")
        result = parse_override_config(config)
        assert isinstance(result, OverrideSet)
        assert "WR1" in result.players
        assert result.players["WR1"]["target_share"] == 0.28

    def test_parses_team_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
teams:
  KC:
    pass_rate: 0.62
""")
        result = parse_override_config(config)
        assert "KC" in result.teams
        assert result.teams["KC"]["pass_rate"] == 0.62

    def test_empty_config_returns_empty_overrides(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("season: 2025\n")
        result = parse_override_config(config)
        assert len(result.players) == 0
        assert len(result.teams) == 0

    def test_parses_games_missed(self, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("""
season: 2025
players:
  QB1:
    games_missed: [4, 5, 6]
""")
        result = parse_override_config(config)
        assert result.players["QB1"]["games_missed"] == [4, 5, 6]


class TestParseCLIOverride:
    def test_player_override(self):
        result = parse_cli_override("mahomes.target_share=0.30")
        assert result == ("mahomes", "target_share", 0.30)

    def test_player_override_integer(self):
        result = parse_cli_override("mahomes.games_played=14")
        assert result == ("mahomes", "games_played", 14)

    def test_team_override(self):
        result = parse_cli_override("KC.pass_rate=0.65")
        assert result == ("KC", "pass_rate", 0.65)

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_cli_override("invalid_no_equals")

    def test_invalid_format_no_dot_raises(self):
        with pytest.raises(ValueError):
            parse_cli_override("nodot=0.5")
