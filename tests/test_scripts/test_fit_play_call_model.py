from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from fit_play_call_model import collect_examples_from_pbp


def test_collect_examples_from_pbp_keeps_only_pass_and_run_rows() -> None:
    pbp = pl.DataFrame(
        {
            "play_type": ["pass", "run", "punt"],
            "posteam": ["KC", "BUF", "KC"],
            "defteam": ["BUF", "KC", "BUF"],
            "home_team": ["KC", "KC", "KC"],
            "away_team": ["BUF", "BUF", "BUF"],
            "posteam_score": [7, 3, 7],
            "defteam_score": [3, 7, 3],
            "score_differential": [4, -4, 4],
            "qtr": [1, 1, 1],
            "quarter_seconds_remaining": [850, 810, 760],
            "down": [1, 2, 4],
            "ydstogo": [10, 3, 7],
            "yardline_100": [75, 40, 60],
            "week": [1, 1, 1],
            "spread_line": [-2.5, -2.5, -2.5],
            "total_line": [48.5, 48.5, 48.5],
        }
    )

    examples = collect_examples_from_pbp(pbp)

    assert [example.label for example in examples] == [1, 0]
