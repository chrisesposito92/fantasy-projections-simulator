import pytest
from click.testing import CliRunner
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
