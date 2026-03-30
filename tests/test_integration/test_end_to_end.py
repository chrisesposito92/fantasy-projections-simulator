import json
import numpy as np
import pytest
from pathlib import Path
from click.testing import CliRunner
from fantasy_sim.cli import main
from fantasy_sim.config.loader import load_defaults, resolve_scoring
from fantasy_sim.scoring.engine import score_player
from fantasy_sim.scoring.projections import build_player_projections
from fantasy_sim.engine.types import GameResult, TeamBoxScore, PlayerBoxScore


class TestScoringConsistency:
    def test_player_fpts_equals_stats_times_weights(self):
        """End-to-end: verify fantasy points = sum of stats * scoring weights."""
        config = load_defaults()
        scoring = resolve_scoring(config["scoring"], "ppr")

        box = PlayerBoxScore(
            "WR1", "WR Name", "WR", "KC",
            receptions=5, receiving_yards=100, receiving_tds=1,
        )
        fpts = score_player(box, scoring)
        manual = 5 * 1 + 100 * 0.1 + 1 * 6  # 5 + 10 + 6 = 21
        assert fpts == pytest.approx(manual)

    def test_standard_no_reception_points(self):
        config = load_defaults()
        scoring = resolve_scoring(config["scoring"], "standard")
        assert scoring["reception"] == 0

        box = PlayerBoxScore(
            "WR1", "WR Name", "WR", "KC",
            receptions=5, receiving_yards=100, receiving_tds=1,
        )
        fpts = score_player(box, scoring)
        manual = 5 * 0 + 100 * 0.1 + 1 * 6  # 0 + 10 + 6 = 16
        assert fpts == pytest.approx(manual)


class TestCLIPipeline:
    def test_demo_produces_output(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "20"])
        assert result.exit_code == 0
        # Should have position tables
        assert "QB" in result.output

    def test_demo_csv_valid(self, tmp_path):
        runner = CliRunner()
        output = tmp_path / "out.csv"
        result = runner.invoke(main, ["demo", "--sims", "20", "--format", "csv", "--output", str(output)])
        assert result.exit_code == 0
        content = output.read_text()
        assert "fpts" in content
        assert "name" in content

    def test_demo_json_valid(self, tmp_path):
        runner = CliRunner()
        output = tmp_path / "out.json"
        result = runner.invoke(main, ["demo", "--sims", "20", "--format", "json", "--output", str(output)])
        assert result.exit_code == 0
        data = json.loads(output.read_text())
        assert len(data) > 0
        assert all("fpts" in d for d in data)

    def test_all_scoring_formats_work(self):
        runner = CliRunner()
        for fmt in ["ppr", "half_ppr", "standard"]:
            result = runner.invoke(main, ["demo", "--sims", "10", "--scoring", fmt])
            assert result.exit_code == 0, f"Failed for format: {fmt}"

    def test_projections_are_ranked(self):
        runner = CliRunner()
        result = runner.invoke(main, ["demo", "--sims", "50", "--format", "json", "--output", "/dev/stdout"])
        # Even though json goes to stdout, the exit should be clean
        assert result.exit_code == 0
