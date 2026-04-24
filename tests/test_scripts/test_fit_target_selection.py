"""Focused tests for scripts/fit_target_selection.py helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from fit_target_selection import _state_from_row


def _base_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "home_team": "KC",
        "away_team": "BUF",
        "posteam": "KC",
        "score_differential": 0,
        "qtr": 1,
        "down": 1,
        "ydstogo": 10,
        "yardline_100": 75,
        "week": 1,
    }
    row.update(overrides)
    return row


def test_state_from_row_converts_game_seconds_with_quarter_boundary() -> None:
    state = _state_from_row(
        _base_row(qtr=2, game_seconds_remaining=2700)
    )

    assert state is not None
    assert state.quarter == 2
    assert state.clock == 900


def test_state_from_row_preserves_end_of_previous_quarter_boundary() -> None:
    state = _state_from_row(
        _base_row(qtr=1, game_seconds_remaining=2700)
    )

    assert state is not None
    assert state.quarter == 1
    assert state.clock == 0
