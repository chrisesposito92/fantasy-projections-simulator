"""Tests for the PFF WR/TE depth-role engine."""

from __future__ import annotations

import polars as pl

from fantasy_sim.data.pff.depth_role import DepthRoleEngine
from fantasy_sim.data.pff.loader import PffLoader
from fantasy_sim.data.pff.models import DepthRoleConfig, DepthRolePositionConfig
from fantasy_sim.models.player import PlayerModel, PlayerOutcomes, PlayerUsage, TeamRoster


def _make_roster() -> TeamRoster:
    return TeamRoster(
        team="KC",
        players=[
            PlayerModel(
                "WR_A",
                "WR A",
                "WR",
                "KC",
                PlayerUsage(target_share=0.28, air_yards_share=0.34),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "WR_B",
                "WR B",
                "WR",
                "KC",
                PlayerUsage(target_share=0.22, air_yards_share=0.24),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "TE_A",
                "TE A",
                "TE",
                "KC",
                PlayerUsage(target_share=0.18, air_yards_share=0.12),
                PlayerOutcomes(),
            ),
            PlayerModel(
                "RB_A",
                "RB A",
                "RB",
                "KC",
                PlayerUsage(target_share=0.10, air_yards_share=0.04),
                PlayerOutcomes(),
            ),
        ],
    )


def _write_receiving_depth(pff_dir, season: int, rows: list[dict]) -> None:
    pff_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "player_id": pl.Int64,
        "player": pl.Utf8,
        "team": pl.Utf8,
        "position": pl.Utf8,
        "season": pl.Int64,
        "week": pl.Int64,
        "game_id": pl.Utf8,
        "routes": pl.Float64,
        "targets": pl.Float64,
        "short_targets": pl.Float64,
        "medium_targets": pl.Float64,
        "deep_targets": pl.Float64,
        "behind_los_targets": pl.Float64,
        "short_avg_depth_of_target": pl.Float64,
        "medium_avg_depth_of_target": pl.Float64,
        "deep_avg_depth_of_target": pl.Float64,
        "behind_los_avg_depth_of_target": pl.Float64,
    }
    df = pl.DataFrame(rows, schema=schema, infer_schema_length=None) if rows else pl.DataFrame(schema=schema)
    df.write_parquet(pff_dir / f"receiving_depth_{season}.parquet")


def _engine(pff_dir) -> DepthRoleEngine:
    config = DepthRoleConfig(
        enabled=True,
        positions=("WR", "TE"),
        wr=DepthRolePositionConfig(0.10, 0.12, (0.94, 1.06)),
        te=DepthRolePositionConfig(0.08, 0.06, (0.95, 1.05)),
        min_routes=15,
        min_targets=6,
        min_games=4,
        early_season_blend=True,
    )
    return DepthRoleEngine(PffLoader(pff_dir), config)


def test_apply_adjusts_wr_and_te_role_volume_only(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 30,
                "targets": 10,
                "short_targets": 2,
                "medium_targets": 3,
                "deep_targets": 5,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 4.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 24.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
            {
                "player_id": 102,
                "player": "WR B",
                "team": "KC",
                "position": "RWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 28,
                "targets": 6,
                "short_targets": 4,
                "medium_targets": 2,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 10.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
            {
                "player_id": 103,
                "player": "TE A",
                "team": "KC",
                "position": "TE-L",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 24,
                "targets": 8,
                "short_targets": 5,
                "medium_targets": 2,
                "deep_targets": 1,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 4.0,
                "medium_avg_depth_of_target": 8.0,
                "deep_avg_depth_of_target": 18.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(
        roster,
        pff_crosswalk={101: "WR_A", 102: "WR_B", 103: "TE_A"},
        target_season=2024,
        max_week=18,
    )

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    wr_b = next(player for player in roster.players if player.player_id == "WR_B")
    te_a = next(player for player in roster.players if player.player_id == "TE_A")
    rb_a = next(player for player in roster.players if player.player_id == "RB_A")

    assert wr_a.usage.target_share > 0.28
    assert wr_a.usage.air_yards_share > 0.34
    assert wr_b.usage.air_yards_share < 0.24
    assert te_a.usage.target_share > 0.18
    assert rb_a.usage.target_share == 0.10


def test_low_sample_players_stay_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "g1",
                "routes": 6,
                "targets": 2,
                "short_targets": 1,
                "medium_targets": 1,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            },
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34


def test_early_season_blend_uses_previous_season_when_current_sample_is_thin(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(
        pff_dir,
        2023,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2023,
                "week": 10,
                "game_id": "old",
                "routes": 34,
                "targets": 11,
                "short_targets": 2,
                "medium_targets": 3,
                "deep_targets": 6,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 5.0,
                "medium_avg_depth_of_target": 11.0,
                "deep_avg_depth_of_target": 23.0,
                "behind_los_avg_depth_of_target": -1.0,
            }
        ],
    )
    _write_receiving_depth(
        pff_dir,
        2024,
        [
            {
                "player_id": 101,
                "player": "WR A",
                "team": "KC",
                "position": "LWR",
                "season": 2024,
                "week": 1,
                "game_id": "new",
                "routes": 10,
                "targets": 2,
                "short_targets": 2,
                "medium_targets": 0,
                "deep_targets": 0,
                "behind_los_targets": 0,
                "short_avg_depth_of_target": 3.0,
                "medium_avg_depth_of_target": 0.0,
                "deep_avg_depth_of_target": 0.0,
                "behind_los_avg_depth_of_target": -1.0,
            }
        ],
    )
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {101: "WR_A"}, 2024, 2)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.air_yards_share > 0.34


def test_missing_crosswalk_stays_neutral(tmp_path):
    pff_dir = tmp_path / "pff" / "processed" / "nfl"
    _write_receiving_depth(pff_dir, 2024, [])
    roster = _make_roster()
    engine = _engine(pff_dir)

    engine.apply(roster, {}, 2024, 18)

    wr_a = next(player for player in roster.players if player.player_id == "WR_A")
    assert wr_a.usage.target_share == 0.28
    assert wr_a.usage.air_yards_share == 0.34
