import pytest
from click.testing import CliRunner
from unittest.mock import patch
from pathlib import Path
import polars as pl
import numpy as np
from fantasy_sim.cli import main


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
        mock_loader = MockLoader.return_value
        mock_loader.load_schedules.return_value = pl.DataFrame([
            {"season": 2024, "week": 1, "game_id": "g1",
             "home_team": "KC", "away_team": "BUF"},
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

        def make_roster(team):
            return TeamRoster(team=team, players=[
                PlayerModel(f"{team}_QB", "QB", "QB", team, PlayerUsage(snap_share=1.0), PlayerOutcomes()),
                PlayerModel(f"{team}_WR", "WR", "WR", team, PlayerUsage(target_share=0.50),
                           PlayerOutcomes(catch_rate=0.60, receiving_yards_dist=np.array([8, 12]))),
                PlayerModel(f"{team}_RB", "RB", "RB", team, PlayerUsage(carry_share=1.0, target_share=0.50),
                           PlayerOutcomes(rushing_yards_dist=np.array([3, 5, 7]),
                                         catch_rate=0.70, receiving_yards_dist=np.array([4, 6]))),
            ])

        mock_builder.build_game.return_value = (
            make_dists("KC"), make_dists("BUF"), make_roster("KC"), make_roster("BUF"),
        )

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
        assert defaults["simulation"]["historical_seasons"] == [2022, 2023, 2024]


class TestBacktestCommand:
    def test_backtest_help(self, runner):
        result = runner.invoke(main, ["backtest", "--help"])
        assert result.exit_code == 0
        assert "season" in result.output.lower()
