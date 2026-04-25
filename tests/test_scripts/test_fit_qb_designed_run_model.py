import json
import sys
from pathlib import Path

import polars as pl
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fantasy_sim.data.qb_rushing import QB_DESIGNED_RUN_MODEL_TYPE, QB_DESIGNED_RUN_SCHEMA_VERSION
from fit_qb_designed_run_model import collect_examples_from_pbp, fit_artifact_for_season


class FakeLoader:
    def __init__(self, pbp, rosters):
        self._pbp = pbp
        self._rosters = rosters

    def load_pbp(self, seasons):
        assert seasons == [2023]
        return self._pbp

    def load_rosters(self, seasons):
        assert seasons == [2023]
        return self._rosters


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
                "play_type": "run",
                "rusher_player_id": "QB1" if idx < 4 else "RB1",
                "qb_scramble": 0,
                "qb_kneel": 0,
                "qb_spike": 0,
                "no_play": 0,
                "yards_gained": 8 if idx < 4 else 4,
                "down": 3,
                "ydstogo": 2,
                "yardline_100": 35,
                "qtr": 2,
                "quarter_seconds_remaining": 300,
                "score_differential": -3,
                "spread_line": 2.0,
                "total_line": 47.0,
            }
        )
    return pl.DataFrame(rows)


def _rosters():
    return pl.DataFrame(
        [
            {"season": 2023, "week": 1, "player_id": "QB1", "position": "QB"},
            {"season": 2023, "week": 1, "player_id": "RB1", "position": "RB"},
        ]
    )


def test_collect_examples_from_pbp_excludes_scrambles_and_builds_tail_buckets():
    examples, priors, tail_buckets = collect_examples_from_pbp(_pbp(), _rosters())

    assert len(examples) == 12
    assert sum(example.label for example in examples) == 4
    assert priors.team["BUF"] == pytest.approx(4 / 12)
    assert tail_buckets["global"] == (8, 8, 8, 8)


def test_collect_examples_from_pbp_requires_rusher_player_id():
    pbp = _pbp().drop("rusher_player_id")

    with pytest.raises(ValueError, match="rusher_player_id"):
        collect_examples_from_pbp(pbp, _rosters())


def test_fit_artifact_for_season_writes_json(tmp_path):
    artifact = fit_artifact_for_season(
        FakeLoader(_pbp(), _rosters()),
        target_season=2024,
        min_source_season=2023,
        training_years=1,
        output_dir=tmp_path,
        l2=1.0,
        max_iter=50,
    )

    path = tmp_path / "qb_designed_run_model_2024.json"
    saved = json.loads(path.read_text())
    assert artifact["schema_version"] == QB_DESIGNED_RUN_SCHEMA_VERSION
    assert saved["model_type"] == QB_DESIGNED_RUN_MODEL_TYPE
    assert saved["target_season"] == 2024
    assert saved["source_seasons"] == [2023]
    assert saved["diagnostics"]["num_examples"] == 12
    assert saved["tail_buckets"]["global"] == [8, 8, 8, 8]
