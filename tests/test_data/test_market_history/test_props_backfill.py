from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from fantasy_sim.data.market_history.props_backfill import (
    DEFAULT_PROP_MARKETS,
    build_snapshot_timestamp,
    load_events_inventory,
    raw_props_path,
    save_raw_props_snapshot,
)


def _inventory_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [1, 2],
            "gameday": ["2024-09-08", "2024-09-15"],
            "snapshot_date": ["2024-09-08T12:00:00Z", "2024-09-15T12:00:00Z"],
            "snapshot_timestamp": ["2024-09-08T11:55:00Z", "2024-09-15T11:55:00Z"],
            "previous_snapshot_timestamp": ["2024-09-08T11:50:00Z", "2024-09-15T11:50:00Z"],
            "next_snapshot_timestamp": ["2024-09-08T12:00:00Z", "2024-09-15T12:00:00Z"],
            "event_id": ["event-1", "event-2"],
            "commence_time": ["2024-09-08T17:00:00Z", "2024-09-15T20:25:00Z"],
            "home_team": ["Buffalo Bills", "Kansas City Chiefs"],
            "away_team": ["Arizona Cardinals", "Baltimore Ravens"],
            "home_team_abbr": ["BUF", "KC"],
            "away_team_abbr": ["ARI", "BAL"],
            "sport_key": ["americanfootball_nfl", "americanfootball_nfl"],
            "sport_title": ["NFL", "NFL"],
            "schedule_game_id": ["2024_01_ARI_BUF", "2024_02_BAL_KC"],
        }
    )


def test_load_events_inventory_reads_and_filters_weeks(tmp_path):
    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    _inventory_frame().write_parquet(processed_dir / "events_inventory_2024.parquet")

    frame = load_events_inventory([2024], processed_dir=processed_dir, weeks=[2])

    assert frame["event_id"].to_list() == ["event-2"]


def test_build_snapshot_timestamp_uses_date_source_and_offset():
    row = _inventory_frame().row(0, named=True)

    assert build_snapshot_timestamp(row, date_source="commence_time") == "2024-09-08T17:00:00Z"
    assert build_snapshot_timestamp(
        row,
        date_source="commence_time",
        offset_minutes=-30,
    ) == "2024-09-08T16:30:00Z"


def test_raw_props_path_includes_snapshot_label():
    path = raw_props_path(
        2024,
        "event-1",
        snapshot_label="close",
        raw_props_dir=Path("/tmp/props"),
    )

    assert str(path) == "/tmp/props/2024/close/event-1.json"


def test_save_raw_props_snapshot_persists_request_metadata(tmp_path):
    path = tmp_path / "2024" / "close" / "event-1.json"
    row = _inventory_frame().row(0, named=True)

    save_raw_props_snapshot(
        path,
        event_row=row,
        snapshot_label="close",
        snapshot_timestamp="2024-09-08T17:00:00Z",
        markets=DEFAULT_PROP_MARKETS[:2],
        regions="us",
        payload={"data": {"id": "event-1", "bookmakers": []}},
        headers={"x-requests-last": "20", "x-requests-used": "100", "x-requests-remaining": "9900"},
    )

    saved = json.loads(path.read_text())
    assert saved["season"] == 2024
    assert saved["week"] == 1
    assert saved["event_id"] == "event-1"
    assert saved["snapshot_label"] == "close"
    assert saved["snapshot_timestamp"] == "2024-09-08T17:00:00Z"
    assert saved["markets"] == list(DEFAULT_PROP_MARKETS[:2])
    assert saved["headers"]["x-requests-last"] == "20"
