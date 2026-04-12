from __future__ import annotations

import polars as pl

from fantasy_sim.data.availability.loader import WeeklyRoleInputLoader


class _StubDataLoader:
    def load_rosters(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "position": ["WR"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "pfr_id": ["WideOn00"],
                "depth_chart_position": ["WR1"],
                "status_description_abbr": ["ACT"],
            }
        )

    def load_player_stats(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "position": ["WR"],
                "attempts": [0],
                "carries": [0],
                "targets": [8],
                "receptions": [6],
                "target_share": [0.24],
            }
        )

    def load_snap_counts(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "pfr_player_id": ["WideOn00"],
                "offense_pct": [0.72],
            }
        )

    def load_injuries(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "team": ["KC"],
                "player_id": ["00-001"],
                "player_name": ["Wide One"],
                "position": ["WR"],
                "report_status": ["Questionable"],
                "practice_status": ["Limited"],
            }
        )

    def load_depth_charts(self, seasons):
        return pl.DataFrame(
            {
                "season": [2024],
                "week": [5],
                "club_code": ["KC"],
                "gsis_id": ["00-001"],
                "position": ["WR"],
                "depth_position": ["WR1"],
                "full_name": ["Wide One"],
            }
        )


def test_load_weekly_merges_explicit_and_fallback_inputs():
    loader = WeeklyRoleInputLoader(loader=_StubDataLoader())
    frame = loader.load_weekly([2024])

    row = frame.filter(pl.col("player_id") == "00-001").row(0, named=True)

    assert row["team"] == "KC"
    assert row["position"] == "WR"
    assert row["targets"] == 8
    assert row["offense_pct"] == 0.72
    assert row["report_status"] == "Questionable"
    assert row["depth_position"] == "WR1"


def test_load_weekly_handles_missing_injuries_with_null_columns():
    stub = _StubDataLoader()
    stub.load_injuries = lambda seasons: pl.DataFrame()

    loader = WeeklyRoleInputLoader(loader=stub)
    frame = loader.load_weekly([2024])

    row = frame.filter(pl.col("player_id") == "00-001").row(0, named=True)
    assert row["report_status"] is None
    assert row["practice_status"] is None


def test_load_weekly_keeps_one_row_when_depth_chart_has_special_teams_entries():
    stub = _StubDataLoader()
    stub.load_depth_charts = lambda seasons: pl.DataFrame(
        {
            "season": [2024, 2024],
            "week": [5, 5],
            "club_code": ["KC", "KC"],
            "gsis_id": ["00-001", "00-001"],
            "position": ["WR", "KR"],
            "depth_position": ["WR1", "KR1"],
            "full_name": ["Wide One", "Wide One"],
        }
    )

    loader = WeeklyRoleInputLoader(loader=stub)
    frame = loader.load_weekly([2024])

    player_rows = frame.filter(pl.col("player_id") == "00-001")
    assert player_rows.height == 1
    assert player_rows.row(0, named=True)["depth_position"] == "WR1"
