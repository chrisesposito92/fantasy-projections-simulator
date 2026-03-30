import json
import csv
import pytest
from pathlib import Path
from fantasy_sim.output.export import export_csv, export_json


@pytest.fixture
def sample_projections():
    return [
        {"rank": 1, "name": "P.Mahomes", "position": "QB", "team": "KC",
         "fpts": 22.4, "pass_yards": 274, "pass_tds": 2.1},
        {"rank": 2, "name": "J.Allen", "position": "QB", "team": "BUF",
         "fpts": 21.9, "pass_yards": 268, "pass_tds": 2.0},
    ]


class TestExportCSV:
    def test_creates_file(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        assert output.exists()

    def test_csv_has_headers(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        with open(output) as f:
            reader = csv.DictReader(f)
            assert "name" in reader.fieldnames
            assert "fpts" in reader.fieldnames

    def test_csv_has_correct_rows(self, tmp_path, sample_projections):
        output = tmp_path / "results.csv"
        export_csv(sample_projections, output)
        with open(output) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["name"] == "P.Mahomes"


class TestExportJSON:
    def test_creates_file(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        assert output.exists()

    def test_json_is_valid(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        with open(output) as f:
            data = json.load(f)
        assert len(data) == 2

    def test_json_has_correct_data(self, tmp_path, sample_projections):
        output = tmp_path / "results.json"
        export_json(sample_projections, output)
        with open(output) as f:
            data = json.load(f)
        assert data[0]["name"] == "P.Mahomes"
        assert data[0]["fpts"] == 22.4
