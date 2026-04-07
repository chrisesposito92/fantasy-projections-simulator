import pytest
import click
from click.testing import CliRunner
from unittest.mock import patch
from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.cli import main


from fantasy_sim.engine.types import TeamDistributions
from fantasy_sim.models.distributions import (
    PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
)
from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes


def _make_test_dists(team):
    """Create minimal TeamDistributions for CLI tests."""
    return TeamDistributions(
        play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
        play_outcomes=PlayOutcomeDist(distributions={}, defaults={
            "pass": np.array([0, 5, 8, 10, 12, 15]),
            "run": np.array([2, 3, 4, 5, 6]),
        }),
        turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
        kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
        drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
    )


def _make_test_roster(team):
    """Create minimal TeamRoster for CLI tests."""
    return TeamRoster(team=team, players=[
        PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
        PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                   PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
        PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                   PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                 catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
    ])


def _wire_mocks(MockLoader, MockBuilder, schedule_rows):
    """Wire loader and builder mocks with schedule data and default team context."""
    mock_loader = MockLoader.return_value
    mock_loader.load_schedules.return_value = pl.DataFrame(schedule_rows)
    mock_loader.cache_dir = Path("/tmp/cache")
    mock_builder = MockBuilder.return_value
    mock_builder.build_game.return_value = (
        _make_test_dists("KC"), _make_test_dists("BUF"),
        _make_test_roster("KC"), _make_test_roster("BUF"),
    )
    return mock_loader, mock_builder


@pytest.fixture
def runner():
    return CliRunner()


class TestCLI:
    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "fantasy-sim" in result.output.lower() or "Usage" in result.output

    def test_demo_command(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10"])
        assert result.exit_code == 0
        assert "QB" in result.output or "Projections" in result.output

    def test_demo_csv_export(self, runner, tmp_path):
        output = tmp_path / "test.csv"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()

    def test_demo_json_export(self, runner, tmp_path):
        output = tmp_path / "test.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "json", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()

    def test_demo_scoring_format(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", "standard"])
        assert result.exit_code == 0

    def test_demo_half_ppr(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", "half_ppr"])
        assert result.exit_code == 0


class TestWeekCommand:
    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_week_command_runs(self, MockLoader, MockBuilder, runner):
        """Week command should load schedules, build context, run sims."""
        _wire_mocks(MockLoader, MockBuilder, [
            {"season": 2024, "week": 1, "game_id": "g1",
             "home_team": "KC", "away_team": "BUF"},
        ])
        result = runner.invoke(main, ["week", "1", "--season", "2024", "--sims", "10"])
        assert result.exit_code == 0


class TestOverrideCLI:
    def test_override_flag_accepted(self, runner):
        result = runner.invoke(main, ["demo", "--sims", "10", "--override", "HOME_WR1.target_share=0.30"])
        assert result.exit_code == 0

    def test_config_flag_accepted(self, runner, tmp_path):
        config = tmp_path / "season.yaml"
        config.write_text("season: 2025\nplayers:\n  HOME_WR1:\n    target_share: 0.30\n")
        result = runner.invoke(main, ["demo", "--sims", "10", "--config", str(config)])
        assert result.exit_code == 0

    def test_multiple_overrides(self, runner):
        result = runner.invoke(main, [
            "demo", "--sims", "10",
            "--override", "HOME_WR1.target_share=0.30",
            "--override", "HOME_RB1.carry_share=0.75",
        ])
        assert result.exit_code == 0


class TestConfigResolution:
    def test_resolve_config_chain_defaults_only(self):
        """Without custom config, should use defaults for the given format."""
        from fantasy_sim.cli import _resolve_config_chain
        result = _resolve_config_chain("ppr", scoring_config_path=None)
        assert result["passing_td"] == 4
        assert result["reception"] == 1

    def test_resolve_config_chain_with_scoring_config(self, tmp_path):
        """Custom scoring config should override the preset."""
        from fantasy_sim.cli import _resolve_config_chain
        custom = tmp_path / "custom.yaml"
        custom.write_text("inherit: ppr\noverrides:\n  passing_td: 6\n")
        result = _resolve_config_chain("ppr", scoring_config_path=str(custom))
        assert result["passing_td"] == 6
        assert result["reception"] == 1  # inherited from ppr

    def test_defaults_yaml_provides_num_sims(self):
        """defaults.yaml should provide simulation.num_sims == 1000."""
        from fantasy_sim.config.loader import load_defaults
        defaults = load_defaults()
        assert defaults["simulation"]["num_sims"] == 1000

    def test_defaults_yaml_provides_historical_seasons(self):
        """defaults.yaml should provide simulation.historical_seasons."""
        from fantasy_sim.config.loader import load_defaults
        defaults = load_defaults()
        assert defaults["simulation"]["historical_seasons"] == [2021, 2022, 2023, 2024]


class TestGameCommand:
    """Gap 17: game command — single-game deep dive."""

    def test_game_help(self, runner):
        result = runner.invoke(main, ["game", "--help"])
        assert result.exit_code == 0
        assert "game" in result.output.lower() or "home" in result.output.lower()

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_game_command_runs(self, MockLoader, MockBuilder, runner):
        """game KC BUF --week 5 should simulate and display results."""
        _wire_mocks(MockLoader, MockBuilder, [
            {"season": 2024, "week": 5, "game_id": "2024_05_KC_BUF",
             "home_team": "KC", "away_team": "BUF"},
        ])
        result = runner.invoke(main, ["game", "KC", "BUF", "--week", "5", "--sims", "10"])
        assert result.exit_code == 0
        assert "KC" in result.output
        assert "BUF" in result.output
        assert "Win" in result.output or "win" in result.output

    def test_game_demo_mode(self, runner):
        """game with --demo should work without real data."""
        result = runner.invoke(main, ["game", "HOME", "AWAY", "--demo", "--sims", "10"])
        assert result.exit_code == 0
        assert "HOME" in result.output
        assert "AWAY" in result.output


class TestPlayerCommand:
    """Gap 18: player command — single player projection."""

    def test_player_help(self, runner):
        result = runner.invoke(main, ["player", "--help"])
        assert result.exit_code == 0
        assert "player" in result.output.lower()

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_player_command_runs(self, MockLoader, MockBuilder, runner):
        """player 'nico_collins' --week 5 should find and display the player."""
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 5, "game_id": "2024_05_HOU_BUF",
             "home_team": "HOU", "away_team": "BUF"},
        ])
        mock_loader.cache_dir = Path("/tmp/cache")

        mock_builder = MockBuilder.return_value
        from fantasy_sim.engine.types import TeamDistributions
        from fantasy_sim.models.distributions import (
            PlayCallingDist, PlayOutcomeDist, TurnoverRates, KickingModel, DriveStartModel,
        )
        from fantasy_sim.models.player import TeamRoster, PlayerModel, PlayerUsage, PlayerOutcomes

        def make_dists(team):
            return TeamDistributions(
                play_calling=PlayCallingDist(team=team, distributions={}, default={"pass": 0.55, "run": 0.45}),
                play_outcomes=PlayOutcomeDist(distributions={}, defaults={
                    "pass": np.array([0, 5, 8, 10, 12, 15]),
                    "run": np.array([2, 3, 4, 5, 6]),
                }),
                turnover_rates=TurnoverRates(team=team, int_rate=0.02, fumble_rate=0.01, sack_rate=0.06, sack_fumble_rate=0.10),
                kicking=KickingModel(fg_make_rate={"0_39": 0.93, "40_49": 0.82, "50_plus": 0.65}, xp_rate=0.94),
                drive_start=DriveStartModel(touchback_rate=0.55, touchback_yardline=75, return_yardlines=np.array([74, 76])),
            )

        hou_roster = TeamRoster(team="HOU", players=[
            PlayerModel("HOU_QB", "QB", "QB", "HOU", PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel("nico_collins", "Nico Collins", "WR", "HOU", PlayerUsage(target_share=0.50),
                       PlayerOutcomes(catch_rate=0.65, receiving_yards_dist=np.array([8, 12, 15, 20]))),
            PlayerModel("HOU_RB", "RB", "RB", "HOU", PlayerUsage(carry_share=1.0, target_share=0.50),
                       PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                     catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
        ])
        buf_roster = TeamRoster(team="BUF", players=[
            PlayerModel("BUF_QB", "QB", "QB", "BUF", PlayerUsage(snap_share=1.0), PlayerOutcomes()),
            PlayerModel("BUF_WR", "WR", "WR", "BUF", PlayerUsage(target_share=0.50),
                       PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
            PlayerModel("BUF_RB", "RB", "RB", "BUF", PlayerUsage(carry_share=1.0, target_share=0.50),
                       PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                     catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
        ])

        mock_builder.build_game.return_value = (
            make_dists("HOU"), make_dists("BUF"), hou_roster, buf_roster,
        )

        result = runner.invoke(main, [
            "player", "nico_collins", "--week", "5", "--season", "2024", "--sims", "10"
        ])
        assert result.exit_code == 0
        assert "Nico Collins" in result.output or "nico_collins" in result.output

    def test_player_not_found(self, runner):
        """Player not in any game should show helpful error."""
        result = runner.invoke(main, ["player", "nonexistent_player_xyz", "--demo", "--sims", "10"])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "No player" in result.output


class TestBacktestCommand:
    def test_backtest_help(self, runner):
        result = runner.invoke(main, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "season" in result.output.lower()


class TestWeeksValidation:
    """Validate week number parsing and rejection of non-positive weeks."""

    def test_season_invalid_week_range(self, runner):
        """Week 0 in a range should produce a helpful error."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "0-5", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_season_invalid_week_zero(self, runner):
        """Week 0 should produce a helpful error."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "0", "--sims", "10"])
        assert result.exit_code != 0 or "invalid" in result.output.lower()

    def test_season_valid_week_range(self, runner):
        """Valid range should not raise validation error (may fail on data loading)."""
        result = runner.invoke(main, ["season", "--season", "2024", "--weeks", "1-2", "--sims", "10"])
        assert "invalid week" not in result.output.lower()


class TestFormatInference:
    """Format auto-inference from --output file extension."""

    def test_json_extension_infers_json(self, runner, tmp_path):
        """--output foo.json without --format should export JSON."""
        output = tmp_path / "result.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        import json
        data = json.loads(output.read_text())
        assert isinstance(data, list)

    def test_csv_extension_infers_csv(self, runner, tmp_path):
        """--output foo.csv without --format should export CSV."""
        output = tmp_path / "result.csv"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        assert "," in content  # CSV has commas

    def test_explicit_format_overrides_extension(self, runner, tmp_path):
        """--format csv --output foo.json should export CSV (format wins)."""
        output = tmp_path / "result.json"
        result = runner.invoke(main, ["demo", "--sims", "10", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        assert output.exists()
        content = output.read_text()
        # Should be CSV despite .json extension
        assert "," in content
        import json
        with pytest.raises(json.JSONDecodeError):
            json.loads(content)

    def test_unknown_extension_defaults_to_table(self, runner, tmp_path):
        """--output foo.txt without --format should display table (no file)."""
        output = tmp_path / "result.txt"
        result = runner.invoke(main, ["demo", "--sims", "10", "--output", str(output)])
        assert result.exit_code == 0
        # Table mode doesn't write files, so output should NOT exist
        assert not output.exists()


class TestSeasonAggregation:
    """Season-level aggregation of per-game projections."""

    def test_aggregate_player_projections_sums_stats(self):
        """Two entries for same player should sum into one."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "pass_yards": 250.0, "pass_tds": 2.0, "interceptions": 1.0,
             "sacks": 1.0, "rush_yards": 10.0, "rush_tds": 0.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 0.0, "rank": 1},
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 15.0, "pass_yards": 200.0, "pass_tds": 1.0, "interceptions": 0.0,
             "sacks": 2.0, "rush_yards": 5.0, "rush_tds": 1.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 1.0, "rank": 2},
        ]
        result = _aggregate_player_projections(projs)
        assert len(result) == 1
        assert result[0]["player_id"] == "p1"
        assert result[0]["fpts"] == 35.0
        assert result[0]["pass_yards"] == 450.0
        assert result[0]["pass_tds"] == 3.0
        assert result[0]["rush_tds"] == 1.0
        assert result[0]["fumbles_lost"] == 1.0
        assert result[0]["rank"] == 1

    def test_aggregate_player_projections_multiple_players(self):
        """Multiple players should each be aggregated and ranked by fpts."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "pass_yards": 250.0, "pass_tds": 2.0, "interceptions": 0.0,
             "sacks": 0.0, "rush_yards": 0.0, "rush_tds": 0.0,
             "targets": 0.0, "receptions": 0.0, "receiving_yards": 0.0,
             "receiving_tds": 0.0, "fumbles_lost": 0.0, "rank": 1},
            {"player_id": "p2", "name": "WR1", "position": "WR", "team": "KC",
             "fpts": 25.0, "pass_yards": 0.0, "pass_tds": 0.0, "interceptions": 0.0,
             "sacks": 0.0, "rush_yards": 0.0, "rush_tds": 0.0,
             "targets": 8.0, "receptions": 5.0, "receiving_yards": 100.0,
             "receiving_tds": 1.0, "fumbles_lost": 0.0, "rank": 2},
        ]
        result = _aggregate_player_projections(projs)
        assert len(result) == 2
        assert result[0]["player_id"] == "p2"
        assert result[0]["rank"] == 1
        assert result[1]["player_id"] == "p1"
        assert result[1]["rank"] == 2

    def test_aggregate_drops_detail_fields(self):
        """Aggregation should drop floor/ceiling/stddev fields."""
        from fantasy_sim.cli import _aggregate_player_projections
        projs = [
            {"player_id": "p1", "name": "QB1", "position": "QB", "team": "KC",
             "fpts": 20.0, "fpts_floor": 10.0, "fpts_ceiling": 30.0, "fpts_stddev": 5.0,
             "pass_yards": 250.0, "pass_yards_floor": 150.0, "pass_yards_ceiling": 350.0, "pass_yards_stddev": 50.0,
             "pass_tds": 2.0, "pass_tds_floor": 1.0, "pass_tds_ceiling": 3.0, "pass_tds_stddev": 0.5,
             "interceptions": 0.0, "interceptions_floor": 0.0, "interceptions_ceiling": 1.0, "interceptions_stddev": 0.3,
             "rush_yards": 0.0, "rush_yards_floor": 0.0, "rush_yards_ceiling": 0.0, "rush_yards_stddev": 0.0,
             "rush_tds": 0.0, "rush_tds_floor": 0.0, "rush_tds_ceiling": 0.0, "rush_tds_stddev": 0.0,
             "targets": 0.0, "targets_floor": 0.0, "targets_ceiling": 0.0, "targets_stddev": 0.0,
             "receptions": 0.0, "receptions_floor": 0.0, "receptions_ceiling": 0.0, "receptions_stddev": 0.0,
             "receiving_yards": 0.0, "receiving_yards_floor": 0.0, "receiving_yards_ceiling": 0.0, "receiving_yards_stddev": 0.0,
             "receiving_tds": 0.0, "receiving_tds_floor": 0.0, "receiving_tds_ceiling": 0.0, "receiving_tds_stddev": 0.0,
             "fumbles_lost": 0.0, "fumbles_lost_floor": 0.0, "fumbles_lost_ceiling": 0.0, "fumbles_lost_stddev": 0.0,
             "sacks": 0.0, "rank": 1},
        ]
        result = _aggregate_player_projections(projs)
        assert "fpts_floor" not in result[0]
        assert "fpts_ceiling" not in result[0]
        assert "fpts_stddev" not in result[0]
        assert "pass_yards_floor" not in result[0]
        assert "fpts" in result[0]
        assert "pass_yards" in result[0]

    def test_aggregate_dst_projections(self):
        """DST projections for same team should sum across weeks."""
        from fantasy_sim.cli import _aggregate_dst_projections
        projs = [
            {"team": "KC", "fpts": 8.0, "sacks": 3.0, "interceptions": 1.0,
             "fumble_recoveries": 0.0, "dst_tds": 0.0, "safeties": 0.0,
             "points_allowed": 17.0, "rank": 1},
            {"team": "KC", "fpts": 10.0, "sacks": 2.0, "interceptions": 2.0,
             "fumble_recoveries": 1.0, "dst_tds": 1.0, "safeties": 0.0,
             "points_allowed": 14.0, "rank": 1},
        ]
        result = _aggregate_dst_projections(projs)
        assert len(result) == 1
        assert result[0]["fpts"] == 18.0
        assert result[0]["sacks"] == 5.0
        assert result[0]["interceptions"] == 3.0
        assert result[0]["points_allowed"] == 31.0

    def test_aggregate_kicker_projections(self):
        """Kicker projections for same player should sum across weeks."""
        from fantasy_sim.cli import _aggregate_kicker_projections
        projs = [
            {"name": "K1", "team": "KC", "player_id": "k1", "position": "K",
             "fpts": 9.0, "fg_attempts": 3.0, "fg_made": 2.0,
             "fg_50_plus": 1.0, "xp_attempts": 4.0, "xp_made": 3.0, "rank": 1},
            {"name": "K1", "team": "KC", "player_id": "k1", "position": "K",
             "fpts": 7.0, "fg_attempts": 2.0, "fg_made": 2.0,
             "fg_50_plus": 0.0, "xp_attempts": 3.0, "xp_made": 3.0, "rank": 1},
        ]
        result = _aggregate_kicker_projections(projs)
        assert len(result) == 1
        assert result[0]["fpts"] == 16.0
        assert result[0]["fg_made"] == 4.0
        assert result[0]["xp_made"] == 6.0


class TestSeasonByWeek:
    """--by-week flag on season command."""

    _SEASON_SCHEDULE = [
        {"season": 2024, "week": 1, "game_id": "g1", "game_type": "REG",
         "home_team": "KC", "away_team": "BUF"},
        {"season": 2024, "week": 2, "game_id": "g2", "game_type": "REG",
         "home_team": "KC", "away_team": "MIA"},
    ]

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_default_aggregates(self, MockLoader, MockBuilder, runner):
        """Default season output should have one entry per player (aggregated)."""
        _wire_mocks(MockLoader, MockBuilder, self._SEASON_SCHEDULE)
        result = runner.invoke(main, ["season", "--season", "2024", "--sims", "5"])
        assert result.exit_code == 0
        assert "Season Projections" in result.output

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_by_week_shows_week_headers(self, MockLoader, MockBuilder, runner):
        """--by-week should show week-level headers."""
        _wire_mocks(MockLoader, MockBuilder, self._SEASON_SCHEDULE)
        result = runner.invoke(main, ["season", "--season", "2024", "--sims", "5", "--by-week"])
        assert result.exit_code == 0
        assert "Week 1" in result.output
        assert "Week 2" in result.output

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_by_week_json_includes_week_field(self, MockLoader, MockBuilder, runner, tmp_path):
        """--by-week --format json should include 'week' field on each row."""
        _wire_mocks(MockLoader, MockBuilder, self._SEASON_SCHEDULE)
        output = tmp_path / "by_week.json"
        result = runner.invoke(main, [
            "season", "--season", "2024", "--sims", "5",
            "--by-week", "--format", "json", "--output", str(output),
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(output.read_text())
        assert len(data) > 0
        for entry in data:
            assert "week" in entry

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_aggregated_json_no_week_field(self, MockLoader, MockBuilder, runner, tmp_path):
        """Default season JSON should NOT include 'week' field."""
        _wire_mocks(MockLoader, MockBuilder, self._SEASON_SCHEDULE)
        output = tmp_path / "aggregated.json"
        result = runner.invoke(main, [
            "season", "--season", "2024", "--sims", "5",
            "--format", "json", "--output", str(output),
        ])
        assert result.exit_code == 0
        import json
        data = json.loads(output.read_text())
        assert len(data) > 0
        for entry in data:
            assert "week" not in entry


class TestDetailFlag:
    """Gap 19: --detail flag on demo and game commands."""

    def test_demo_detail_flag(self, runner):
        """--detail flag should be accepted on demo."""
        result = runner.invoke(main, ["demo", "--sims", "10", "--detail"])
        assert result.exit_code == 0
        assert "Flr" in result.output or "Floor" in result.output or "Ceil" in result.output

    def test_game_detail_flag(self, runner):
        """--detail flag should be accepted on game command."""
        result = runner.invoke(main, ["game", "HOME", "AWAY", "--demo", "--sims", "10", "--detail"])
        assert result.exit_code == 0


class TestRegularSeasonDefault:
    """Season command should default to regular season games only."""

    def test_parse_weeks_all_returns_empty(self):
        """'all' should return empty list (signals dynamic lookup)."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        assert _parse_and_validate_weeks("all") == []

    def test_parse_weeks_allows_playoff_weeks(self):
        """Explicit week 19+ should be accepted (no hardcoded 1-18 limit)."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        result = _parse_and_validate_weeks("19-22")
        assert result == [19, 20, 21, 22]

    def test_parse_weeks_rejects_zero(self):
        """Week 0 should still be rejected."""
        from fantasy_sim.cli import _parse_and_validate_weeks
        with pytest.raises(click.BadParameter):
            _parse_and_validate_weeks("0")

    @patch("fantasy_sim.cli.GameContextBuilder")
    @patch("fantasy_sim.cli.DataLoader")
    def test_season_default_excludes_playoffs(self, MockLoader, MockBuilder, runner):
        """Default weeks='all' should only simulate REG games, not playoff games."""
        _, mock_builder = _wire_mocks(MockLoader, MockBuilder, [
            {"season": 2024, "week": 18, "game_id": "g_reg", "game_type": "REG",
             "home_team": "KC", "away_team": "BUF"},
            {"season": 2024, "week": 19, "game_id": "g_wc", "game_type": "WC",
             "home_team": "KC", "away_team": "MIA"},
        ])
        result = runner.invoke(main, ["season", "--season", "2024", "--sims", "5"])
        assert result.exit_code == 0
        assert mock_builder.build_game.call_count == 1
