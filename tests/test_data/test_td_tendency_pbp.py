"""Tests for PBP-derived red zone TD counting in _aggregate_pbp_stats."""

import polars as pl
from fantasy_sim.data.player_builder import _aggregate_pbp_stats


def _make_pbp_with_rz_tds() -> pl.DataFrame:
    """Build minimal PBP DataFrame with red zone TD plays."""
    return pl.DataFrame({
        "play_type": ["pass", "pass", "pass", "run", "run", "pass"],
        "season": [2024] * 6,
        "game_id": ["g1"] * 6,
        "posteam": ["KC"] * 6,
        "passer_player_id": ["qb1", "qb1", "qb1", None, None, "qb1"],
        "receiver_player_id": ["wr1", "wr1", "wr1", None, None, "te1"],
        "rusher_player_id": [None, None, None, "rb1", "rb1", None],
        "complete_pass": [1, 1, 0, 0, 0, 1],
        "yards_gained": [15, 8, 0, 3, 5, 6],
        "yardline_100": [18, 10, 5, 4, 2, 6],
        "touchdown": [0, 1, 0, 0, 1, 1],
        "pass_touchdown": [0, 1, 0, 0, 0, 1],
        "rush_touchdown": [0, 0, 0, 0, 1, 0],
        "sack": [0] * 6,
        "interception": [0] * 6,
        "fumble_lost": [0] * 6,
    })


class TestPbpRzTdCounting:

    def test_receiving_rz_tds_counted(self):
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        assert stats["receiving"]["wr1"]["rz_tds"] == 1
        assert stats["receiving"]["te1"]["rz_tds"] == 1

    def test_rushing_rz_tds_counted(self):
        pbp = _make_pbp_with_rz_tds()
        stats = _aggregate_pbp_stats(pbp, [2024])
        assert stats["rushing"]["rb1"]["rz_tds"] == 1

    def test_non_rz_tds_not_counted(self):
        pbp = pl.DataFrame({
            "play_type": ["pass"],
            "season": [2024],
            "game_id": ["g1"],
            "posteam": ["KC"],
            "passer_player_id": ["qb1"],
            "receiver_player_id": ["wr2"],
            "rusher_player_id": [None],
            "complete_pass": [1],
            "yards_gained": [45],
            "yardline_100": [45],
            "touchdown": [1],
            "pass_touchdown": [1],
            "rush_touchdown": [0],
            "sack": [0],
            "interception": [0],
            "fumble_lost": [0],
        })
        stats = _aggregate_pbp_stats(pbp, [2024])
        assert stats["receiving"]["wr2"]["rz_tds"] == 0
