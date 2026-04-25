import json
import sys
from pathlib import Path

import polars as pl

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fantasy_sim.data.qb_rushing import QB_SCRAMBLE_MODEL_TYPE, QB_SCRAMBLE_SCHEMA_VERSION
from fit_qb_scramble_model import collect_examples_from_pbp, fit_artifact_for_season


class FakeLoader:
    def __init__(self, pbp):
        self._pbp = pbp

    def load_pbp(self, seasons):
        assert seasons == [2023]
        return self._pbp


def _pbp():
    rows = []
    for idx in range(12):
        rows.append(
            {
                "season": 2023,
                "week": 1,
                "posteam": "BUF",
                "defteam": "KC",
                "home_team": "KC",
                "away_team": "BUF",
                "play_type": "run" if idx < 4 else "pass",
                "passer_player_id": "QB1",
                "passer_player_name": "Mobile QB",
                "qb_scramble": 1 if idx < 4 else 0,
                "down": 3,
                "ydstogo": 8,
                "yardline_100": 35,
                "qtr": 2,
                "quarter_seconds_remaining": 300,
                "score_differential": -3,
                "spread_line": 2.0,
                "total_line": 47.0,
            }
        )
    return pl.DataFrame(rows)


def test_collect_examples_from_pbp_includes_passes_and_scrambles():
    examples, priors = collect_examples_from_pbp(_pbp())

    assert len(examples) == 12
    assert sum(example.label for example in examples) == 4
    assert priors.qb["QB1"] == 4 / 12


def test_fit_artifact_for_season_writes_json(tmp_path):
    artifact = fit_artifact_for_season(
        FakeLoader(_pbp()),
        target_season=2024,
        min_source_season=2023,
        training_years=1,
        output_dir=tmp_path,
        l2=1.0,
        max_iter=50,
    )

    path = tmp_path / "qb_scramble_model_2024.json"
    saved = json.loads(path.read_text())
    assert artifact["schema_version"] == QB_SCRAMBLE_SCHEMA_VERSION
    assert saved["model_type"] == QB_SCRAMBLE_MODEL_TYPE
    assert saved["target_season"] == 2024
    assert saved["source_seasons"] == [2023]
    assert saved["diagnostics"]["num_examples"] == 12
