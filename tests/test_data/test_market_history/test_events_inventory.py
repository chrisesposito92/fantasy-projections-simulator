from __future__ import annotations

import json

import polars as pl

from fantasy_sim.data.market_history.events_inventory import (
    EVENT_INVENTORY_SCHEMA,
    build_request_window,
    build_schedule_day_frame,
    build_events_inventory_for_season,
    flatten_raw_snapshot,
    load_the_odds_api_key,
)


def test_load_the_odds_api_key_prefers_env_var(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("THE_ODDS_API_KEY=file-value\n")
    monkeypatch.setenv("THE_ODDS_API_KEY", "env-value")

    assert load_the_odds_api_key(env_file) == "env-value"


def test_load_the_odds_api_key_falls_back_to_legacy_name_in_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("THE_ODDS_API=legacy-value\n")

    assert load_the_odds_api_key(env_file) == "legacy-value"


def test_build_request_window_uses_midday_snapshot_and_next_day_cutoff():
    snapshot_date, commence_from, commence_to = build_request_window("2024-09-08")

    assert snapshot_date == "2024-09-08T12:00:00Z"
    assert commence_from == "2024-09-08T00:00:00Z"
    assert commence_to == "2024-09-09T12:00:00Z"


def test_build_schedule_day_frame_returns_unique_regular_season_days():
    schedules = pl.DataFrame(
        {
            "season": [2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 2],
            "game_type": ["REG", "REG", "POST", "REG"],
            "gameday": ["2024-09-08", "2024-09-08", "2025-01-10", "2024-09-15"],
        }
    )

    result = build_schedule_day_frame(schedules)

    assert result.select(["season", "week", "gameday"]).to_dicts() == [
        {"season": 2024, "week": 1, "gameday": "2024-09-08"},
        {"season": 2024, "week": 2, "gameday": "2024-09-15"},
    ]
    assert result["snapshot_date"].to_list() == [
        "2024-09-08T12:00:00Z",
        "2024-09-15T12:00:00Z",
    ]


def test_flatten_raw_snapshot_maps_schedule_game_id_and_team_abbreviations():
    record = {
        "season": 2024,
        "week": 1,
        "gameday": "2024-09-08",
        "snapshot_date": "2024-09-08T12:00:00Z",
        "payload": {
            "timestamp": "2024-09-08T11:55:00Z",
            "previous_timestamp": "2024-09-08T11:50:00Z",
            "next_timestamp": "2024-09-08T12:00:00Z",
            "data": [
                {
                    "id": "event-1",
                    "sport_key": "americanfootball_nfl",
                    "sport_title": "NFL",
                    "commence_time": "2024-09-08T17:00:00Z",
                    "home_team": "Buffalo Bills",
                    "away_team": "Arizona Cardinals",
                }
            ],
        },
    }
    schedule_lookup = {
        ("2024-09-08", "BUF", "ARI"): {
            "game_id": "2024_01_ARI_BUF",
            "season": 2024,
            "week": 1,
            "gameday": "2024-09-08",
            "home_team": "BUF",
            "away_team": "ARI",
        }
    }

    frame = flatten_raw_snapshot(record, schedule_lookup)

    assert frame.schema == EVENT_INVENTORY_SCHEMA
    assert frame.row(0, named=True) == {
        "season": 2024,
        "week": 1,
        "gameday": "2024-09-08",
        "snapshot_date": "2024-09-08T12:00:00Z",
        "snapshot_timestamp": "2024-09-08T11:55:00Z",
        "previous_snapshot_timestamp": "2024-09-08T11:50:00Z",
        "next_snapshot_timestamp": "2024-09-08T12:00:00Z",
        "event_id": "event-1",
        "commence_time": "2024-09-08T17:00:00Z",
        "home_team": "Buffalo Bills",
        "away_team": "Arizona Cardinals",
        "home_team_abbr": "BUF",
        "away_team_abbr": "ARI",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "schedule_game_id": "2024_01_ARI_BUF",
    }


def test_flatten_raw_snapshot_maps_rams_to_la_schedule_abbreviation():
    record = {
        "season": 2024,
        "week": 3,
        "gameday": "2024-09-22",
        "snapshot_date": "2024-09-22T12:00:00Z",
        "payload": {
            "timestamp": "2024-09-22T11:55:00Z",
            "previous_timestamp": "2024-09-22T11:50:00Z",
            "next_timestamp": "2024-09-22T12:00:00Z",
            "data": [
                {
                    "id": "event-rams",
                    "sport_key": "americanfootball_nfl",
                    "sport_title": "NFL",
                    "commence_time": "2024-09-22T20:25:00Z",
                    "home_team": "Los Angeles Rams",
                    "away_team": "San Francisco 49ers",
                }
            ],
        },
    }
    schedule_lookup = {
        ("2024-09-22", "LA", "SF"): {
            "game_id": "2024_03_SF_LA",
            "season": 2024,
            "week": 3,
            "gameday": "2024-09-22",
            "home_team": "LA",
            "away_team": "SF",
        }
    }

    frame = flatten_raw_snapshot(record, schedule_lookup)

    assert frame["home_team_abbr"].to_list() == ["LA"]
    assert frame["schedule_game_id"].to_list() == ["2024_03_SF_LA"]


def test_build_events_inventory_for_season_reads_cached_raw_json(tmp_path):
    raw_dir = tmp_path / "raw" / "events" / "2024"
    raw_dir.mkdir(parents=True)
    (raw_dir / "2024-09-08.json").write_text(
        json.dumps(
            {
                "season": 2024,
                "week": 1,
                "gameday": "2024-09-08",
                "snapshot_date": "2024-09-08T12:00:00Z",
                "payload": {
                    "timestamp": "2024-09-08T11:55:00Z",
                    "previous_timestamp": "2024-09-08T11:50:00Z",
                    "next_timestamp": "2024-09-08T12:00:00Z",
                    "data": [
                        {
                            "id": "event-1",
                            "sport_key": "americanfootball_nfl",
                            "sport_title": "NFL",
                            "commence_time": "2024-09-08T17:00:00Z",
                            "home_team": "Buffalo Bills",
                            "away_team": "Arizona Cardinals",
                        }
                    ],
                },
            }
        )
    )
    schedules = pl.DataFrame(
        {
            "game_id": ["2024_01_ARI_BUF"],
            "season": [2024],
            "week": [1],
            "game_type": ["REG"],
            "gameday": ["2024-09-08"],
            "home_team": ["BUF"],
            "away_team": ["ARI"],
        }
    )

    output_path = build_events_inventory_for_season(
        2024,
        raw_events_dir=tmp_path / "raw" / "events",
        processed_dir=tmp_path / "processed",
        schedules=schedules,
    )

    frame = pl.read_parquet(output_path)
    assert output_path.name == "events_inventory_2024.parquet"
    assert frame.schema == EVENT_INVENTORY_SCHEMA
    assert frame["event_id"].to_list() == ["event-1"]
    assert frame["schedule_game_id"].to_list() == ["2024_01_ARI_BUF"]
